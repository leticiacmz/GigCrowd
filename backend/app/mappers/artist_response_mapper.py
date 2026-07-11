from app.domain.artist import Artist
from app.schemas.artist_response import ArtistResponse
from app.schemas.artist_search import ArtistSearchItem


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
            id=artist.id,
            slug=artist.slug,

            followers=artist.followers,

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

            provider_artist_id=artist.provider_artist_id,

            name=artist.name,
            
            id=artist.id,

            slug=artist.slug,

            followers=artist.followers,

            image=artist.image,

            genres=artist.genres,

            popularity=artist.popularity,

            verified=artist.verified,

            is_imported=False,
        )