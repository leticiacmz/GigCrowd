"""A listing pages through windows, and a window is never a bigger read.

The artist page shows the whole year-grouped history, but one response is
bounded at 1000 rows - a bound that has always been a property of the
listing rather than of trust. Paging keeps that bound while making the
rows past it reachable: the same query, the same `starts_at`-descending
ordering, `skip` and `limit` cut over it.

The rules these tests pin:

* the default call - no offset, the 1000-row bound - is the call the
  endpoint has always been, so an existing client sees no change;
* windows are cut from the SAME ordering, so window two continues where
  window one stopped, with no row repeated and none skipped;
* `trusted_listing_filter` runs on every window: an unverifiable future
  row cannot slip in through a later window, and the past stays history.
"""
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.repositories.event_repository import EventRepository
from tests.support.fake_mongo import FakeDatabase

ARTIST = "david-guetta"
SONGKICK_ID = "149066"

NOW = datetime.now(UTC)

TRUSTED_URL = (
    "https://www.songkick.com/festivals/1235-lollapalooza/"
    "id/43456086-lollapalooza-2027"
)


def listing_row(
    *,
    title: str,
    starts_at: datetime,
    trusted: bool,
) -> dict:
    """One row of the artist's listing, in the shape the store holds.

    Past rows need no source at all - history makes no claim about the
    future, and the trust clause lets it stand. A future row carries a
    concrete Songkick address only when the test means it to be
    verifiable; without one it is exactly the row the listing must keep
    out of every window.
    """

    return {
        "_id": ObjectId(),
        "external_ids": {"songkick": SONGKICK_ID},
        "artist_slugs": [ARTIST],
        "artist_slug": ARTIST,
        "venue_slug": "unknown-venue",
        "title": title,
        "starts_at": starts_at,
        "ends_at": starts_at,
        "event_type": "Concert",
        "festival": None,
        "lineup": [],
        "date_status": "source" if trusted else None,
        "location": None,
        "source": (
            {
                "provider": "songkick",
                "external_id": SONGKICK_ID,
                "url": TRUSTED_URL,
            }
            if trusted
            else {"provider": "songkick", "external_id": SONGKICK_ID}
        ),
        "sold_out": False,
        "free": False,
        "ticket_url": None,
        "going_count": 0,
        "maybe_count": 0,
        "went_count": 0,
        "created_at": NOW - timedelta(days=90),
        "updated_at": NOW - timedelta(days=90),
    }


def listing() -> list[dict]:
    """Five history rows, one verifiable future row, one hidden future row.

    Ordered here the way the listing orders them: newest first. The
    untrusted future row is the only one the trust clause rejects, so any
    test that finds it has watched trust leak through a window.
    """

    return [
        listing_row(
            title=f"{ARTIST} show {index}",
            starts_at=NOW - timedelta(days=index),
            trusted=False,
        )
        # `range(1, 6)` gives days 1..5 back from now, so `show 1` is the
        # most recent past row and `show 5` the oldest.
        for index in range(1, 6)
    ] + [
        listing_row(
            title=f"{ARTIST} future announced",
            starts_at=NOW + timedelta(days=30),
            trusted=True,
        ),
        listing_row(
            title=f"{ARTIST} future unverifiable",
            starts_at=NOW + timedelta(days=40),
            trusted=False,
        ),
    ]


def titles(events) -> list[str]:
    return [event.title for event in events]


@pytest.mark.asyncio
async def test_the_default_call_is_still_the_whole_listing():
    """No offset, the listing's own bound - byte-for-byte the old call."""

    database = FakeDatabase({"events": listing()})
    repository = EventRepository(database)

    events = await repository.get_all_by_artist_slug(ARTIST)

    # Six rows: the untrusted future row is gone, every history row and
    # the verifiable future row stand, newest first - and `show 1` is the
    # most recent past row, one day behind now.
    assert titles(events) == [
        f"{ARTIST} future announced",
        *[f"{ARTIST} show {index}" for index in range(1, 6)],
    ]


@pytest.mark.asyncio
async def test_windows_cut_the_same_ordering_without_repeating_a_row():
    """Window two continues where window one stopped."""

    database = FakeDatabase({"events": listing()})
    repository = EventRepository(database)

    first = await repository.get_all_by_artist_slug(
        ARTIST, offset=0, limit=2
    )
    second = await repository.get_all_by_artist_slug(
        ARTIST, offset=2, limit=2
    )
    third = await repository.get_all_by_artist_slug(
        ARTIST, offset=4, limit=2
    )

    whole = titles(first) + titles(second) + titles(third)

    # The windows, laid end to end, are the default listing exactly: no
    # row repeated, none skipped, the same order throughout.
    assert whole == [
        f"{ARTIST} future announced",
        *[f"{ARTIST} show {index}" for index in range(1, 6)],
    ]


@pytest.mark.asyncio
async def test_a_window_past_the_end_is_empty_rather_than_wrapped():
    database = FakeDatabase({"events": listing()})
    repository = EventRepository(database)

    beyond = await repository.get_all_by_artist_slug(
        ARTIST, offset=6, limit=2
    )

    assert beyond == []


@pytest.mark.asyncio
async def test_a_window_asking_for_nothing_still_gets_the_minimum():
    """A limit of zero is clamped, never read as "no limit"."""

    database = FakeDatabase({"events": listing()})
    repository = EventRepository(database)

    one = await repository.get_all_by_artist_slug(
        ARTIST, offset=0, limit=0
    )

    assert len(one) == 1


@pytest.mark.asyncio
async def test_a_later_window_cannot_reach_an_unverifiable_future_row():
    """Trust runs on every window, not once at the front door."""

    database = FakeDatabase({"events": listing()})
    repository = EventRepository(database)

    # Walk every window of the listing and collect what each one shows.
    seen: list[str] = []

    for offset in range(0, 8, 2):
        window = await repository.get_all_by_artist_slug(
            ARTIST, offset=offset, limit=2
        )
        seen.extend(titles(window))

    assert f"{ARTIST} future unverifiable" not in seen

    # And the history it must never cost is all still there.
    for index in range(1, 6):
        assert f"{ARTIST} show {index}" in seen
