from app.core.logger import get_logger

from typing import Optional

from app.domain.songkick_identity import (
    normalize_songkick_artist_id,
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

from app.services.event_enrichment_service import (
    EventEnrichmentService,
)

from app.domain.artist import Artist

import asyncio

import time


logger = get_logger(
    "songkick_event_import"
)

# How many source failures in a row end an import's enrichment pass.
#
# A failure is not cheap - the client retries a dead source rather than
# give up on the first timeout - so a pass over an unreachable Songkick
# would otherwise burn the whole bound one timeout at a time. Five in a
# row is a source that is down, not five events that are unlucky: the rest
# of the batch is deferred to the scheduler, which is what the safety net
# is for, and the import finishes with the events it already has.
_SOURCE_FAILURE_STREAK_LIMIT = 5


class SongkickEventImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
        artist_repository: ArtistRepository,
        enrichment_service: Optional[
            EventEnrichmentService
        ] = None,
        enrich_fields: Optional[list[str]] = None,
        enrich_limit: int = 60,
        enrich_delay_seconds: float = 1.5,
        lineup_importer=None,
        lineup_artist_limit: int = 100,
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

        # Enrichment is a collaborator, not a hard dependency. Without one the
        # importer still writes events; they simply arrive incomplete and the
        # scheduler picks them up later. That is the degraded path, not the
        # normal one.
        self.enrichment_service = enrichment_service

        self.enrich_fields = enrich_fields

        self.enrich_limit = max(
            0,
            enrich_limit,
        )

        self.enrich_delay_seconds = enrich_delay_seconds

        # Turns announced performers into artists, by Songkick id. Off by being
        # absent, and it never fetches an artist's gigography - see
        # `LineupArtistImporter`.
        self.lineup_importer = lineup_importer

        self.lineup_artist_limit = max(
            0,
            lineup_artist_limit,
        )

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
                ↓
            EventEnrichmentService, for anything still incomplete

        The last arrow is the part that makes an imported event trustworthy
        without a human. A listing that carries no date is not evidence that
        the event has none - the concrete event page nearly always does - so an
        event that arrives incomplete is read again from its own page straight
        away, through the same enrichment service the scheduler uses.
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

        # Events this run wrote that still need their concrete source read.
        # Collected here and enriched after the mapping loop, so the pacing
        # toward Songkick is in one place instead of interleaved with mapping.
        incomplete: list[str] = []

        # Lineups this run brought in. Turned into artists after enrichment, so
        # the lineup a concrete festival page just recovered is included, not
        # only the one the listing happened to carry.
        announced: dict[str, dict] = {}

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

                # --------------------------------------------------
                # Incomplete?
                # --------------------------------------------------
                #
                # Decided here, from the event that was just mapped, so it costs
                # no extra query. The rule is the enrichment service's, called
                # here on purpose: the importer and the scheduler must agree on
                # what "incomplete" means, and one definition cannot disagree
                # with itself.
                #
                # An event is only a candidate if it also has a concrete source
                # to read. A listing that gave nothing to re-read cannot be
                # improved by asking it again.
                # --------------------------------------------------

                source_url = (event.source or {}).get(
                    "url"
                ) or (event.festival or {}).get("url")

                if source_url and EventEnrichmentService.is_incomplete(
                    event,
                    self.enrich_fields,
                ):

                    incomplete.append(
                        str(event.external_ids["songkick"])
                    )

                # --------------------------------------------------
                # Announced performers
                # --------------------------------------------------
                #
                # A lineup is a list of real artists, and each entry carries
                # the Songkick id that decides who they are. Collecting them
                # here and creating the artists after enrichment means the
                # lineup a concrete festival page is about to recover is
                # included too, not only the one this listing happened to
                # carry.
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
        # ENRICH WHAT IS STILL INCOMPLETE
        # --------------------------------------------------
        #
        # An imported event that arrived without a date is not finished. The
        # concrete Songkick page for that event very nearly always states the
        # real date, so the import reads it now rather than leaving the record
        # for a human to notice or for a scheduled run to reach much later.
        #
        # This is not a second enrichment implementation. Every event here goes
        # through `EventEnrichmentService.enrich_event`, which plans, fetches,
        # parses and writes exactly as the scheduler does. The scheduler remains
        # the safety net for whatever this pass defers or fails on.
        # --------------------------------------------------

        events_enriched = 0
        events_enrichment_failed = 0
        events_enrichment_deferred = 0

        if incomplete and not self.enrichment_service:

            # Enrichment is switched off. The scheduler will pick these up; say
            # so rather than letting an incomplete import look like a complete
            # one.
            events_enrichment_deferred = len(incomplete)

            logger.info(
                f"[EVENT IMPORT] Enrichment is not configured; "
                f"{len(incomplete)} incomplete event(s) were "
                f"written for the scheduler to recover"
            )

        elif incomplete:

            batch = incomplete[: self.enrich_limit]

            events_enrichment_deferred = (
                len(incomplete) - len(batch)
            )

            logger.info(
                f"[EVENT IMPORT] Reading the concrete source for "
                f"{len(batch)} incomplete event(s); "
                f"{events_enrichment_deferred} deferred to the "
                f"scheduler"
            )

            consecutive_failures = 0

            for index, songkick_event_id in enumerate(batch):

                if consecutive_failures >= (
                    _SOURCE_FAILURE_STREAK_LIMIT
                ):

                    # Accounted rather than dropped: these events are
                    # exactly what the scheduler exists for, and the
                    # report has to say how many were handed over.
                    deferred_here = len(batch) - index

                    events_enrichment_deferred += deferred_here

                    logger.warning(
                        f"[EVENT IMPORT] enrichment stopped after "
                        f"{consecutive_failures} consecutive "
                        f"failures; {deferred_here} event(s) "
                        f"deferred to the scheduler"
                    )

                    break

                try:

                    stored_event_id = (
                        await self.event_repository
                        .get_id_by_external_id(
                            "songkick",
                            songkick_event_id,
                        )
                    )

                except Exception as exc:

                    logger.warning(
                        f"[EVENT IMPORT] could not resolve the "
                        f"stored id for Songkick event "
                        f"{songkick_event_id}: {exc}"
                    )

                    events_enrichment_failed += 1

                    consecutive_failures += 1

                    continue

                if not stored_event_id:

                    events_enrichment_failed += 1

                    consecutive_failures += 1

                    continue

                try:

                    # Named for what it is rather than reusing `result`.
                    #
                    # `result` is the provider's answer for this artist, and this
                    # loop runs over every event that came back. Assigning the
                    # enrichment outcome to the same name meant that by the end of
                    # the loop `result` no longer described the artist at all -
                    # and the return statement below reads from it. Nothing
                    # crashed; the artist simply arrived with nothing the
                    # provider had said about them.
                    enrichment = await (
                        self.enrichment_service.enrich_event(
                            stored_event_id,
                            fields=self.enrich_fields,
                        )
                    )

                except Exception as exc:

                    # One unreachable page must not end an import. The record
                    # stays incomplete and the scheduler retries it.
                    logger.warning(
                        f"[EVENT IMPORT] enrichment raised for "
                        f"{songkick_event_id}: {exc}"
                    )

                    events_enrichment_failed += 1

                    consecutive_failures += 1

                    if index and self.enrich_delay_seconds and (
                        index + 1 < len(batch)
                    ):
                        await asyncio.sleep(
                            self.enrich_delay_seconds
                        )

                    continue

                outcome = enrichment.get("outcome")

                if outcome in (
                    "updated",
                    "unchanged",
                    "complete",
                    "skipped",
                ):

                    events_enriched += 1

                    consecutive_failures = 0

                else:

                    events_enrichment_failed += 1

                    consecutive_failures += 1

                    logger.info(
                        f"[EVENT IMPORT] enrichment for "
                        f"{songkick_event_id} did not resolve: "
                        f"{outcome}"
                    )

                if (
                    index
                    and self.enrich_delay_seconds
                    and index + 1 < len(batch)
                ):
                    await asyncio.sleep(
                        self.enrich_delay_seconds
                    )

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
            f"🔎 Events read at source during import: "
            f"{events_enriched}"
        )

        logger.info(
            f"⚠️ Enrichment failures (scheduler will retry): "
            f"{events_enrichment_failed}"
        )

        logger.info(
            f"⏳ Deferred to the scheduler: "
            f"{events_enrichment_deferred}"
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
            # How many of the events this run wrote were still missing something
            # afterwards. `events_incomplete_found` is the count the import
            # decided needed a source read; the difference between it and
            # `events_enriched` is what the scheduler still owes.
            "events_incomplete_found": len(incomplete),
            "events_enriched": events_enriched,
            "events_enrichment_failed": events_enrichment_failed,
            "events_enrichment_deferred": (
                events_enrichment_deferred
            ),
            "lineup_artists": (
                lineup_report.as_dict()
                if lineup_report is not None
                else None
            ),
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
    ) -> list[str]:
        """
        Resolve Songkick numeric artist IDs to local artist slugs.

        The initiating artist is always included.
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

        if unresolved_ids:

            logger.info(
                f"Unresolved Songkick artist IDs: "
                f"{unresolved_ids}. "
                f"Event will proceed with "
                f"{len(artist_slugs)} resolved artist(s)."
            )

        return artist_slugs