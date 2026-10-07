from datetime import datetime, UTC, timedelta

from typing import Optional

from app.core.logger import get_logger

from app.domain.artist import Artist

from app.repositories.artist_repository import (
    ArtistRepository,
)

from app.services.event_import_service import (
    EventImportService,
)


logger = get_logger(
    "synchronization"
)


def default_ttl_hours() -> int:
    """How long an artist's sync is considered fresh, from configuration.

    Read at call time rather than captured at import so a setting changed by a
    test, or reloaded by the application, takes effect without rebuilding
    anything.
    """

    from app.config import settings

    return int(settings.ARTIST_SYNC_TTL_HOURS)


class SynchronizationService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
        event_import_service: EventImportService,
        ttl_hours: Optional[int] = None,
    ):

        self.artist_repository = (
            artist_repository
        )

        self.event_import_service = (
            event_import_service
        )

        # How stale an artist is allowed to be before another visit is worth it.
        # Settled once here so the job that selects artists and the guard that
        # protects an individual artist agree by construction.
        self.ttl_hours = int(
            default_ttl_hours()
            if ttl_hours is None
            else ttl_hours
        )

    # ============================================================
    # STALENESS
    # ============================================================

    def stale_before(
        self,
        now: Optional[datetime] = None,
    ) -> datetime:
        """The moment before which an artist has not been synced recently enough.

        Exposed so a batch selection can be built from exactly the boundary this
        guard uses. Deriving the two independently is how a job ends up handing
        the service an artist the service then refuses, or worse, one it accepts
        an hour too often.
        """

        moment = now or datetime.now(UTC)

        return moment - timedelta(
            hours=self.ttl_hours
        )

    def needs_sync(
        self,
        artist: Artist,
        now: Optional[datetime] = None,
    ) -> bool:
        """Whether this artist's stored data has aged past the TTL.

        An artist never synced is always eligible. Mongo may hand back a naive
        datetime, which is compared as though it were UTC - the same assumption
        every other timestamp in this project makes.
        """

        last_sync = artist.last_synced_at

        if not last_sync:

            return True

        if last_sync.tzinfo is None:

            last_sync = last_sync.replace(
                tzinfo=UTC
            )

        moment = now or datetime.now(UTC)

        return (
            moment - last_sync
        ) > timedelta(
            hours=self.ttl_hours
        )


    async def synchronize_artist(
        self,
        artist: Artist,
        *,
        force: bool = False,
        provider: str = "songkick",
    ):

        if (
            not force
            and not self.needs_sync(
                artist,
            )
        ):

            logger.info(
                f"{artist.name} sync skipped. "
                "Cache valid."
            )

            return {
                "artist": artist,
                "synced": False,
                "reason": "cache_valid",
            }


        logger.info(
            f"Starting sync for {artist.name}"
        )


        try:

            result = await (
                self.event_import_service
                .sync_artist_events(
                    artist,
                    provider=provider
                )
            )


            events_received = result.get(
                "events_received",
                0,
            )

            # --------------------------------------------------
            # WHO THEY ARE
            # --------------------------------------------------
            #
            # The fetch just read this artist's own page, and that page states
            # their photograph. Without this, an artist whose record came from a
            # festival lineup keeps their poster thumbnail - or no picture at all
            # - forever, even after the page that could supply one has been read.
            #
            # Only fills a gap. An image already stored came from somewhere the
            # catalogue chose deliberately, and replacing it because some other
            # page mentions a different picture would be fixing a problem nobody
            # reported while destroying whatever was there.
            # --------------------------------------------------

            await self._store_artist_image(
                artist,
                result,
            )


            if events_received > 0:

                await (
                    self.artist_repository
                    .update_last_synced(
                        artist.id
                    )
                )


                artist.last_synced_at = (
                    datetime.now(UTC)
                )

                artist.sync_status = (
                    "success"
                )

            else:

                logger.warning(
                    f"{artist.name} sync returned "
                    "0 events. Marking as synced-empty."
                )


                # Recorded like any other completed fetch, and deliberately.
                #
                # "The provider was asked and there is nothing" is an answer, and
                # caching it for the TTL is what stops a genuinely unbooked artist
                # from being re-fetched every single time somebody opens the page.
                # It used to be left unsynced on purpose, so the artist would stay
                # eligible for a retry - but eligibility for a retry was also how
                # the scheduler used to drain the entire pending catalogue. The
                # right place to retry is a person opening the artist, and that
                # path never consults the TTL.
                await (
                    self.artist_repository
                    .update_sync_empty(
                        artist.id
                    )
                )


                artist.last_synced_at = (
                    datetime.now(UTC)
                )


                artist.sync_status = (
                    "empty"
                )


            return {
                "artist": artist,
                "synced": True,
                "result": result,
            }


        except Exception as error:

            logger.exception(
                f"Sync failed for {artist.name}: "
                f"{error}"
            )


            await (
                self.artist_repository
                .update_sync_error(
                    artist.id
                )
            )


            artist.sync_status = (
                "error"
            )


            raise

    # ============================================================
    # ARTIST FACTS
    # ============================================================

    async def _store_artist_image(
        self,
        artist: Artist,
        result: dict,
    ) -> None:
        """Adopt the photograph this artist's own page published, if we lack one.

        Never raises and never overwrites. A missing picture is a cosmetic gap; a
        synchronization that fails *because* it could not fill one would turn a
        cosmetic gap into an artist that never becomes initialized, which is a far
        worse outcome than a page with no headshot.
        """

        if artist.image:
            return

        published = (
            (result.get("artist_facts") or {}).get("image")
        )

        if not published:
            return

        try:

            await self.artist_repository.update_image(
                artist.id,
                published,
            )

            artist.image = published

            logger.info(
                f"Stored the photograph {artist.name}'s own "
                f"Songkick page publishes"
            )

        except Exception as exc:

            logger.warning(
                f"Could not store the photograph for "
                f"{artist.name}: {exc}"
            )