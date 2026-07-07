from datetime import UTC, datetime
from typing import Any

from app.utils.slug import generate_slug


class ArtistMerge:

    @staticmethod
    def merge(
        spotify: dict[str, Any] | None = None,
        bandsintown: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        spotify = spotify or {}
        bandsintown = bandsintown or {}

        name = (
            spotify.get("name")
            or bandsintown.get("name")
            or ""
        )

        now = datetime.now(UTC)

        providers = []

        if spotify:
            providers.append("spotify")

        if bandsintown:
            providers.append("bandsintown")

        return {
            "name": name,

            "slug": generate_slug(name),

            "followers": spotify.get("followers", 0),

            "genres": spotify.get("genres", []),

            "image": spotify.get("image"),

            "external_ids": {
                "spotify": spotify.get("id"),
                "bandsintown": bandsintown.get("id"),
            },

            "providers": providers,

            "sync_metadata": {
                "spotify_last_sync": now,
                "bandsintown_last_sync": now,
                "search_count": 1,
                "sync_failures": 0,
            },

            "last_synced_at": now,

            "created_at": now,

            "updated_at": now,

            "sync_status": "pending",
        }