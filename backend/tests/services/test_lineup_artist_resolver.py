"""Deciding which lineup entries may be linked to a GigCrowd artist.

A festival names far more artists than GigCrowd has imported, so the majority of
lineup entries have nothing to link to. The tests below pin down that the
unlinked ones stay unlinked: that resolution is driven by the Songkick id and
never by a name, that an id two artists both claim links to nothing rather than
to one of them, and that resolving is read-only so it cannot damage the stored
guarantee that every entry carries a real Songkick id.
"""
from __future__ import annotations

import pytest

from app.services.lineup_artist_resolver import (
    LineupArtistResolver,
    external_id_for,
    stored_id_of,
)
from tests.support.fake_mongo import FakeDatabase


class Repository:
    """The slice of the artist repository the resolver uses."""

    def __init__(self, db):
        self.collection = db["artists"]


def artist(name: str, slug: str, songkick_id: str | None = None) -> dict:
    document = {
        "_id": slug,
        "name": name,
        "slug": slug,
        "external_ids": {},
    }

    if songkick_id:
        document["external_ids"]["songkick"] = songkick_id

    return document


def build(artists: list[dict], entries: list[dict] | None = None):
    """A resolver over a fixed catalogue and a fixed set of lineup entries."""

    database = FakeDatabase({
        "artists": artists,
        "events": [
            {"_id": slug, "lineup": lineup}
            for slug, lineup in (entries or {}).items()
        ],
    })

    resolver = LineupArtistResolver(Repository(database))

    class WithEntries(LineupArtistResolver):
        """The resolver with the aggregate replaced by a fixed list.

        The shared test double implements `$match` + `$group` only, so the
        `$unwind` that flattens lineups is stood in for here. Everything the
        resolver actually decides is still exercised.
        """

        async def _lineup_entries(self, db):
            return list(self._fixed_entries)

    fixed = WithEntries(Repository(database))
    fixed._fixed_entries = []  # type: ignore[attr-defined]

    return resolver, fixed, database


class TestIdentifierForms:
    """A lineup id and a stored id are the same number in two spellings."""

    def test_a_bare_id_is_given_the_stored_prefix(self):
        assert external_id_for("976211") == "Artist976211"

    def test_an_already_stored_id_is_left_alone(self):
        # A caller holding either form must not have to know which it has.
        assert external_id_for("Artist976211") == "Artist976211"

    def test_surrounding_whitespace_is_ignored(self):
        assert external_id_for("  976211 ") == "Artist976211"

    def test_the_stored_form_is_reduced_to_the_lineup_form(self):
        assert stored_id_of("Artist976211") == "976211"

    def test_a_lineup_form_passes_through_reduction(self):
        assert stored_id_of("976211") == "976211"

    def test_an_empty_id_stays_empty(self):
        assert external_id_for("") == ""
        assert external_id_for("   ") == ""


class TestResolving:
    """The id is the only thing that decides a link."""

    @pytest.mark.asyncio
    async def test_a_matching_id_resolves_to_the_imported_artist(self):
        resolver, _, _ = build([
            artist("Demi Lovato", "demi-lovato", "Artist976211"),
        ])

        resolved = await resolver.resolve(["976211"])

        assert resolved == {"976211": "demi-lovato"}

    @pytest.mark.asyncio
    async def test_an_artist_with_no_songkick_id_never_resolves(self):
        # The catalogue is mostly Spotify-only artists. They must not be linked
        # by name, or a festival bill would attach itself to the wrong band.
        resolver, _, _ = build([
            artist("Arctic Monkeys", "arctic-monkeys"),
        ])

        assert await resolver.resolve(["520117"]) == {}

    @pytest.mark.asyncio
    async def test_an_unimported_artist_resolves_to_nothing(self):
        resolver, _, _ = build([])

        assert await resolver.resolve(["976211"]) == {}

    @pytest.mark.asyncio
    async def test_resolution_never_falls_back_to_the_name(self):
        """Two artists can share a name; a name is not an identity."""

        resolver, _, _ = build([
            artist("The Killers", "the-killers-a", "Artist111"),
            artist("The Killers", "the-killers-b", "Artist222"),
        ])

        # Both ids resolve, because the ids are what matched. Nothing is
        # resolved by name, and neither page borrows the other's slug.
        resolved = await resolver.resolve(["111", "222"])

        assert resolved == {
            "111": "the-killers-a",
            "222": "the-killers-b",
        }

    @pytest.mark.asyncio
    async def test_an_entry_with_no_id_resolves_to_nothing(self):
        resolver, _, _ = build([
            artist("Mystery", "mystery", "Artist1"),
        ])

        assert await resolver.resolve([""]) == {}
        assert await resolver.resolve([None]) == {}

    @pytest.mark.asyncio
    async def test_a_whole_lineup_resolves_in_one_query(self):
        database = FakeDatabase({
            "artists": [
                artist("A", "a", "Artist1"),
                artist("B", "b", "Artist2"),
                artist("C", "c", "Artist3"),
            ]
        })

        reads: list[int] = []

        collection = database["artists"]
        original = collection.find

        def counted(query, projection=None):
            reads.append(1)
            return original(query, projection)

        collection.find = counted

        resolver = LineupArtistResolver(
            type("R", (), {"collection": collection})()
        )

        resolved = await resolver.resolve(["1", "2", "3", "4"])

        # A thirty-act lineup must not cost thirty queries.
        assert len(reads) == 1
        assert resolved == {"1": "a", "2": "b", "3": "c"}

    @pytest.mark.asyncio
    async def test_resolving_writes_nothing(self):
        database = FakeDatabase({
            "artists": [artist("Demi Lovato", "demi-lovato", "Artist976211")]
        })

        resolver = LineupArtistResolver(
            type("R", (), {"collection": database["artists"]})()
        )

        before = [dict(d) for d in database["artists"].documents]

        await resolver.resolve(["976211"])

        assert database["artists"].documents == before


class TestAmbiguity:
    """Two artists claiming one Songkick id links to neither.

    This is a duplicated import, and deciding which of the two is the real one is
    a judgement about identity, not something a resolver may make on its own.
    Picking either would present a coin flip to a reader as a fact.
    """

    @pytest.mark.asyncio
    async def test_a_contested_id_resolves_to_nothing(self):
        resolver, _, _ = build([
            artist("Lorde", "lorde", "Artist6715369"),
            artist("Lorde", "lorde-2", "Artist6715369"),
        ])

        assert await resolver.resolve(["6715369"]) == {}

    @pytest.mark.asyncio
    async def test_a_contested_id_does_not_take_its_neighbour_along(self):
        resolver, _, _ = build([
            artist("Contested", "contested", "Artist111"),
            artist("Contested", "contested-2", "Artist111"),
            artist("Clean", "clean", "Artist222"),
        ])

        resolved = await resolver.resolve(["111", "222"])

        assert resolved == {"222": "clean"}

    @pytest.mark.asyncio
    async def test_two_artists_with_one_slug_are_not_ambiguous(self):
        # Same slug twice is the same page described twice, not two identities.
        resolver, _, _ = build([
            artist("Clean", "clean", "Artist222"),
            artist("Clean", "clean", "Artist222"),
        ])

        assert await resolver.resolve(["222"]) == {"222": "clean"}

    @pytest.mark.asyncio
    async def test_an_artist_with_no_slug_is_not_counted_as_a_claim(self):
        # An imported artist with no page cannot be linked to and must not
        # poison a perfectly good one that holds the same id.
        resolver, _, _ = build([
            {"_id": "x", "name": "Nameless", "external_ids":
                {"songkick": "Artist222"}},
            artist("Real", "real", "Artist222"),
        ])

        assert await resolver.resolve(["222"]) == {"222": "real"}


class TestReporting:
    """The measurement half: what can be linked, and what cannot."""

    @pytest.mark.asyncio
    async def test_entries_are_split_into_resolved_and_unresolved(self):
        _, resolver, _ = build(
            [
                artist("Demi Lovato", "demi-lovato", "Artist976211"),
                artist("Lorde", "lorde", "Artist6715369"),
            ],
        )

        resolver._fixed_entries = [
            {"name": "Demi Lovato", "songkick_id": "976211"},
            {"name": "Demi Lovato", "songkick_id": "976211"},
            {"name": "Lorde", "songkick_id": "6715369"},
            {"name": "Nobody", "songkick_id": "404"},
        ]

        report = await resolver.report(None)

        assert report.entries == 4
        assert report.entries_with_songkick_id == 4
        assert report.entries_without_songkick_id == 0
        assert report.resolved_entries == 3
        assert report.unresolved_entries == 1
        assert report.resolved_ids == 2
        assert report.unresolved_ids == 1

    @pytest.mark.asyncio
    async def test_the_totals_add_up_to_the_number_of_entries(self):
        """A report whose parts do not sum to the whole is not a measurement."""

        _, resolver, _ = build(
            [
                artist("Demi Lovato", "demi-lovato", "Artist976211"),
                artist("Twin", "twin-a", "Artist555"),
                artist("Twin", "twin-b", "Artist555"),
            ],
        )

        resolver._fixed_entries = [
            {"name": "Demi Lovato", "songkick_id": "976211"},
            {"name": "Demi Lovato", "songkick_id": "976211"},
            {"name": "Demi Lovato", "songkick_id": "976211"},
            {"name": "Twin", "songkick_id": "555"},
            {"name": "Nobody", "songkick_id": "404"},
            {"name": "Nameless", "songkick_id": ""},
        ]

        report = await resolver.report(None)

        assert report.resolved_entries == 3
        assert report.ambiguous_entries == 1
        assert report.unresolved_entries == 1

        assert (
            report.resolved_entries
            + report.ambiguous_entries
            + report.unresolved_entries
            + report.entries_without_songkick_id
        ) == report.entries

    @pytest.mark.asyncio
    async def test_an_entry_with_no_id_is_reported_separately(self):
        _, resolver, _ = build([])

        resolver._fixed_entries = [
            {"name": "Anonymous", "songkick_id": None},
            {"name": "Known", "songkick_id": "404"},
        ]

        report = await resolver.report(None)

        assert report.entries_without_songkick_id == 1
        assert report.unresolved_entries == 1
        assert report.distinct_songkick_ids == 1

    @pytest.mark.asyncio
    async def test_an_ambiguous_id_is_reported_with_both_claimants(self):
        _, resolver, _ = build([
            artist("Twin", "twin-a", "Artist555"),
            artist("Twin", "twin-b", "Artist555"),
        ])

        resolver._fixed_entries = [
            {"name": "Twin", "songkick_id": "555"},
        ]

        report = await resolver.report(None)

        assert report.ambiguous_ids == 1
        assert report.ambiguous_entries == 1

        detail = report.ambiguous_detail[0]

        assert detail["songkick_id"] == "555"
        assert sorted(detail["slugs"]) == ["twin-a", "twin-b"]

    @pytest.mark.asyncio
    async def test_reporting_counts_the_catalogue_it_was_measured_against(self):
        _, resolver, _ = build([
            artist("A", "a", "Artist1"),
            artist("B", "b"),
        ])

        resolver._fixed_entries = []

        report = await resolver.report(None)

        assert report.imported_artists == 2
        assert report.artists_with_songkick_id == 1

    @pytest.mark.asyncio
    async def test_reporting_is_read_only(self):
        database = FakeDatabase({
            "artists": [artist("Demi Lovato", "demi-lovato", "Artist976211")],
            "events": [],
        })

        _, resolver, _ = build(
            [artist("Demi Lovato", "demi-lovato", "Artist976211")],
        )

        resolver._fixed_entries = [
            {"name": "Demi Lovato", "songkick_id": "976211"},
        ]

        before = [dict(d) for d in database["artists"].documents]

        await resolver.report(database)

        assert database["artists"].documents == before

    @pytest.mark.asyncio
    async def test_an_empty_lineup_reports_zeroes_rather_than_failing(self):
        _, resolver, _ = build([artist("A", "a", "Artist1")])

        resolver._fixed_entries = []

        report = await resolver.report(None)

        assert report.entries == 0
        assert report.resolved_ids == 0
        assert report.unresolved_ids == 0

        assert "entries=0" in report.summary()


class TestTheStoredGuaranteeIsNotDisturbed:
    """Enrichment and resolution must not cost the lineup its Songkick ids."""

    def test_the_pipeline_projects_the_id_rather_than_deriving_one(self):
        import inspect

        from app.services.lineup_artist_resolver import (
            LineupArtistResolver as Resolver,
        )

        source = inspect.getsource(Resolver._lineup_entries)

        # The id is read from the stored entry. It is never computed from the
        # name, and the name is never used as a fallback identifier.
        assert "$lineup.songkick_id" in source
        assert "$lineup.songkickId" in source
        assert "casefold" not in source
        assert "normalized_name" not in source
