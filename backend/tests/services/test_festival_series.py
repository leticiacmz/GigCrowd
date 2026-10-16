"""The festival addressed by its series, with no date in hand.

`GET /festivals/series/{series_id}` names the festival itself, so a reader can
arrive from a search result, a shared link or another page without first
standing on one of its events. Both addresses read the same stored records and
must describe them identically; this file pins the ways arriving by series
alone can go wrong: identity decided by anything but the source's own series
segment, a neighbour's night selected, an address of a longer series id
matched, or an unheld lineup presented as an empty bill.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.festival_service import FestivalService
from tests.services.test_festival_service import (
    CANONICAL,
    DAY_ONE,
    DAY_TWO,
    SERIES,
    Artists,
    Repository,
    build,
    festival_document,
)


UNSTARTED_ID = "507f1f77bcf86cd799439013"

# A date of the same festival whose date could never be read. It is still an
# edition; it simply sorts below the dated ones rather than inheriting a date
# from a sibling night.
UNSTARTED = festival_document(
    UNSTARTED_ID,
    "Primavera Sound Sem Data",
    lineup=[],
)

# Another festival that happens to share Songkick's canonical address of the
# series under test. Its own festival block states a different series, so an
# address match alone must never make it an edition.
NEIGHBOUR_ID = "507f1f77bcf86cd799439099"

NEIGHBOUR = festival_document(
    NEIGHBOUR_ID,
    "Primavera Sound Madrid 2022",
    starts_at=datetime(2022, 9, 10, 20, tzinfo=UTC),
    series_id="99999",
)


class TestArrivingBySeries:
    """The address names the festival, so no record has to be opened first."""

    @pytest.mark.asyncio
    async def test_the_series_resolves_with_no_event_in_hand(self):
        """Identity, dates and lineup are read from the series alone."""

        festival = await build([DAY_ONE, DAY_TWO]).get_series(SERIES)

        assert festival is not None
        assert festival.identity.series_id == SERIES
        assert festival.identity.name == "Primavera Sound São Paulo"
        assert festival.identity.editions_count == 2
        assert festival.lineup[0].name == "Pixies"

    @pytest.mark.asyncio
    async def test_the_default_selection_is_the_chronologically_last_date(
        self,
    ):
        """A festival still running opens on the upcoming date.

        The latest date is the upcoming one while the series is running, and
        the most recent once it has run. An undated edition sits last: giving
        it a date borrowed from a sibling night would claim a night it was
        never stated to happen on.
        """

        festival = await build(
            [DAY_ONE, UNSTARTED, DAY_TWO]
        ).get_series(SERIES)

        assert festival.selected_event_id == str(
            DAY_TWO["_id"]
        )

        assert [
            entry.event.id for entry in festival.editions
        ] == [
            str(DAY_TWO["_id"]),
            str(DAY_ONE["_id"]),
            UNSTARTED_ID,
        ]

    @pytest.mark.asyncio
    async def test_an_edition_can_be_named_explicitly(self):
        """`?edition=` is how a link opens on the date the reader came from."""

        festival = await build([DAY_ONE, DAY_TWO]).get_series(
            SERIES,
            edition_event_id=str(DAY_ONE["_id"]),
        )

        assert festival.selected_event_id == str(DAY_ONE["_id"])
        assert festival.lineup[0].name == "Arctic Monkeys"

    @pytest.mark.asyncio
    async def test_an_edition_of_another_festival_is_never_selected(
        self,
    ):
        """Another festival's night is not borrowed for this one.

        An id that is not an edition of this series falls back to the default
        selection: showing the stranger's lineup under this festival's name
        would state something the data never said.
        """

        festival = await build([DAY_ONE, NEIGHBOUR]).get_series(
            SERIES,
            edition_event_id=NEIGHBOUR_ID,
        )

        assert festival.selected_event_id == str(DAY_ONE["_id"])


class TestWhatTheAddressFallbackMayDo:
    """The fallback fetches candidates; identity still decides."""

    @pytest.mark.asyncio
    async def test_a_date_imported_without_its_block_is_still_listed(
        self,
    ):
        """A date whose festival block was never written states its series in
        its own address.

        That is the same structured-source rule that named the series
        elsewhere, so the date belongs to the series even though no block was
        ever written beside it - and finding it read-time is what the pending
        backfill would later store.
        """

        bare = festival_document(
            "507f1f77bcf86cd799439098",
            "Primavera Sound Dia 3 2022",
            starts_at=datetime(2022, 11, 4, 19, tzinfo=UTC),
        )
        bare.pop("festival")
        bare["source"] = {
            "provider": "songkick",
            "external_id": "40385546",
            "url": CANONICAL,
        }

        festival = await build([bare]).get_series(SERIES)

        assert festival is not None
        assert festival.identity.series_id == SERIES
        assert festival.identity.editions_count == 1
        assert [entry.event.id for entry in festival.editions] == [
            "507f1f77bcf86cd799439098"
        ]

    @pytest.mark.asyncio
    async def test_a_shared_address_fetches_candidates_but_identity_decides(
        self,
    ):
        """The neighbour states another series in its own block.

        Its address is the canonical one of the series under test, so the
        address fallback does fetch it as a candidate - and the identity
        re-check is exactly what drops it again. Without that check two
        festivals that share an address would be read as one.
        """

        festival = await build([DAY_ONE, NEIGHBOUR]).get_series(SERIES)

        assert festival.identity.editions_count == 1
        assert [entry.event.id for entry in festival.editions] == [
            str(DAY_ONE["_id"])
        ]

    @pytest.mark.asyncio
    async def test_an_address_of_a_longer_series_id_is_not_this_series(
        self,
    ):
        """Series 3441108 must not match the address of series 34411088.

        The digits of the id have to end where the address' own slug begins,
        or every shorter series would collect the events of its longer
        neighbours.
        """

        longer = festival_document(
            "507f1f77bcf86cd799439097",
            "Primavera Sound 2023",
            starts_at=datetime(2023, 6, 1, 20, tzinfo=UTC),
            series_id="34411088",
        )
        longer["festival"]["url"] = CANONICAL.replace(
            "/3441108-primavera/",
            "/34411088-primavera/",
        )

        assert await build([longer]).get_series(SERIES) is None

    @pytest.mark.asyncio
    async def test_a_future_fixture_is_not_listed_as_an_edition(self):
        """The provenance rule the event page applies is not bypassed here.

        An edition list reaches into the future, and a development fixture
        dated next year must not sit in it looking exactly like an announced
        festival.
        """

        fixture = festival_document(
            "507f1f77bcf86cd799430170",
            "Primavera Sound 2027",
            starts_at=datetime.now(UTC) + timedelta(days=90),
            source={
                "provider": "songkick",
                "external_id": "40385599",
                "url": CANONICAL,
                "provenance": "fixture",
            },
        )

        festival = await build([DAY_ONE, fixture]).get_series(SERIES)

        assert festival.identity.editions_count == 1
        assert festival.selected_event_id == str(DAY_ONE["_id"])


class TestWhatIsRefused:
    """A malformed or unknown address is a clean 404, not a quiet query."""

    @pytest.mark.asyncio
    async def test_an_unknown_series_reads_as_none(self):
        """No stored record states this series, so the route can 404."""

        assert await build([DAY_ONE]).get_series("123456789") is None

    @pytest.mark.asyncio
    async def test_a_malformed_series_id_never_reaches_the_database(self):
        """A series id is numeric, and anything else is refused by shape.

        The address pattern built for the fallback is only ever a literal
        because of this check, so a malformed id cannot become a query with
        meanings of its own.
        """

        class NoQueries:
            """A repository that fails the test if it is asked anything."""

            def __init__(self):
                self.collection = self

            def find(self, *args, **kwargs):
                raise AssertionError(
                    "the database must not be queried for a malformed id"
                )

        service = FestivalService(
            NoQueries(),
            artist_repository=None,
        )

        assert await service.get_series("not-a-series") is None
        assert await service.get_series("") is None
        assert await service.get_series(None) is None


class TestBothAddressesAgree:
    """The same records, read from either end, describe the same festival."""

    @pytest.mark.asyncio
    async def test_arriving_by_series_and_by_date_agree(self):
        """Only the opened date may differ between the two addresses.

        Identity, the edition set and the count are properties of the stored
        records, so two readers of the same festival cannot be told different
        things about them depending on which door they came through.
        """

        from_a_date = await build([DAY_ONE, DAY_TWO]).get_festival(
            str(DAY_ONE["_id"])
        )

        from_the_series = await build([DAY_ONE, DAY_TWO]).get_series(
            SERIES
        )

        assert (
            from_a_date.identity.series_id
            == from_the_series.identity.series_id
        )
        assert (
            from_a_date.identity.editions_count
            == from_the_series.identity.editions_count
        )
        assert {
            entry.event.id for entry in from_a_date.editions
        } == {
            entry.event.id for entry in from_the_series.editions
        }

        # They differ only in which date the page opens on: the record the
        # reader arrived from, versus the chronologically last one.
        assert from_a_date.selected_event_id == str(DAY_ONE["_id"])
        assert from_the_series.selected_event_id == str(
            DAY_TWO["_id"]
        )


class TestTheLineupStateIsHonest:
    """An unheld lineup is `unknown`, never an empty bill.

    The stored record cannot say whether the source named no one, the read
    failed, or it never ran - so a response reading stored data alone must
    refuse to claim any of the three, and must never present an unheld lineup
    as "the festival announced no one".
    """

    @pytest.mark.asyncio
    async def test_a_held_lineup_is_ok(self):
        """Performers are held for both dates, and the page says so."""

        festival = await build([DAY_ONE, DAY_TWO]).get_series(SERIES)

        states = {
            entry.event.id: entry.lineup_state
            for entry in festival.editions
        }

        assert states[str(DAY_ONE["_id"])] == "ok"
        assert states[str(DAY_TWO["_id"])] == "ok"
        assert festival.lineup_state == "ok"

    @pytest.mark.asyncio
    async def test_an_unheld_lineup_is_unknown_per_date(self):
        """The state belongs to each date, not to the series as a whole.

        A festival's lineup differs per edition, so one night holding its
        performers says nothing about the next: each date answers for itself,
        and the top-level state answers for the date the page shows.
        """

        festival = await build([DAY_ONE, UNSTARTED]).get_series(SERIES)

        states = {
            entry.event.id: entry.lineup_state
            for entry in festival.editions
        }

        assert states[str(DAY_ONE["_id"])] == "ok"
        assert states[UNSTARTED_ID] == "unknown"

        # The default selection is the last dated edition, which holds its
        # lineup, so the page's own state is `ok`.
        assert festival.lineup_state == "ok"

        # But when the reader opens the undated date, the page answers for
        # that date alone.
        undated = await build([DAY_ONE, UNSTARTED]).get_series(
            SERIES,
            edition_event_id=UNSTARTED_ID,
        )

        assert undated.lineup_state == "unknown"
