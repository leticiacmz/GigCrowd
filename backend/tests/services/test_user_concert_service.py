"""The concert profile.

The rules these tests pin down are the ones that keep a profile honest: a
festival is counted once however many days of it you attended, a review has to
carry something worth reading, a show is labelled with artist names rather
than slugs, and every list is assembled without a query per row.
"""
from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.domain.festival import festival_key
from app.repositories.show_log_repository import ShowLogRepository
from app.services.user_concert_service import UserConcertService
from tests.support.fake_mongo import FakeDatabase


NOW = datetime.now(UTC)

USER_ID = "6a00000000000000000000aa"


class CountingDatabase(FakeDatabase):
    """A `FakeDatabase` that records every query the service issues.

    The point of the N+1 guard is that the number of queries does not grow with
    the number of rows, so the queries have to be observable.
    """

    def __init__(self):
        super().__init__()
        self.reads: list[tuple[str, str]] = []

    def _wrap(self, name: str, collection):
        return _CountingCollection(
            collection,
            self.reads,
            name,
        )

    def __getattr__(self, name: str):
        # `FakeDatabase.__getattr__` reaches the collection through `self[...]`,
        # so the base `__getitem__` is called directly: going through the
        # override below would wrap the collection twice and count every query
        # two times.
        return self._wrap(
            name,
            FakeDatabase.__getitem__(self, name),
        )

    def __getitem__(self, name: str):
        return self._wrap(
            name,
            FakeDatabase.__getitem__(self, name),
        )


class _CountingCollection:

    # Attribute reads that are not queries. Reading `.documents` to seed a
    # fixture, or a collection's own name, must not be counted as a request.
    NOT_A_QUERY = {
        "name",
        "documents",
        "_collection",
        "_reads",
        "_name",
    }

    def __init__(
        self,
        collection,
        reads: list,
        name: str,
    ):
        self._collection = collection
        self._reads = reads
        self._name = name

    def __getattr__(self, name: str):
        if name in self.NOT_A_QUERY:

            return getattr(self._collection, name, None)

        attribute = getattr(
            self._collection,
            name,
        )

        def recorded(*args, **kwargs):
            self._reads.append(
                (self._name, name)
            )
            return attribute(*args, **kwargs)

        return recorded


@pytest.fixture
def db() -> CountingDatabase:

    return CountingDatabase()


@pytest.fixture
def service(db: CountingDatabase) -> UserConcertService:

    class Users:

        async def get_by_id(self, identifier):

            for user in db.users.documents:

                if str(user["_id"]) == str(identifier):
                    return user

            return None

        async def get_by_username(self, username):

            for user in db.users.documents:

                if user.get("username") == username:
                    return user

            return None

    return UserConcertService(
        user_repository=Users(),
        show_log_repository=ShowLogRepository(db),
        db=db,
    )


async def seed_user(db, username: str = "leticiacmz"):

    await db.users.insert_one({
        "_id": ObjectId(USER_ID),
        "username": username,
    })


async def seed_event(
    db,
    *,
    event_id: str,
    title: str = "Some Concert",
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    festival: dict | None = None,
    event_type: str = "Concert",
    artist_slug: str = "some-artist",
    artist_slugs: list | None = None,
    location: dict | None = None,
):

    document = {
        "_id": ObjectId(event_id),
        "title": title,
        "venue_slug": "some-venue",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "festival": festival,
        "event_type": event_type,
        "artist_slug": artist_slug,
        "artist_slugs": artist_slugs or [],
        "location": location
        or {"city": "São Paulo", "country": "BR"},
    }

    await db.events.insert_one(document)

    return str(document["_id"])


async def seed_log(
    db,
    *,
    event_id: str,
    user_id: str = USER_ID,
    status: str = "went",
    **fields,
):

    document = {
        "_id": f"log-{event_id}",
        "user_id": user_id,
        "event_id": event_id,
        "status": status,
        "date": NOW - timedelta(days=1),
        "created_at": NOW - timedelta(days=1),
        "updated_at": NOW - timedelta(days=1),
    }

    document.update(fields)

    await db.show_logs.insert_one(document)

    return document


async def seed_artist(
    db,
    *,
    slug: str,
    name: str,
    image: str | None = None,
    genres: list | None = None,
    followers_count: int = 0,
):

    await db.artists.insert_one({
        "_id": ObjectId(),
        "slug": slug,
        "name": name,
        "image": image,
        "genres": genres or [],
        "followers_count": followers_count,
    })


class TestReviews:

    @pytest.mark.asyncio
    async def test_a_review_is_returned_with_its_show(
        self,
        service,
        db,
    ):

        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            title="Rock in Rio",
            starts_at=NOW - timedelta(days=30),
        )

        await seed_artist(
            db,
            slug="some-artist",
            name="Some Artist",
        )

        await seed_log(
            db,
            event_id=event_id,
            rating=5,
            review="Best night of the year",
            reviewed_at=NOW - timedelta(days=1),
        )

        result = await service.get_reviews(
            "leticiacmz",
        )

        assert result["total"] == 1

        review = result["reviews"][0]

        assert review.event_id == event_id
        assert review.title == "Rock in Rio"
        assert review.rating == 5
        assert review.review == "Best night of the year"
        assert review.artist_names == ["Some Artist"]
        assert review.city == "São Paulo"

    @pytest.mark.asyncio
    async def test_a_bare_rating_is_not_a_review(
        self,
        service,
        db,
    ):

        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=30),
        )

        await seed_log(db, event_id=event_id, rating=3)

        result = await service.get_reviews("leticiacmz")

        assert result["reviews"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_a_photo_alone_is_a_review(
        self,
        service,
        db,
    ):

        # A photo of the show is an opinion too, and it is the only thing on
        # some logs.
        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=30),
        )

        await seed_log(
            db,
            event_id=event_id,
            rating=4,
            photo_url="https://example.test/p.jpg",
            reviewed_at=NOW,
        )

        result = await service.get_reviews("leticiacmz")

        assert result["total"] == 1
        assert result["reviews"][0].photo_url == (
            "https://example.test/p.jpg"
        )

    @pytest.mark.asyncio
    async def test_reviews_are_newest_written_first(
        self,
        service,
        db,
    ):

        await seed_user(db)

        for index in range(3):

            event_id = await seed_event(
                db,
                event_id=f"6a00000000000000000000{index + 1:02d}",
                starts_at=NOW - timedelta(days=index + 1),
            )

            await seed_log(
                db,
                event_id=event_id,
                review=f"Show {index}",
                reviewed_at=NOW - timedelta(days=index),
            )

        result = await service.get_reviews("leticiacmz")

        assert [review.review for review in result["reviews"]] == [
            "Show 0",
            "Show 1",
            "Show 2",
        ]

    @pytest.mark.asyncio
    async def test_a_review_for_a_deleted_event_is_skipped(
        self,
        service,
        db,
    ):

        await seed_user(db)

        await seed_log(
            db,
            event_id="6a0000000000000000000099",
            review="Into the void",
            reviewed_at=NOW,
        )

        result = await service.get_reviews("leticiacmz")

        # There is nothing to render without the event, and rendering a blank
        # row would look like a bug on the profile.
        assert result["reviews"] == []

    @pytest.mark.asyncio
    async def test_an_unknown_user_is_reported_as_missing(
        self,
        service,
        db,
    ):

        assert await service.get_reviews("nobody") is None

    @pytest.mark.asyncio
    async def test_a_user_can_be_resolved_by_id_too(
        self,
        service,
        db,
    ):

        # `/users/me/...` holds an id; `/users/profile/{username}/...` holds a
        # username. Both must return the same profile.
        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=30),
        )

        await seed_log(
            db, event_id=event_id, review="Great", reviewed_at=NOW,
        )

        assert (await service.get_reviews(USER_ID))["total"] == 1


class TestEvents:

    @pytest.mark.asyncio
    async def test_only_attended_shows_are_listed(
        self,
        service,
        db,
    ):

        await seed_user(db)

        attended = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=10),
        )

        planned = await seed_event(
            db,
            event_id="6a0000000000000000000002",
            starts_at=NOW + timedelta(days=10),
        )

        await seed_log(db, event_id=attended, status="went")
        await seed_log(db, event_id=planned, status="going")

        result = await service.get_events("leticiacmz")

        assert [event.event_id for event in result["events"]] == [
            attended,
        ]
        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_the_count_is_the_full_list_not_the_page(
        self,
        service,
        db,
    ):

        await seed_user(db)

        for index in range(5):

            event_id = await seed_event(
                db,
                event_id=f"6a00000000000000000000{index + 1:02d}",
                starts_at=NOW - timedelta(days=index + 1),
            )

            await seed_log(db, event_id=event_id)

        result = await service.get_events(
            "leticiacmz",
            limit=2,
        )

        assert len(result["events"]) == 2
        assert result["total"] == 5

    @pytest.mark.asyncio
    async def test_a_multi_artist_bill_is_named_in_full(
        self,
        service,
        db,
    ):

        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=10),
            artist_slug="headliner",
            artist_slugs=["headliner", "support"],
        )

        await seed_artist(db, slug="headliner", name="Headliner")
        await seed_artist(db, slug="support", name="Support Act")

        await seed_log(db, event_id=event_id)

        result = await service.get_events("leticiacmz")

        assert result["events"][0].artist_names == [
            "Headliner",
            "Support Act",
        ]

    @pytest.mark.asyncio
    async def test_an_unknown_artist_slug_falls_back_to_the_slug(
        self,
        service,
        db,
    ):

        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            starts_at=NOW - timedelta(days=10),
            artist_slug="never-imported",
        )

        await seed_log(db, event_id=event_id)

        result = await service.get_events("leticiacmz")

        # Showing the slug is better than showing an empty line, and it makes
        # a missing import visible instead of invisible.
        assert result["events"][0].artist_names == [
            "never-imported",
        ]


class TestFestivals:

    @pytest.mark.asyncio
    async def test_two_days_of_one_festival_count_once(
        self,
        service,
        db,
    ):

        # Three shows, one festival weekend. The count a profile shows is the
        # number of festivals, not the number of tickets.
        await seed_user(db)

        for index in range(3):

            event_id = await seed_event(
                db,
                event_id=f"6a00000000000000000000{index + 1:02d}",
                title="Beyond The Valley 2026",
                event_type="FestivalInstance",
                starts_at=NOW + timedelta(days=index + 1),
                festival={
                    "series_id": "1125073",
                    "name": "Beyond The Valley 2026",
                },
            )

            await seed_log(db, event_id=event_id)

        result = await service.get_festivals("leticiacmz")

        assert result["total"] == 1

        festival = result["festivals"][0]

        assert festival.key == "series:1125073"
        assert festival.name == "Beyond The Valley 2026"
        assert festival.shows_count == 3
        assert festival.editions_count == 1

    @pytest.mark.asyncio
    async def test_two_editions_of_a_series_count_once_each(
        self,
        service,
        db,
    ):

        await seed_user(db)

        for index, year in enumerate((2025, 2026)):

            event_id = await seed_event(
                db,
                event_id=f"6a00000000000000000000{index + 1:02d}",
                title=f"Beyond The Valley {year}",
                event_type="FestivalInstance",
                starts_at=datetime(
                    year, 6, 1, tzinfo=UTC,
                ),
                festival={
                    "series_id": "1125073",
                    "name": f"Beyond The Valley {year}",
                },
            )

            await seed_log(db, event_id=event_id)

        result = await service.get_festivals("leticiacmz")

        assert result["total"] == 1

        festival = result["festivals"][0]

        assert festival.editions_count == 2
        assert festival.shows_count == 2
        assert festival.first_date.year == 2025
        assert festival.last_date.year == 2026

    @pytest.mark.asyncio
    async def test_two_different_festivals_count_twice(
        self,
        service,
        db,
    ):

        await seed_user(db)

        first = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            title="Rock in Rio",
            event_type="FestivalInstance",
            starts_at=NOW - timedelta(days=200),
            festival={"series_id": "1", "name": "Rock in Rio"},
        )

        second = await seed_event(
            db,
            event_id="6a0000000000000000000002",
            title="Tomorrowland",
            event_type="FestivalInstance",
            starts_at=NOW - timedelta(days=30),
            festival={"series_id": "2", "name": "Tomorrowland"},
        )

        await seed_log(db, event_id=first)
        await seed_log(db, event_id=second)

        result = await service.get_festivals("leticiacmz")

        assert result["total"] == 2
        # Most recent first, so the profile leads with what happened lately.
        assert result["festivals"][0].name == "Tomorrowland"

    @pytest.mark.asyncio
    async def test_a_concert_is_not_a_festival(
        self,
        service,
        db,
    ):

        # A single show is not a festival with one edition. Treating it as one
        # would put every show on every profile in the festival count.
        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            title="A Tuesday Concert",
            starts_at=NOW - timedelta(days=10),
        )

        await seed_log(db, event_id=event_id)

        result = await service.get_festivals("leticiacmz")

        assert result["festivals"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_an_undated_festival_does_not_become_a_past_one(
        self,
        service,
        db,
    ):

        # Attendance itself already required a date, so this is defensive: a
        # festival with no date must not produce a wrong date on the profile.
        await seed_user(db)

        event_id = await seed_event(
            db,
            event_id="6a0000000000000000000001",
            title="Mystery Festival",
            event_type="FestivalInstance",
            starts_at=None,
            festival={"series_id": "9", "name": "Mystery"},
        )

        await seed_log(db, event_id=event_id)

        result = await service.get_festivals("leticiacmz")

        assert result["total"] == 1
        assert result["festivals"][0].editions_count == 1


class TestFestivalIdentity:

    def test_a_series_id_wins_over_the_name(self):

        # Two editions named differently share the provider's series id, so
        # they are one festival.
        assert festival_key({
            "title": "Beyond The Valley 2025",
            "event_type": "FestivalInstance",
            "festival": {
                "series_id": "1125073",
                "name": "Beyond The Valley 2025",
            },
        }) == festival_key({
            "title": "Beyond The Valley 2026",
            "event_type": "FestivalInstance",
            "festival": {
                "series_id": "1125073",
                "name": "Beyond The Valley 2026",
            },
        })

    def test_the_same_name_spelled_differently_is_one_festival(self):

        assert festival_key({
            "title": "Rock in Rio",
            "event_type": "FestivalInstance",
            "festival": {"name": "Rock in Rio"},
        }) == festival_key({
            "title": "Rock In Rio!",
            "event_type": "FestivalInstance",
            "festival": {"name": "rock in rio"},
        })

    def test_years_are_never_stripped_to_force_a_match(self):

        # These are adjacent editions, not one festival with a typo. Collapsing
        # them would report a figure that does not exist.
        assert festival_key({
            "title": "Gigcrowd Fest 2025",
            "event_type": "FestivalInstance",
            "festival": {"name": "Gigcrowd Fest 2025"},
        }) != festival_key({
            "title": "Gigcrowd Fest 2026",
            "event_type": "FestivalInstance",
            "festival": {"name": "Gigcrowd Fest 2026"},
        })

    def test_a_festival_without_metadata_is_identified_by_its_title(self):

        assert festival_key({
            "title": "Coachella",
            "event_type": "Festival",
        }) == "title:coachella"

    def test_a_concert_has_no_festival_identity(self):

        assert festival_key({
            "title": "A Tuesday Concert",
            "event_type": "Concert",
        }) is None

    def test_a_series_id_never_collides_with_a_name(self):

        assert festival_key({
            "title": "X",
            "event_type": "FestivalInstance",
            "festival": {"series_id": "name:coachella"},
        }) != festival_key({
            "title": "Coachella",
            "event_type": "Festival",
        })


class TestArtists:

    @pytest.mark.asyncio
    async def test_followed_artists_are_the_communities(
        self,
        service,
        db,
    ):

        # The product has one concept of belonging to an artist's community:
        # following the artist. So the list is the follows, resolved to names.
        await seed_user(db)
        await seed_artist(
            db,
            slug="some-artist",
            name="Some Artist",
            image="https://example.test/a.jpg",
            genres=["rock"],
            followers_count=120,
        )

        await db.artist_follows.insert_one({
            "_id": ObjectId(),
            "user_id": ObjectId(USER_ID),
            "artist_slug": "some-artist",
            "created_at": NOW - timedelta(days=5),
        })

        result = await service.get_artists("leticiacmz")

        assert result["total"] == 1

        artist = result["artists"][0]

        assert artist.slug == "some-artist"
        assert artist.name == "Some Artist"
        assert artist.image == "https://example.test/a.jpg"
        assert artist.genres == ["rock"]
        assert artist.followers_count == 120
        assert artist.is_following

    @pytest.mark.asyncio
    async def test_a_follow_stored_with_a_string_id_still_resolves(
        self,
        service,
        db,
    ):

        # Historic rows store the user id as a string in some collections and
        # as an `ObjectId` in others. Both must resolve, or a user's
        # communities silently disappear.
        await seed_user(db)
        await seed_artist(db, slug="some-artist", name="Some Artist")

        await db.artist_follows.insert_one({
            "_id": ObjectId(),
            "user_id": USER_ID,
            "artist_slug": "some-artist",
            "created_at": NOW,
        })

        result = await service.get_artists("leticiacmz")

        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_community_activity_is_counted_in_one_query(
        self,
        service,
        db,
    ):

        await seed_user(db)

        posts_per_artist = {"a": 1, "b": 2, "c": 3}

        for slug, count in posts_per_artist.items():

            await seed_artist(db, slug=slug, name=slug.upper())

            await db.artist_follows.insert_one({
                "_id": ObjectId(),
                "user_id": ObjectId(USER_ID),
                "artist_slug": slug,
                "created_at": NOW,
            })

            for _ in range(count):

                await db.community_posts.insert_one({
                    "_id": ObjectId(),
                    "artist_slug": slug,
                    "user_id": ObjectId(USER_ID),
                    "content": "hi",
                })

        before = len(db.reads)

        result = await service.get_artists("leticiacmz")

        aggregations = [
            read
            for read in db.reads[before:]
            if read[1] == "aggregate"
        ]

        # One grouped aggregation covers every artist, rather than one count
        # per followed artist.
        assert len(aggregations) == 1

        counts = {
            artist.slug: artist.posts_count
            for artist in result["artists"]
        }

        assert counts == posts_per_artist

    @pytest.mark.asyncio
    async def test_a_follow_for_an_unimported_artist_is_still_reported(
        self,
        service,
        db,
    ):

        # The follow is real. Hiding it would make the count disagree with the
        # list, and would look like the follow never happened.
        await seed_user(db)

        await db.artist_follows.insert_one({
            "_id": ObjectId(),
            "user_id": ObjectId(USER_ID),
            "artist_slug": "never-imported",
            "created_at": NOW,
        })

        result = await service.get_artists("leticiacmz")

        assert result["total"] == 1
        assert result["artists"][0].name == "never-imported"
        assert result["artists"][0].image is None

    @pytest.mark.asyncio
    async def test_someone_who_follows_nobody_has_no_communities(
        self,
        service,
        db,
    ):

        await seed_user(db)

        result = await service.get_artists("leticiacmz")

        assert result == {
            "username": "leticiacmz",
            "artists": [],
            "total": 0,
        }


class TestQueryShape:

    @pytest.mark.asyncio
    async def test_a_page_of_shows_costs_a_fixed_number_of_queries(
        self,
        service,
        db,
    ):

        # Ten shows resolve their events in one query and their artists in
        # another. If either grew per row, this profile would issue twenty
        # requests instead of four.
        await seed_user(db)

        await seed_artist(db, slug="shared-artist", name="Shared")

        async def add_show(index: int):

            event_id = f"6a00000000000000000000{index + 1:02d}"

            await seed_event(
                db,
                event_id=event_id,
                starts_at=NOW - timedelta(days=index + 1),
                artist_slug=f"artist-{index}",
                artist_slugs=[f"artist-{index}", "shared-artist"],
            )

            await seed_artist(
                db,
                slug=f"artist-{index}",
                name=f"A{index}",
            )

            await seed_log(
                db,
                event_id=event_id,
                review=f"Show {index}",
                reviewed_at=NOW - timedelta(days=index),
            )

        await add_show(0)

        before = len(db.reads)

        small = await service.get_reviews("leticiacmz")

        small_reads = list(db.reads[before:])

        for index in range(1, 10):

            await add_show(index)

        before = len(db.reads)

        large = await service.get_reviews("leticiacmz")

        large_reads = list(db.reads[before:])

        assert len(small["reviews"]) == 1
        assert len(large["reviews"]) == 10

        # One read for the logs, one for the events, one for the artist names
        # and one for the total. Adding nine more shows must not add a single
        # request.
        assert len(large_reads) == len(small_reads) == 4

    @pytest.mark.asyncio
    async def test_an_empty_profile_answers_without_guessing(
        self,
        service,
        db,
    ):

        await seed_user(db)

        result = await service.get_events("leticiacmz")

        assert result["events"] == []
        assert result["total"] == 0

        result = await service.get_festivals("leticiacmz")

        assert result["festivals"] == []

        result = await service.get_reviews("leticiacmz")

        assert result["reviews"] == []
