from app.domain.artist import Artist

from app.schemas.artist_response import (
    ArtistResponse,
)

from app.schemas.artist_search import (
    ArtistSearchItem,
)

from app.schemas.artist_profile_response import (
    ArtistProfileResponse,
)


class ArtistResponseMapper:

    @staticmethod
    def from_domain(
        artist: Artist,
    ) -> ArtistResponse:

        songkick_id = artist.external_ids.get(
            "songkick"
        )

        return ArtistResponse(

            provider="songkick",

            provider_artist_id=songkick_id,

            name=artist.name,

            id=artist.id,

            slug=artist.slug,

            image=artist.image,

            genres=artist.genres,

            popularity=artist.popularity,

            verified=artist.verified,

            is_imported=True,
        )

    @staticmethod
    def from_search_item(
        artist: ArtistSearchItem,
    ) -> ArtistResponse:

        return ArtistResponse(

            provider=artist.provider,

            provider_artist_id=(
                artist.provider_artist_id
            ),

            name=artist.name,

            image=artist.image,

            genres=artist.genres,

            popularity=artist.popularity,

            verified=artist.verified,

            is_imported=artist.is_imported,
        )

    @staticmethod
    def to_response(
        artist: Artist,
        followers_count: int = 0,
    ) -> ArtistProfileResponse:

        return ArtistProfileResponse(

            id=artist.id,

            slug=artist.slug,

            name=artist.name,

            image=artist.image,

            genres=artist.genres,

            external_ids=artist.external_ids,

            followers_count=followers_count,

            popularity=artist.popularity,

            verified=artist.verified,

            events={
                "upcoming": 0,
                "total": 0,
            },
        )