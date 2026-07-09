from app.schemas.artist_search import ArtistSearchItem


class SpotifyMapper:

    @staticmethod
    def map_search_results(payload: dict) -> list[ArtistSearchItem]:

        artists = payload.get("artists", {}).get("items", [])

        results: list[ArtistSearchItem] = []

        for artist in artists:

            images = artist.get("images", [])

            results.append(
                ArtistSearchItem(
                    provider="spotify",
                    provider_artist_id=artist["id"],
                    name=artist["name"],
                    followers=artist.get("followers", {}).get("total"),
                    image=images[0]["url"] if images else None,
                    popularity=artist.get("popularity"),
                    verified=False,
                    genres=artist.get("genres", []),
                )
            )

        return results