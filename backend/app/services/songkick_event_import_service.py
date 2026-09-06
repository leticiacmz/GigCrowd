from app.core.logger import get_logger

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


class SongkickEventImportService:

    def __init__(
        self,
        provider_manager: ProviderManager,
        event_repository: EventRepository,
        venue_repository: VenueRepository,
        artist_repository: ArtistRepository,
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
        """

        started_at = time.perf_counter()

        logger.info(
            f"🎤 Synchronizing Songkick events for: "
            f"'{artist.name}'"
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

        result = await songkick_provider.get_artist_events(
            artist.name
        )

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
            "events_received": len(payloads),
            "events_created": events_created,
            "events_existing": events_existing,
            "events_skipped": events_skipped,
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