from datetime import datetime, UTC, timedelta

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


class SynchronizationService:

    def __init__(
        self,
        artist_repository: ArtistRepository,
        event_import_service: EventImportService,
    ):

        self.artist_repository = (
            artist_repository
        )

        self.event_import_service = (
            event_import_service
        )


    async def synchronize_artist(
        self,
        artist: Artist,
        *,
        force: bool = False,
    ):

        if (
            not force
            and not self._needs_sync(
                artist
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
                    artist
                )
            )


            events_received = result.get(
                "events_received",
                0,
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
                    "0 events. Keeping previous sync."
                )


                await (
                    self.artist_repository
                    .update_sync_empty(
                        artist.id
                    )
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



    def _needs_sync(
        self,
        artist: Artist,
    ) -> bool:


        if not artist.last_synced_at:

            return True


        last_sync = (
            artist.last_synced_at
        )


        #
        # Mongo pode retornar datetime sem timezone
        #
        if last_sync.tzinfo is None:

            last_sync = last_sync.replace(
                tzinfo=UTC
            )


        return (
            datetime.now(UTC)
            - last_sync
        ) > timedelta(
            hours=24
        )