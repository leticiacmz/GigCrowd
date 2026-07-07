from datetime import datetime, UTC
from typing import Any


class ArtistMerge:

    @staticmethod
    def merge(
        spotify: dict[str, Any] | None = None,
        bandsintown: dict[str, Any] | None = None
    ) -> dict[str, Any]:

        spotify = spotify or {}
        bandsintown = bandsintown or {}

        return {

            "name": spotify.get("name")
                or bandsintown.get("name"),

            "followers": spotify.get("followers", 0),

            "genres": spotify.get("genres", []),

            "image": spotify.get("image"),

            "external_ids": {

                "spotify": spotify.get("id"),

                "bandsintown": bandsintown.get("id")

            },

            "providers": [

                provider

                for provider in [
                    "spotify" if spotify else None,
                    "bandsintown" if bandsintown else None
                ]

                if provider
            ],

            "last_synced_at": datetime.now(UTC),

            "created_at": datetime.now(UTC),

            "updated_at": datetime.now(UTC),

            "sync_status": "pending"

        }