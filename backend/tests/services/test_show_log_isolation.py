"""Presence belongs to the event that was explicitly confirmed.

Two artists can play the same Lollapalooza day. They are two events that
share a festival block - not one attendance record waiting to be split -
so confirming one must leave the other untouched in every direction the
answer travels: the sibling's stored document, its counts, what a GET
answers about it, what the lists contain, and the event the feed resolves
behind the activity. The tests below hold each of those directions.
"""
from datetime import UTC, datetime

import pytest
from bson import ObjectId

from app.models.activity import ActivityType
from app.models.show_log import (
    AttendanceStatus,
    ShowLogCreate,
    ShowLogUpdate,
)
from app.repositories.event_repository import EventRepository
from app.repositories.show_log_repository import ShowLogRepository
from app.routes.show_logs import _record_show_log_activity
from app.services import activity_service as activity_module
from app.services.activity_service import ActivityService
from app.services.show_log_service import ShowLogService
from tests.support.fake_mongo import FakeDatabase

# One festival day, two headliners: the exact shape of the regression.
FESTIVAL_DAY = datetime(2026, 3, 20, 21, 0, tzinfo=UTC)

ALICE = "user-1"

LOLLA_BLOCK = {
    "series_id": "1235",
    "name": "Lollapalooza 2026",
    "url": "https://www.songkick.com/festivals/1235-lollapalooza",
}


def an_edition_show(
    artist: str,
    title: str,
    document_id: str,
) -> dict:
    """One show on the festival day, with the edition block it belongs to."""

    return {
        "_id": ObjectId(document_id),
        "title": title,
        "artist_slug": artist,
        "artist_slugs": [artist],
        "venue_slug": "hippodromo-pigeon",
        "event_type": "Festival",
        "starts_at": FESTIVAL_DAY,
        "ends_at": FESTIVAL_DAY,
        "going_count": 0,
        "maybe_count": 0,
        "went_count": 0,
        "festival": dict(LOLLA_BLOCK),
    }


@pytest.fixture
def db():
    return FakeDatabase()


@pytest.fixture
def service(db):
    return ShowLogService(
        ShowLogRepository(db),
        EventRepository(db),
    )


async def add_show(db, event: dict) -> str:
    await db.events.insert_one(event)
    return str(event["_id"])


async def snapshot(db, event_id: str) -> dict:
    return await db.events.find_one({"_id": ObjectId(event_id)})


@pytest.mark.asyncio
async def test_confirming_one_artist_leaves_the_sibling_show_untouched(
    db,
    service,
):
    """The sibling's document, counts and GET answer must not move."""

    first = await add_show(
        db,
        an_edition_show(
            "dua-lipa",
            "Dua Lipa @ Lollapalooza 2026",
            "6a1000000000000000000001",
        ),
    )
    sibling = await add_show(
        db,
        an_edition_show(
            "harry-styles",
            "Harry Styles @ Lollapalooza 2026",
            "6a1000000000000000000002",
        ),
    )

    sibling_before = await snapshot(db, sibling)

    await service.create_show_log(
        ALICE,
        ShowLogCreate(
            event_id=first,
            status=AttendanceStatus.WENT,
        ),
    )

    # The confirmed show moved...
    confirmed = await snapshot(db, first)
    assert confirmed["went_count"] == 1

    # ...and the sibling is byte-identical to what it was.
    assert await snapshot(db, sibling) == sibling_before

    # A GET about the sibling answers nothing.
    assert await service.get_show_log(ALICE, sibling) is None

    # Exactly one pair exists, and it names the confirmed event.
    pairs = await db.show_logs.find({}).to_list(length=10)
    assert [(row["user_id"], row["event_id"]) for row in pairs] == [
        (ALICE, first)
    ]

    # The profile lists carry only the confirmed show.
    logs = await service.get_user_show_logs(ALICE)
    assert [log.event_id for log in logs] == [first]

    history = await service.get_user_concert_history(ALICE)
    assert [log.event_id for log in history] == [first]


@pytest.mark.asyncio
async def test_two_confirmations_stay_two_records_and_update_one_at_a_time(
    db,
    service,
):
    """A user may attend both shows; editing one never reaches the other."""

    first = await add_show(
        db,
        an_edition_show(
            "dua-lipa",
            "Dua Lipa @ Lollapalooza 2026",
            "6a1000000000000000000001",
        ),
    )
    second = await add_show(
        db,
        an_edition_show(
            "harry-styles",
            "Harry Styles @ Lollapalooza 2026",
            "6a1000000000000000000002",
        ),
    )

    for event_id in (first, second):
        await service.create_show_log(
            ALICE,
            ShowLogCreate(
                event_id=event_id,
                status=AttendanceStatus.WENT,
            ),
        )

    second_log_before = await db.show_logs.find_one(
        {"event_id": second}
    )
    second_before = await snapshot(db, second)

    # Editing the first show's attendance...
    await service.update_show_log(
        ALICE,
        first,
        ShowLogUpdate(status=AttendanceStatus.MAYBE),
    )

    # ...rewrites only the first show's row and counts.
    assert await db.show_logs.find_one({"event_id": second}) == (
        second_log_before
    )
    assert await snapshot(db, second) == second_before

    first_after_update = await snapshot(db, first)
    assert first_after_update["went_count"] == 0
    assert first_after_update["maybe_count"] == 1

    # Withdrawing the first show's attendance removes exactly one record.
    assert await service.delete_show_log(ALICE, first) is True

    remaining = await db.show_logs.find({}).to_list(length=10)
    assert [row["event_id"] for row in remaining] == [second]

    assert await snapshot(db, second) == second_before
    assert (await snapshot(db, first))["went_count"] == 0
    assert (await snapshot(db, first))["maybe_count"] == 0


@pytest.mark.asyncio
async def test_feed_activity_of_a_show_resolves_only_to_its_own_event(
    db,
    service,
    monkeypatch,
):
    """The timeline behind a confirmation names the confirmed event alone."""

    first = await add_show(
        db,
        an_edition_show(
            "dua-lipa",
            "Dua Lipa @ Lollapalooza 2026",
            "6a1000000000000000000001",
        ),
    )
    sibling = await add_show(
        db,
        an_edition_show(
            "harry-styles",
            "Harry Styles @ Lollapalooza 2026",
            "6a1000000000000000000002",
        ),
    )

    log = await service.create_show_log(
        ALICE,
        ShowLogCreate(
            event_id=first,
            status=AttendanceStatus.WENT,
        ),
    )

    monkeypatch.setattr(
        activity_module,
        "get_database",
        lambda: db,
    )

    await _record_show_log_activity(
        {"_id": ALICE},
        ShowLogCreate(
            event_id=first,
            status=AttendanceStatus.WENT,
        ),
        log,
    )

    activities = await db.activities.find({}).to_list(length=10)
    assert len(activities) == 1
    assert activities[0]["activity_type"] in {
        ActivityType.ATTEND_EVENT.value,
        ActivityType.CREATE_REVIEW.value,
    }
    assert activities[0]["target_type"] == "show_log"
    # The activity points at the log, and the log points at its own event.
    assert activities[0]["target_id"] == str(log.id)

    feed = await ActivityService.get_feed_activities(ALICE)
    resolved = [
        item["target"]["id"]
        for item in feed
        if (item.get("target") or {}).get("kind") == "event"
    ]

    assert resolved, "the confirmation must appear in the feed"
    assert set(resolved) == {first}
    assert sibling not in resolved


@pytest.mark.asyncio
async def test_two_people_confirming_the_same_show_keep_their_own_presence(
    db,
    service,
):
    """Presence is a pair, not a property of the show.

    A second person confirming the same event must not overwrite the first
    person's log or leak into their lists, and each person's GET answers
    their own status. The counters are the event's own answer to "how many",
    so both people are counted there - one per status.
    """

    show = await add_show(
        db,
        an_edition_show(
            "dua-lipa",
            "Dua Lipa @ Lollapalooza 2026",
            "6a1000000000000000000003",
        ),
    )

    await service.create_show_log(
        ALICE,
        ShowLogCreate(
            event_id=show,
            status=AttendanceStatus.WENT,
        ),
    )

    bob = "user-2"

    await service.create_show_log(
        bob,
        ShowLogCreate(
            event_id=show,
            status=AttendanceStatus.MAYBE,
        ),
    )

    # Two rows, one per person, each keeping its own status.
    alice_log = await service.get_show_log(ALICE, show)
    bob_log = await service.get_show_log(bob, show)

    assert alice_log.status == AttendanceStatus.WENT
    assert bob_log.status == AttendanceStatus.MAYBE

    # Neither person's list carries the other's confirmation.
    alice_list = await service.get_user_show_logs(ALICE)
    bob_list = await service.get_user_show_logs(bob)

    assert [log.event_id for log in alice_list] == [show]
    assert [log.event_id for log in bob_list] == [show]
    assert [log.status for log in alice_list] == [
        AttendanceStatus.WENT
    ]
    assert [log.status for log in bob_list] == [
        AttendanceStatus.MAYBE
    ]

    # The event counts people, one per status.
    document = await snapshot(db, show)
    assert document["went_count"] == 1
    assert document["maybe_count"] == 1
    assert document["going_count"] == 0

    # And both pairs exist, each naming its own user.
    pairs = await db.show_logs.find({}).to_list(length=10)
    assert sorted(
        (row["user_id"], row["event_id"]) for row in pairs
    ) == sorted([(ALICE, show), (bob, show)])
