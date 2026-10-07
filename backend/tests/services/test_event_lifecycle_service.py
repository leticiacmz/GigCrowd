"""Asking people about shows that have already happened.

The rules worth protecting are all about restraint rather than function:

* a plan is never quietly turned into a fact
* nobody is asked the same question twice
* a person who has already written about the show is not asked again
* one broken row does not cost everyone else their prompt
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.activity import (
    SYSTEM_ACTOR_ID,
    NotificationType,
)
from app.services.event_lifecycle_service import (
    ATTENDANCE_CHECK,
    REVIEW_PROMPT,
    EventLifecycleService,
    plan_prompt,
)
from tests.support.fake_mongo import FakeDatabase


NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def make_user(user_id: str, username: str) -> dict:
    return {
        "_id": user_id,
        "username": username,
        "avatar_url": None,
        "is_active": True,
    }


def make_event(
    event_id: str,
    *,
    hours_ago: float,
    ends_hours_ago: float | None = None,
    title: str = "Marina Sena at Ibirapuera",
) -> dict:
    """An event that finished `hours_ago` hours before NOW."""

    ends = NOW - timedelta(hours=ends_hours_ago or hours_ago)

    return {
        "_id": event_id,
        "title": title,
        "event_type": "Concert",
        "artist_slug": "marina-sena",
        "starts_at": ends - timedelta(hours=3),
        "ends_at": ends,
    }


def build(
    logs: list[dict] | None = None,
    events: list[dict] | None = None,
    users: list[dict] | None = None,
    notifications: list[dict] | None = None,
) -> FakeDatabase:
    return FakeDatabase(
        {
            "users": users
            if users is not None
            else [make_user("u1", "alice"), make_user("u2", "bob")],
            "show_logs": logs or [],
            "events": events or [],
            "notifications": notifications or [],
            "activities": [],
        }
    )


def log_for(
    user_id: str,
    event_id: str,
    status: str,
    review: str | None = None,
    lifecycle: dict | None = None,
) -> dict:
    document = {
        "_id": f"log-{user_id}-{event_id}",
        "user_id": user_id,
        "event_id": event_id,
        "status": status,
    }

    if review is not None:
        document["review"] = review
        document["rating"] = 5

    if lifecycle is not None:
        document["lifecycle"] = lifecycle

    return document


class TestWhichPrompt:
    """The decision, tested without a database."""

    def test_a_plan_is_asked_whether_it_happened(self):
        assert plan_prompt("going", has_review=False) == ATTENDANCE_CHECK

    def test_an_uncertainty_is_asked_the_same_way(self):
        # `maybe` and `going` are both plans, and both are answered by the same
        # question, so they share a prompt.
        assert plan_prompt("maybe", has_review=False) == ATTENDANCE_CHECK

    def test_an_attended_show_is_asked_for_a_review(self):
        assert plan_prompt("went", has_review=False) == REVIEW_PROMPT

    def test_an_already_reviewed_show_is_not_asked_again(self):
        assert plan_prompt("went", has_review=True) is None

    def test_an_unknown_status_is_not_prompted(self):
        assert plan_prompt(None, has_review=False) is None
        assert plan_prompt("cancelled", has_review=False) is None

    def test_the_two_prompts_are_distinct_persisted_types(self):
        # They ask different things, so they are different rows rather than one
        # type with a flag on it.
        assert NotificationType.EVENT_ATTENDANCE_CHECK.value == "event_attendance_check"
        assert NotificationType.EVENT_REVIEW_PROMPT.value == "event_review_prompt"

    def test_a_prompt_is_not_a_person(self):
        assert SYSTEM_ACTOR_ID == "system"


class TestWhoGetsAsked:
    @pytest.mark.asyncio
    async def test_a_past_show_with_a_plan_is_asked(self):
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.attendance_checks == 1
        assert result.review_prompts == 0

    @pytest.mark.asyncio
    async def test_a_maybe_show_is_asked(self):
        db = build(
            logs=[log_for("u1", "e1", "maybe")],
            events=[make_event("e1", hours_ago=5)],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.attendance_checks == 1

    @pytest.mark.asyncio
    async def test_an_attended_unreviewed_show_gets_a_review_prompt(self):
        db = build(
            logs=[log_for("u1", "e1", "went")],
            events=[make_event("e1", hours_ago=5)],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.review_prompts == 1
        assert result.attendance_checks == 0

    @pytest.mark.asyncio
    async def test_an_already_reviewed_show_is_not_asked(self):
        db = build(
            logs=[log_for("u1", "e1", "went", review="Great night")],
            events=[make_event("e1", hours_ago=5)],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.notified == 0
        assert result.skipped_reviewed == 1
        assert db.notifications.documents == []

    @pytest.mark.asyncio
    async def test_a_future_show_is_not_asked(self):
        # An event that has not happened cannot be reviewed.
        db = build(
            logs=[log_for("u1", "e1", "went")],
            events=[make_event("e1", hours_ago=-48)],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.notified == 0
        assert db.notifications.documents == []

    @pytest.mark.asyncio
    async def test_a_show_finished_long_ago_is_left_alone(self):
        # Without a lookback window the first pass would notify somebody about a
        # concert from three years ago.
        db = build(
            logs=[log_for("u1", "e1", "went")],
            events=[make_event("e1", hours_ago=24 * 365)],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.notified == 0

    @pytest.mark.asyncio
    async def test_a_show_log_for_a_deleted_event_is_skipped(self):
        db = build(
            logs=[log_for("u1", "gone", "went")],
            events=[],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.notified == 0


class TestNobodyIsAskedTwice:
    @pytest.mark.asyncio
    async def test_running_twice_sends_one_notification(self):
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
        )

        service = EventLifecycleService(db)

        first = await service.run(now=NOW)
        second = await service.run(now=NOW)

        assert first.attendance_checks == 1
        assert second.notified == 0
        assert second.skipped_already_asked == 1

        assert len(db.notifications.documents) == 1

    @pytest.mark.asyncio
    async def test_the_marker_is_written_on_the_show_log(self):
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
        )

        await EventLifecycleService(db).run(now=NOW)

        stored = db.show_logs.documents[0]

        assert ATTENDANCE_CHECK in (stored.get("lifecycle") or {})

    @pytest.mark.asyncio
    async def test_a_notification_that_is_already_there_is_not_repeated(self):
        # Even with the marker lost - a hand edit, or a run that died between
        # the insert and the marker - the collection itself refuses a duplicate.
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
            notifications=[
                {
                    "_id": "n1",
                    "recipient_id": "u1",
                    "actor_id": SYSTEM_ACTOR_ID,
                    "type": ATTENDANCE_CHECK,
                    "related_entity_type": "event",
                    "related_entity_id": "e1",
                    "context": {},
                    "read": False,
                    "created_at": NOW,
                }
            ],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.notified == 0
        assert len(db.notifications.documents) == 1

    @pytest.mark.asyncio
    async def test_two_people_are_each_asked_about_the_same_show(self):
        # The notification belongs to the recipient, so one person's prompt
        # never suppresses another's.
        db = build(
            logs=[
                log_for("u1", "e1", "going"),
                log_for("u2", "e1", "going"),
            ],
            events=[make_event("e1", hours_ago=5)],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.attendance_checks == 2

        recipients = {
            document["recipient_id"]
            for document in db.notifications.documents
        }

        assert recipients == {"u1", "u2"}


class TestWhatIsWritten:
    @pytest.mark.asyncio
    async def test_the_notification_points_at_the_event(self):
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
        )

        await EventLifecycleService(db).run(now=NOW)

        document = db.notifications.documents[0]

        assert document["related_entity_type"] == "event"
        assert document["related_entity_id"] == "e1"
        assert document["context"]["event_title"].startswith("Marina Sena")

    @pytest.mark.asyncio
    async def test_the_sender_is_the_system_not_the_reader(self):
        # A prompt is not somebody acting, so it must not look like the reader
        # notifying themselves.
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
        )

        await EventLifecycleService(db).run(now=NOW)

        document = db.notifications.documents[0]

        assert document["actor_id"] == SYSTEM_ACTOR_ID
        assert document["actor_id"] != document["recipient_id"]

    @pytest.mark.asyncio
    async def test_the_state_at_the_time_of_asking_is_recorded(self):
        # Somebody who confirms afterwards should still be able to see what they
        # had said when they were asked.
        db = build(
            logs=[log_for("u1", "e1", "maybe")],
            events=[make_event("e1", hours_ago=5)],
        )

        await EventLifecycleService(db).run(now=NOW)

        document = db.notifications.documents[0]

        assert document["context"]["status_at_prompt"] == "maybe"


class TestAttendanceIsNeverInvented:
    @pytest.mark.asyncio
    async def test_a_prompt_does_not_change_any_show_log_status(self):
        db = build(
            logs=[
                log_for("u1", "e1", "going"),
                log_for("u2", "e2", "maybe"),
            ],
            events=[
                make_event("e1", hours_ago=5),
                make_event("e2", hours_ago=5),
            ],
        )

        await EventLifecycleService(db).run(now=NOW)

        statuses = {
            document["event_id"]: document["status"]
            for document in db.show_logs.documents
        }

        # Both plans are exactly as they were. The reader confirms, or does not.
        assert statuses == {"e1": "going", "e2": "maybe"}

    @pytest.mark.asyncio
    async def test_no_activity_is_created_for_the_prompt(self):
        # An activity row would put "went to X" on the timeline of the people
        # who follow this reader, which is precisely the fabrication being
        # avoided.
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
            users=[make_user("u1", "alice")],
        )

        await EventLifecycleService(db).run(now=NOW)

        assert db.activities.documents == []


class TestRestraint:
    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing(self):
        db = build(
            logs=[log_for("u1", "e1", "going")],
            events=[make_event("e1", hours_ago=5)],
        )

        result = await EventLifecycleService(db).run(
            dry_run=True, now=NOW
        )

        assert result.attendance_checks == 1
        assert db.notifications.documents == []

    @pytest.mark.asyncio
    async def test_a_batch_size_bounds_the_pass(self):
        logs = [
            log_for("u1", f"e{index}", "going")
            for index in range(10)
        ]

        events = [
            make_event(f"e{index}", hours_ago=5)
            for index in range(10)
        ]

        db = build(logs=logs, events=events)

        result = await EventLifecycleService(db).run(
            batch_size=3, now=NOW
        )

        assert result.notified <= 3
        assert len(db.notifications.documents) <= 3

    @pytest.mark.asyncio
    async def test_one_broken_row_does_not_cost_anyone_else_their_prompt(
        self,
        monkeypatch,
    ):
        db = build(
            logs=[
                log_for("u1", "e1", "going"),
                log_for("u2", "e2", "going"),
            ],
            events=[
                make_event("e1", hours_ago=5),
                make_event("e2", hours_ago=5),
            ],
        )

        service = EventLifecycleService(db)

        original = service._notify
        calls = {"n": 0}

        async def flaky(log, event, kind):
            calls["n"] += 1

            if calls["n"] == 1:
                raise RuntimeError("boom")

            return await original(log, event, kind)

        monkeypatch.setattr(service, "_notify", flaky)

        result = await service.run(now=NOW)

        assert result.failed == 1
        assert result.notified == 1

    @pytest.mark.asyncio
    async def test_an_event_id_is_matched_in_either_storage_form(self):
        # A show log holds a string id and the event an ObjectId; only one of the
        # two is right depending on how old the row is.
        from bson import ObjectId

        oid = ObjectId("6ac3ecb0257180503f7eb27e")

        db = build(
            logs=[log_for("u1", str(oid), "went")],
            events=[{**make_event(oid, hours_ago=5), "_id": oid}],
        )

        result = await EventLifecycleService(db).run(now=NOW)

        assert result.review_prompts == 1
