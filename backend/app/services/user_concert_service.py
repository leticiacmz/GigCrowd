"""The concert half of a profile.

A profile answers four questions about a person as a concertgoer: what did they
see, what did they say about it, which festivals have they been to, and which
artists do they follow. Each answer comes from a collection that already backs
it, and nothing here invents a figure.

Every list is assembled in a fixed number of queries. The events behind a page
of show logs are resolved in one batch and the artists behind those events in
another, so a profile costs the same whether the user has logged one show or
five hundred.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.domain.festival import (
    festival_date,
    festival_image,
    festival_key,
    festival_name,
)
from app.models.show_log import AttendanceStatus
from app.schemas.user_concert import (
    FestivalSummary,
    ProfileArtist,
    ProfileEvent,
    ProfileReview,
)
from app.utils.ids import object_id_variants

# The profile shows the newest few of each list; the full list stays behind the
# count the profile links to.
DEFAULT_LIMIT = 12


class UserConcertService:

    def __init__(
        self,
        user_repository,
        show_log_repository,
        db,
    ):

        self.user_repository = user_repository
        self.show_log_repository = show_log_repository
        self.db = db


    # ============================================================
    # RESOLUTION
    # ============================================================

    async def _resolve_user(
        self,
        identifier: str,
    ) -> Optional[dict]:

        """Find a user by id or by username.

        `/users/me/...` holds an id while `/users/profile/{username}/...`
        holds a username, and both must report the same lists.
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
        fields: Optional[dict] = None,
    ) -> dict[str, dict]:
        """Fetch every event referenced by the show logs, in one query.

        Returns the events keyed by their id in string form, because that is
        the form show logs store and the only form a lookup can use.
        """

        wanted = [
            str(event_id)
            for event_id in event_ids
            if event_id
        ]

        if not wanted:
            return {}

        variants: list = []

        for event_id in wanted:

            for variant in object_id_variants(event_id):

                if variant not in variants:

                    variants.append(variant)

        cursor = self.db.events.find(
            {"_id": {"$in": variants}},
            fields or {},
        )

        documents = await cursor.to_list(
            length=len(variants)
        )

        return {
            str(document["_id"]): document
            for document in documents
        }


    async def _load_artist_names(
        self,
        slugs: list[str],
    ) -> dict[str, str]:
        """Resolve artist slugs to display names, in one query.

        Events reference artists by slug, and a profile needs the names. The
        names come from the `artists` collection so a show is never labelled
        with a slug the reader cannot read.
        """

        wanted = [
            slug
            for slug in dict.fromkeys(slugs)
            if slug
        ]

        if not wanted:
            return {}

        cursor = self.db.artists.find(
            {
                "slug": {"$in": wanted},
            },
            {
                "slug": 1,
                "name": 1,
            },
        )

        documents = await cursor.to_list(
            length=len(wanted)
        )

        return {
            document["slug"]: document.get("name")
            or document["slug"]
            for document in documents
            if document.get("slug")
        }


    @staticmethod
    def _artist_slugs(
        event: dict,
    ) -> list[str]:
        """The slugs an event belongs to.

        Events reference artists either as a single `artist_slug` or as an
        `artist_slugs` array for a multi-artist bill.
        """

        slugs: list[str] = []

        single = event.get("artist_slug")

        if single and single not in slugs:
            slugs.append(single)

        for slug in event.get("artist_slugs") or []:

            if slug and slug not in slugs:
                slugs.append(slug)

        return slugs


    # ============================================================
    # ASSEMBLY
    # ============================================================

    async def _events_from_logs(
        self,
        logs: list[dict],
        events: dict[str, dict],
        artist_names: dict[str, str],
    ) -> list[ProfileEvent]:

        """Turn show logs into profile events.

        A log whose event no longer exists is dropped rather than rendered as
        a blank row, because there is nothing to show and no date to place it.
        """

        items: list[ProfileEvent] = []

        for log in logs:

            event = events.get(
                str(log.get("event_id"))
            )

            if not event:
                continue

            items.append(
                self._profile_event(
                    log,
                    event,
                    artist_names,
                )
            )

        return items


    def _profile_event(
        self,
        log: dict,
        event: dict,
        artist_names: dict[str, str],
    ) -> ProfileEvent:

        slugs = self._artist_slugs(event)

        location = event.get("location") or {}

        festival = self._festival_summary(event)

        return ProfileEvent(
            event_id=str(log.get("event_id")),
            title=event.get("title") or "",
            starts_at=event.get("starts_at"),
            ends_at=event.get("ends_at"),
            event_type=event.get("event_type")
            or "Concert",
            venue_slug=event.get("venue_slug"),
            venue_name=event.get("venue_name"),
            city=location.get("city"),
            country=location.get("country"),
            artist_slugs=slugs,
            artist_names=[
                artist_names.get(slug, slug)
                for slug in slugs
            ],
            status=log.get("status"),
            festival=festival,
        )


    @staticmethod
    def _festival_summary(
        event: dict,
    ) -> Optional[FestivalSummary]:
        """The festival an event belongs to, as a single-edition summary."""

        key = festival_key(event)

        if not key:
            return None

        return FestivalSummary(
            key=key,
            name=festival_name(event) or "",
            event_id=str(event.get("_id")) if event.get("_id") else None,
            editions_count=1,
            shows_count=1,
            first_date=festival_date(event),
            last_date=festival_date(event),
            image_url=festival_image(event),
        )


    # ============================================================
    # PUBLIC API
    # ============================================================

    async def get_reviews(
        self,
        identifier: str,
        limit: int = DEFAULT_LIMIT,
    ) -> Optional[dict]:
        """A user's reviews, most recently written first."""

        user = await self._resolve_user(
            identifier
        )

        if not user:
            return None

        logs = await self.show_log_repository.get_user_reviews(
            str(user["_id"]),
            limit=limit,
        )

        events = await self._load_events(
            [log.get("event_id") for log in logs],
        )

        artist_names = await self._load_artist_names(
            self._slugs_of(events.values())
        )

        reviews: list[ProfileReview] = []

        for log in logs:

            event = events.get(
                str(log.get("event_id"))
            )

            if not event:
                continue

            base = self._profile_event(
                log,
                event,
                artist_names,
            )

            reviews.append(
                ProfileReview(
                    **base.model_dump(),
                    rating=int(
                        log.get("rating") or 0
                    ),
                    review=log.get("review") or None,
                    photo_url=log.get("photo_url")
                    or None,
                    reviewed_at=log.get("reviewed_at")
                    or log.get("updated_at"),
                )
            )

        return {
            "username": user.get("username"),
            "reviews": reviews,
            "total": await self.show_log_repository.count_user_reviews(
                str(user["_id"]),
            ),
        }


    async def get_events(
        self,
        identifier: str,
        limit: int = DEFAULT_LIMIT,
    ) -> Optional[dict]:
        """The events a user attended, most recent first."""

        user = await self._resolve_user(
            identifier
        )

        if not user:
            return None

        logs = await self.show_log_repository.get_user_logs(
            str(user["_id"]),
            status=AttendanceStatus.WENT,
            limit=limit,
        )

        events = await self._load_events(
            [log.get("event_id") for log in logs],
        )

        artist_names = await self._load_artist_names(
            self._slugs_of(events.values())
        )

        return {
            "username": user.get("username"),
            "events": await self._events_from_logs(
                logs,
                events,
                artist_names,
            ),
            "total": await self.show_log_repository.count_user_logs(
                str(user["_id"]),
                status=AttendanceStatus.WENT,
            ),
        }


    async def get_festivals(
        self,
        identifier: str,
    ) -> Optional[dict]:
        """The festivals a user has been to, one row per festival.

        Every show is considered, not just the ones on the first page, because
        two editions of the same festival must collapse into one row however
        far apart they are in the log.
        """

        user = await self._resolve_user(
            identifier
        )

        if not user:
            return None

        logs = await self.show_log_repository.get_user_logs(
            str(user["_id"]),
            status=AttendanceStatus.WENT,
            limit=None,
        )

        events = await self._load_events(
            [log.get("event_id") for log in logs],
        )

        grouped: dict[str, dict] = {}

        for log in logs:

            event = events.get(
                str(log.get("event_id"))
            )

            if not event:
                continue

            key = festival_key(event)

            if not key:
                continue

            moment = festival_date(event)

            edition = self._edition_key(moment)

            entry = grouped.get(key)

            if entry is None:

                grouped[key] = {
                    "summary": FestivalSummary(
                        key=key,
                        name=festival_name(event) or "",
                        event_id=str(
                            event.get("_id")
                        )
                        if event.get("_id")
                        else None,
                        editions_count=1,
                        shows_count=1,
                        first_date=moment,
                        last_date=moment,
                        image_url=festival_image(event),
                    ),
                    "editions": {edition},
                }

                continue

            summary = entry["summary"]

            summary.shows_count += 1

            if edition not in entry["editions"]:

                entry["editions"].add(edition)
                summary.editions_count += 1

            if (
                moment
                and (
                    summary.first_date is None
                    or moment < summary.first_date
                )
            ):
                summary.first_date = moment

            if (
                moment
                and (
                    summary.last_date is None
                    or moment > summary.last_date
                )
            ):
                summary.last_date = moment

                # The row links to the newest edition behind it, so the link
                # follows the festival forward rather than to its first night.
                summary.event_id = (
                    str(event.get("_id"))
                    if event.get("_id")
                    else summary.event_id
                )

            if not summary.image_url:
                summary.image_url = festival_image(event)

            if not summary.name:
                summary.name = festival_name(event) or ""

        festivals = sorted(
            (
                entry["summary"]
                for entry in grouped.values()
            ),
            key=lambda festival: (
                festival.last_date
                or datetime.min,
                festival.name,
            ),
            reverse=True,
        )

        return {
            "username": user.get("username"),
            "festivals": festivals,
            "total": len(festivals),
        }


    @staticmethod
    def _edition_key(
        moment: Optional[datetime],
    ) -> str:
        """The identity of one festival edition.

        An edition is the calendar year of the show. Without a date there is
        nothing to compare, so the edition counts once and cannot inflate the
        figure.
        """

        return moment.strftime("%Y") if moment else "unknown"


    async def get_artists(
        self,
        identifier: str,
        limit: int = DEFAULT_LIMIT,
    ) -> Optional[dict]:
        """The artists a user follows, which are their communities.

        Community membership here is the follow itself: the product has no
        other concept of belonging to an artist's community, and every artist
        returned links to that community.
        """

        user = await self._resolve_user(
            identifier
        )

        if not user:
            return None

        cursor = self.db.artist_follows.find(
            {
                "user_id": {
                    "$in": object_id_variants(
                        str(user["_id"])
                    ),
                },
            },
        ).sort("created_at", -1)

        follows = await cursor.to_list(
            length=None,
        )

        slugs = [
            follow["artist_slug"]
            for follow in follows
            if follow.get("artist_slug")
        ]

        if not slugs:

            return {
                "username": user.get("username"),
                "artists": [],
                "total": 0,
            }

        # One query for the artists and one for the community sizes, rather
        # than one pair of queries per followed artist.
        artist_documents = await self.db.artists.find(
            {
                "slug": {"$in": list(dict.fromkeys(slugs))},
            },
        ).to_list(length=len(set(slugs)))

        by_slug = {
            document["slug"]: document
            for document in artist_documents
            if document.get("slug")
        }

        post_counts = await self._community_post_counts(
            slugs,
        )

        artists = [
            self._profile_artist(
                slug,
                by_slug.get(slug),
                post_counts,
            )
            for slug in dict.fromkeys(slugs)
        ]

        # A follow whose artist was never imported still belongs to the user,
        # so it is reported with the slug as its name instead of disappearing.
        artists.sort(
            key=lambda artist: (
                artist.image is None,
                artist.name.casefold(),
            )
        )

        return {
            "username": user.get("username"),
            "artists": artists[:limit],
            "total": len(artists),
        }


    async def _community_post_counts(
        self,
        slugs: list[str],
    ) -> dict[str, int]:
        """How many posts each artist community holds.

        Counted in one grouped query, so a profile with thirty followed
        artists does not issue thirty counts.
        """

        pipeline = [
            {
                "$match": {
                    "artist_slug": {
                        "$in": list(
                            dict.fromkeys(slugs),
                        ),
                    },
                }
            },
            {
                "$group": {
                    "_id": "$artist_slug",
                    "count": {"$sum": 1},
                }
            },
        ]

        cursor = self.db.community_posts.aggregate(
            pipeline
        )

        counts: dict[str, int] = {}

        async for item in cursor:

            counts[item["_id"]] = item["count"]

        return counts


    @staticmethod
    def _profile_artist(
        slug: str,
        document: Optional[dict],
        post_counts: dict[str, int],
    ) -> ProfileArtist:

        return ProfileArtist(
            slug=slug,
            name=(document or {}).get("name") or slug,
            image=(document or {}).get("image"),
            genres=(document or {}).get("genres") or [],
            followers_count=int(
                (document or {}).get("followers_count")
                or 0
            ),
            posts_count=post_counts.get(slug, 0),
            is_following=True,
        )


    @staticmethod
    def _slugs_of(events) -> list[str]:
        """Every artist slug referenced by a set of events."""

        slugs: list[str] = []

        for event in events:

            single = event.get("artist_slug")

            if single and single not in slugs:
                slugs.append(single)

            for slug in event.get("artist_slugs") or []:

                if slug and slug not in slugs:
                    slugs.append(slug)

        return slugs
