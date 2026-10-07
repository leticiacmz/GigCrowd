"""Real profile statistics.

Every number here is counted from the persisted documents that back it, so a
profile can never advertise a figure that has no row behind it. The work is
done in a fixed number of queries regardless of how many shows or posts a user
has, because the events behind the show logs are resolved in one batch.
"""
from datetime import UTC, datetime

from app.domain.event_artists import personal_artist_slugs
from app.domain.event_schedule import is_upcoming
from app.domain.festival import festival_key
from app.utils.ids import id_matches, object_id_variants


class UserStatsService:

    def __init__(
        self,
        user_repository,
        show_log_repository,
        follow_repository,
        db,
    ):

        self.user_repository = user_repository
        self.show_log_repository = show_log_repository
        self.follow_repository = follow_repository
        self.db = db


    async def _resolve_user(
        self,
        identifier: str,
    ) -> dict | None:
        """Find a user by id or by username.

        `/users/me/stats` holds an id while
        `/users/profile/{username}/stats` holds a username, and both have to
        report the same figures, so both forms are accepted here.
        """

        user = await self.user_repository.get_by_id(
            identifier
        )

        if not user:

            user = await self.user_repository.get_by_username(
                identifier
            )

        return user


    async def _load_events(
        self,
        event_ids: list,
    ) -> list[dict]:
        """Fetch every event referenced by the show logs in one query."""

        if not event_ids:
            return []

        variants: list = []

        for event_id in event_ids:

            for variant in object_id_variants(event_id):

                if variant not in variants:

                    variants.append(variant)


        cursor = self.db.events.find(
            {"_id": {"$in": variants}},
            {
                "artist_slug": 1,
                "artist_slugs": 1,
                # Needed so a festival date's performers count towards the
                # artists this person has actually seen.
                "lineup": 1,
                "starts_at": 1,
                "ends_at": 1,
                "title": 1,
                "event_type": 1,
                "festival": 1,
            },
        )

        return await cursor.to_list(
            length=len(variants)
        )


    @staticmethod
    def _artist_slugs(
        event: dict,
    ) -> set[str]:
        """The slugs an event belongs to.

        Events reference artists by slug, either as a single `artist_slug` or
        as an `artist_slugs` array for a multi-artist bill.
        """

        slugs: set[str] = set()

        single = event.get("artist_slug")

        if single:
            slugs.add(single)

        for slug in event.get("artist_slugs") or []:
            if slug:
                slugs.add(slug)

        return slugs


    async def get_user_stats(
        self,
        identifier: str,
    ) -> dict | None:
        """Count a user's real activity.

        `identifier` is either the user id or the username; see
        `_resolve_user`.
        """

        user = await self._resolve_user(
            identifier
        )

        if not user:
            return None


        user_id = str(user["_id"])


        # The social graph is counted from the `follows` collection itself
        # rather than from the denormalized counters on the user document,
        # which drift whenever a counter update is missed. This keeps the
        # number on the profile header equal to the list behind it.
        followers_count = (
            await self.follow_repository.count_followers(
                user_id,
            )
        )

        following_count = (
            await self.follow_repository.count_following(
                user_id,
            )
        )


        logs = await self.show_log_repository.get_user_logs(
            user_id,
        )


        counts = {
            "went": 0,
            "going": 0,
            "maybe": 0,
        }

        for log in logs:

            log_status = log.get("status")

            if log_status in counts:

                counts[log_status] += 1


        # One query resolves every event behind the show logs, instead of one
        # lookup per log.
        events = await self._load_events(
            [
                log.get("event_id")
                for log in logs
                if log.get("event_id")
            ]
        )


        artists: set[str] = set()

        festivals: set[str] = set()

        upcoming = 0

        now = datetime.now(UTC)

        # A festival is somewhere the person has been, so it is counted from
        # attended shows only. Counting a show someone is merely going to would
        # advertise a festival the profile's own list cannot show.
        attended_event_ids = {
            str(log.get("event_id"))
            for log in logs
            if log.get("status") == "went"
        }

        for event in events:

            festival = festival_key(event)

            if festival and str(event.get("_id")) in attended_event_ids:
                festivals.add(festival)

            if str(event.get("_id")) in attended_event_ids:
                # Only the event's own direct artist reference. A festival date
                # has no headline artist, so attending one adds nobody to this
                # set - which is the point: a lineup is not a record of what
                # someone watched.
                artists |= personal_artist_slugs(event)

            # Whether the show is still ahead is the shared schedule rule, so
            # the count on the profile cannot disagree with the badge on the
            # event itself.
            if is_upcoming(event, now):

                upcoming += 1


        # Posts live in `community_posts`; counting any other collection would
        # report a figure with nothing behind it.
        total_posts = await self.db.community_posts.count_documents(
            id_matches(
                "user_id",
                user_id,
            )
        )


        return {
            "username": user.get("username"),

            "followers_count": followers_count,

            "following_count": following_count,

            "shows_attended": counts["went"],

            "shows_going": counts["going"],

            "shows_maybe": counts["maybe"],

            # The figure the profile header shows under "Artists". It is the
            # number of distinct artists this person has been to a show of, and
            # it is deliberately not the number they follow: following an artist
            # is an intention, and this section is a history.
            "artists_seen": len(
                artists
            ),

            "upcoming_events": upcoming,

            "total_posts": total_posts,

            # The concert profile's own figures: what the person has seen,
            # what they wrote about it, and who they follow on stage.
            "reviews_count": await self.show_log_repository.count_user_reviews(
                user_id,
            ),

            "festivals_count": len(
                festivals
            ),

            "followed_artists_count": (
                await self.db.artist_follows.count_documents(
                    id_matches(
                        "user_id",
                        user_id,
                    )
                )
            ),
        }