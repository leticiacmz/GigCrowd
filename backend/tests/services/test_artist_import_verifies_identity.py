"""An imported Songkick id is a claim, and it is proved before it is written.

Selecting an artist from search hands the route an id. Nothing about that
transfer proves the id addresses the artist named beside it: a wrong number
imports cleanly, it just becomes a permanent catalogue row for somebody else.
The festival lineup path has always proved the id against the artist's own page
first and refused when it could not. The explicit import path wrote whatever it
was handed, which is the gap these tests close.

Two things are pinned here: a refusal happens *before* the write, and both
paths store the id in the same one spelling, so the artist a search imports and
the artist a lineup links are the same row.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.songkick_identity import canonical_songkick_artist_id
from app.providers.songkick.artist_mapper import SongkickArtistMapper
from app.schemas.artist_import import ArtistImportRequest
from app.services.artist_import_service import ArtistImportService
from app.services.songkick_artist_verifier import VerifiedArtist


class AcceptingVerifier:
    """The shared verifier's yes, supplied instead of fetched."""

    def __init__(self):
        self.calls = []

    async def verify(self, songkick_id, name=None):
        self.calls.append((songkick_id, name))

        return VerifiedArtist(
            valid=True,
            songkick_id=songkick_id,
            canonical_name=name,
            requested_name=name,
            name_agrees=True,
        )


class RejectingVerifier:
    """The shared verifier's no: the page does not show that identity."""

    async def verify(self, songkick_id, name=None):
        return VerifiedArtist(valid=False, reason="no_artist_page")


def a_service(verifier):
    repository = AsyncMock()
    repository.get_by_songkick_id = AsyncMock(return_value=None)
    repository.get_by_external_id = AsyncMock(return_value=None)
    repository.generate_unique_slug = AsyncMock(return_value="marina-sena")
    repository.insert_artist = AsyncMock()

    service = ArtistImportService(
        provider_manager=MagicMock(),
        artist_repository=repository,
        verifier=verifier,
    )

    return service, repository


class TestTheImportProvesWhatItIsAboutToWrite:
    @pytest.mark.asyncio
    async def test_an_unproved_id_is_rejected_before_any_write(self):
        """The regression: a supplied id was persisted without being checked."""

        service, repository = a_service(RejectingVerifier())

        with pytest.raises(ValueError) as caught:
            await service.import_songkick_artist(
                "Marina Sena",
                {"id": "976211", "name": "Marina Sena"},
            )

        assert "could not be verified" in str(caught.value)
        repository.insert_artist.assert_not_called()

    @pytest.mark.asyncio
    async def test_a_verifier_is_created_when_none_was_supplied(self):
        """One verifier class, used the way the lineup path uses it.

        Leaving it unset must not mean going without: it is created on first
        use, so the route and the importer share one identity check rather than
        each growing its own.
        """

        service, repository = a_service(verifier=None)
        service.verifier = None

        sentinel = AcceptingVerifier()

        import app.services.songkick_artist_verifier as verifier_module

        with pytest.MonkeyPatch.context() as patched:
            patched.setattr(
                verifier_module,
                "SongkickArtistVerifier",
                MagicMock(return_value=sentinel),
            )

            await service.import_songkick_artist(
                "Marina Sena",
                {"id": "976211", "name": "Marina Sena"},
            )

        assert service.verifier is sentinel
        assert sentinel.calls == [("Artist976211", "Marina Sena")]
        repository.insert_artist.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_verified_id_is_stored_in_the_one_spelling(self):
        """Search import and lineup import must produce the same row."""

        service, repository = a_service(AcceptingVerifier())

        result = await service.import_artist(
            ArtistImportRequest(
                provider="songkick",
                provider_artist_id="976211",
                artist_data={"name": "Marina Sena"},
            )
        )

        inserted = repository.insert_artist.await_args[0][0]

        assert inserted.external_ids["songkick"] == "Artist976211"
        assert result["is_new"] is True

        # The lookup that decides reuse speaks the same spelling, so the same
        # artist is found rather than created twice.
        repository.get_by_songkick_id.assert_awaited_with("Artist976211")

    @pytest.mark.asyncio
    async def test_the_identity_is_checked_even_when_the_id_is_reused(self):
        """Verifying only the create path would verify only half the imports."""

        verifier = AcceptingVerifier()

        service, repository = a_service(verifier)

        existing = MagicMock()
        existing.slug = "marina-sena"
        repository.get_by_songkick_id = AsyncMock(return_value=existing)
        repository.update_external_data = AsyncMock()

        result = await service.import_songkick_artist(
            "Marina Sena",
            {"id": "976211", "name": "Marina Sena"},
        )

        assert verifier.calls == [("Artist976211", "Marina Sena")]
        assert result["is_new"] is False
        repository.insert_artist.assert_not_called()


class TestWhatCountsAsASongkickIdentity:
    def test_the_search_import_mapper_stores_the_stored_spelling(self):
        artist = SongkickArtistMapper.to_domain(
            {
                "id": 976211,
                "name": "Marina Sena",
                "is_valid": True,
            }
        )

        assert artist.external_ids["songkick"] == "Artist976211"

    def test_a_foreign_id_is_not_a_songkick_identity(self):
        """A Spotify id must never be persisted as a Songkick one."""

        with pytest.raises(ValueError):
            SongkickArtistMapper.to_domain(
                {"id": "spotify_id_123", "name": "Marina Sena"}
            )

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (976211, "Artist976211"),
            ("976211", "Artist976211"),
            ("Artist976211", "Artist976211"),
            ("artist976211", "Artist976211"),
            ("  976211 ", "Artist976211"),
            ("spotify_id_123", None),
            ("", None),
            (None, None),
        ],
    )
    def test_the_canonical_form_decides_one_spelling(
        self, value, expected
    ):
        assert canonical_songkick_artist_id(value) == expected
