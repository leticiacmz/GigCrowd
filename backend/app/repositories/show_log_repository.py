from datetime import UTC, datetime
from typing import Optional

from bson import ObjectId

from app.repositories.base import BaseRepository
from app.utils.ids import id_matches, ids_match

# The one status that means "I was there". A calendar of attended shows marks
# days from this and nothing else.
ATTENDED_STATUS = "went"


class ShowLogRepository(BaseRepository):


    def __init__(self, db):

        super().__init__(
            db,
            "show_logs",
        )


    @staticmethod
    def _pair_query(
        user_id: str,
        event_id: str,
    ) -> dict:
        """Match one user's log for one event.

        Both identifiers are matched in either storage form so an existing log
        is always found, updated and deleted.
        """

        return {
            **id_matches("user_id", user_id),
            **id_matches("event_id", event_id),
        }


    def pair_query(
        self,
        user_id: str,
        event_id: str,
    ) -> dict:
        """The query for one user's log of one event.

        Exposed so the service can reach an existing log in the same way the
        repository does, instead of restating the matching rule.
        """

        return self._pair_query(
            user_id,
            event_id,
        )


    async def get_user_logs(
        self,
        user_id: str,
        status=None,
        skip: int = 0,
        limit: Optional[int] = 50,
    ):
        """One user's show logs, most recent first.

        A single log exists per event, so filtering by status returns each
        event in exactly one state. The logs are ordered by the event date the
        log records, which is the field that answers "when was this show?".
        """

        query = id_matches("user_id", user_id)

        if status is not None:

            query["status"] = (
                status.value
                if hasattr(status, "value")
                else status
            )

        cursor = (
            self.collection
            .find(query)
            .sort("date", -1)
            .skip(max(0, skip))
        )

        if limit is not None:

            cursor = cursor.limit(limit)

        return await cursor.to_list(
            length=None,
        )


    async def get_user_logs_page(
        self,
        user_id: str,
        status=None,
        *,
        before_date=None,
        before_id=None,
        limit: int = 40,
    ):
        """One page of a user's show logs, newest first, by cursor.

        Cursor pagination rather than `skip`, because a concert diary is read by
        scrolling to the past: with `skip`, page 40 has to walk past 39 pages of
        documents to find its own, and the cost grows with every row already read.

        The cursor is the (date, id) of the last row of the previous page. `id` is
        part of it because several shows routinely share one date - a festival with
        three nights, or two rooms on the same bill - and a date-only cursor would
        skip or repeat those rows depending on their storage order.
        """

        query = id_matches("user_id", user_id)

        if status is not None:

            query["status"] = (
                status.value
                if hasattr(status, "value")
                else status
            )

        if before_date is not None:

            query["$or"] = [
                {"date": {"$lt": before_date}},
                {
                    "date": before_date,
                    "_id": {"$lt": ObjectId(before_id)},
                }
                if before_id
                else {"date": {"$lt": before_date}},
            ]

        cursor = (
            self.collection
            .find(query)
            .sort([("date", -1), ("_id", -1)])
            .limit(max(1, int(limit)))
        )

        return await cursor.to_list(length=None)

    async def attended_dates_between(
        self,
        user_id: str,
        start,
        end,
    ):
        """The dates in `[start, end)` on which this user says they went.

        Only `went`. A `going` or `maybe` log records an intention, and a festival
        lineup membership records that an act was on the bill - neither means
        anybody was in the room, so neither may mark a day on a calendar of shows
        attended.

        Bounded by the range rather than the whole history, so rendering one month
        costs one month of logs however many years somebody has been going to
        shows.

        Returns `{date: number of shows that day}`, sorted newest date first.
        """

        rows = await self.collection.find(
            {
                **id_matches("user_id", user_id),
                "status": ATTENDED_STATUS,
                "date": {"$gte": start, "$lt": end},
            }
        ).to_list(length=None)

        counts: dict = {}

        for row in rows:

            moment = row.get("date")

            if not isinstance(moment, datetime):
                continue

            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=UTC)

            key = moment.date().isoformat()

            counts[key] = counts.get(key, 0) + 1

        return dict(
            sorted(
                counts.items(),
                key=lambda pair: pair[0],
                reverse=True,
            )
        )

    async def attended_years(
        self,
        user_id: str,
        limit: int = 50,
    ) -> list[dict]:
        """The years this user says they went to a show, newest first.

        This exists so a calendar's year selector can offer the years somebody
        actually has shows in, instead of making them click backwards from this
        one to reach 2021. Aggregated by the database and bounded, so a profile
        with thousands of logs costs one small grouped query rather than a
        request per candidate year.

        Only `went`, for the same reason the calendar marks only `went`. A year
        the person only ever clicked "going" for is not a year they saw a show,
        and offering it in a list of years they have would be a small lie that
        makes the selector look broken when the month turns out to be empty.
        """

        pipeline = [
            {
                "$match": {
                    **id_matches("user_id", user_id),
                    "status": ATTENDED_STATUS,
                    "date": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": {"$year": "$date"},
                    "shows": {"$sum": 1},
                }
            },
            {"$sort": {"_id": -1}},
            {"$limit": max(1, int(limit))},
        ]

        rows = await self.collection.aggregate(
            pipeline
        ).to_list(length=None)

        return [
            {"year": int(row["_id"]), "shows": int(row.get("shows") or 0)}
            for row in rows
            if row.get("_id") is not None
        ]

    @staticmethod
    def _review_query(
        user_id: str,
    ) -> dict:
        """Match the logs of one user that carry a review.

        A review needs more than a rating: text or a photo is what makes it
        worth showing, so a bare star rating is not counted as one.
        """

        return {
            **id_matches("user_id", user_id),
            # `$exists` is part of the clause on purpose: in MongoDB `$nin`
            # also matches a document where the field is absent, which would
            # make every bare star rating count as a review.
            "$or": [
                {
                    "review": {
                        "$exists": True,
                        "$nin": [None, ""],
                    }
                },
                {
                    "photo_url": {
                        "$exists": True,
                        "$nin": [None, ""],
                    }
                },
            ],
        }


    async def get_user_reviews(
        self,
        user_id: str,
        skip: int = 0,
        limit: Optional[int] = 50,
    ):
        """The logs that carry a review, most recently reviewed first."""

        cursor = (
            self.collection
            .find(
                self._review_query(user_id),
            )
            .sort("reviewed_at", -1)
            .skip(max(0, skip))
        )

        if limit is not None:

            cursor = cursor.limit(limit)

        return await cursor.to_list(
            length=None,
        )


    async def count_user_reviews(
        self,
        user_id: str,
    ) -> int:

        return await self.collection.count_documents(
            self._review_query(user_id),
        )


    async def get_by_user_and_event(
        self,
        user_id: str,
        event_id: str,
    ):

        return await self.collection.find_one(
            self._pair_query(
                user_id,
                event_id,
            )
        )


    async def delete_by_user_and_event(
        self,
        user_id: str,
        event_id: str,
    ):

        result = await self.collection.delete_one(
            self._pair_query(
                user_id,
                event_id,
            )
        )

        return result.deleted_count > 0


    async def count_by_status(
        self,
        event_id: str,
        status: str,
    ):

        return await self.collection.count_documents(
            {
                **ids_match("event_id", [event_id]),
                "status": status,
            }
        )


    async def count_user_logs_by_status(
        self,
        user_id: str,
    ) -> dict[str, int]:
        """Every status a user's logs hold, in one grouped query.

        A profile shows three separate counts - attended, want to go and maybe -
        and they all have to come from the same rows the lists behind them come
        from. Counting each status with its own query would mean three round
        trips to answer one question, and would let the counts and the lists
        disagree if a log were written between them.
        """

        pipeline = [
            {"$match": id_matches("user_id", user_id)},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1},
                }
            },
        ]

        cursor = self.collection.aggregate(pipeline)

        counts: dict[str, int] = {}

        async for item in cursor:

            status = item.get("_id")

            if not status:
                continue

            counts[str(status)] = int(item.get("count") or 0)

        return counts


    async def count_user_logs(
        self,
        user_id: str,
        status=None,
    ) -> int:
        """How many logs a user holds, optionally in one status.

        Counted from the collection rather than from the length of a page, so
        the number a profile shows always matches the full list behind it.
        """

        query = id_matches("user_id", user_id)

        if status is not None:

            query["status"] = (
                status.value
                if hasattr(status, "value")
                else status
            )

        return await self.collection.count_documents(
            query
        )


    async def get_user_status(
        self,
        user_id: str,
        event_id: str,
    ):

        log = await self.collection.find_one(
            self._pair_query(
                user_id,
                event_id,
            )
        )

        if not log:
            return None

        return log["status"]


    async def get_attendance_summary(
        self,
        event_id: str,
    ):

        pipeline = [
            {
                "$match": ids_match(
                    "event_id",
                    [event_id],
                )
            },
            {
                "$group": {
                    "_id": "$status",
                    "count": {
                        "$sum": 1,
                    }
                }
            }
        ]

        cursor = self.collection.aggregate(
            pipeline
        )

        result = {}

        async for item in cursor:
            result[item["_id"]] = item["count"]

        return result


    async def update_review(
        self,
        user_id: str,
        event_id: str,
        rating: int,
        review: str | None,
    ):

        await self.collection.update_one(
            self._pair_query(
                user_id,
                event_id,
            ),
            {
                "$set": {
                    "rating": rating,
                    "review": review,
                    "reviewed_at": datetime.utcnow(),
                }
            },
        )

        return await self.get_by_user_and_event(
            user_id,
            event_id,
        )


    async def delete_review(
        self,
        user_id: str,
        event_id: str,
    ):

        await self.collection.update_one(
            self._pair_query(
                user_id,
                event_id,
            ),
            {
                "$unset": {
                    "rating": "",
                    "review": "",
                    "reviewed_at": "",
                }
            },
        )

        return await self.get_by_user_and_event(
            user_id,
            event_id,
        )