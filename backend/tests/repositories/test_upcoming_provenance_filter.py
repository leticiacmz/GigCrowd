"""Upcoming listings must not present a fixture as an announced show.

The rules being enforced are in `event_provenance`; these tests check they are
actually applied to the queries the product reads, rather than only being
available for something to call someday.

Nothing here names an artist. A fixture stays a fixture whatever it is called.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.domain.event_provenance import (
    PROVENANCE_FIXTURE,
    is_trustworthy_upcoming,
    untrusted_upcoming_clause,
)
from app.repositories.event_repository import EventRepository
from tests.support.fake_mongo import matches as clause_matches

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def event(
    slug: str,
    *,
    songkick_id: str,
    in_days: int,
    provenance: str | None = None,
    url: str | None = "https://www.songkick.com/concerts/1-a-show",
    title: str = "A Show",
) -> dict:
    source: dict = {"provider": "songkick"}

    if provenance:
        source["provenance"] = provenance

    if url is not None:
        source["url"] = url

    return {
        "_id": ObjectId(),
        "title": title,
        "event_type": "Concert",
        "artist_slug": slug,
        "artist_slugs": [slug],
        "starts_at": NOW + timedelta(days=in_days),
        "ends_at": None,
        "external_ids": {"songkick": songkick_id},
        "source": source,
        "date_status": "source",
    }


class TestTheClauseMatchesTheRule:
    """The database clause and the readable rule must agree, case by case.

    Two implementations of one rule drift apart. These pair them so a change to
    either one that the other does not follow fails here rather than in the
    product.
    """

    def assert_agrees(
        self,
        row: dict,
        *,
        untrusted: bool,
        verdict: str,
    ) -> None:
        trustworthy, reason = is_trustworthy_upcoming(row, now=NOW)

        assert trustworthy is (not untrusted), reason
        assert reason == verdict

        assert clause_matches(row, untrusted_upcoming_clause()) is untrusted

    def test_a_recorded_fixture_is_disqualified(self):
        self.assert_agrees(
            event(
                "someone",
                songkick_id="40352877",
                in_days=30,
                provenance=PROVENANCE_FIXTURE,
            ),
            untrusted=True,
            verdict="development fixture, not a provider event",
        )

    def test_a_fixture_id_without_provenance_is_still_disqualified(self):
        # Rows written before provenance was recorded carry no marker, and they
        # are exactly the ones that must not slip through.
        self.assert_agrees(
            event("someone", songkick_id="9900109", in_days=30),
            untrusted=True,
            verdict="development fixture, not a provider event",
        )

    def test_a_real_songkick_event_is_qualified(self):
        self.assert_agrees(
            event("someone", songkick_id="40352877", in_days=30),
            untrusted=False,
            verdict="verified_songkick_provenance",
        )

    def test_a_claimed_provider_with_no_url_is_disqualified(self):
        self.assert_agrees(
            event("someone", songkick_id="40352877", in_days=30, url=None),
            untrusted=True,
            verdict="claims a provider but has no source to verify",
        )

    def test_a_url_on_another_host_is_not_evidence(self):
        self.assert_agrees(
            event(
                "someone",
                songkick_id="40352877",
                in_days=30,
                url="https://example.com/show/1",
            ),
            untrusted=True,
            verdict="claims a provider but has no source to verify",
        )

    def test_the_id_pattern_is_anchored(self):
        # An unanchored pattern would disqualify a real id that merely contained
        # the fixture digits.
        self.assert_agrees(
            event("someone", songkick_id="1129900109", in_days=30),
            untrusted=False,
            verdict="verified_songkick_provenance",
        )

    def test_a_past_fixture_is_trustworthy(self):
        # History makes no claim about the future, so the fixture stays visible
        # where the development environment and the test accounts expect it.
        #
        # The clause itself says nothing about dates: the query applies it to
        # rows the date filter has already selected, so this verdict is the
        # function's alone to give.
        trustworthy, reason = is_trustworthy_upcoming(
            event(
                "someone",
                songkick_id="9900103",
                in_days=-30,
                provenance=PROVENANCE_FIXTURE,
            ),
            now=NOW,
        )

        assert trustworthy is True
        assert reason == "not_upcoming"

    def test_the_clause_is_a_single_readable_operator(self):
        clause = untrusted_upcoming_clause()

        assert list(clause) == ["$or"]


class TestWhatUpcomingListingsReturn:
    """The queries themselves, against a database holding all four cases."""

    @pytest.mark.asyncio
    async def test_a_real_future_show_is_listed(self, seeded):
        repository, _ = seeded

        rows = await repository.get_upcoming_by_artist_slug(
            "marina-sena"
        )

        assert [row.title for row in rows] == ["Real Future Show"]

    @pytest.mark.asyncio
    async def test_a_fixture_future_show_is_not_listed(self, seeded):
        repository, _ = seeded

        titles = [
            row.title
            for row in await repository.get_upcoming_by_artist_slug(
                "gal-costa"
            )
        ]

        assert titles == []

    @pytest.mark.asyncio
    async def test_an_unverifiable_future_show_is_not_listed(self, seeded):
        repository, _ = seeded

        titles = [
            row.title
            for row in await repository.get_upcoming_by_artist_slug(
                "tim-bernardes"
            )
        ]

        assert titles == []

    @pytest.mark.asyncio
    async def test_history_is_untouched(self, seeded):
        # A finished fixture is history and makes no claim about the future, so
        # it stays where the development environment and the test accounts
        # expect to find it.
        repository, _ = seeded

        rows = await repository.get_all_by_artist_slug("gal-costa")

        titles = {row.title for row in rows}

        assert "Past Fixture Show" in titles

    @pytest.mark.asyncio
    async def test_a_mixed_listing_drops_the_future_fixture(
        self,
        seeded,
    ):
        # The artist Events tab lists history and future together, year by year.
        # A fixture in next year's group looks exactly like an announcement
        # there, which is the same mistake as a fixture in an upcoming list.
        repository, _ = seeded

        rows = await repository.get_all_by_artist_slug(
            "arctic-monkeys"
        )

        titles = {row.title for row in rows}

        assert "Next Year Fixture" not in titles
        assert "Real Future Show" in titles

    @pytest.mark.asyncio
    async def test_a_mixed_listing_keeps_the_past_fixture(
        self,
        seeded,
    ):
        repository, _ = seeded

        rows = await repository.get_all_by_artist_slug(
            "gal-costa"
        )

        titles = {row.title for row in rows}

        # History is what the development environment and the manual test
        # accounts are built on, so it has to survive the filter.
        assert "Past Fixture Show" in titles
        assert "Fixture Future Show" not in titles

    @pytest.mark.asyncio
    async def test_a_mixed_listing_keeps_past_and_future_real_shows(
        self,
        seeded,
    ):
        repository, _ = seeded

        rows = await repository.get_all_by_artist_slug(
            "marina-sena"
        )

        titles = {row.title for row in rows}

        assert titles == {
            "Real Future Show",
            "Past Real Show",
        }

    @pytest.mark.asyncio
    async def test_a_past_real_show_is_untouched(self, seeded):
        repository, _ = seeded

        rows = await repository.get_all_by_artist_slug("marina-sena")

        titles = {row.title for row in rows}

        assert "Past Real Show" in titles

    @pytest.mark.asyncio
    async def test_the_upcoming_count_agrees_with_the_upcoming_list(
        self,
        seeded,
    ):
        repository, _ = seeded

        for slug in ("marina-sena", "gal-costa", "tim-bernardes"):

            listed = await repository.get_upcoming_by_artist_slug(slug)

            counted = await repository.count_upcoming_by_artist_slug(
                slug
            )

            assert counted == len(listed), slug

    @pytest.mark.asyncio
    async def test_a_fixture_show_dated_next_year_is_not_a_real_gig(
        self,
        seeded,
    ):
        repository, database = seeded
        # The specific shape that started this: a plausible future date on an
        # artist who is not touring, backed by a URL that resolves to nothing.
        rows = await repository.get_all_by_artist_slug("arctic-monkeys")

        titles = {row.title for row in rows}

        # The document is still in the database - this is a filter, not a
        # deletion - and it is absent from both listings.
        stored = await database["events"].find(
            {"title": "Next Year Fixture"}
        ).to_list(length=1)

        assert stored

        assert "Next Year Fixture" not in titles

        upcoming = await repository.get_upcoming_by_artist_slug(
            "arctic-monkeys"
        )

        upcoming_titles = {row.title for row in upcoming}

        assert "Next Year Fixture" not in upcoming_titles
        assert "Real Future Show" in upcoming_titles


@pytest.fixture
def seeded():
    """A database holding one of each case the rule has to tell apart."""

    from tests.support.fake_mongo import FakeDatabase

    documents = [
        # A genuine import, still to come.
        event(
            "marina-sena",
            songkick_id="40352877",
            in_days=30,
            title="Real Future Show",
        ),
        # A fixture, dated next year, on an artist who also has a real show.
        # Both together are the point: filtering has to remove the fixture and
        # leave the genuine one, so a pass here cannot come from emptying the
        # listing altogether.
        event(
            "arctic-monkeys",
            songkick_id="9900108",
            in_days=400,
            title="Next Year Fixture",
        ),
        event(
            "arctic-monkeys",
            songkick_id="40352999",
            in_days=90,
            title="Real Future Show",
        ),
        # A fixture recorded as such.
        event(
            "gal-costa",
            songkick_id="40352877",
            in_days=43,
            provenance=PROVENANCE_FIXTURE,
            title="Fixture Future Show",
        ),
        # A provider claim with nothing to check.
        event(
            "tim-bernardes",
            songkick_id="40352878",
            in_days=50,
            url=None,
            title="Unverifiable Show",
        ),
        # History, which must not be touched.
        event(
            "marina-sena",
            songkick_id="40352879",
            in_days=-400,
            title="Past Real Show",
        ),
        event(
            "gal-costa",
            songkick_id="9900103",
            in_days=-30,
            title="Past Fixture Show",
        ),
    ]

    database = FakeDatabase({"events": documents})

    return EventRepository(database), database
