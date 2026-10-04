"""Re-read an event's source and fill in what is genuinely missing.

An imported event can arrive without a date, without a venue or without a
lineup, because the page it was read from did not expose them or the reader that
parsed it did not understand the shape. Enrichment goes back to the source and
fills those gaps.

Three rules hold everywhere in this module:

1. Nothing is invented. A field is written only when the source states it. An
   event the source does not date stays undated and is reported as such.
2. A valid stored value is never replaced by a missing or a different one.
   Enrichment adds; it does not second-guess.
3. Every run is idempotent and safe to repeat. Re-running against an
   already-enriched event writes nothing.

The service is deliberately field-agnostic: `plan()` reports what an event is
missing, and `apply_patch()` decides what is safe to write. That is what lets
the same flow enrich dates today and lineup or venue tomorrow without changing
the runner.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

from pymongo.errors import DuplicateKeyError

from app.core.logger import get_logger
from app.providers.songkick.client import SongkickClient
from app.repositories.event_repository import EventRepository

logger = get_logger("event_enrichment")


# How a run is expected to end. These are recorded on the event so a later run
# can tell "the source has no date" from "we could not read the date".
DATE_FROM_SOURCE = "source"
DATE_UNAVAILABLE = "unavailable"
DATE_PARSER_FAILED = "parser_failed"

# The fields a run can fill. A caller names the ones it cares about so the run
# only pays for the page visits that can actually return them.
DATE_FIELDS = ["starts_at", "ends_at"]
LINEUP_FIELDS = ["lineup"]
LOCATION_FIELDS = ["location"]

ALL_ENRICHABLE_FIELDS = (
    DATE_FIELDS + LINEUP_FIELDS + LOCATION_FIELDS
)


@dataclass
class EnrichmentPlan:
    """What one event is missing and whether it can be re-read at all."""

    event_id: str
    title: str
    source_url: Optional[str]
    songkick_id: Optional[str]
    reasons: list[str] = field(default_factory=list)
    eligible: bool = False
    skip_reason: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "source_url": self.source_url,
            "songkick_id": self.songkick_id,
            "missing": list(self.reasons),
            "eligible": self.eligible,
            "skip_reason": self.skip_reason,
        }


@dataclass
class EnrichmentReport:
    """The result of a run, split by outcome."""

    examined: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_no_source: int = 0
    failed_source: int = 0
    no_date_on_source: int = 0
    parser_failures: int = 0
    write_failures: int = 0
    dry_run: bool = False
    failures: list[dict] = field(
        default_factory=list
    )

    def as_dict(self) -> dict:
        return {
            "examined": self.examined,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped_no_source": self.skipped_no_source,
            "failed_source": self.failed_source,
            "no_date_on_source": self.no_date_on_source,
            "parser_failures": self.parser_failures,
            "write_failures": self.write_failures,
            "dry_run": self.dry_run,
            "failures": self.failures[:20],
        }

    def summary(self) -> str:
        mode = (
            "DRY RUN - nothing written"
            if self.dry_run
            else "written"
        )

        return (
            f"{mode}: examined={self.examined} "
            f"updated={self.updated} "
            f"unchanged={self.unchanged} "
            f"no_source={self.skipped_no_source} "
            f"source_failed={self.failed_source} "
            f"no_date_on_source={self.no_date_on_source} "
            f"parser_failures={self.parser_failures} "
            f"write_failures={self.write_failures}"
        )


class EventEnrichmentService:
    """Fill missing event fields from the provider's own page."""

    def __init__(
        self,
        event_repository: EventRepository,
        client: Optional[SongkickClient] = None,
    ):
        self.event_repository = event_repository
        self.client = client or SongkickClient()

    # ============================================================
    # PLANNING
    # ============================================================

    async def plan(
        self,
        limit: Optional[int] = None,
        include_dated: bool = False,
        fields: Optional[list[str]] = None,
    ) -> list[EnrichmentPlan]:
        """Report what is missing, without fetching or writing anything.

        This is the dry-run surface. It costs one indexed query and answers the
        only question worth asking before touching the database: which events
        are worth a source visit, and which cannot be re-read at all.

        `fields` narrows what makes an event worth a visit. Enriching dates is
        the urgent job and touches every undated event; enriching a lineup only
        applies to festival dates, because that is the only kind of page that
        carries one. Asking for both would pay for a page fetch per concert to
        discover there is nothing to read.
        """

        wanted = set(
            fields
            if fields is not None
            else ALL_ENRICHABLE_FIELDS
        )

        query: dict[str, Any] = {}

        if not include_dated:
            query["$or"] = [
                {
                    "$and": [
                        {
                            "starts_at": {
                                "$exists": False,
                            }
                        },
                        {
                            "ends_at": {
                                "$exists": False,
                            },
                        },
                    ]
                },
                {"starts_at": None},
                {"ends_at": None},
                {
                    "date_status": DATE_UNAVAILABLE,
                },
                {
                    "date_status": DATE_PARSER_FAILED,
                },
            ]

        cursor = self.event_repository.collection.find(
            query,
            {
                "title": 1,
                "event_type": 1,
                "source.url": 1,
                "external_ids.songkick": 1,
                "starts_at": 1,
                "ends_at": 1,
                "date_status": 1,
                "lineup": 1,
                "location": 1,
            },
        ).sort("_id", 1)

        documents = await cursor.to_list(length=None)

        plans: list[EnrichmentPlan] = []

        for document in documents:
            plan = self._plan_for(document)

            if self._is_worth_visiting(
                plan,
                document,
                wanted,
            ):
                plans.append(plan)

            # The limit is applied after filtering, never to the database
            # query: a query limit would cut off candidates that filtering was
            # about to reject and quietly shorten the run.
            if (
                limit is not None
                and len(plans) >= limit
            ):
                break

        return plans

    @staticmethod
    def _is_worth_visiting(
        plan: EnrichmentPlan,
        document: dict,
        wanted: set[str],
    ) -> bool:
        """Whether this event would gain anything from a source visit.

        A lineup is only ever on a festival date's page, so asking a concert
        page for one costs a fetch and returns nothing. The same reasoning
        applies to the identity half of a festival, which a concert has none of.
        """

        is_festival = str(
            document.get("event_type") or ""
        ).lower() in {
            "festival",
            "festivalinstance",
        }

        interesting = {
            reason
            for reason in plan.reasons
            if reason in wanted
        }

        if "lineup" in interesting and not is_festival:
            interesting.discard("lineup")

        # A date job is about recovering a date the event does not have. An
        # event with a start but no end is usually a single-evening concert,
        # which the source genuinely leaves open-ended, so paying for a page
        # fetch to confirm that would be waste.
        if wanted & set(DATE_FIELDS):
            if "starts_at" not in interesting:
                interesting -= set(DATE_FIELDS)

        if not interesting:
            return False

        plan.reasons = sorted(interesting)

        return True

    def _plan_for(
        self,
        document: dict,
    ) -> EnrichmentPlan:
        source = document.get("source") or {}

        source_url = source.get("url") or None

        plan = EnrichmentPlan(
            event_id=str(document["_id"]),
            title=document.get("title") or "",
            source_url=source_url,
            songkick_id=(
                document.get("external_ids")
                or {}
            ).get("songkick"),
        )

        if not document.get("starts_at"):
            plan.reasons.append("starts_at")

        if not document.get("ends_at"):
            plan.reasons.append("ends_at")

        if not document.get("lineup"):
            plan.reasons.append("lineup")

        if not document.get("location"):
            plan.reasons.append("location")

        if source_url:
            plan.eligible = True

        elif plan.songkick_id:
            plan.skip_reason = (
                "has a Songkick id but no source URL"
            )

        else:
            plan.skip_reason = (
                "no Songkick source to re-read"
            )

        return plan

    # ============================================================
    # PATCHING
    # ============================================================

    @staticmethod
    def apply_patch(
        document: dict,
        source: dict,
    ) -> dict:
        """The fields that can be written from this source read.

        Returns only what is both missing locally and present on the source, so
        the caller can tell an actual enrichment from a no-op. A stored value is
        never replaced: enrichment adds, it does not overwrite.
        """

        patch: dict[str, Any] = {}

        # --------------------------------------------------------
        # Dates
        # --------------------------------------------------------

        start = source.get(
            "start_date"
        )

        end = source.get(
            "end_date"
        )

        if start and not document.get(
            "starts_at"
        ):
            patch["starts_at"] = start

        if end and not document.get("ends_at"):
            patch["ends_at"] = end

        # How the dates were resolved is itself a stored field, so it is only
        # written when it actually differs. Rewriting an identical value would
        # make every repeat run report a change and stop the run from ever
        # being idempotent.
        if start or end:
            resolved = DATE_FROM_SOURCE

        elif not document.get("starts_at"):
            # The source was read and simply has no date. Recorded so a later
            # run does not keep paying for the same visit.
            resolved = DATE_UNAVAILABLE

        else:
            resolved = None

        if (
            resolved is not None
            and document.get("date_status")
            != resolved
        ):
            patch["date_status"] = resolved

        # --------------------------------------------------------
        # Lineup
        # --------------------------------------------------------

        lineup = source.get("lineup")

        if lineup and not document.get("lineup"):
            patch["lineup"] = lineup

        # --------------------------------------------------------
        # Festival identity
        # --------------------------------------------------------

        festival = source.get("festival")

        if isinstance(
            festival,
            dict,
        ) and festival.get("series_id"):

            current = document.get(
                "festival"
            )

            if not isinstance(
                current,
                dict,
            ) or not current.get(
                "series_id"
            ):
                patch["festival"] = festival

        # --------------------------------------------------------
        # Venue and location
        # --------------------------------------------------------

        venue = source.get("venue")

        if isinstance(
            venue,
            dict,
        ) and venue:

            # The event document holds only a venue slug, not the venue, so
            # there is nothing to merge against here. What the source states is
            # handed to `_update_venue`, which owns the rule for what a stored
            # venue may have filled in.
            incoming = {
                field_name: value
                for field_name, value in venue.items()
                if value
            }

            if incoming:
                patch["_venue"] = incoming

        location = source.get("location")

        if isinstance(
            location,
            dict,
        ) and location:

            merged_location = dict(
                document.get("location")
                if isinstance(
                    document.get("location"),
                    dict,
                )
                else {}
            )

            changed = False

            for field_name, value in location.items():
                if value is not None and merged_location.get(
                    field_name
                ) in (None, ""):
                    merged_location[field_name] = value
                    changed = True

            if changed:
                patch["location"] = merged_location

        for field_name in (
            "ticket_url",
            "description",
            "songkick_image",
            "event_status",
        ):
            value = source.get(field_name)

            if value and not document.get(
                field_name
            ):
                patch[field_name] = value

        return patch

    # ============================================================
    # RUNNING
    # ============================================================

    async def enrich_one(
        self,
        plan: EnrichmentPlan,
        dry_run: bool = False,
    ) -> dict:
        """Re-read one event's source and report what happened.

        A failure here never propagates: one unreachable page must not end a
        run over thousands of events.
        """

        document = await (
            self.event_repository.collection.find_one(
                {"_id": _object_id(plan.event_id)}
            )
        )

        if document is None:
            return {
                "event_id": plan.event_id,
                "outcome": "missing",
            }

        if not plan.source_url:
            return {
                "event_id": plan.event_id,
                "outcome": "skipped",
                "reason": plan.skip_reason,
            }

        try:
            source = await self.client.enrich_event_details(
                {"url": plan.source_url}
            )
        except Exception as exc:
            logger.warning(
                f"[ENRICH] source failed for "
                f"{plan.event_id}: {exc}"
            )

            return {
                "event_id": plan.event_id,
                "outcome": "source_failed",
                "error": str(exc)[:200],
            }

        if not source:
            return {
                "event_id": plan.event_id,
                "outcome": "parser_failed",
            }

        patch = self.apply_patch(
            document,
            source,
        )

        # `_venue` is applied through the venue repository, not the event
        # document, so it is split out here.
        venue_patch = patch.pop(
            "_venue",
            None,
        )

        fields = sorted(patch.keys())

        # What the venue write would actually change. Deciding this here is
        # what makes a repeat run report "unchanged": the source keeps stating
        # the venue, but the stored venue already carries those values, so
        # there is genuinely nothing left to do.
        venue_updates = (
            await self._venue_updates(
                document,
                venue_patch,
            )
            if venue_patch
            else {}
        )

        if venue_updates:
            fields.append("venue")

        if not fields:
            return {
                "event_id": plan.event_id,
                "outcome": "unchanged",
            }

        if dry_run:
            return {
                "event_id": plan.event_id,
                "outcome": "would_update",
                "fields": fields,
            }

        # A write failure on one record must not end a run over thousands.
        # The record is reported and the run continues; because every write is
        # a field-level merge of missing data, the next run retries it safely.
        try:
            if patch:
                await self._update_event(
                    plan.event_id,
                    patch,
                )

            if venue_updates:
                await self._update_venue(
                    document,
                    venue_updates,
                )

        except Exception as exc:
            logger.warning(
                f"[ENRICH] write failed for "
                f"{plan.event_id}: {exc}"
            )

            return {
                "event_id": plan.event_id,
                "outcome": "write_failed",
                "error": str(exc)[:200],
            }

        logger.info(
            f"[ENRICH] {plan.event_id} updated: {fields}"
        )

        return {
            "event_id": plan.event_id,
            "outcome": "updated",
            "fields": fields,
        }

    async def _update_event(
        self,
        event_id: str,
        patch: dict,
    ):
        """Write only the fields enrichment decided were safe."""

        from app.domain.event_schedule import (
            parse_source_datetime,
        )

        update: dict[str, Any] = {}

        # A date that is present but unreadable is a parser problem, and must
        # not be recorded as a successful read. It is tracked separately from
        # the patch's own verdict so that the two cannot contradict each other.
        date_unreadable = False

        for field_name, value in patch.items():

            if field_name in (
                "starts_at",
                "ends_at",
            ):
                # The source states dates as ISO strings, not as datetime
                # objects, so they are parsed rather than passed through.
                moment = parse_source_datetime(
                    value
                )

                if moment is None:
                    date_unreadable = True
                    continue

                update[field_name] = moment

                continue

            if field_name == "date_status":
                continue

            update[field_name] = value

        # `date_status` is decided last so it reflects what was actually
        # written, rather than what the source appeared to offer.
        if date_unreadable:
            update["date_status"] = (
                DATE_PARSER_FAILED
            )

        elif "starts_at" in update or "ends_at" in update:
            update["date_status"] = (
                DATE_FROM_SOURCE
            )

        else:
            status = patch.get("date_status")

            if status:
                update["date_status"] = status

        if not update:
            return

        await self.event_repository.collection.update_one(
            {"_id": _object_id(event_id)},
            {"$set": update},
        )

    async def _venue_updates(
        self,
        document: dict,
        venue: dict,
    ) -> dict[str, Any]:
        """What filling in this event's venue would actually change.

        Two rules, both learned from a real run. A venue has a unique index on
        name + city + country, so overwriting a venue's name with the name its
        source happens to use can collide with a different venue that already
        holds that name. And a venue is an identity, not a detail: renaming one
        to match a source would silently merge two places or split one in two.

        So only absent fields are filled and an existing name is never touched.
        An empty result means the stored venue already says everything the
        source does, which is what lets a repeat run report no change.
        """

        slug = document.get("venue_slug")

        if not slug:
            return {}

        existing = await (
            self.event_repository.db.venues.find_one(
                {"slug": slug},
                {
                    "_id": 1,
                    "name": 1,
                    "city": 1,
                    "country": 1,
                    "street_address": 1,
                    "postal_code": 1,
                },
            )
        )

        if existing is None:
            # The event points at a venue document that does not exist. That is
            # a data problem of its own, not something enrichment should fix by
            # inventing a venue.
            logger.warning(
                f"[ENRICH] venue {slug!r} not found; "
                "skipped venue enrichment"
            )
            return {}

        updates: dict[str, Any] = {}

        for stored, incoming in (
            ("name", venue.get("name")),
            ("city", venue.get("city")),
            ("country", venue.get("country")),
            (
                "street_address",
                venue.get("street"),
            ),
            ("postal_code", venue.get("postal_code")),
        ):
            if incoming and existing.get(stored) in (
                None,
                "",
            ):
                updates[stored] = incoming

        return updates

    async def _update_venue(
        self,
        document: dict,
        updates: dict[str, Any],
    ):
        """Apply the field fills decided by `_venue_updates`."""

        slug = document.get("venue_slug")

        if not slug or not updates:
            return

        try:
            await self.event_repository.db.venues.update_one(
                {"slug": slug},
                {"$set": updates},
            )
        except DuplicateKeyError:
            # The source describes a venue that already exists under a
            # different slug. Merging them is a decision, not a side effect of
            # a backfill, so it is left for a human.
            logger.warning(
                f"[ENRICH] venue {slug!r} collides with an "
                f"existing venue on {sorted(updates)}; skipped"
            )

    async def run(
        self,
        limit: Optional[int] = None,
        dry_run: bool = True,
        delay_seconds: float = 1.0,
        include_dated: bool = False,
        fields: Optional[list[str]] = None,
    ) -> EnrichmentReport:
        """Walk the plan and enrich each event.

        `dry_run` is the default: a run that changes the database has to be
        asked for. `delay_seconds` keeps the run polite, because the cost is a
        page fetch per event on someone else's servers.
        """

        report = EnrichmentReport(
            dry_run=dry_run
        )

        plans = await self.plan(
            limit=limit,
            include_dated=include_dated,
            fields=fields,
        )

        logger.info(
            f"[ENRICH] planned {len(plans)} events "
            f"(dry_run={dry_run})"
        )

        for index, plan in enumerate(plans):

            report.examined += 1

            if not plan.eligible:
                report.skipped_no_source += 1
                continue

            result = await self.enrich_one(
                plan,
                dry_run=dry_run,
            )

            outcome = result.get(
                "outcome"
            )

            if outcome == "updated":
                report.updated += 1

            elif outcome == "would_update":
                report.updated += 1

            elif outcome == "unchanged":
                report.unchanged += 1

            elif outcome == "source_failed":
                report.failed_source += 1
                report.failures.append(result)

            elif outcome == "parser_failed":
                report.parser_failures += 1
                report.failures.append(result)

            elif outcome == "write_failed":
                report.write_failures += 1
                report.failures.append(result)

            if index and delay_seconds:
                await asyncio.sleep(
                    delay_seconds
                )

        logger.info(
            f"[ENRICH] {report.summary()}"
        )

        return report

    async def report_only(
        self,
        limit: Optional[int] = None,
        fields: Optional[list[str]] = None,
    ) -> dict:
        """A plan summary that fetches nothing.

        Used to answer "how many records are eligible, likely recoverable and
        likely unrecoverable" before spending a single request on Songkick.
        """

        plans = await self.plan(
            limit=limit,
            fields=fields,
        )

        eligible = [
            plan
            for plan in plans
            if plan.eligible
        ]

        # A missing start date and a missing end date are different problems and
        # are counted separately on purpose.
        #
        # A concert genuinely has no end: it starts and it is over. A festival
        # that ends on the sixth and a concert on the third look identical in
        # storage, so reporting them as one "missing date" figure made the report
        # claim 191 undated events when exactly one was undated. Only a missing
        # start means the event cannot be placed in time at all.
        return {
            "total_missing_something": len(plans),
            "eligible": len(eligible),
            "no_source": len(plans) - len(eligible),
            "missing_start_date": sum(
                1
                for plan in plans
                if "starts_at" in plan.reasons
            ),
            "missing_end_date": sum(
                1
                for plan in plans
                if "ends_at" in plan.reasons
                and "starts_at" not in plan.reasons
            ),
            "missing_lineup": sum(
                1
                for plan in plans
                if "lineup" in plan.reasons
            ),
            "missing_location": sum(
                1
                for plan in plans
                if "location" in plan.reasons
            ),
            "sample": [
                plan.to_dict()
                for plan in eligible[:5]
            ],
        }


def _object_id(value: str):
    """The stored id, accepting either storage form."""

    from app.utils.ids import to_object_id

    parsed = to_object_id(value)

    return parsed if parsed is not None else value