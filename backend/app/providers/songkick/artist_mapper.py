from app.domain.artist import Artist

from app.utils.slug import generate_slug
from app.utils.text import normalize_text


class SongkickArtistMapper:

    @staticmethod
    def _merge_genres(
        spotify_genres: list[str] | None,
        songkick_genres: list[str] | None,
    ) -> list[str]:

        """
        Merge Spotify and Songkick genres.

        Genres are deduplicated case-insensitively and
        ignoring surrounding whitespace.

        The first-seen display value is preserved.

        Example:

            Spotify:
                ["Rock", "Alternative Rock"]

            Songkick:
                ["rock", "Pop"]

            Result:
                ["Rock", "Alternative Rock", "Pop"]
        """

        result: list[str] = []

        seen: set[str] = set()

        for genre in (
            (spotify_genres or [])
            + (songkick_genres or [])
        ):

            if not isinstance(
                genre,
                str,
            ):
                continue

            normalized = (
                genre.strip().casefold()
            )

            if not normalized:
                continue

            if normalized in seen:
                continue

            seen.add(normalized)

            result.append(
                genre.strip()
            )

        return result

    @staticmethod
    def to_domain(
        songkick_artist_data: dict,
        spotify_artist: Artist | None = None,
        fallback_image: str | None = None,
    ) -> Artist:
        """
        Build the canonical Artist.

        Songkick is responsible for canonical identity:

        - name
        - slug
        - Songkick external ID
        - verification

        Spotify is responsible for enrichment:

        - Spotify external ID
        - image
        - genres
        - popularity

        Followers are intentionally not imported from
        Spotify because GigCrowd followers are internal
        to the application.
        """

        name = songkick_artist_data.get(
            "name"
        )

        if not name:

            raise ValueError(
                "Songkick artist data requires a name."
            )

        songkick_id = songkick_artist_data.get(
            "id"
        )

        if not songkick_id:

            raise ValueError(
                "Songkick artist data requires an id."
            )

        # ==================================================
        # IMAGE
        # ==================================================

        songkick_image = (
            songkick_artist_data.get(
                "image"
            )
        )

        spotify_image = (
            spotify_artist.image
            if spotify_artist
            else None
        )

        image = (
            songkick_image
            or spotify_image
            or fallback_image
        )

        # ==================================================
        # EXTERNAL IDS
        # ==================================================

        external_ids = {
            "songkick": str(
                songkick_id
            ),
        }

        if spotify_artist:

            spotify_id = (
                spotify_artist.external_ids.get(
                    "spotify"
                )
            )

            if spotify_id:

                external_ids["spotify"] = (
                    spotify_id
                )

        # ==================================================
        # GENRES
        # ==================================================

        songkick_genres = (
            songkick_artist_data.get(
                "genres",
                [],
            )
            or []
        )

        spotify_genres = (
            spotify_artist.genres
            if spotify_artist
            else []
        )

        genres = (
            SongkickArtistMapper._merge_genres(
                spotify_genres=spotify_genres,
                songkick_genres=songkick_genres,
            )
        )

        # ==================================================
        # ARTIST
        # ==================================================

        return Artist(

            name=name,

            normalized_name=normalize_text(
                name
            ),

            slug=generate_slug(
                name
            ),

            external_ids=external_ids,

            image=image,

            genres=genres,

            popularity=(
                spotify_artist.popularity
                if spotify_artist
                else None
            ),

            verified=songkick_artist_data.get(
                "is_valid",
                False,
            ),

            sync_status=None,

            last_synced_at=None,
        )
