from app.domain.artist import Artist
from app.utils.slug import generate_slug
from app.utils.text import normalize_text


class SongkickArtistMapper:

    @staticmethod
    def to_domain(
        songkick_artist_data: dict,
        fallback_image: str | None = None,
    ) -> Artist:

        name = songkick_artist_data.get(
            "name"
        )

        songkick_image = songkick_artist_data.get(
            "image"
        )

        image = (
            songkick_image
            or fallback_image
        )

        return Artist(

            name=name,

            normalized_name=normalize_text(
                name
            ),

            slug=generate_slug(
                name
            ),

            external_ids={
                "songkick": songkick_artist_data.get(
                    "id"
                )
            },

            followers=None,

            image=image,

            genres=[],

            popularity=(
                int(
                    songkick_artist_data.get(
                        "popularity",
                        0
                    ) * 100
                )
                if songkick_artist_data.get(
                    "popularity"
                )
                else None
            ),

            verified=songkick_artist_data.get(
                "is_valid",
                False
            ),

            sync_status=None,

            last_synced_at=None,
        )