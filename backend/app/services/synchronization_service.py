from datetime import datetime, UTC, timedelta

from app.core.logger import get_logger


logger = get_logger("synchronization")


class SynchronizationService:

    def __init__(
        self,
        event_import_service,
        artist_repository,
    ):

        self.event_import_service = event_import_service

        self.artist_repository = artist_repository


    async def synchronize_artist(
        self,
        artist,
        *,
        force: bool = True,
    ):

        if (
            not force
            and not self._needs_sync(artist)
        ):

            logger.info(
                f"{artist.name} sync skipped. Cache valid."
            )

            return {
                "artist": artist,
                "synced": False,
                "reason": "cache_valid",
            }


        logger.info(
            f"Starting sync for {artist.name}"
        )


        result = await (
            self.event_import_service
            .sync_artist_events(
                artist
            )
        )


        await self.artist_repository.update_last_synced(
            artist.id
        )


        return {
            "artist": artist,
            "synced": True,
            "result": result,
        }



    def _needs_sync(
        self,
        artist,
    ) -> bool:


        if not artist.last_synced_at:

            return True


        last_sync = artist.last_synced_at


        # Corrige datas antigas do Mongo
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