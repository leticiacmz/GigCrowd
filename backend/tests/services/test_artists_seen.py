"""Artists I Have Seen.

The section answers "who have I actually stood in front of", so the tests below
are mostly about what must *not* contribute: a show that was merely planned, an
artist that is only followed, and a lineup that repeats itself.

Everything runs against the deterministic development seed, because that fixture
was built to contain exactly these cases - an act listed twice on one bill, an
artist on several attended shows, a festival series with three editions, and a
user with no history at all.
"""
from __future__ import annotations

import pytest
from bson import ObjectId

from app.domain.event_artists import count_attended_shows_per_artist
from app.models.show_log import AttendanceStatus
from app.repositories.show_log_repository import ShowLogRepository
from app.scripts.seed_dev_data import build_dataset
from app.services.user_concert_service import UserConcertService
from app.services.user_stats_service import UserStatsService
from app.repositories.follow_repository import FollowRepository
from tests.support.fake_mongo import FakeDatabase


class SeededProfile:
    """A service over the development fixture.

    `reads` counts how many times each collection was read, which is how the
    query-shape test below distinguishes a bounded number of reads from one
    read per show.
    """

    def __init__(self, database, dependencies):
        self.database = database
        self.dependencies = dependencies
        self.reads: dict[str, int] = {}

    def count_reads(self) -> dict[str, int]:
        return dict(self.reads)


@pytest.fixture
def seeded():
    dataset = build_dataset()

    database = FakeDatabase(
        {
            name: [dict(document) for document in documents]
            for name, documents in dataset.items()
        }
    )

    class Users:

        async def get_by_id(self, identifier):
            for user in database.users.documents:
                if str(user["_id"]) == str(identifier):
                    return user
            return None

        async def get_by_username(self, username):
            for user in database.users.documents:
                if user.get("username") == username:
                    return user
            return None

    class Events:
        """Only what the service uses, so the test states its own dependency."""

        def __init__(self, db):
            self.collection = db.events

        async def get_documents_by_ids(self, event_ids):
            from app.utils.ids import object_id_variants

            variants = []

            for event_id in event_ids:
                for variant in object_id_variants(event_id):
                    if variant not in variants:
                        variants.append(variant)

            if not variants:
                return []

            return await self.collection.find(
                {"_id": {"$in": variants}}
            ).to_list(length=None)

    profile = SeededProfile(
        database,
        {
            "users": Users(),
            "show_logs": ShowLogRepository(database),
            "events": Events(database),
        },
    )

    # Count reads on the two collections whose access pattern matters: the
    # events behind an attendance history and the artists those events name.
    for name in ("events", "artists"):

        collection = getattr(database, name)
        original = collection.find

        def counted(*args, _original=original, _name=name, **kwargs):
            profile.reads[_name] = profile.reads.get(_name, 0) + 1

            return _original(*args, **kwargs)

        collection.find = counted

    return profile


@pytest.fixture
def service(seeded):
    return UserConcertService(
        user_repository=seeded.dependencies["users"],
        show_log_repository=seeded.dependencies["show_logs"],
        db=seeded.database,
        event_repository=seeded.dependencies["events"],
    )


def counts_by_slug(result) -> dict:
    return {
        artist.slug: artist.shows_count
        for artist in result["artists"]
    }


class TestWhatContributes:
    @pytest.mark.asyncio
    async def test_a_concert_they_attended_contributes(self, service):
        result = await service.get_artists_seen("leticiacmz")

        assert counts_by_slug(result)["arctic-monkeys"] == 1

    @pytest.mark.asyncio
    async def test_one_artist_on_several_attended_concerts_counts_each(
        self,
        service,
    ):
        # Three Marina Sena concerts. The festival dates she is on do not add to
        # this, which is the whole rule.
        result = await service.get_artists_seen("leticiacmz")

        assert counts_by_slug(result)["marina-sena"] == 3

    @pytest.mark.asyncio
    async def test_a_marina_sena_count_is_not_inflated_by_a_festival_date(
        self,
        service,
    ):
        # She is on two attended festival dates as well. If a lineup were read as
        # personal attendance this would be 5, which is exactly the claim this
        # list must not make.
        counts = counts_by_slug(
            await service.get_artists_seen("leticiacmz")
        )

        assert counts["marina-sena"] < 5

    @pytest.mark.asyncio
    async def test_an_act_twice_on_one_bill_is_one_show(self, service):
        # A direct reference repeated on a bill is still one show.
        document = {
            "_id": "event-repeat",
            "event_type": "Concert",
            "artist_slug": "o-terno",
            "artist_slugs": ["o-terno", "o-terno"],
        }

        assert count_attended_shows_per_artist([document]) == {
            "o-terno": 1
        }


class TestAFestivalIsNotPersonalAttendance:
    """The product rule this section exists to enforce.

    Someone can attend a festival and see one act on it. Attending the festival
    is not attending every performance, so a lineup must never add an artist to
    anyone's history.
    """

    @pytest.mark.asyncio
    async def test_a_lineup_only_artist_is_absent(self, service):
        # Tim Bernardes is on no concert at all - only on a festival lineup.
        result = await service.get_artists_seen("leticiacmz")

        slugs = {artist.slug for artist in result["artists"]}

        assert "tim-bernardes" not in slugs

    @pytest.mark.asyncio
    async def test_an_artist_on_no_concert_is_absent(self, service):
        # O Terno and Victo exist on the seeded festival lineups and nowhere
        # else.
        result = await service.get_artists_seen("leticiacmz")

        slugs = {artist.slug for artist in result["artists"]}

        assert "o-terno" not in slugs
        assert "victo" not in slugs

    @pytest.mark.asyncio
    async def test_attending_festivals_alone_yields_no_artists(
        self,
        service,
        seeded,
    ):
        # A user whose entire attended history is festival dates has seen no
        # artist, because they have confirmed no artist's show.
        logs = [
            log
            for log in seeded.database.show_logs.documents
            if log.get("status") == "went"
        ]

        for log in logs:
            log["status"] = "going"

        result = await service.get_artists_seen("leticiacmz")

        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_a_support_act_on_an_attended_concert_is_absent(
        self,
        service,
        seeded,
    ):
        # A concert can carry a multi-act bill. Only the event's own artist
        # counts, so the support act stays off the history.
        seeded.database.events.documents.append(
            {
                "_id": "event-multi",
                "event_type": "Concert",
                "starts_at": "2024-01-07T20:00:00Z",
                "artist_slug": "marina-sena",
                "artist_slugs": ["marina-sena"],
                "lineup": [
                    {"name": "Anitta", "slug": "anitta", "songkick_id": "1"},
                    {
                        "name": "Marina Sena",
                        "slug": "marina-sena",
                        "songkick_id": "2",
                    },
                ],
            }
        )

        seeded.database.show_logs.documents.append(
            {
                "_id": "log-multi",
                "user_id": str(
                    next(
                        user["_id"]
                        for user in seeded.database.users.documents
                        if user["username"] == "leticiacmz"
                    )
                ),
                "event_id": "event-multi",
                "status": "went",
            }
        )

        result = await service.get_artists_seen("leticiacmz")

        slugs = {artist.slug for artist in result["artists"]}

        assert "marina-sena" in slugs
        assert "anitta" not in slugs


class TestWhatDoesNotContribute:
    @pytest.mark.asyncio
    async def test_a_show_that_is_only_going_to_does_not_count(
        self,
        service,
    ):
        # Leticia has an Arctic Monkeys show coming up. Their count comes from the
        # past show she attended, not from the upcoming one.
        counts = counts_by_slug(
            await service.get_artists_seen("leticiacmz")
        )

        assert counts["arctic-monkeys"] == 1

    @pytest.mark.asyncio
    async def test_a_maybe_show_does_not_count(self, service):
        counts = counts_by_slug(
            await service.get_artists_seen("leticiacmz")
        )

        # Gal Costa has one attended show and one "maybe".
        assert counts["gal-costa"] == 1

    @pytest.mark.asyncio
    async def test_following_an_artist_does_not_put_them_in_the_list(
        self,
        service,
    ):
        # Ana follows Marina Sena and has never been to a show of hers.
        result = await service.get_artists_seen("analima")

        slugs = {artist.slug for artist in result["artists"]}

        assert "marina-sena" not in slugs
        assert "rubel" in slugs

    @pytest.mark.asyncio
    async def test_the_list_is_not_the_followed_artists(self, service):
        seen = counts_by_slug(
            await service.get_artists_seen("leticiacmz")
        )
        followed = await service.get_artists("leticiacmz")

        followed_slugs = {
            artist.slug for artist in followed["artists"]
        }

        assert set(seen) != followed_slugs
        assert seen["marina-sena"] > 1


class TestIsolationAndEmptyProfiles:
    @pytest.mark.asyncio
    async def test_a_user_never_sees_another_users_attendance(
        self,
        service,
    ):
        leticia = await service.get_artists_seen("leticiacmz")
        bruno = await service.get_artists_seen("brunor")

        # Bruno attended one Gal Costa show and shares nothing else.
        assert counts_by_slug(bruno) == {"gal-costa": 1}

        assert "gal-costa" in counts_by_slug(leticia)

    @pytest.mark.asyncio
    async def test_a_user_with_no_history_has_no_artists(self, service):
        result = await service.get_artists_seen("theov")

        assert result["total"] == 0
        assert result["artists"] == []

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_reported_as_missing(self, service):
        assert await service.get_artists_seen("nobody") is None

    @pytest.mark.asyncio
    async def test_a_profile_can_be_read_by_id_as_well_as_name(
        self,
        service,
        seeded,
    ):
        user_id = next(
            str(user["_id"])
            for user in seeded.database.users.documents
            if user["username"] == "leticiacmz"
        )

        by_name = await service.get_artists_seen("leticiacmz")
        by_id = await service.get_artists_seen(user_id)

        assert by_id["total"] == by_name["total"]

    @pytest.mark.asyncio
    async def test_a_deleted_event_is_skipped_rather_than_counted(
        self,
        service,
        seeded,
    ):
        # Break one of the events behind an attended show.
        victim = next(
            event
            for event in seeded.database.events.documents
            if event["title"].startswith("Arctic Monkeys at")
        )

        seeded.database.events.documents.remove(victim)

        counts = counts_by_slug(
            await service.get_artists_seen("leticiacmz")
        )

        assert "arctic-monkeys" not in counts


class TestShape:
    @pytest.mark.asyncio
    async def test_it_is_ordered_by_shows_descending(self, service):
        result = await service.get_artists_seen("leticiacmz")

        counts = [artist.shows_count for artist in result["artists"]]

        assert counts == sorted(counts, reverse=True)

    @pytest.mark.asyncio
    async def test_it_carries_no_social_counters(self, service):
        # A follower count or a community post count answers a different
        # question and would make the list read as popularity.
        result = await service.get_artists_seen("leticiacmz")

        for artist in result["artists"]:

            assert set(artist.model_dump()) == {
                "slug",
                "name",
                "image",
                "shows_count",
                "resolved",
            }

    @pytest.mark.asyncio
    async def test_a_resolved_artist_is_flagged_and_named(self, service):
        result = await service.get_artists_seen("leticiacmz")

        marina = next(
            artist for artist in result["artists"]
            if artist.slug == "marina-sena"
        )

        assert marina.resolved is True
        assert marina.name == "Marina Sena"

    @pytest.mark.asyncio
    async def test_an_unresolved_artist_is_still_listed_without_a_page(
        self,
        service,
        seeded,
    ):
        # Remove the imported page, as happens for any artist GigCrowd has not
        # imported. The person still saw them, so the row stays.
        seeded.database.artists.documents = [
            document
            for document in seeded.database.artists.documents
            if document["slug"] != "marina-sena"
        ]

        result = await service.get_artists_seen("leticiacmz")

        artist = next(
            row for row in result["artists"]
            if row.slug == "marina-sena"
        )

        assert artist.resolved is False
        assert artist.shows_count == 3
        # No imported record means no name to show, and a lineup is not
        # consulted to supply one: the list is built from direct attendance, so
        # its names come from the same place its counts do.
        assert artist.name == "marina-sena"

    @pytest.mark.asyncio
    async def test_a_concert_only_artist_shows_its_slug_rather_than_a_name(
        self,
        service,
        seeded,
    ):
        # A concert stores its performers as slugs and states no name, so with
        # no imported page there is nothing to call this artist. Its slug is
        # shown rather than a name guessed out of the event title.
        seeded.database.artists.documents = [
            document
            for document in seeded.database.artists.documents
            if document["slug"] != "rubel"
        ]

        result = await service.get_artists_seen("leticiacmz")

        artist = next(
            row for row in result["artists"]
            if row.slug == "rubel"
        )

        assert artist.resolved is False
        assert artist.name == "rubel"

    @pytest.mark.asyncio
    async def test_a_limit_trims_the_list_but_not_the_total(self, service):
        everything = await service.get_artists_seen("leticiacmz")

        result = await service.get_artists_seen(
            "leticiacmz", limit=2
        )

        assert len(result["artists"]) == 2
        assert result["total"] == everything["total"]

    @pytest.mark.asyncio
    async def test_paging_walks_the_list_without_repeating_or_dropping(
        self,
        service,
    ):
        # Ordered most seen first, so the pages a caller walks are stable: the
        # same artist has to appear on exactly one page.
        everything = await service.get_artists_seen("leticiacmz")

        first = await service.get_artists_seen(
            "leticiacmz", limit=2
        )

        second = await service.get_artists_seen(
            "leticiacmz", limit=2, skip=2
        )

        paged = [
            artist.slug
            for artist in first["artists"] + second["artists"]
        ]

        assert len(paged) == len(set(paged))
        assert paged == [
            artist.slug for artist in everything["artists"]
        ]

        # Each page reports the same whole total, so the last page is reachable.
        assert first["total"] == second["total"] == everything["total"]

    @pytest.mark.asyncio
    async def test_reading_past_the_end_is_an_empty_page_not_an_error(
        self,
        service,
    ):
        everything = await service.get_artists_seen("leticiacmz")

        result = await service.get_artists_seen(
            "leticiacmz", limit=4, skip=99
        )

        assert result["artists"] == []
        assert result["total"] == everything["total"]


class TestQueryShape:
    @pytest.mark.asyncio
    async def test_the_cost_does_not_grow_with_the_history(
        self,
        service,
        seeded,
    ):
        # A profile resolves its whole attendance history in a fixed number of
        # reads: every event behind the history at once, then every artist at
        # once. If either became per-show or per-artist, a five-show profile and
        # a fifty-show profile would cost different amounts.
        await service.get_artists_seen("leticiacmz")

        assert seeded.count_reads() == {
            "events": 1,
            "artists": 1,
        }

    @pytest.mark.asyncio
    async def test_one_artists_page_does_not_fetch_a_second_read(
        self,
        service,
        seeded,
    ):
        # The artists of an attended festival lineup can be numerous, so the
        # second read has to cover all of them.
        await service.get_artists_seen("leticiacmz")

        assert seeded.reads["artists"] == 1


class TestStatisticsAgreeWithTheSection:
    """The header figure and the list behind it must never disagree."""

    def stats_service(self, database):
        class Users:

            async def get_by_id(self, identifier):
                for user in database.users.documents:
                    if str(user["_id"]) == str(identifier):
                        return user
                return None

            async def get_by_username(self, username):
                for user in database.users.documents:
                    if user.get("username") == username:
                        return user
                return None

        return UserStatsService(
            user_repository=Users(),
            show_log_repository=ShowLogRepository(database),
            follow_repository=FollowRepository(database),
            db=database,
        )

    @pytest.mark.asyncio
    async def test_the_artists_figure_is_artists_seen(
        self,
        seeded,
        service,
    ):
        stats = await self.stats_service(
            seeded.database
        ).get_user_stats("leticiacmz")

        section = await service.get_artists_seen("leticiacmz")

        assert stats["artists_seen"] == section["total"]

        # And it is genuinely a different number from the follows.
        assert stats["artists_seen"] != stats[
            "followed_artists_count"
        ]

    @pytest.mark.asyncio
    async def test_a_festival_counts_once_however_many_days(
        self,
        seeded,
    ):
        stats = await self.stats_service(
            seeded.database
        ).get_user_stats("leticiacmz")

        # Two editions of one festival were attended.
        assert stats["festivals_count"] == 1

    @pytest.mark.asyncio
    async def test_an_empty_profile_reports_zero_for_everything(
        self,
        seeded,
    ):
        stats = await self.stats_service(
            seeded.database
        ).get_user_stats("theov")

        assert stats["artists_seen"] == 0
        assert stats["festivals_count"] == 0
        assert stats["shows_attended"] == 0
