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

                    followers=artist.get(
                        "followers",
                        {},
                    ).get(
                        "total"
                    ),

                    image=images[0]["url"] if images else None,

                    popularity=artist.get(
                        "popularity"
                    ),

                    verified=False,

                    genres=artist.get(
                        "genres",
                        [],
                    ),
                )
            )

        return results

    @staticmethod
    def map_artist(
        payload: dict,
    ) -> Artist:
        """
        Map Spotify artist data to domain Artist.
        
        IMPORTANT: This should only be used for enrichment of existing canonical artists.
        The slug and identity should come from Songkick, not Spotify.
        """
        images = payload.get(
            "images",
            [],
        )

        return Artist(

            name=payload["name"],

            normalized_name=normalize_text(
                payload["name"]
            ),

            # Note: Slug should come from Songkick, not Spotify
            # This is kept for backward compatibility but should not be used for canonical creation
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

    @staticmethod
    def map_enrichment(
        payload: dict,
    ) -> dict:
        """
        Map Spotify artist data to enrichment fields only.
        
        This returns only the fields that can be used to enrich
        an existing canonical Artist without modifying identity.
        """
        images = payload.get("images", [])

        return {
            "external_ids": {
                "spotify": payload["id"]
            },
            "followers": payload.get("followers", {}).get("total"),
            "image": images[0]["url"] if images else None,
            "genres": payload.get("genres", []),
            "popularity": payload.get("popularity"),
        }