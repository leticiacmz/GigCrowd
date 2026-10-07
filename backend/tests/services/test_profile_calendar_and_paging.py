"""The attended calendar and the cursor-paged diary.

Two behaviours, both about not telling a reader something untrue:

* A calendar marks a day only for a show the person says they went to. `going` and
  `maybe` are intentions and a festival bill is an announcement; neither means
  anybody was in the room.
* Paging by cursor must not skip or repeat rows, including the several shows that
  routinely share one date.

Neither touches the database - these run against a fake one.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.models.show_log import AttendanceStatus
from app.repositories.show_log_repository import ShowLogRepository
from app.repositories.user_repository import UserRepository
from app.services.user_concert_service import UserConcertService
from tests.support.fake_mongo import FakeDatabase

USER_ID = "650000000000000000000001"
USER_NAME = "someone"


def a_log(
    *,
    day: str,
    status: str = "went",
    event_id: str | None = None,
    ident: str | None = None,
) -> dict:
    moment = datetime.fromisoformat(f"{day}T20:00:00+00:00")

    document = {
        "_id": ObjectId(ident) if ident else ObjectId(),
        "user_id": USER_ID,
        "event_id": event_id or str(ObjectId()),
        "status": status,
        "date": moment,
        "created_at": moment,
        "updated_at": moment,
    }

    return document


def an_event(
    *,
    ident: str,
    title: str,
    starts_at: datetime,
    ends_at: datetime | None = None,
) -> dict:
    return {
        "_id": ObjectId(ident),
        "title": title,
        "event_type": "Concert",
        "venue_slug": "a-venue",
        "artist_slug": "someone",
        "artist_slugs": ["someone"],
        "starts_at": starts_at,
        "ends_at": ends_at,
        "external_ids": {},
        "source": None,
        "festival": None,
        "lineup": [],
        "location": None,
    }


def a_service(
    logs: list[dict],
    events: list[dict] | None = None,
) -> UserConcertService:
    # A log whose event has been deleted is skipped rather than shown as a
    # phantom row, so paging needs a real event behind every log.
    stored_events = (
        list(events)
        if events is not None
        else [
            an_event(
                ident=str(log["event_id"]),
                title=f"Show {index}",
                starts_at=log["date"],
            )
            for index, log in enumerate(logs)
        ]
    )

    database = FakeDatabase(
        {
            "users": [
                {
                    "_id": ObjectId(USER_ID),
                    "username": USER_NAME,
                }
            ],
            "show_logs": logs,
            "events": stored_events,
            "artists": [],
            "venues": [],
        }
    )

    class EventRepositoryStub:
        """Reads the events behind a page of logs, in one query."""

        async def get_documents_by_ids(self, event_ids):

            wanted = {str(value) for value in event_ids if value}

            return [
                document
                for document in database["events"].documents
                if str(document.get("_id")) in wanted
            ]

    return UserConcertService(
        user_repository=UserRepository(database),
        show_log_repository=ShowLogRepository(database),
        db=database,
        event_repository=EventRepositoryStub(),
    )


class TestOnlyWentMarksADay:
    @pytest.mark.asyncio
    async def test_a_went_show_marks_its_day(self):
        service = a_service(
            [
                a_log(day="2024-03-15"),
                a_log(day="2025-07-04", status="going"),
                a_log(day="2025-08-01", status="maybe"),
            ]
        )

        result = await service.get_attended_calendar(
            USER_NAME, year=2025, month=7
        )

        assert result["days"] == {}
    @pytest.mark.asyncio
    async def test_the_right_month_is_read(self):
        service = a_service(
            [
                a_log(day="2024-03-15"),
                a_log(day="2024-04-02"),
                a_log(day="2024-04-20"),
            ]
        )

        march = await service.get_attended_calendar(
            USER_NAME, year=2024, month=3
        )

        april = await service.get_attended_calendar(
            USER_NAME, year=2024, month=4
        )

        assert march["days"] == {"2024-03-15": 1}
        assert april["days"] == {"2024-04-02": 1, "2024-04-20": 1}

    @pytest.mark.asyncio
    async def test_two_shows_on_one_day_are_counted_together(self):
        # Two festivals in one room is one day with two shows on it, and the
        # calendar is allowed to say so rather than pretending it was one night.
        service = a_service(
            [a_log(day="2024-03-15"), a_log(day="2024-03-15")]
        )

        result = await service.get_attended_calendar(
            USER_NAME, year=2024, month=3
        )

        assert result["days"] == {"2024-03-15": 2}
        assert result["total"] == 2

    @pytest.mark.asyncio
    async def test_december_reads_the_right_range(self):
        # A December page is the one place an off-by-one would hide, because the
        # next month is the next year.
        service = a_service(
            [
                a_log(day="2024-12-24"),
                a_log(day="2025-01-01"),
            ]
        )

        result = await service.get_attended_calendar(
            USER_NAME, year=2024, month=12
        )

        assert result["days"] == {"2024-12-24": 1}

    @pytest.mark.asyncio
    async def test_days_are_newest_first(self):
        service = a_service(
            [
                a_log(day="2024-03-01"),
                a_log(day="2024-03-20"),
                a_log(day="2024-03-10"),
            ]
        )

        result = await service.get_attended_calendar(
            USER_NAME, year=2024, month=3
        )

        assert list(result["days"]) == [
            "2024-03-20",
            "2024-03-10",
            "2024-03-01",
        ]

    @pytest.mark.asyncio
    async def test_a_month_with_nothing_is_empty_not_an_error(self):
        service = a_service([a_log(day="2024-03-15")])

        result = await service.get_attended_calendar(
            USER_NAME, year=2024, month=6
        )

        assert result["days"] == {}
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_an_impossible_month_is_refused(self):
        service = a_service([])

        with pytest.raises(ValueError):
            await service.get_attended_calendar(
                USER_NAME, year=2024, month=13
            )

    @pytest.mark.asyncio
    async def test_another_persons_shows_never_appear(self):
        logs = [a_log(day="2024-03-15")]

        logs.append({
            **a_log(day="2024-03-16"),
            "user_id": "650000000000000000000009",
        })

        service = a_service(logs)

        result = await service.get_attended_calendar(
            USER_NAME, year=2024, month=3
        )

        assert result["days"] == {"2024-03-15": 1}


class TestTheDiaryPagesWithoutLosingRows:
    @pytest.mark.asyncio
    async def test_pages_cover_every_row_exactly_once(self):
        logs = [
            a_log(
                day=f"2024-01-{day:02d}",
                ident=f"6500000000000000000000{day:02d}",
            )
            for day in range(1, 26)
        ]

        service = a_service(logs)

        seen: list[str] = []
        cursor = None

        for _ in range(10):

            page = await service.get_events_page(
                USER_NAME, limit=10,
                before_date=cursor[0] if cursor else None,
                before_id=cursor[1] if cursor else None,
            )

            if not page["events"]:
                break

            seen.extend(
                row.event_id for row in page["events"]
            )

            raw = page["next_cursor"]

            if raw is None:
                break

            cursor = (raw["date"], raw["id"])

        # Every log, once.
        assert len(seen) == 25
        assert len(set(seen)) == 25

    @pytest.mark.asyncio
    async def test_shows_sharing_a_date_are_all_reached(self):
        # A festival with three nights: every row has the same date, so a cursor
        # made of the date alone would either skip or repeat them.
        logs = [
            a_log(
                day="2024-03-15",
                ident=f"65000000000000000000000{index}",
            )
            for index in range(5)
        ]

        service = a_service(logs)

        seen: list[str] = []
        cursor = None

        for _ in range(10):

            page = await service.get_events_page(
                USER_NAME, limit=2,
                before_date=cursor[0] if cursor else None,
                before_id=cursor[1] if cursor else None,
            )

            if not page["events"]:
                break

            seen.extend(row.event_id for row in page["events"])

            raw = page["next_cursor"]

            if raw is None:
                break

            cursor = (raw["date"], raw["id"])

        assert len(seen) == 5
        assert len(set(seen)) == 5

    @pytest.mark.asyncio
    async def test_the_last_page_offers_no_further_cursor(self):
        service = a_service(
            [a_log(day="2024-03-15", ident="650000000000000000000015")]
        )

        page = await service.get_events_page(USER_NAME, limit=10)

        assert page["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_a_full_page_that_is_not_the_last_offers_a_cursor(self):
        logs = [
            a_log(
                day=f"2024-01-{day:02d}",
                ident=f"6500000000000000000000{day:02d}",
            )
            for day in range(1, 6)
        ]

        service = a_service(logs)

        page = await service.get_events_page(USER_NAME, limit=5)

        assert page["next_cursor"] is not None

    @pytest.mark.asyncio
    async def test_the_page_is_newest_first(self):
        logs = [
            a_log(
                day=f"2024-01-{day:02d}",
                ident=f"6500000000000000000000{day:02d}",
            )
            for day in range(1, 6)
        ]

        service = a_service(logs)

        page = await service.get_events_page(USER_NAME, limit=5)

        stamps = [row.starts_at for row in page["events"]]

        assert stamps == sorted(stamps, reverse=True)

    @pytest.mark.asyncio
    async def test_each_page_carries_the_same_counts(self):
        # The breakdown on the profile is drawn from these responses, so a figure
        # must not depend on which page it arrived with.
        logs = [a_log(day="2024-01-01", status="went")]
        logs.append(a_log(day="2024-01-02", status="going"))

        service = a_service(logs)

        page = await service.get_events_page(USER_NAME, limit=1)

        assert page["counts"]
        assert page["total"] == 1

    @pytest.mark.asyncio
    async def test_a_malformed_cursor_is_refused(self):
        service = a_service([])

        with pytest.raises(ValueError):
            await service.get_events_page(
                USER_NAME, before_date="not-a-date"
            )

    @pytest.mark.asyncio
    async def test_paging_going_returns_only_going(self):
        logs = [a_log(day="2024-01-01", status="went")]
        logs.append(a_log(day="2024-01-02", status="going"))

        service = a_service(logs)

        page = await service.get_events_page(
            USER_NAME, status=AttendanceStatus.GOING, limit=10
        )

        assert page["total"] == 1

    @pytest.mark.asyncio
    async def test_a_log_without_an_event_is_skipped_not_shown(self):
        # A show that has since been deleted must not appear as a phantom row.
        service = a_service([a_log(day="2024-01-01")], events=[])

        page = await service.get_events_page(USER_NAME, limit=10)

        assert page["events"] == []


class TestTheYearSelectorKnowsWhichYearsMatter:
    """The calendar can only offer years somebody can reach.

    Without this, a profile whose shows are in 2021 is opened in 2026 and the only
    route back is the next-month arrow, sixty times. The selector exists to make
    that a single choice, so what it offers has to be the years that actually have
    something in them.
    """

    @pytest.mark.asyncio
    async def test_only_years_with_an_attended_show_are_offered(self):
        service = a_service(
            [
                a_log(day="2021-03-25"),
                a_log(day="2021-03-27"),
                a_log(day="2023-11-04"),
            ]
        )

        result = await service.get_attended_years(USER_NAME)

        years = [row["year"] for row in result["years"]]

        assert 2021 in years
        assert 2023 in years
        assert 2022 not in years

        counts = {
            row["year"]: row["shows"] for row in result["years"]
        }

        assert counts[2021] == 2
        assert counts[2023] == 1

    @pytest.mark.asyncio
    async def test_the_list_is_newest_first(self):
        service = a_service(
            [
                a_log(day="2021-03-25"),
                a_log(day="2024-08-01"),
                a_log(day="2022-05-05"),
            ]
        )

        result = await service.get_attended_years(USER_NAME)

        years = [row["year"] for row in result["years"]]

        assert years == sorted(years, reverse=True)

    @pytest.mark.asyncio
    async def test_intentions_do_not_create_a_year(self):
        """A year somebody only ever clicked "going" for is not one they saw a show.

        Offering it would be a small lie that makes the selector look broken when
        the month turns out to be empty.
        """

        service = a_service(
            [
                a_log(day="2021-03-25"),
                a_log(day="2022-05-05", status="going"),
                a_log(day="2023-06-06", status="maybe"),
            ]
        )

        result = await service.get_attended_years(USER_NAME)

        years = [row["year"] for row in result["years"]]

        assert 2021 in years
        assert 2022 not in years
        assert 2023 not in years

    @pytest.mark.asyncio
    async def test_the_current_year_is_always_offered(self):
        """The year somebody opens a calendar in has to be selectable.

        Even with nothing logged in it yet - otherwise the selector silently omits
        "now", which is exactly the year a reader is most likely to want.
        """

        service = a_service([a_log(day="2021-03-25")])

        result = await service.get_attended_years(USER_NAME)

        years = [row["year"] for row in result["years"]]

        assert result["current_year"] in years
        assert years[0] == result["current_year"]

    @pytest.mark.asyncio
    async def test_an_empty_history_is_empty_rather_than_missing(self):
        """No shows is a real answer, and has to be distinguishable from an error."""

        service = a_service([])

        result = await service.get_attended_years(USER_NAME)

        assert result["has_any"] is False

        # Just the current year, so the selector is not empty.
        assert len(result["years"]) == 1

    @pytest.mark.asyncio
    async def test_a_log_without_a_date_is_skipped(self):
        """A log with no instant cannot belong to a year.

        Counting it under one would put a show in a year nothing states.
        """

        logs = [a_log(day="2021-03-25")]

        logs.append(
            {**a_log(day="2021-03-26"), "date": None}
        )

        service = a_service(logs)

        result = await service.get_attended_years(USER_NAME)

        counts = {
            row["year"]: row["shows"] for row in result["years"]
        }

        assert counts[2021] == 1