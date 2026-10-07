"""A festival lineup becomes a list of real, linkable artists.

The feature is small; the ways it can go wrong are not. Every one of the rules
below exists because the alternative is a catalogue containing a confidently
wrong record, which is far worse than a name that is merely unlinked:

* identity is the Songkick id, never a name
* no fuzzy matching, no first-result fallback
* no Spotify
* idempotent, and it never duplicates
* creating an artist never starts a gigography fetch

The last one matters most in practice. Folding a fetch into this would rebuild
the old bug where opening a page changed the database - a festival with thirty
names on the bill would cost thirty outbound requests the moment somebody looked
at the poster.
"""
from __future__ import annotations

import pytest

from app.repositories.artist_repository import ArtistRepository
from app.services.lineup_artist_importer import (
    LineupArtistImporter,
)
from app.services.lineup_artist_resolver import (
    external_id_for,
    stored_id_of,
)
from app.utils.slug import generate_slug
from tests.support.fake_mongo import FakeDatabase


def entry(
    name: str,
    songkick_id: str | None,
    **extra,
) -> dict:
    return {
        "name": name,
        "songkick_id": songkick_id,
        "image": None,
        "genres": [],
        **extra,
    }


class StubVerifier:
    """An identity check that answers from a table instead of from Songkick.

    The importer validates every new identity against the artist's own page
    before creating a record, which is a network call by design. These tests are
    about what the importer does with the verdict - create, refuse, reuse - and
    driving that through the real Songkick site would make them slow, flaky and
    dependent on a third party's uptime.

    `accepted` is the set of ids the fake Songkick knows; anything else is
    refused the way a 404 would be.
    """

    def __init__(self, accepted=None, names=None):
        self.accepted = (
            accepted
            if accepted is not None
            else None  # accept everything
        )
        self.names = names or {}
        self.calls: list[str] = []

    async def verify(self, songkick_id, *, name=None):
        from app.services.songkick_artist_verifier import (
            ACCEPTED,
            REJECTED_NO_PAGE,
            VerifiedArtist,
        )

        self.calls.append(str(songkick_id))

        from app.domain.songkick_identity import (
            normalize_songkick_artist_id,
        )

        trusted = normalize_songkick_artist_id(songkick_id)

        if not trusted:
            return VerifiedArtist(
                valid=False,
                reason="not_a_songkick_artist_id",
                requested_name=name,
            )

        if self.accepted is not None and trusted not in self.accepted:
            return VerifiedArtist(
                valid=False,
                reason=REJECTED_NO_PAGE,
                songkick_id=trusted,
                requested_name=name,
            )

        return VerifiedArtist(
            valid=True,
            reason=ACCEPTED,
            songkick_id=trusted,
            canonical_name=self.names.get(trusted, name),
            image="https://images.test/artist.jpg",
        )


def world(
    artists: list[dict] | None = None,
    verifier=None,
    validate: bool = True,
) -> tuple[
    LineupArtistImporter,
    ArtistRepository,
    FakeDatabase,
]:
    database = FakeDatabase(
        {
            "artists": artists or [],
            "events": [],
        }
    )

    repository = ArtistRepository(database)

    importer = LineupArtistImporter(
        repository,
        verifier=verifier or StubVerifier(),
        validate=validate,
    )

    return importer, repository, database


class TestAnAnnouncedPerformerBecomesAnArtist:
    @pytest.mark.asyncio
    async def test_a_lineup_entry_with_an_id_is_created(self):
        importer, _, database = world()

        report = await importer.ensure_for_entries(
            [entry("Tim Bernardes", "2668421")]
        )

        assert report.created == 1
        assert await database.artists.count_documents({}) == 1

        stored = await database.artists.find_one({})

        assert stored["name"] == "Tim Bernardes"
        assert stored["slug"] == "tim-bernardes"
        assert stored["external_ids"]["songkick"] == (
            external_id_for("2668421")
        )

    @pytest.mark.asyncio
    async def test_an_existing_artist_is_left_untouched(self):
        importer, _, database = world(
            [
                {
                    "name": "Tim Bernardes",
                    "slug": "tim-bernardes",
                    "normalized_name": "tim bernardes",
                    "external_ids": {
                        "songkick": external_id_for("2668421")
                    },
                    "genres": ["MPB", "Indie"],
                    "image": "https://example.test/tb.jpg",
                }
            ]
        )

        report = await importer.ensure_for_entries(
            [entry("Tim Bernardes", "2668421")]
        )

        assert report.created == 0
        assert report.resolved_existing == 1
        assert await database.artists.count_documents({}) == 1

        # Nothing rewritten. An import that renamed or re-slugged an artist that
        # already had a page would break every link to it.
        stored = await database.artists.find_one({})

        assert stored["genres"] == ["MPB", "Indie"]
        assert stored["image"] == "https://example.test/tb.jpg"

    @pytest.mark.asyncio
    async def test_an_entry_without_an_id_is_left_alone(self):
        """No id, no identity, no record.

        A name is not an identifier: two different artists can share one, and
        creating a record from it would put the wrong act in the catalogue with
        no way to tell afterwards.
        """

        importer, _, database = world()

        report = await importer.ensure_for_entries(
            [entry("Some Band", None)]
        )

        assert report.entries_without_songkick_id == 1
        assert report.skipped_no_id == 1
        assert report.created == 0
        assert await database.artists.count_documents({}) == 0


class TestIdentity:
    @pytest.mark.asyncio
    async def test_two_acts_with_the_same_name_stay_separate(self):
        """A name collision is not a merge, and not a coin flip either.

        Both are real and distinct, and the Songkick id is what says so. Choosing
        between them by name would link a festival bill to the wrong band, and the
        error would be permanent.
        """

        importer, _, database = world()

        await importer.ensure_for_entries(
            [
                entry("The Killers", "111"),
                entry("The Killers", "222"),
            ]
        )

        assert await database.artists.count_documents({}) == 2

        ids = {
            (await database.artists.find_one({"slug": slug}))[
                "external_ids"
            ]["songkick"]
            for slug in ("the-killers", "the-killers-2")
        }

        assert ids == {
            external_id_for("111"),
            external_id_for("222"),
        }

    @pytest.mark.asyncio
    async def test_the_same_id_announced_twice_creates_one_artist(self):
        """A festival lists the same act on more than one date.

        Handled by identity rather than by the database alone: two passes over one
        lineup would each see no existing artist, because the first write is not
        visible until it lands, and both would insert.
        """

        importer, _, database = world()

        report = await importer.ensure_for_entries(
            [
                entry("Marina Sena", "3090429"),
                entry("Marina Sena", "3090429"),
                entry("MARINA SENA", "3090429"),
            ]
        )

        assert report.created == 1
        assert await database.artists.count_documents({}) == 1

    @pytest.mark.asyncio
    async def test_the_stored_and_bare_id_forms_are_the_same_artist(self):
        """A lineup carries `3090429`; an artist stores `Artist3090429`.

        Translating between the two forms is the whole of the format difference,
        and getting it wrong would create a second record for an artist that
        already exists.
        """

        importer, _, database = world(
            [
                {
                    "name": "Marina Sena",
                    "slug": "marina-sena",
                    "normalized_name": "marina sena",
                    "external_ids": {
                        "songkick": external_id_for("3090429")
                    },
                }
            ]
        )

        report = await importer.ensure_for_entries(
            [entry("Marina Sena", "Artist3090429")]
        )

        assert report.created == 0
        assert await database.artists.count_documents({}) == 1

    def test_the_id_form_helpers_round_trip(self):
        assert external_id_for("3090429") == "Artist3090429"
        assert external_id_for("Artist3090429") == "Artist3090429"
        assert stored_id_of("Artist3090429") == "3090429"
        assert stored_id_of("3090429") == "3090429"


class TestIdempotence:
    @pytest.mark.asyncio
    async def test_running_the_same_lineup_ten_times_changes_nothing(self):
        """Repetition is the normal case, not an edge case.

        Lineups are re-read on every sync, every festival edition is walked, and a
        script may be run twice. A pass that kept adding artists would turn a
        repeated import into a growing catalogue of duplicates.
        """

        importer, _, database = world()

        lineup = [
            entry("Marina Sena", "3090429"),
            entry("Tim Bernardes", "2668421"),
            entry("O Terno", "2921978"),
            entry("Victo", "9988771"),
            entry("Unnamed Support", None),
        ]

        for _ in range(10):
            await importer.ensure_for_entries(list(lineup))

        assert await database.artists.count_documents({}) == 4

        slugs = sorted(
            row["slug"]
            for row in await database.artists.find({}).to_list(
                length=None
            )
        )

        assert slugs == [
            "marina-sena",
            "o-terno",
            "tim-bernardes",
            "victo",
        ]

    @pytest.mark.asyncio
    async def test_a_second_pass_creates_nothing_and_says_so(self):
        importer, _, _ = world()

        lineup = [entry("Marina Sena", "3090429")]

        first = await importer.ensure_for_entries(list(lineup))

        assert first.created == 1

        second = await importer.ensure_for_entries(list(lineup))

        assert second.created == 0
        assert second.resolved_existing == 1


class TestCreatingIsNotImporting:
    @pytest.mark.asyncio
    async def test_no_gigography_is_fetched(self):
        """The boundary this module exists to hold.

        The importer takes no provider at all - it cannot fetch anything even by
        accident. Stated as a test because the next person to add a
        "while we're here, let's sync them" is going to be someone with a reason,
        and this is the line that reason should have to argue with.
        """

        import inspect

        parameters = inspect.signature(
            LineupArtistImporter.__init__
        ).parameters

        for name in (
            "provider_manager",
            "synchronization_service",
            "event_import_service",
        ):
            assert name not in parameters

    @pytest.mark.asyncio
    async def test_no_events_are_written(self):
        importer, _, database = world()

        await importer.ensure_for_entries(
            [
                entry(f"Act {index}", str(100 + index))
                for index in range(40)
            ]
        )

        assert await database.artists.count_documents({}) == 40
        assert await database.events.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_a_created_artist_is_still_owed_a_sync(self):
        """A stub that looks synced is a stub nobody ever imports."""

        from app.mappers.artist_document_mapper import (
            ArtistDocumentMapper,
        )
        from app.services.synchronization_service import (
            SynchronizationService,
        )

        importer, repository, database = world()

        await importer.ensure_for_entries(
            [entry("Marina Sena", "3090429")]
        )

        stored = await database.artists.find_one({})

        service = SynchronizationService(
            artist_repository=repository,
            event_import_service=None,
        )

        assert service.needs_sync(
            ArtistDocumentMapper.to_domain(stored)
        )


class TestWholeFestivals:
    @pytest.mark.asyncio
    async def test_one_pass_covers_every_date_of_the_series(self):
        """A festival's bill is read as one set, not once per edition.

        Treating each date separately would ask the same question once per night,
        and for a festival with thirty artists on three dates that is ninety
        questions where four would do.
        """

        importer, _, database = world()

        for day in (1, 2, 3):
            await database.events.insert_one(
                {
                    "title": f"Villa Sound 2026 - Day {day}",
                    "event_type": "FestivalInstance",
                    "starts_at": None,
                    "festival": {
                        "series_id": "44001",
                        "name": "Villa Sound",
                    },
                    "lineup": [
                        entry("Marina Sena", "3090429"),
                        entry("Tim Bernardes", "2668421"),
                    ],
                }
            )

        report = await importer.ensure_for_festival("44001")

        # Two distinct artists, even though six entries named them.
        assert report.created == 2
        assert await database.artists.count_documents({}) == 2

    @pytest.mark.asyncio
    async def test_a_genre_from_the_lineup_is_stored(self):
        """The source stated it, so it is kept.

        This is what eventually backs the events genre filter, which is built from
        artist metadata and nowhere else.
        """

        importer, _, database = world()

        await importer.ensure_for_entries(
            [
                entry(
                    "Marina Sena",
                    "3090429",
                    genres=["MPB", "Pop"],
                )
            ]
        )

        stored = await database.artists.find_one({})

        assert stored["genres"] == ["MPB", "Pop"]


class TestEveryCreatedArtistIsReachable:
    """A created artist has to have an address.

    `generate_slug` reduces a name to ASCII, so a name written in a non-Latin
    script slugifies to nothing. Songkick's festival bills are full of them -
    Japanese, Chinese, Korean, Cyrillic - and the first version of this feature
    created 23 artists whose slug was a bare counter: `-2`, `-3`, `-4`.

    Those artists exist, resolve by Songkick id, and have no page anybody can
    open. A lineup of them renders as a grid of dead links.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "name",
        [
            "レミオロメン",
            "斉藤和義",
            "土屋アンナ",
        ],
    )
    async def test_a_name_that_slugifies_to_nothing_still_gets_an_address(
        self, name
    ):
        """The real case: no ASCII characters at all in the name.

        These are the names that produced 23 artists with the slug `-2`. The
        Songkick id is the identity this catalogue is keyed on, so the slug is
        built from it - which works identically for every script and can never
        collide with another artist's.
        """

        assert generate_slug(name) == ""

        importer, _, database = world()

        await importer.ensure_for_entries([entry(name, "12345")])

        stored = await database.artists.find_one({})

        slug = stored["slug"]

        assert slug
        # A leading hyphen is the unique-slug loop's way of saying "the base
        # slugified to nothing" - the shape that was never an address.
        assert not slug.startswith("-")
        assert "12345" in slug

    @pytest.mark.asyncio
    async def test_a_name_with_some_ascii_keeps_the_slug_it_already_has(self):
        """`乃木坂46` slugifies to `46`, and `46` is a perfectly good address.

        Worth stating because the tempting shortcut - treat a digits-only slug
        as broken - would send an act whose name happens to end in digits to a
        mangled fallback instead of the obvious address it already has.
        """

        importer, _, database = world()

        await importer.ensure_for_entries([entry("乃木坂46", "999")])

        stored = await database.artists.find_one({})

        assert stored["slug"] == "46"

    @pytest.mark.asyncio
    async def test_an_artist_named_after_a_number_keeps_that_address(self):
        """A name that slugs to digits is still a real, addressable slug.

        The tempting shortcut is to treat "the slug is all digits" as
        unaddressable, which sends a band genuinely called `1234` to a mangled
        fallback instead of the obvious address it already has.
        """

        importer, _, database = world()

        await importer.ensure_for_entries([entry("1234", "999")])

        stored = await database.artists.find_one({})

        assert stored["slug"] == "1234"

    @pytest.mark.asyncio
    async def test_two_non_latin_acts_do_not_collide(self):
        """The fallback has to be unique per artist, not per collision."""

        importer, _, database = world()

        await importer.ensure_for_entries(
            [
                entry("レミオロメン", "111"),
                entry("土屋アンナ", "222"),
            ]
        )

        slugs = [
            document["slug"]
            for document in await database.artists.find(
                {}
            ).to_list(length=None)
        ]

        assert len(slugs) == 2
        assert len(set(slugs)) == 2

        assert all(slug and not slug.startswith("-") for slug in slugs)


class TestAnIdentityMustBeProvedBeforeAnArtistExists:
    """A link on a poster is not an identity, and a number is not proof.

    Creating an `Artist` is permanent and linkable from every festival that
    announced the name. A record written from an id nobody checked claims an
    identity this system never established, and nothing in the stored document
    would say so. So the id is checked against the artist's own page first, and a
    refusal means no record at all.
    """

    @pytest.mark.asyncio
    async def test_a_verified_identity_creates_the_artist(self):
        importer, _, database = world(
            verifier=StubVerifier(accepted={"2668421"})
        )

        report = await importer.ensure_for_entries(
            [entry("Tim Bernardes", "2668421")]
        )

        assert report.created == 1
        assert report.rejected == 0
        assert await database.artists.count_documents({}) == 1

    @pytest.mark.asyncio
    async def test_an_identity_songkick_does_not_have_creates_nothing(self):
        """A 404 is not "not in the search results".

        The two look alike and mean opposite things, and conflating them is how
        an invented identity gets written.
        """

        importer, _, database = world(
            verifier=StubVerifier(accepted={"2668421"})
        )

        report = await importer.ensure_for_entries(
            [entry("A Band That Does Not Exist", "9999999")]
        )

        assert report.created == 0
        assert report.rejected == 1
        assert await database.artists.count_documents({}) == 0

        assert report.rejections[0]["reason"] == "no_artist_page"

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_refused_without_a_record(self):
        importer, _, database = world()

        report = await importer.ensure_for_entries(
            [entry("Someone", "not-an-id-at-all")]
        )

        assert report.created == 0
        assert await database.artists.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_a_spotify_id_is_refused(self):
        """The two id spaces are unrelated; borrowing across them is silent.

        A Spotify artist id is 22 base62 characters and a Songkick artist id is
        numeric. Reading one as the other addresses a different artist entirely,
        so it is refused before a request is made.
        """

        importer, _, database = world()

        report = await importer.ensure_for_entries(
            [entry("Someone", "0cHZbUIBIOaZJX0zvNb8Nj")]
        )

        assert report.created == 0
        assert report.rejected == 1
        assert await database.artists.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_the_canonical_name_from_the_page_wins(self):
        """The artist's own page is the authority on who they are.

        A poster's spelling is a rendering of a name; the page is the name. Storing
        the poster's version would mean two records for one act whenever the two
        disagree.
        """

        importer, _, database = world(
            verifier=StubVerifier(
                accepted={"2668421"},
                names={"2668421": "Tim Bernardes (official)"},
            )
        )

        await importer.ensure_for_entries(
            [entry("Tim Bernardes", "2668421")]
        )

        stored = await database.artists.find_one({})

        assert stored["name"] == "Tim Bernardes (official)"

    @pytest.mark.asyncio
    async def test_an_already_imported_artist_is_not_re_verified(self):
        """A record that exists needs no proof, and no request.

        Validation is for deciding whether to create. Re-checking every artist on
        every import would mean one page fetch per artist per sync for no
        decision at all.
        """

        verifier = StubVerifier(accepted={"2668421"})

        importer, _, _ = world(
            artists=[
                {
                    "name": "Tim Bernardes",
                    "slug": "tim-bernardes",
                    "normalized_name": "tim bernardes",
                    "external_ids": {"songkick": "Artist2668421"},
                }
            ],
            verifier=verifier,
        )

        report = await importer.ensure_for_entries(
            [entry("Tim Bernardes", "2668421")]
        )

        assert report.resolved_existing == 1
        assert verifier.calls == []

    @pytest.mark.asyncio
    async def test_validation_still_never_fetches_a_gigography(self):
        """Creating an artist and importing one remain different jobs.

        The one request the importer may make is the single identity check. It
        must never become a gigography fetch, which would rebuild the old bug
        where looking at a festival page cost one scrape per name on the bill.
        """

        import inspect

        from app.services.songkick_artist_verifier import (
            SongkickArtistVerifier,
        )

        parameters = inspect.signature(
            SongkickArtistVerifier.__init__
        ).parameters

        # No event import, no synchronization, no gigography.
        for name in (
            "event_import_service",
            "synchronization_service",
            "event_repository",
            "venue_repository",
        ):
            assert name not in parameters

        # And it exposes exactly the one read it is allowed to make.
        reads = {
            name
            for name in dir(SongkickArtistVerifier)
            if not name.startswith("_")
            and callable(getattr(SongkickArtistVerifier, name))
        }

        assert reads == {"verify"}


class TestFailureIsContained:
    @pytest.mark.asyncio
    async def test_one_bad_entry_does_not_abandon_the_bill(self):
        """A festival announces thirty names; one raising must not cost the rest."""

        importer, repository, database = world()

        original = repository.ensure_by_songkick_id

        async def flaky(songkick_id, name, **kwargs):
            if name == "Broken":
                raise RuntimeError("nope")

            return await original(songkick_id, name, **kwargs)

        repository.ensure_by_songkick_id = flaky

        report = await importer.ensure_for_entries(
            [
                entry("Marina Sena", "3090429"),
                entry("Broken", "1"),
                entry("Tim Bernardes", "2668421"),
            ]
        )

        assert report.created == 2
        assert report.failed == 1
        assert await database.artists.count_documents({}) == 2
