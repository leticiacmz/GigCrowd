from app.domain.artist import Artist
from app.schemas.artist_response import ArtistResponse


class ArtistResponseMapper:

    @staticmethod
    def from_domain(
        artist: Artist,
    ) -> ArtistResponse:

        spotify_id = artist.external_ids.get(
            "spotify"
        )

        return ArtistResponse(

            provider="spotify",

            provider_artist_id=spotify_id,

            name=artist.name,

            slug=artist.slug,

            followers=artist.followers,

            image=artist.image,

            genres=artist.genres,

            popularity=artist.popularity,

            verified=artist.verified,

            is_imported=True,
        )