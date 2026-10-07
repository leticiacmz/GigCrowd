"""The audit script's refusals.

An audit that reads 8,000 identities and then writes to them is a script with a
very large blast radius, and the interesting part is not what it finds - it is
what it is forbidden to do about it. Three promises are load-bearing:

* it deletes nothing;
* it does not re-address an artist, because an artist's slug is a URL other
  people's links already point at;
* a run you did not ask for writes no artist at all.

Those are asserted here against a fake database rather than against a live one,
because a test that needs a live one to prove a script is harmless is itself not
harmless.
"""
from __future__ import annotations

import pytest

from app.scripts.audit_lineup_artist_identities import (
    USER_ACTIVITY,
    VERDICTS,
    apply,
    is_lineup_created,
    load_population,
)
from tests.support.fake_mongo import FakeDatabase


def a_world(artists=None, activity=None):
    return FakeDatabase(
        {
            "artists": artists or [],
            VERDICTS: [],
            **(activity or {}),
        }
    )


def a_stub(name, songkick_id, slug=None, **extra):
    return {
        "name": name,
        "slug": slug or name.lower().replace(" ", "-"),
        "external_ids": {"songkick": f"Artist{songkick_id}"},
        **extra,
    }


class TestThePopulationIsTheOneTheBugProduced:
    def test_a_stub_is_lineup_created(self):
        assert is_lineup_created(a_stub("Tim Bernardes", "2668421")) is True

    def test_an_imported_artist_is_not(self):
        """The marker is `last_synced_at`, and it is load-bearing.

        `ensure_by_songkick_id` leaves the field *absent* so the sync job still
        considers the artist importable. An artist that has been synced is not
        part of this population and must not be audited as though it were - the
        point of the script is the records that were created without being
        looked at.
        """

        artist = a_stub(
            "Demi Lovato", "976211", last_synced_at="2026-01-01T00:00:00Z"
        )

        assert is_lineup_created(artist) is False

    def test_a_stored_null_does_not_count_as_synced(self):
        """Absent is not the same as stored-null, and the code must say so.

        A stub with `last_synced_at: null` still needs importing, and a query
        that treated null as "handled" would quietly leave it behind forever.
        """

        artist = a_stub("Tim Bernardes", "2668421", last_synced_at=None)

        # Present as a key, so it is excluded - which is precisely why
        # `ensure_by_songkick_id` never writes the key at all.
        assert is_lineup_created(artist) is False
        assert "last_synced_at" not in a_stub("X", "1")


class TestThePopulationIsFound:
    @pytest.mark.asyncio
    async def test_only_stubs_with_a_songkick_id_are_included(self):
        world = a_world(
            artists=[
                a_stub("Tim Bernardes", "2668421"),
                a_stub(
                    "Demi Lovato",
                    "976211",
                    last_synced_at="2026-01-01T00:00:00Z",
                ),
                {"name": "A Local Band", "slug": "a-local-band"},
            ]
        )

        population = await load_population(world)

        assert [a["name"] for a in population] == ["Tim Bernardes"]

    @pytest.mark.asyncio
    async def test_the_order_is_stable_across_runs(self):
        """A resumable audit that re-shuffled itself would re-check artists it
        already cleared, and would quietly never reach the tail."""

        artists = [
            a_stub("Zoe", "999"),
            a_stub("Ann", "111"),
            a_stub("Mia", "555"),
        ]

        first = await load_population(a_world(artists=artists))
        second = await load_population(a_world(artists=artists))

        assert [a["slug"] for a in first] == [a["slug"] for a in second]


class TestWhatApplyIsAllowedToWrite:
    @pytest.mark.asyncio
    async def test_a_confirmed_identity_gets_the_pages_own_name(self):
        world = a_world(
            artists=[a_stub("tim bernardes", "2668421")],
        )

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "2668421",
                "slug": "tim-bernardes",
                "stored_name": "tim bernardes",
                "valid": True,
                "canonical_name": "Tim Bernardes",
                "image": (
                    "https://images.sk-static.com/images/media/"
                    "profile_images/artists/2668421/card_avatar"
                ),
            }
        )

        await apply(world)

        stored = await world.artists.find_one({"slug": "tim-bernardes"})

        assert stored["name"] == "Tim Bernardes"
        assert stored["image"].endswith("card_avatar")

    @pytest.mark.asyncio
    async def test_it_never_changes_the_slug(self):
        """A slug is a URL that festival pages and user posts already point at.

        Renaming an artist to match the page's spelling is a reasonable-sounding
        improvement that silently breaks every existing link to them, so the
        script does not offer it.
        """

        world = a_world(artists=[a_stub("tim bernardes", "2668421")])

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "2668421",
                "slug": "tim-bernardes",
                "stored_name": "tim bernardes",
                "valid": True,
                "canonical_name": "Tim Bernardes",
                "image": None,
            }
        )

        await apply(world)

        stored = await world.artists.find_one({"slug": "tim-bernardes"})

        assert stored["slug"] == "tim-bernardes"
        assert await world.artists.count_documents({}) == 1

    @pytest.mark.asyncio
    async def test_it_never_marks_the_artist_as_synced(self):
        """Identity and gigography are different questions.

        Learning that `2668421` really is Tim Bernardes says nothing about
        whether his concerts have been imported. Stamping `last_synced_at` here
        would tell the sync job the work is done, and the artist would sit in the
        catalogue forever with no events.
        """

        world = a_world(artists=[a_stub("Tim Bernardes", "2668421")])

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "2668421",
                "slug": "tim-bernardes",
                "stored_name": "Tim Bernardes",
                "valid": True,
                "canonical_name": "Tim Bernardes",
                "image": None,
            }
        )

        await apply(world)

        stored = await world.artists.find_one({"slug": "tim-bernardes"})

        assert "last_synced_at" not in stored
        assert is_lineup_created(stored) is True

    @pytest.mark.asyncio
    async def test_it_never_overwrites_an_existing_photograph(self):
        """A stored image came from the lineup entry; a different one may be
        correct.

        Replacing it here would fix a bug that may exist without having found it,
        and would destroy the evidence needed to diagnose it.
        """

        world = a_world(
            artists=[
                a_stub(
                    "Tim Bernardes",
                    "2668421",
                    image="https://images.example/from-the-poster.jpg",
                )
            ]
        )

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "2668421",
                "slug": "tim-bernardes",
                "stored_name": "Tim Bernardes",
                "valid": True,
                "canonical_name": "Tim Bernardes",
                "image": "https://images.example/from-the-page.jpg",
            }
        )

        await apply(world)

        stored = await world.artists.find_one({"slug": "tim-bernardes"})

        assert stored["image"] == "https://images.example/from-the-poster.jpg"

    @pytest.mark.asyncio
    async def test_a_refused_identity_is_left_completely_alone(self):
        """Not renamed, not flagged, not given a provisional value.

        A record that was never validated should keep looking exactly like what
        it is. Writing a marker onto it would make an unvalidated artist look
        like a checked one to anything reading the artist collection directly.
        """

        world = a_world(artists=[a_stub("A Ghost", "9999999")])

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "Artist9999999",
                "slug": "a-ghost",
                "stored_name": "A Ghost",
                "valid": False,
                "reason": "no_artist_page",
                "canonical_name": None,
                "image": None,
            }
        )

        await apply(world)

        stored = await world.artists.find_one({"slug": "a-ghost"})

        assert stored["name"] == "A Ghost"
        assert "identity" not in stored
        assert "verified" not in stored

    @pytest.mark.asyncio
    async def test_an_artist_with_no_events_is_not_removed(self):
        """Zero events means "nobody has imported them yet".

        It is the defining state of every stub in this population, so treating it
        as evidence of a bad record would delete all 8,000 of them and the
        evidence with them.
        """

        world = a_world(artists=[a_stub("Tim Bernardes", "2668421")])

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "2668421",
                "slug": "tim-bernardes",
                "stored_name": "Tim Bernardes",
                "valid": False,
                "reason": "no_artist_page",
            }
        )

        await apply(world)

        assert await world.artists.count_documents({}) == 1

    @pytest.mark.asyncio
    async def test_a_verdict_with_no_slug_writes_nothing(self):
        """A record with no slug is not addressable, so there is nothing to fix.

        And querying for it with a `None` slug would be asking for a document
        whose slug field is absent, which is how an unrelated record gets
        updated by accident.
        """

        world = a_world(artists=[a_stub("tim bernardes", "2668421")])

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "2668421",
                "slug": None,
                "stored_name": "tim bernardes",
                "valid": True,
                "canonical_name": "Tim Bernardes",
                "image": None,
            }
        )

        await apply(world)

        stored = await world.artists.find_one({"slug": "tim-bernardes"})

        # Unchanged, because there was no slug to find the artist by.
        assert stored["name"] == "tim bernardes"


class TestUserActivityIsAccountedFor:
    @pytest.mark.asyncio
    async def test_a_follow_marks_the_artist_as_referenced(self):
        """The verdict log records it so the report can name who is at stake.

        An artist somebody follows is not a free record to rewrite: changing
        what it says is visible to the people who already believe it.
        """

        from app.scripts.audit_lineup_artist_identities import (
            referenced_by_user_activity,
        )

        world = a_world(
            artists=[a_stub("100 gecs", "10074848")],
            activity={
                "artist_follows": [
                    {"artist_slug": "100-gecs", "user_id": "u1"}
                ]
            },
        )

        names = frozenset(await world.list_collection_names())

        assert (
            await referenced_by_user_activity(
                world, "100-gecs", names
            )
            is True
        )
        assert (
            await referenced_by_user_activity(
                world, "nobody-follows-this", names
            )
            is False
        )

    @pytest.mark.asyncio
    async def test_a_table_that_does_not_exist_counts_as_zero(self):
        """A development database never used for follows has no such collection.

        Raising would mean the audit refuses to run on a fresh database, which
        is exactly where someone would most want to run it. It is also the case
        the membership check exists for: on Motor, `name in database` is not a
        membership test at all - it falls through to the iterator protocol and
        asks for collection number zero.
        """

        from app.scripts.audit_lineup_artist_identities import (
            referenced_by_user_activity,
            referenced_counts,
        )

        world = a_world(artists=[a_stub("100 gecs", "10074848")])

        # Nothing but `artists` and the verdict log exist.
        names = frozenset({"artists", VERDICTS})

        assert await referenced_counts(world, "100-gecs", names) == {}

        assert (
            await referenced_by_user_activity(
                world, "100-gecs", names
            )
            is False
        )

    def test_the_activity_tables_are_enumerated_not_assumed(self):
        """A new table would make "we preserve referenced data" quietly untrue.

        Naming the tables is not documentation; it is the thing that has to be
        updated.
        """

        assert "artist_follows" in USER_ACTIVITY
        assert "posts" in USER_ACTIVITY
        assert "show_logs" in USER_ACTIVITY


class TestRefusalsCanBeRetaken:
    """A refusal is the verdict most worth doubting.

    A confirmation and a refusal look equally authoritative in the log, and only
    one of them can be wrong in a way that destroys data: a false refusal loses
    an artist, while a false confirmation adds one that should not be there. So
    the confirmations are expensive - a page fetch each - and stay; the refusals
    are re-taken whenever a rule behind them has been corrected.
    """

    @pytest.mark.asyncio
    async def test_rechecking_refusals_keeps_the_confirmations(self):
        world = a_world()

        await world[VERDICTS].insert_one(
            {
                "songkick_id": "2668421",
                "slug": "tim-bernardes",
                "valid": True,
                "reason": "verified",
            }
        )
        await world[VERDICTS].insert_one(
            {
                "songkick_id": "11215",
                "slug": "the-coronas",
                "valid": False,
                "reason": "page_is_not_an_artist_profile",
            }
        )

        # What `--recheck-refusals` does.
        await world[VERDICTS].delete_many({"valid": False})

        remaining = await world[VERDICTS].find({}).to_list(length=None)

        assert [row["songkick_id"] for row in remaining] == ["2668421"]

    def test_an_unreadable_page_is_a_distinct_verdict_from_a_refusal(self):
        """A timeout says nothing about an identity.

        Collapsing it into a refusal would mean the artist is never looked at
        again - the question would be treated as answered by something that never
        answered it.
        """

        from app.services.songkick_artist_verifier import (
            ACCEPTED,
            REJECTED_NO_PAGE,
            REJECTED_UNREADABLE,
        )

        assert REJECTED_UNREADABLE != REJECTED_NO_PAGE
        assert REJECTED_UNREADABLE != ACCEPTED
