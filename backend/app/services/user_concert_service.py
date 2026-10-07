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

from datetime import UTC, datetime
from typing import Optional

from app.domain.event_artists import (
    count_attended_shows_per_artist,
)
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
    SeenArtist,
)
from app.utils.ids import object_id_variants

# The profile shows the newest few of each list; the full list stays behind the
# count the profile links to.
DEFAULT_LIMIT = 12

# How many rows one page of the scrollable diary carries.
#
# Bounded on purpose. The diary is read by scrolling to the past, so a page that
# is too small makes many round trips for a reader with a long history, and one
# that is too large makes the first scroll wait for shows nobody will reach.
DEFAULT_PAGE_SIZE = 40

# The three states a show can be in on someone's profile.
#
# These are the values `AttendanceStatus` already persists, so the breakdown
# reads one collection that was always being written and never invents a second
# attendance system. A single log exists per user and event, so the three
# counts always add up to the number of shows a person has logged.
SHOW_STATUS = AttendanceStatus.WENT
PLAN_STATUS = AttendanceStatus.GOING
MAYBE_STATUS = AttendanceStatus.MAYBE

# The order the breakdown is presented in, which is also the order a person
# reads their own history in: what already happened, what is planned, what is
# undecided.
SHOW_STATUS_ORDER = (
    SHOW_STATUS,
    PLAN_STATUS,
    MAYBE_STATUS,
)

# What each stored state is called in the product.
#
# Storage spelling and interface spelling are different jobs. The wire uses the
# product's words, so a client that asks for `want-to-go` reads back
# `want-to-go` and never has to know that the database says `going`.
SHOW_STATUS_LABELS: dict[AttendanceStatus, str] = {
    SHOW_STATUS: "attended",
    PLAN_STATUS: "want-to-go",
    MAYBE_STATUS: "maybe",
}


def show_status_label(
    status: Optional[AttendanceStatus],
) -> Optional[str]:
    """The wire name for an attendance state."""

    if status is None:
        return None

    return SHOW_STATUS_LABELS[status]


def show_status_counts(counts: dict) -> dict[str, int]:
    """The three breakdown figures, always all three present.

    A status with no rows reports zero rather than going missing, so the
    frontend never has to decide whether an absent key means "nobody has any of
    these" or "this was not measured".
    """

    return {
        SHOW_STATUS_LABELS[status]: int(
            counts.get(status.value) or 0
        )
        for status in SHOW_STATUS_ORDER
    }


# What a client may ask for, in the words the product uses.
#
# The stored values are the terse ones (`went`, `going`), because that is what
# `AttendanceStatus` has always persisted. The wire accepts both, so a caller can
# use the product wording that appears in the interface and does not have to
# know how the database happens to spell it.
SHOW_STATUS_ALIASES: dict[str, AttendanceStatus] = {
    "went": SHOW_STATUS,
    "attended": SHOW_STATUS,
    "i-went": SHOW_STATUS,
    "going": PLAN_STATUS,
    "want-to-go": PLAN_STATUS,
    "want_to_go": PLAN_STATUS,
    "maybe": MAYBE_STATUS,
}


def resolve_show_status(
    value: Optional[str],
) -> Optional[AttendanceStatus]:
    """Turn a requested breakdown state into the status that selects it.

    Returns `None` for `all` and for an absent value, which both mean "every
    logged show". An unrecognised value raises rather than being silently
    treated as one of the three, because quietly answering a different question
    than the one that was asked is worse than refusing it.
    """

    if value is None:
        return None

    key = str(value).strip().lower()

    if key in {"", "all"}:
        return None

    if key not in SHOW_STATUS_ALIASES:
        raise ValueError(
            f"Unknown show status {value!r}. Expected one of: "
            + ", ".join(SHOW_STATUS_ALIASES)
        )

    return SHOW_STATUS_ALIASES[key]


class UserConcertService:

    def __init__(
        self,
        user_repository,
        show_log_repository,
        db,
        event_repository=None,
    ):

        self.user_repository = user_repository
        self.show_log_repository = show_log_repository
        self.db = db

        # Resolving a whole attendance history needs the events behind it.
        # Optional so that callers who only read reviews or artists followed do
        # not have to build one.
        self.event_repository = event_repository


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
            # A show log becomes a review by carrying an opinion, so the two are
            # the same row read two ways rather than two collections.
            has_review=bool(log.get("review")),
            rating=log.get("rating"),
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
    # ARTISTS I HAVE SEEN
    # ============================================================

    async def get_artists_seen(
        self,
        identifier: str,
        limit: Optional[int] = None,
        skip: int = 0,
    ) -> Optional[dict]:
        """The artists this person has actually stood in front of.

        Followed artists are deliberately not this list. "Artists" on a
        profile used to mean the people someone had pressed Follow on, which is
        a list of intentions; this one is a list of things that happened.

        The chain is deliberately short and costs a fixed number of queries
        however long the attendance history is:

            attended show logs  ->  those events, in one query
                               ->  artists per event, read from the documents
                               ->  imported artists, in one query

        Counting happens per distinct event rather than per lineup row, so an
        act listed twice on one bill is one show and two concrete days of the
        same festival are two.
        """

        user = await self._resolve_user(
            identifier
        )

        if not user:
            return None

        logs = await self.show_log_repository.get_user_logs(
            str(user["_id"]),
            status=SHOW_STATUS,
            limit=None,
        )

        if not logs:
            return {
                "username": user.get("username"),
                "artists": [],
                "total": 0,
            }

        documents = await self._attended_event_documents(logs)

        if not documents:
            return {
                "username": user.get("username"),
                "artists": [],
                "total": 0,
            }

        counts = count_attended_shows_per_artist(documents)

        artists = await self._seen_artist_rows(counts)

        return {
            "username": user.get("username"),
            "artists": (
                artists[skip: skip + limit]
                if limit is not None
                else artists[skip:]
            ),
            # The whole history, not the page. A caller paging through needs to
            # know how many there are, and a total that shrank with the page
            # would make the last page unreachable.
            "total": len(artists),
        }

    async def _attended_event_documents(
        self,
        logs: list[dict],
    ) -> list[dict]:
        """The events behind these show logs, in one query.

        A log whose event has since been deleted is skipped rather than
        contributing a phantom show to a count.
        """

        return await self.event_repository.get_documents_by_ids(
            [log.get("event_id") for log in logs]
        )

    async def _seen_artist_rows(
        self,
        counts: dict[str, int],
    ) -> list[SeenArtist]:
        """Label and order the counted artists.

        Imported artists are read in one query, so a name and an image are
        never fetched per artist.

        The name comes only from an imported artist record. A lineup entry is
        deliberately not consulted: the list is built from direct attendance, so
        borrowing a name from a festival bill would put an act on someone's
        history that nothing else in the list agrees with. An artist with no
        page shows its slug and reports itself unresolved, so the client does not
        build a link to a page that does not exist.
        """

        slugs = list(counts)

        documents = await self.db.artists.find(
            {"slug": {"$in": slugs}},
            {
                "slug": 1,
                "name": 1,
                "image": 1,
            },
        ).to_list(length=len(slugs))

        by_slug = {
            document["slug"]: document
            for document in documents
            if document.get("slug")
        }

        rows: list[SeenArtist] = []

        for slug, shows in counts.items():

            document = by_slug.get(slug)

            rows.append(
                SeenArtist(
                    slug=slug,
                    # With no imported record there is no name to show, and the
                    # slug is shown rather than one invented from an event
                    # title.
                    name=(document or {}).get("name") or slug,
                    image=(document or {}).get("image"),
                    shows_count=shows,
                    resolved=document is not None,
                )
            )

        # Most seen first, then alphabetically so two equal counts have a stable
        # order rather than depending on dictionary order.
        rows.sort(
            key=lambda artist: (
                -artist.shows_count,
                artist.name.casefold(),
            )
        )

        return rows

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
                    **base.model_dump(
                        # `rating` is stated below, because a review's rating is
                        # required while a plain show's is not. Passing the base
                    # value as well would set it twice.
                        exclude={"rating"},
                    ),
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
        skip: int = 0,
        status: Optional[AttendanceStatus] = SHOW_STATUS,
    ) -> Optional[dict]:
        """One state of a user's shows, most recent first.

        `status` narrows the list to one of the three states a show can be in.
        It defaults to the shows someone actually attended, which is what the
        profile has always shown, and passing `None` returns every logged show
        across all three.

        The three counts travel with every response and are counted from the same
        query the list is drawn from, so a figure on the profile can never
        disagree with the rows behind it.
        """

        user = await self._resolve_user(
            identifier
        )

        if not user:
            return None

        user_id = str(user["_id"])

        logs = await self.show_log_repository.get_user_logs(
            user_id,
            status=status,
            skip=skip,
            limit=limit,
        )

        events = await self._load_events(
            [log.get("event_id") for log in logs],
        )

        artist_names = await self._load_artist_names(
            self._slugs_of(events.values())
        )

        counts = show_status_counts(
            await self.show_log_repository.count_user_logs_by_status(
                user_id
            )
        )

        # `total` is the size of the list that was asked for, so a client paging
        # through one state knows how many rows that state holds without having
        # to add up the counts.
        if status is None:
            total = sum(counts.values())
        else:
            total = counts.get(SHOW_STATUS_LABELS[status], 0)

        return {
            "username": user.get("username"),
            "events": await self._events_from_logs(
                logs,
                events,
                artist_names,
            ),
            "total": total,
            "status": show_status_label(status),
            "counts": counts,
            "limit": limit,
            "skip": max(0, skip),
        }


    async def get_attended_calendar(
        self,
        identifier: str,
        *,
        year: int,
        month: int,
    ) -> Optional[dict]:
        """The shows attended in one calendar month.

        Only logs marked `went` mark a day. A `going` or `maybe` log is an
        intention and a festival lineup is a bill, so neither may appear here - a
        calendar that showed a day as attended because somebody once clicked
        "going" would be telling a reader something untrue about their own life.

        The query is bounded to the month, so opening the calendar costs one month
        of logs rather than the whole history, and a profile with years of shows
        behind it renders exactly as fast as one with a handful.
        """

        user = await self._resolve_user(identifier)

        if not user:
            return None

        if not 1 <= int(month) <= 12:

            raise ValueError(
                f"month must be between 1 and 12, got {month!r}"
            )

        start = datetime(
            int(year),
            int(month),
            1,
            tzinfo=UTC,
        )

        end = (
            datetime(int(year) + 1, 1, 1, tzinfo=UTC)
            if int(month) == 12
            else datetime(
                int(year),
                int(month) + 1,
                1,
                tzinfo=UTC,
            )
        )

        counts = await self.show_log_repository.attended_dates_between(
            str(user["_id"]),
            start,
            end,
        )

        return {
            "username": user.get("username"),
            "year": int(year),
            "month": int(month),
            "days": counts,
            "total": sum(counts.values()),
            # Whether this month or the one before it has anything at all, so the
            # client can grey out a previous-month control without a second request.
            "has_any": True,
        }

    async def get_attended_years(
        self,
        identifier: str,
        *,
        limit: int = 50,
    ) -> Optional[dict]:
        """The years this user has shows in, newest first.

        A calendar that can only be moved a month at a time makes somebody with
        five years of shows click sixty times to reach the one they mean. This
        is what lets the year selector offer the years that actually have
        something in them, and it is aggregated in the database so the cost does
        not grow with the length of the history.

        The current year is always included, even with nothing logged in it,
        because it is the year somebody opens a calendar in and an empty option
        there reads as a broken selector.
        """

        user = await self._resolve_user(identifier)

        if not user:
            return None

        rows = await self.show_log_repository.attended_years(
            str(user["_id"]),
            limit=limit,
        )

        this_year = datetime.now(UTC).year

        years = sorted(
            {int(row["year"]) for row in rows}
            | {this_year},
            reverse=True,
        )

        counts = {int(row["year"]): int(row["shows"]) for row in rows}

        return {
            "username": user.get("username"),
            "years": [
                {"year": year, "shows": counts.get(year, 0)}
                for year in years
            ],
            "current_year": this_year,
            "has_any": any(
                row["shows"] for row in rows
            ),
        }

    async def get_events_page(
        self,
        identifier: str,
        *,
        status: Optional[AttendanceStatus] = SHOW_STATUS,
        before_date: Optional[str] = None,
        before_id: Optional[str] = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> Optional[dict]:
        """One page of a user's shows, newest first, addressed by cursor.

        The cursor is opaque to the client: it passes back whatever `next_cursor`
        it was given. Paging by position would mean page 40 walking past every row
        before it, which for a long-running diary is the difference between an
        instant and a stall.
        """

        user = await self._resolve_user(identifier)

        if not user:
            return None

        user_id = str(user["_id"])

        parsed_date = None

        if before_date:

            try:
                parsed_date = datetime.fromisoformat(
                    before_date
                )

            except ValueError as error:

                raise ValueError(
                    f"before_date must be an ISO date, got "
                    f"{before_date!r}"
                ) from error

            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(tzinfo=UTC)

        logs = await self.show_log_repository.get_user_logs_page(
            user_id,
            status=status,
            before_date=parsed_date,
            before_id=before_id,
            limit=limit,
        )

        events = await self._load_events(
            [log.get("event_id") for log in logs],
        )

        artist_names = await self._load_artist_names(
            self._slugs_of(events.values())
        )

        counts = show_status_counts(
            await self.show_log_repository.count_user_logs_by_status(
                user_id
            )
        )

        if status is None:
            total = sum(counts.values())
        else:
            total = counts.get(SHOW_STATUS_LABELS[status], 0)

        rows = await self._events_from_logs(
            logs,
            events,
            artist_names,
        )

        # A next cursor is only offered when the page came back full. An empty or
        # short page means the end was reached, and inviting a further request
        # would just repeat the last page for ever.
        next_cursor = None

        if len(logs) >= limit and logs:

            last = logs[-1]

            moment = last.get("date")

            if isinstance(moment, datetime):

                next_cursor = {
                    "date": moment.isoformat(),
                    "id": str(last.get("_id")),
                }

        return {
            "username": user.get("username"),
            "events": rows,
            "total": total,
            "status": show_status_label(status),
            "counts": counts,
            "limit": limit,
            "next_cursor": next_cursor,
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
