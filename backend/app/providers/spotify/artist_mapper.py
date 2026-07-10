from app.domain.artist import Artist
from app.utils.slug import generate_slug
from app.utils.text import normalize_text


class SpotifyArtistMapper:

    ...

    @staticmethod
    def map_artist(payload: dict) -> Artist:

        images = payload.get("images", [])

        return Artist(

            name=payload["name"],

            normalized_name=normalize_text(
                payload["name"]
            ),

            slug=generate_slug(
                payload["name"]
            ),

            external_ids={
                "spotify": payload["id"]
            },

            followers=payload.get(
                "followers",
                {},
            ).get(
                "total"
            ),

            image=images[0]["url"] if images else None,

            genres=payload.get(
                "genres",
                [],
            ),

            popularity=payload.get(
                "popularity"
            ),

            verified=False,
        )