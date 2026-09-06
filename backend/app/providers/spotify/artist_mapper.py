from app.domain.artist import Artist
from app.schemas.artist_search import ArtistSearchItem

from app.utils.slug import generate_slug
from app.utils.text import normalize_text


class SpotifyArtistMapper:

    @staticmethod
    def map_search_results(
        payload: dict,
    ) -> list[ArtistSearchItem]:

        artists = payload.get(
            "artists",
            {},
        ).get(
            "items",
            [],
        )

        results: list[ArtistSearchItem] = []

        for artist in artists:

            images = artist.get(
                "images",
                [],
            )

            results.append(
                ArtistSearchItem(

                    provider="spotify",

                    provider_artist_id=artist["id"],

                    name=artist["name"],

                    image=(
                        images[0]["url"]
                        if images
                        else None
                    ),

                    popularity=artist.get(
                        "popularity"
                    ),

                    verified=False,

                    genres=(
                        artist.get(
                            "genres",
                            [],
                        )
                        or []
                    ),
                )
            )

        return results

    @staticmethod
    def map_artist(
        payload: dict,
    ) -> Artist:

        images = payload.get(
            "images",
            [],
        )

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

            image=(
                images[0]["url"]
                if images
                else None
            ),

            genres=(
                payload.get(
                    "genres",
                    [],
                )
                or []
            ),

            popularity=payload.get(
                "popularity"
            ),

            verified=False,
        )

    @staticmethod
    def map_enrichment(
        payload: dict,
    ) -> dict:

        images = payload.get(
            "images",
            [],
        )

        return {
            "external_ids": {
                "spotify": payload["id"]
            },

            "image": (
                images[0]["url"]
                if images
                else None
            ),

            "genres": (
                payload.get(
                    "genres",
                    [],
                )
                or []
            ),

            "popularity": payload.get(
                "popularity"
            ),
        }