from app.core.logger import get_logger

from app.domain.songkick_identity import (
    normalize_songkick_artist_id,
)

from app.domain.event_schedule import (
    is_upcoming,
)

from app.mappers.songkick_event_mapper import SongkickEventMapper

from app.repositories.event_repository import (
    EventRepository,
)

from app.repositories.venue_repository import (
    VenueRepository,
)

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.services.provider_manager import (
    ProviderManager,
)

from app.domain.artist import Artist

import time


logger = get_logger(
    "songkick_event_import"
)


def _lineup_songkick_ids(payload: dict) -> list[str]:
    """The Songkick artist ids stated in a payload's lineup, in bill order.

    Only what the source actually stated: an entry without an id contributes
    nothing, and nothing is guessed from a name. Both spellings the payload
    may carry are read, because the detail page and the JSON-LD parse of it
    do not agree on one. Duplicates are removed while the announced order is
    kept, so the first artist on the bill resolves before the last.
    """

    entries = (
        payload.get("lineup")
        or payload.get("performers")
        or []
    )

    if not isinstance(entries, list):
        return []

    ids: list[str] = []

    for entry in entries:

        if not isinstance(entry, dict):
            continue

        value = (
            entry.get("songkick_id")
            or entry.get("songkickId")
        )

        if not value:
            continue

        text = str(value).strip()

        if text and text not in ids:

            ids.append(text)

    return ids

# ============================================================
# EXTRACTION GAPS
# ============================================================
#
# What one run could not obtain, judged on the event that was just mapped.
# These are the fields a reader of the event page is entitled to expect, and
# each one is reported where it is found rather than counted for some later
# process to chase: an event id, the field, and the source it came from.
#
# `parser_failed` is not a gap. It is a failure - the source stated a date and
# it could not be read - and it is reported separately, because "the page had
# nothing" and "we could not read what the page had" need different answers.

_GAP_DATE = "date"
_GAP_VENUE = "venue"
_GAP_LINEUP = "lineup"

# The mapper's placeholder for a payload that stated no venue name. Standing
# in for a missing value, it is the one name an event can carry without the
# source having said it, which is exactly what a gap is.
_UNSTATED_VENUE_NAME = "Unknown Venue"


def extraction_gaps(event, venue) -> list[str]:
    """The fields this run did not obtain for `event`, in a fixed order.

    Judged on the event that was just written, so the report describes what is
    actually stored rather than what the payload looked like before mapping.
    The order is fixed so two summaries can be compared field by field: an
    operator diffing them should see numbers change, not the shape.

    A livestream is expected to have no venue, so it is never asked for one -
    an event that is *supposed* to be placeless is not missing anything.
    """

    gaps: list[str] = []

    if event.starts_at is None and event.ends_at is None:
        gaps.append(_GAP_DATE)

    if event.event_type != "Livestream" and (
        venue.name == _UNSTATED_VENUE_NAME
    ):
        gaps.append(_GAP_VENUE)

    if (
        event.event_type == "FestivalInstance"
        and not event.lineup
    ):
        gaps.append(_GAP_LINEUP)

    return gaps


class SongkickEventImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
        artist_repository: ArtistRepository,
        lineup_importer=None,
        lineup_artist_limit: int = 100,
        lineup_enrichment=None,
    ):

        self.provider_manager = provider_manager

        self.event_repository = (
            event_repository
        )

        self.venue_repository = (
            venue_repository
        )

        self.artist_repository = (
            artist_repository
        )

        # Turns announced performers into artists, by Songkick id. Off by being
        # absent, and it never fetches an artist's gigography - see
        # `LineupArtistImporter`.
        self.lineup_importer = lineup_importer

        self.lineup_artist_limit = max(
            0,
            lineup_artist_limit,
        )

        # The one deferred collaborator, and the deliberate exception to the
        # "nothing is queued for later" rule this service otherwise keeps.
        # It is not asked to finish anything this run needs: events are
        # written, reported and visible before it is given a single id, and
        # it only ever adds to what is stored - see
        # `LineupEnrichmentService`. Off by being absent.
        self.lineup_enrichment = lineup_enrichment

    async def sync_artist_events(
        self,
        artist: Artist,
    ):
        """
        Synchronize events for an artist from Songkick.

        Flow:

            SongkickClient
                ↓
            SongkickProvider
                ↓
            canonical event catalogue
                ↓
            SongkickEventMapper
                ↓
            Venue + Event repositories

        Everything the artist page, the calendar, the gigography and the
        search results state is merged during extraction by event id, and an
        event still missing something afterwards has its own page read once,
        in this same run, before it is written - bounded by
        `SONGKICK_EVENT_PAGE_READS_PER_SCRAPE` so one sync can never spend an
        unbounded amount of time inside somebody else's servers.

        What is still missing once those pages are exhausted is a fact about
        the source, not a debt: it is reported here, as an extraction gap with
        the event id, the field and where it came from. Nothing is handed to a
        later process - there is no second pass over incomplete events - and
        nothing is invented to fill a field the source does not state.
        """

        started_at = time.perf_counter()

        logger.info(
            f"🎤 Synchronizing Songkick events for: "
            f"'{artist.name}'"
        )

        # --------------------------------------------------
        # IDENTITY
        # --------------------------------------------------
        #
        # Which Songkick artist this is has to be decided by the artist's own
        # Songkick ID when one is stored, not by its name. Songkick search
        # routinely returns several acts under one name, and a name-led lookup
        # imports the wrong act's gigography without anything looking wrong: the
        # events are real, they just belong to somebody else.
        #
        # Only the `songkick` key is read. A Spotify ID is never used here - the
        # two ID spaces are unrelated and borrowing across them silently addresses
        # a different artist.
        #
        # When no ID is stored, the scrape falls back to an exact name match, and
        # says so in the log rather than pretending it was certain.
        # --------------------------------------------------

        trusted_songkick_id = normalize_songkick_artist_id(
            (artist.external_ids or {}).get(
                "songkick"
            )
        )

        stored_songkick_id = (
            artist.external_ids or {}
        ).get("songkick")

        if trusted_songkick_id:

            logger.info(
                f"Syncing '{artist.name}' by Songkick ID "
                f"{trusted_songkick_id}"
            )

        elif stored_songkick_id:

            # Something was stored that is not a Songkick artist ID. Refusing it
            # is the point; using it would mean asking Songkick for a page named
            # after an identifier from a different provider.
            logger.warning(
                f"'{artist.name}' stores "
                f"{stored_songkick_id!r} as its Songkick ID, which is "
                f"not a Songkick artist ID. Falling back to an "
                f"exact name match. The stored ID should be corrected."
            )

        else:

            logger.warning(
                f"'{artist.name}' has no Songkick ID stored. "
                f"Falling back to an exact name match, which can be "
                f"wrong when several acts share a name."
            )

        # --------------------------------------------------
        # Provider
        # --------------------------------------------------

        songkick_provider = (
            self.provider_manager.get_provider(
                "songkick"
            )
        )

        # --------------------------------------------------
        # Fetch events
        # --------------------------------------------------

        provider_result = (
            await songkick_provider.get_artist_events(
                artist.name,
                artist_id=trusted_songkick_id,
            )
        )

        # What the provider read about the artist, as distinct from the events it
        # read for them. Held under its own name because `result` is reassigned
        # further down this method, and a value the return statement depends on
        # must not share a name with a loop variable - the last one to be written
        # wins silently, and the artist arrives with nothing the provider said.
        artist_page_facts = (
            provider_result.get("artist") or {}
        )

        result = provider_result

        if not isinstance(
            result,
            dict,
        ):

            raise TypeError(
                "SongkickProvider.get_artist_events() "
                "must return a dictionary."
            )

        # --------------------------------------------------
        # Canonical event catalogue
        # --------------------------------------------------
        #
        # SongkickProvider guarantees that upcoming
        # festivals are included in this list.
        #
        # This is important because SongkickClient keeps
        # upcoming_festivals separate from regular events.
        # --------------------------------------------------

        payloads = result.get(
            "events",
            [],
        )

        if not isinstance(
            payloads,
            list,
        ):

            raise TypeError(
                "Songkick provider returned an invalid "
                "'events' value. Expected a list."
            )

        upcoming_festivals = result.get(
            "upcoming_festivals",
            [],
        )

        if not isinstance(
            upcoming_festivals,
            list,
        ):

            upcoming_festivals = []

        logger.info(
            "Songkick import catalogue: "
            f"events={len(payloads)}, "
            f"upcoming_festivals={len(upcoming_festivals)}"
        )

        # --------------------------------------------------
        # Explicit verification of upcoming festivals
        # --------------------------------------------------

        upcoming_festival_ids = set()

        for festival in upcoming_festivals:

            if not isinstance(
                festival,
                dict,
            ):

                continue

            festival_id = (
                festival.get("songkick_id")
                or festival.get("id")
            )

            if festival_id:

                upcoming_festival_ids.add(
                    str(festival_id)
                )

                logger.info(
                    "[EVENT IMPORT] Upcoming festival "
                    "detected: "
                    f"id={festival_id} | "
                    f"name={festival.get('name')} | "
                    f"start={festival.get('start_date')} | "
                    f"end={festival.get('end_date')}"
                )

        logger.info(
            "[EVENT IMPORT] Upcoming festivals in "
            f"provider response: "
            f"{len(upcoming_festival_ids)}"
        )

        # --------------------------------------------------
        # Verify festivals actually reached the canonical
        # event catalogue.
        # --------------------------------------------------

        canonical_festival_ids = set()

        for payload in payloads:

            if not isinstance(
                payload,
                dict,
            ):

                continue

            payload_id = (
                payload.get("songkick_id")
                or payload.get("id")
            )

            if (
                payload_id
                and str(payload_id)
                in upcoming_festival_ids
            ):

                canonical_festival_ids.add(
                    str(payload_id)
                )

                logger.info(
                    "[EVENT IMPORT] Upcoming festival "
                    "is present in canonical payloads: "
                    f"id={payload_id} | "
                    f"name={payload.get('name')}"
                )

        missing_festival_ids = (
            upcoming_festival_ids
            - canonical_festival_ids
        )

        if missing_festival_ids:

            logger.error(
                "[EVENT IMPORT] Upcoming festivals "
                "were NOT included in canonical "
                f"event payloads: {missing_festival_ids}"
            )

        logger.info(
            f"Payloads received: {len(payloads)}"
        )

        if payloads:

            logger.info(
                f"First event payload: {payloads[0]}"
            )

        logger.info(
            f"📥 Received {len(payloads)} events from Songkick."
        )

        # --------------------------------------------------
        # Counters
        # --------------------------------------------------

        venues_created = 0
        venues_existing = 0

        events_created = 0
        events_existing = 0
        events_skipped = 0

        # What this run could not obtain, counted by field as each event is
        # written. Reported in the summary below and never queued for anything
        # else: a gap is a fact about the source, not a work item.
        gap_counts: dict[str, int] = {}

        events_with_gaps = 0

        # Reads of an event's own page that extraction performed to complete
        # this run, as reported by the client that performed them. Zero when
        # every event arrived complete from the pages already paid for.
        extraction = result.get(
            "extraction"
        ) or {}

        # Failures are counted apart from gaps: the source stated a date and
        # this run could not read it, which is a different problem from a
        # source that states no date at all.
        events_date_parse_failed = 0

        # Lineups this run brought in, keyed by Songkick id so two spellings of
        # one act across a bill collapse to one artist. Collected during the
        # mapping loop and turned into artists afterwards, so lineup entries
        # from every payload in the run are included in one pass.
        announced: dict[str, dict] = {}

        # Festival editions this run wrote, by Songkick id. Each one's own
        # page may state more of the bill than the listing did, and that
        # page is read after this run - in the background, never in front of
        # the response - as the one deferred pass the architecture has. A
        # concert's lineup is its one artist and is already associated, so
        # only editions are collected. Two kinds of edition are deliberately
        # not collected, counted beside the queue so the decision is visible
        # in the run that made it: one this run already read (the pass would
        # fetch the identical page) and one that is over or undated (see the
        # mapping loop).
        festival_event_ids: list[str] = []

        festival_editions_own_page_read = 0
        festival_editions_not_upcoming = 0

        # --------------------------------------------------
        # Process events
        # --------------------------------------------------

        for payload in payloads:

            if not isinstance(
                payload,
                dict,
            ):

                logger.warning(
                    "Skipping invalid Songkick event payload: "
                    f"{payload!r}"
                )

                events_skipped += 1

                continue

            # --------------------------------------------------
            # Event ID
            # --------------------------------------------------

            event_id = (
                payload.get("songkick_id")
                or payload.get("id")
            )

            event_url = payload.get(
                "url"
            )

            # --------------------------------------------------
            # Defensive fallback
            # --------------------------------------------------

            if not event_id:

                logger.warning(
                    "Skipping Songkick event without "
                    f"recognized ID. "
                    f"name={payload.get('name')!r}, "
                    f"url={event_url!r}, "
                    f"event_type={payload.get('event_type')!r}, "
                    f"festival_series_id="
                    f"{payload.get('festival_series_id')!r}"
                )

                events_skipped += 1

                continue

            # --------------------------------------------------
            # Log upcoming festival before mapping
            # --------------------------------------------------

            if (
                str(event_id)
                in upcoming_festival_ids
            ):

                logger.info(
                    "[EVENT IMPORT] Processing upcoming "
                    "festival: "
                    f"id={event_id} | "
                    f"name={payload.get('name')} | "
                    f"type={payload.get('event_type')} | "
                    f"start={payload.get('start_date')} | "
                    f"end={payload.get('end_date')}"
                )

            # --------------------------------------------------
            # Artist relationship
            # --------------------------------------------------

            artist_ids = payload.get(
                "artist_ids",
                [],
            )

            artist_slugs = (
                await self._resolve_artist_ids(
                    artist_ids,
                    artist.slug,
                    lineup_ids=(
                        _lineup_songkick_ids(payload)
                    ),
                )
            )

            # The initiating artist must always be included.
            if not artist_slugs:

                artist_slugs = [
                    artist.slug
                ]

            # --------------------------------------------------
            # Map event + venue
            # --------------------------------------------------

            try:

                event, venue = (
                    SongkickEventMapper.to_domain(
                        payload,
                        artist_slugs,
                    )
                )

            except ValueError as exc:

                logger.warning(
                    f"Skipping Songkick event "
                    f"{event_id}: {exc}"
                )

                events_skipped += 1

                continue

            # --------------------------------------------------
            # Venue
            # --------------------------------------------------

            try:

                venue_created = (
                    await self.venue_repository
                    .upsert_venue(
                        venue
                    )
                )

                if venue_created:

                    venues_created += 1

                else:

                    venues_existing += 1

            except Exception as exc:

                logger.exception(
                    f"Failed to upsert venue for "
                    f"Songkick event {event_id}: {exc}"
                )

                events_skipped += 1

                continue

            # --------------------------------------------------
            # Resolve persisted venue
            # --------------------------------------------------

            persisted_venue = None

            for provider, external_id in (
                venue.external_ids.items()
            ):

                if not external_id:
                    continue

                persisted_venue = (
                    await self.venue_repository
                    .get_by_external_id(
                        provider,
                        external_id,
                    )
                )

                if persisted_venue:
                    break

            # --------------------------------------------------
            # Fallback by normalized name
            # --------------------------------------------------

            if not persisted_venue:

                persisted_venue = (
                    await self.venue_repository
                    .get_by_name(
                        venue.name
                    )
                )

            # --------------------------------------------------
            # Resolve final venue slug
            # --------------------------------------------------

            if persisted_venue:

                event.venue_slug = (
                    persisted_venue["slug"]
                )

            else:

                event.venue_slug = venue.slug

                logger.warning(
                    f"Could not resolve persisted venue "
                    f"after upsert. "
                    f"Event={event_id}, "
                    f"venue={venue.name!r}, "
                    f"slug={venue.slug!r}"
                )

            # --------------------------------------------------
            # Event
            # --------------------------------------------------

            try:

                created = (
                    await self.event_repository
                    .upsert_event_by_provider(
                        event,
                        "songkick",
                    )
                )

                if created:

                    events_created += 1

                else:

                    events_existing += 1

                if "festival" in (
                    event.event_type or ""
                ).casefold():

                    # --------------------------------------------------
                    # Whether this edition is worth a background pass
                    # --------------------------------------------------
                    #
                    # The deferred pass exists to read the edition's own
                    # page, and two kinds of edition have nothing to gain
                    # from it:
                    #
                    # * one this run already read (`own_page_read`): the
                    #   page's date, venue and lineup are stored from the
                    #   extraction read, which is the same page through the
                    #   same parser - queueing it would fetch the identical
                    #   page for fields it already stated;
                    # * one that is over or undated: re-reading the page of
                    #   a bill that already happened is the global
                    #   background scraping this queue must not become. Its
                    #   lineup stays as stored - names and ids resolve from
                    #   the stored entries - and the retry on the festival
                    #   page still reads it on request.
                    #
                    # A future edition whose page this run did not read is
                    # queued exactly as before: that read is the deferred
                    # pass earning its place.
                    # --------------------------------------------------

                    if payload.get(
                        "own_page_read"
                    ):

                        festival_editions_own_page_read += 1

                    elif not is_upcoming(event):

                        festival_editions_not_upcoming += 1

                    else:

                        festival_event_ids.append(
                            str(
                                event.external_ids.get(
                                    "songkick"
                                )
                                or event_id
                            )
                        )

                # --------------------------------------------------
                # Extraction gaps, reported where they occur
                # --------------------------------------------------
                #
                # Judged on the event that was just written, so the count
                # describes stored state rather than the payload's shape.
                # Extraction has already read everything it was going to read
                # - the artist page, the calendar, the gigography, the search
                # results, and this event's own page when something was still
                # missing - so what is absent now is absent at the source.
                #
                # Saying so here, with the event id and the field, is the whole
                # point: the gap is diagnosable from the run that produced it,
                # instead of being an item queued for something later to chase.
                # --------------------------------------------------

                source_url = (event.source or {}).get(
                    "url"
                ) or (event.festival or {}).get("url")

                gaps = extraction_gaps(event, venue)

                if gaps:

                    events_with_gaps += 1

                    for gap in gaps:
                        gap_counts[gap] = (
                            gap_counts.get(gap, 0) + 1
                        )

                    logger.warning(
                        "[EXTRACTION GAP] Songkick event "
                        f"{event.external_ids['songkick']} "
                        f"has no {', '.join(gaps)} in any page "
                        f"read this run | name={event.title!r} | "
                        f"source={source_url!r} | "
                        "written as-is; nothing deferred"
                    )

                # --------------------------------------------------
                # Extraction failures
                # --------------------------------------------------

                if event.date_status == "parser_failed":

                    events_date_parse_failed += 1

                    logger.error(
                        "[EXTRACTION FAILURE] Songkick event "
                        f"{event.external_ids['songkick']}: the "
                        "source states a date this run could not read "
                        "(date_status=parser_failed) | "
                        f"source={source_url!r}"
                    )

                # --------------------------------------------------
                # Announced performers
                # --------------------------------------------------
                #
                # A lineup is a list of real artists, and each entry carries
                # the Songkick id that decides who they are. Collected here
                # and turned into artists once every payload in the run has
                # been mapped, so one act announced on several bills becomes
                # one artist.
                #
                # Keyed by Songkick id, because that is the identity. Two
                # spellings of one act across a bill collapse to one artist.
                # --------------------------------------------------

                for entry in event.lineup or []:

                    songkick_id = getattr(
                        entry,
                        "songkick_id",
                        None,
                    )

                    if not songkick_id:
                        continue

                    announced.setdefault(
                        str(songkick_id),
                        {
                            "songkick_id": str(songkick_id),
                            "name": getattr(
                                entry,
                                "name",
                                "",
                            ),
                            # Songkick's own artist link. It rides along so the
                            # importer can tell, without a fetch, that the
                            # source itself stated this id is an artist id.
                            "url": getattr(
                                entry,
                                "url",
                                None,
                            ),
                            "image": getattr(
                                entry,
                                "image",
                                None,
                            ),
                            "genres": list(
                                getattr(
                                    entry,
                                    "genres",
                                    [],
                                )
                                or []
                            ),
                        },
                    )

            except ValueError as exc:

                logger.warning(
                    f"Skipping Songkick event "
                    f"{event_id}: {exc}"
                )

                events_skipped += 1

            except Exception as exc:

                logger.exception(
                    f"Failed to upsert Songkick event "
                    f"{event_id}: {exc}"
                )

                events_skipped += 1

        # --------------------------------------------------
        # MAKE THE ANNOUNCED ARTISTS EXIST
        # --------------------------------------------------
        #
        # A festival names far more artists than the catalogue has, and an
        # unlinked name is not a usable one. This turns each announced
        # performer into an artist so the lineup can be pressed.
        #
        # What it deliberately does not do is import them. A created artist is
        # a stub with a name, a Songkick id and a slug; no gigography is
        # fetched, and no `last_synced_at` is written, so the artist sync job
        # remains free to decide that for itself. Folding a fetch in here would
        # recreate the old bug where looking at a page changed the database.
        # --------------------------------------------------

        lineup_report = None

        if announced and self.lineup_importer:

            batch = list(announced.values())[
                : self.lineup_artist_limit
            ]

            try:

                lineup_report = await (
                    self.lineup_importer.ensure_for_entries(
                        batch
                    )
                )

            except Exception as exc:
                # An artist-creation problem must never cost us the events that
                # were imported successfully above.
                logger.warning(
                    f"[EVENT IMPORT] lineup artists could not "
                    f"be imported: {exc}"
                )

        elif announced and not self.lineup_importer:

            logger.info(
                f"[EVENT IMPORT] {len(announced)} announced "
                f"performer(s) were imported without becoming "
                f"artists; lineup linking is switched off"
            )

        # --------------------------------------------------
        # THE ENRICHMENT THAT FOLLOWS THIS RUN
        # --------------------------------------------------
        #
        # What is queued above is already written and already reported. The
        # queue holds the future editions whose own page this run did not
        # read, so the background pass reads each of those pages exactly
        # once - a re-import of the same events changes nothing (finished
        # editions are not re-enqueued), and editions with nothing to gain
        # from a read were never queued (see the mapping loop). The queue is
        # the event's own `lineup_state`; a failure of this whole step leaves
        # the events exactly as they are.
        # --------------------------------------------------

        lineup_enrichment_queued = 0

        if festival_editions_own_page_read or festival_editions_not_upcoming:

            logger.info(
                "[EVENT IMPORT] lineup enrichment skipped "
                f"{festival_editions_own_page_read} edition(s) "
                "already read in this run and "
                f"{festival_editions_not_upcoming} past or "
                "undated one(s); both keep their stored lineup "
                "and stay enrichable by the festival's retry"
            )

        if festival_event_ids and self.lineup_enrichment:

            try:

                queued = (
                    await self.lineup_enrichment
                    .enqueue_events(festival_event_ids)
                )

                lineup_enrichment_queued = len(queued)

                if queued:

                    self.lineup_enrichment.schedule(queued)

                    logger.info(
                        "[EVENT IMPORT] queued lineup "
                        f"enrichment for {len(queued)} "
                        "festival edition(s) in the background"
                    )

            except Exception as exc:

                # The events are stored and usable either way. A queue that
                # cannot be written is a lost next pass, not a lost event.
                logger.warning(
                    "[EVENT IMPORT] lineup enrichment could "
                    f"not be queued: {exc}"
                )

        # --------------------------------------------------
        # Summary
        # --------------------------------------------------

        elapsed = (
            time.perf_counter()
            - started_at
        )

        logger.info(
            "──────── Songkick Synchronization Summary ────────"
        )

        logger.info(
            f"🎤 Artist: {artist.name}"
        )

        logger.info(
            f"📥 Events received: {len(payloads)}"
        )

        logger.info(
            f"🏟️ Upcoming festivals received: "
            f"{len(upcoming_festival_ids)}"
        )

        logger.info(
            f"🏟️ Upcoming festivals included in payloads: "
            f"{len(canonical_festival_ids)}"
        )

        logger.info(
            f"❌ Upcoming festivals missing from payloads: "
            f"{len(missing_festival_ids)}"
        )

        logger.info(
            f"✅ New events: {events_created}"
        )

        logger.info(
            f"♻️ Existing events: {events_existing}"
        )

        logger.info(
            f"⏭️ Skipped events: {events_skipped}"
        )

        logger.info(
            f"🔎 Event pages read during extraction: "
            f"{extraction.get('event_pages_read', 0)} "
            f"(bound {extraction.get('limit', 0)}), "
            f"unreadable: {extraction.get('event_pages_failed', 0)}"
        )

        if extraction.get("event_pages_skipped"):

            logger.warning(
                f"⚠️ Event pages left unread because the per-run "
                f"bound was reached: "
                f"{extraction.get('event_pages_skipped')}"
            )

        if events_with_gaps:

            logger.warning(
                f"⚠️ Extraction gaps (absent in every page this run "
                f"read): {events_with_gaps} event(s) "
                f"{gap_counts}"
            )

        else:

            logger.info("✅ Extraction gaps: 0")

        if events_date_parse_failed:

            logger.error(
                f"❌ Extraction failures (the source states a value "
                f"this run could not read): "
                f"{events_date_parse_failed}"
            )

        if lineup_report is not None:
            logger.info(
                f"🎪 Lineup artists: "
                f"{lineup_report.summary()}"
            )

        logger.info(
            f"🏟️ New venues: {venues_created}"
        )

        logger.info(
            f"♻️ Existing venues: {venues_existing}"
        )

        logger.info(
            f"⏱️ Finished in {elapsed:.2f}s"
        )

        logger.info(
            "─────────────────────────────────────────"
        )

        return {
            "artist": artist.name,

            # What the provider read about the artist itself, as distinct from
            # the events it read for them. Carried separately rather than folded
            # into `artist`, which is this artist's *name* and has been for
            # longer than this return value has existed.
            #
            # It is here so the caller can finish the job the fetch started: the
            # artist's own page states a photograph, and an artist whose record
            # came from a festival lineup has none until somebody reads it.
            "artist_facts": artist_page_facts,

            "events_received": len(payloads),
            "events_created": events_created,
            "events_existing": events_existing,
            "events_skipped": events_skipped,
            # What this run could not obtain, by field, and how many events
            # carried at least one such gap - reported as of the write. This
            # is a fact about the source and about this run, not a debt: no
            # other process is asked to follow it up, and nothing is invented
            # to close it. `events_extraction_failed` is separate on purpose,
            # because "the page has no date" and "the date could not be read"
            # need different answers from a person.
            "events_with_extraction_gaps": events_with_gaps,
            "extraction_gaps": gap_counts,
            "events_extraction_failed": events_date_parse_failed,
            # How many event pages extraction read to complete this run, how
            # many it left unread because the per-run bound was reached, and
            # how many of the pages it did read could not be parsed at all.
            "event_pages_read": extraction.get(
                "event_pages_read",
                0,
            ),
            "event_pages_unread": extraction.get(
                "event_pages_skipped",
                0,
            ),
            "event_pages_failed": extraction.get(
                "event_pages_failed",
                0,
            ),
            "lineup_artists": (
                lineup_report.as_dict()
                if lineup_report is not None
                else None
            ),
            # Festival editions whose own pages were queued for background
            # lineup enrichment. Reported so a run says what it started,
            # even though none of it was waited for.
            "lineup_enrichment_queued": lineup_enrichment_queued,
            "venues_created": venues_created,
            "venues_existing": venues_existing,
            "elapsed_seconds": round(
                elapsed,
                2,
            ),
        }

    async def _resolve_artist_ids(
        self,
        artist_ids: list[int],
        initiating_artist_slug: str,
        lineup_ids: list[str] | None = None,
    ) -> list[str]:
        """
        Resolve Songkick numeric artist IDs to local artist slugs.

        The initiating artist is always included and always first, so the
        event's primary artist is the one whose sync wrote the record.

        `lineup_ids` are the Songkick artist ids stated in the event's own
        lineup. A festival date's artist list in a gigography payload usually
        names only the artist being browsed, while the stored record may hold
        more - lineup members resolved on an earlier run - so the caller must
        never replace the stored list with this one; the repository merges it
        additively. An id that does not resolve to an imported artist is
        skipped rather than guessed at, which is the same rule the lineup
        resolver applies when it renders a page.
        """

        artist_slugs = [
            initiating_artist_slug
        ]

        unresolved_ids = []

        for songkick_id in artist_ids:

            if not songkick_id:
                continue

            artist = (
                await self.artist_repository
                .get_by_songkick_id(
                    songkick_id
                )
            )

            if artist:

                if artist.slug not in artist_slugs:

                    artist_slugs.append(
                        artist.slug
                    )

                logger.debug(
                    f"Resolved Songkick ID "
                    f"{songkick_id} to slug "
                    f"{artist.slug}"
                )

            else:

                unresolved_ids.append(
                    songkick_id
                )

                logger.warning(
                    f"Could not resolve Songkick "
                    f"artist ID: {songkick_id}"
                )

        # Lineup members resolve through the same identifier the pages are
        # keyed by, so a lineup artist already imported as a stub joins the
        # event's artist list instead of staying a name only the lineup row
        # knows about. One query for the whole lineup, not one per artist.
        if lineup_ids:

            from app.services.lineup_artist_resolver import (
                LineupArtistResolver,
                stored_id_of,
            )

            resolved = await LineupArtistResolver(
                self.artist_repository,
            ).resolve(lineup_ids)

            for lineup_id in lineup_ids:

                slug = resolved.get(
                    stored_id_of(lineup_id)
                )

                if slug and slug not in artist_slugs:

                    artist_slugs.append(slug)

        if unresolved_ids:

            logger.info(
                f"Unresolved Songkick artist IDs: "
                f"{unresolved_ids}. "
                f"Event will proceed with "
                f"{len(artist_slugs)} resolved artist(s)."
            )

        return artist_slugs