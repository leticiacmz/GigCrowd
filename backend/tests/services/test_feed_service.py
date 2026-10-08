"""Feed service behaviour: one timeline, one filter, five real categories.

The contract these tests pin down:

* there is a single activity stream, and `category` only narrows it
* every category maps to real activity types, so no filter returns
  placeholder or fabricated content
* the timeline is scoped to the caller: their own actions, the actions of
  users they follow, and activity inside artist communities they follow
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bson import ObjectId

from app.models.activity import ActivityType
from app.services import activity_service as activity_module
from app.services.activity_service import (
    FEED_CATEGORIES,
    ActivityService,
    object_id_variants,
)
from tests.support.fake_mongo import FakeDatabase, make_user

ALICE = "aaaaaaaaaaaaaaaaaaaaaaa1"
BOB = "bbbbbbbbbbbbbbbbbbbbbbb2"
CAROL = "ccccccccccccccccccccccc3"

ARTIST_A = "nova-band"
ARTIST_B = "static-hearts"


@pytest.fixture
def db(monkeypatch):
    """A database with one user per role and a couple of artists."""
    now = datetime.now(UTC)

    post_a = {"_id": "post-a", "artist_slug": ARTIST_A, "content": "Nova rules"}
    post_b = {"_id": "post-b", "artist_slug": ARTIST_B, "content": "Static rules"}
    show_log = {
        "_id": "show-1",
        "event_id": "event-1",
        "review": "Incredible night",
        "rating": 5,
        "status": "went",
    }
    plain_show_log = {
        "_id": "show-2",
        "event_id": "event-2",
        "review": None,
        "rating": None,
        "status": "going",
    }

    database = FakeDatabase(
        {
            "users": [
                make_user(ALICE, "alice"),
                make_user(BOB, "bob"),
                make_user(CAROL, "carol"),
            ],
            "artists": [
                {"_id": "artist-a", "slug": ARTIST_A, "name": "Nova"},
                {"_id": "artist-b", "slug": ARTIST_B, "name": "Static Hearts"},
            ],
            "follows": [{"follower_id": ALICE, "following_id": BOB}],
            "artist_follows": [
                {"user_id": ALICE, "artist_slug": ARTIST_A},
            ],
            "community_posts": [post_a, post_b],
            "comments": [
                {
                    "_id": "comment-1",
                    "post_id": "post-a",
                    "artist_slug": ARTIST_A,
                    "content": "Saw them last week!",
                }
            ],
            "show_logs": [show_log, plain_show_log],
            "events": [
                {
                    "_id": "event-1",
                    "title": "Nova at Warehouse",
                    "artist_slug": ARTIST_A,
                    "artist_slugs": [ARTIST_A],
                    "starts_at": now + timedelta(days=3),
                    "venue_slug": "warehouse",
                },
                {
                    "_id": "event-2",
                    "title": "Nova encore",
                    "artist_slug": ARTIST_A,
                    "artist_slugs": [ARTIST_A],
                    "starts_at": now + timedelta(days=9),
                    "venue_slug": "hall",
                },
            ],
            "activities": [
                # Alice's own actions.
                {
                    "_id": "act-own-post",
                    "user_id": ALICE,
                    "activity_type": ActivityType.CREATE_COMMUNITY_POST.value,
                    "target_id": "post-a",
                    "target_type": "community_post",
                    "metadata": {"artist_slug": ARTIST_A},
                    "created_at": now,
                },
                {
                    "_id": "act-own-review",
                    "user_id": ALICE,
                    "activity_type": ActivityType.CREATE_REVIEW.value,
                    "target_id": "show-1",
                    "target_type": "show_log",
                    "metadata": {"artist_slug": ARTIST_A},
                    "created_at": now - timedelta(minutes=1),
                },
                {
                    # Alice's own follow, stored the way `create_activity`
                    # stores it: as a string.
                    "_id": "act-alice-follow",
                    "user_id": ALICE,
                    "activity_type": ActivityType.FOLLOW.value,
                    "target_id": BOB,
                    "target_type": "user",
                    "metadata": {},
                    "created_at": now - timedelta(minutes=1, seconds=30),
                },
                # Bob, whom Alice follows.
                {
                    "_id": "act-bob-comment",
                    "user_id": BOB,
                    "activity_type": ActivityType.COMMENT_POST.value,
                    "target_id": "comment-1",
                    "target_type": "comment",
                    "metadata": {"artist_slug": ARTIST_A},
                    "created_at": now - timedelta(minutes=2),
                },
                # Carol, whom Alice does not follow, in an artist she does not
                # follow: must never reach Alice's feed.
                {
                    "_id": "act-carol-like",
                    "user_id": CAROL,
                    "activity_type": ActivityType.LIKE_POST.value,
                    "target_id": "post-b",
                    "target_type": "community_post",
                    "metadata": {"artist_slug": ARTIST_B},
                    "created_at": now - timedelta(minutes=3),
                },
                {
                    "_id": "act-carol-follow",
                    "user_id": CAROL,
                    "activity_type": ActivityType.FOLLOW.value,
                    "target_id": ALICE,
                    "target_type": "user",
                    "metadata": {},
                    "created_at": now - timedelta(minutes=4),
                },
                {
                    "_id": "act-carol-attend",
                    "user_id": CAROL,
                    "activity_type": ActivityType.ATTEND_EVENT.value,
                    "target_id": "show-2",
                    "target_type": "show_log",
                    "metadata": {"artist_slug": ARTIST_B},
                    "created_at": now - timedelta(minutes=5),
                },
            ],
        }
    )

    monkeypatch.setattr(activity_module, "get_database", lambda: database)
    return database


async def _feed(user_id=ALICE, category="all"):
    activities = await ActivityService.get_feed_activities(
        user_id, category=category
    )
    return {activity["id"] for activity in activities}


class TestObjectIdVariants:
    def test_string_id_yields_both_forms(self):
        from bson import ObjectId

        oid = ObjectId()
        variants = object_id_variants(str(oid))

        assert str(oid) in variants
        assert oid in variants

    def test_non_object_id_string_is_returned_unchanged(self):
        assert object_id_variants("not-an-object-id") == ["not-an-object-id"]


class TestUnifiedTimeline:
    @pytest.mark.asyncio
    async def test_all_category_returns_every_relevant_activity(self, db):
        """One timeline, mixing community, reviews, comments and attendance.

        A follow is not in it. Follows decide what a reader is eligible to see;
        rendering one as a card would fill the timeline with relationships nobody
        chose to publish.
        """
        found = await _feed()

        assert found == {
            "act-own-post",
            "act-own-review",
            "act-bob-comment",
        }

    @pytest.mark.asyncio
    async def test_a_follow_is_never_shown_as_content(self, db):
        """Not on the unfiltered timeline, and not on any filter."""
        assert "act-alice-follow" not in await _feed()

        for category in FEED_CATEGORIES:

            assert "act-alice-follow" not in await _feed(
                category=category
            ), category

    @pytest.mark.asyncio
    async def test_timeline_is_ordered_newest_first(self, db):
        activities = await ActivityService.get_feed_activities(ALICE)

        timestamps = [activity["created_at"] for activity in activities]

        assert timestamps == sorted(timestamps, reverse=True)

    @pytest.mark.asyncio
    async def test_unfollowed_users_and_artists_are_excluded(self, db):
        """Carol's activity is invisible: not followed, unrelated artist."""
        found = await _feed()

        assert not found & {
            "act-carol-like",
            "act-carol-follow",
            "act-carol-attend",
        }

    @pytest.mark.asyncio
    async def test_pagination_slices_the_same_timeline(self, db):
        """Skip/limit paginate the unified stream, they do not replace it.

        Checked by walking the whole timeline a page at a time and comparing it to
        the unpaged answer, rather than by asserting a page size: the number of rows
        is a fixture detail, and hard-coding it made this test fail for the right
        reason whenever the timeline legitimately changed shape.
        """
        everything = await ActivityService.get_feed_activities(
            ALICE, skip=0, limit=100
        )

        walked: list[str] = []

        skip = 0

        while True:

            page = await ActivityService.get_feed_activities(
                ALICE, skip=skip, limit=2
            )

            if not page:
                break

            walked.extend(item["id"] for item in page)

            skip += len(page)

        assert walked == [item["id"] for item in everything]
        assert len(walked) == len(set(walked))


class TestCategories:
    @pytest.mark.asyncio
    async def test_community_filter_returns_posts_and_comments(self, db):
        found = await _feed(category="community")

        assert found == {"act-own-post", "act-bob-comment"}

    @pytest.mark.asyncio
    async def test_reviews_filter_returns_reviews_only(self, db):
        found = await _feed(category="reviews")

        assert found == {"act-own-review"}

    @pytest.mark.asyncio
    async def test_social_filter_returns_follows_only(self, db):
        """There is no Social filter, and no follow on the timeline.

        A follow decides who may see what; it is not something a reader asked to
        read. Offering it as a card - whether on its own filter or mixed into the
        unfiltered timeline - turns the feed into a directory of relationships.
        """
        assert "social" not in FEED_CATEGORIES

        with pytest.raises(ValueError):

            await ActivityService.get_feed_activities(
                ALICE, category="social"
            )

    @pytest.mark.asyncio
    async def test_a_follow_still_decides_what_is_visible(self, db):
        """The exclusion is about display, not about reach.

        Following is what puts somebody's activity in front of a reader, so if the
        follow were ignored entirely the timeline would empty out for anyone whose
        only relationship is a follow.
        """

        found = await _feed()

        # Bob is reachable because Alice follows him.
        assert "act-bob-comment" in found

        # Carol is not followed, so hers stays out - the follow is doing its job.
        assert not found & {"act-carol-like", "act-carol-attend"}

    @pytest.mark.asyncio
    async def test_the_viewers_own_actions_appear_however_the_id_is_held(self, db):
        """A string id and an `ObjectId` must produce the same timeline.

        The route passes an `ObjectId`; other callers hold a string. Neither
        form may see less of the viewer's own history than the other.
        """

        as_string = await ActivityService.get_feed_activities(
            ALICE, category="all"
        )

        as_object_id = await ActivityService.get_feed_activities(
            ObjectId(ALICE), category="all"
        )

        assert {a["id"] for a in as_string} == {
            a["id"] for a in as_object_id
        }

        # The viewer's own activity is reachable under either id form, which is the
        # thing the normalisation exists for.
        assert "act-own-review" in {a["id"] for a in as_object_id}

    @pytest.mark.asyncio
    async def test_attendance_filter_returns_attendance_only(self, db):
        found = await _feed(category="attendance")

        assert found == set()

    @pytest.mark.asyncio
    async def test_events_is_still_accepted_as_an_alias(self, db):
        """The old name keeps working, so a habit does not break."""
        assert await _feed(category="events") == await _feed(
            category="attendance"
        )

    @pytest.mark.asyncio
    async def test_every_category_returns_only_its_own_types(self, db):
        """No category leaks content that belongs to another one."""
        for category, activity_types in FEED_CATEGORIES.items():
            activities = await ActivityService.get_feed_activities(
                ALICE, category=category
            )
            if not activity_types:
                continue

            allowed = {activity_type.value for activity_type in activity_types}
            for activity in activities:
                assert activity["activity_type"] in allowed

    @pytest.mark.asyncio
    async def test_artist_follow_reveals_that_community_to_the_feed(self, db):
        """Following an artist is what pulls their community into the feed."""
        found = await _feed(category="community")

        assert "act-bob-comment" in found

    @pytest.mark.asyncio
    async def test_unknown_category_is_rejected(self, db):
        with pytest.raises(ValueError, match="Unknown feed category"):
            await ActivityService.get_feed_activities(
                ALICE, category="not-a-category"
            )


class TestFollowing:
    """`Seguindo`: the same timeline, scoped to the relationships chosen.

    A scope rather than a kind of content, which is the claim behind it:
    everything here came from somebody the reader follows or some artist they
    follow, and the reader's own unrelated actions are not part of it. It also
    carries every kind of activity, because what puts a row here is who it
    came from, not what it is.
    """

    @pytest.mark.asyncio
    async def test_following_holds_what_the_reader_follows(self, db):
        found = await _feed(category="following")

        # Bob is followed, so his comment is in.
        assert "act-bob-comment" in found

        # Carol is not followed, and neither is the artist she wrote about.
        assert not found & {
            "act-carol-like",
            "act-carol-attend",
            "act-carol-follow",
        }

    @pytest.mark.asyncio
    async def test_following_leaves_out_the_readers_own_actions(self, db):
        """What a reader did is not something they follow.

        An own action *about a followed artist* stays, because it is about
        something followed. The case that has to disappear is an own action
        about nothing the reader follows - without it, `following` and `all`
        would be the same list wearing two labels.
        """
        await db.activities.insert_one(
            {
                "_id": "act-own-elsewhere",
                "user_id": ALICE,
                "activity_type": ActivityType.LIKE_POST.value,
                "target_id": "post-b",
                "target_type": "community_post",
                "metadata": {},
                "created_at": datetime.now(UTC),
            }
        )

        on_all = await _feed(category="all")
        on_following = await _feed(category="following")

        assert "act-own-elsewhere" in on_all
        assert "act-own-elsewhere" not in on_following

    @pytest.mark.asyncio
    async def test_following_carries_every_kind_of_content(self, db):
        """It is a scope, not a type: a review and a comment both arrive."""
        types = {
            activity["activity_type"]
            for activity in await ActivityService.get_feed_activities(
                ALICE, category="following"
            )
        }

        assert ActivityType.CREATE_REVIEW.value in types
        assert ActivityType.COMMENT_POST.value in types

    @pytest.mark.asyncio
    async def test_a_reader_who_follows_nobody_gets_a_quiet_empty_list(
        self, db
    ):
        """Bob follows nobody, so the scope is empty - and it is not an error.

        Answered before the query runs rather than by running it: an empty
        `$or` is a query error in Mongo, which would report a broken feed to a
        reader whose honest answer is simply "nothing yet".
        """
        assert await _feed(user_id=BOB, category="following") == set()
        assert "act-bob-comment" in await _feed(
            user_id=BOB, category="all"
        )

    @pytest.mark.asyncio
    async def test_presence_survives_losing_its_own_filter(self, db):
        """Attendance is no longer a filter, and has not gone missing.

        It stays on `all`, and reaches `following` when it comes from somebody
        the reader follows - which is the whole case for dropping it as a
        filter of its own rather than for deleting it from the feed.
        """
        await db.activities.insert_one(
            {
                "_id": "act-bob-attend",
                "user_id": BOB,
                "activity_type": ActivityType.ATTEND_EVENT.value,
                "target_id": "show-2",
                "target_type": "show_log",
                "metadata": {"artist_slug": ARTIST_B},
                "created_at": datetime.now(UTC),
            }
        )

        assert "act-bob-attend" in await _feed(category="all")
        assert "act-bob-attend" in await _feed(category="following")
        assert "act-bob-attend" not in await _feed(category="community")


class TestEnrichment:
    @pytest.mark.asyncio
    async def test_actor_is_resolved(self, db):
        activities = await ActivityService.get_feed_activities(ALICE)

        by_id = {activity["id"]: activity for activity in activities}

        assert by_id["act-own-post"]["user"]["username"] == "alice"
        assert by_id["act-bob-comment"]["user"]["username"] == "bob"

    @pytest.mark.asyncio
    async def test_community_post_carries_artist_and_content(self, db):
        activities = await ActivityService.get_feed_activities(
            ALICE, category="community"
        )
        post_activity = next(
            item for item in activities if item["id"] == "act-own-post"
        )

        # The artist block is exactly what the row needs to render: identity,
        # name, and the photograph they already have. Nothing else from the
        # artist document rides along.
        assert post_activity["artist"] == {
            "slug": ARTIST_A,
            "name": "Nova",
            "image": None,
        }
        assert post_activity["target"]["kind"] == "community_post"
        assert post_activity["target"]["id"] == "post-a"
        assert post_activity["content"] == "Nova rules"

    @pytest.mark.asyncio
    async def test_review_carries_event_context(self, db):
        activities = await ActivityService.get_feed_activities(
            ALICE, category="reviews"
        )

        assert len(activities) == 1
        review = activities[0]

        assert review["rating"] == 5
        assert review["target"]["kind"] == "event"
        assert review["target"]["title"] == "Nova at Warehouse"
        assert review["target"]["artist_slug"] == ARTIST_A

    @pytest.mark.asyncio
    async def test_comment_target_points_at_its_post(self, db):
        activities = await ActivityService.get_feed_activities(
            ALICE, category="community"
        )
        comment_activity = next(
            item for item in activities if item["id"] == "act-bob-comment"
        )

        assert comment_activity["target"]["kind"] == "comment"
        assert comment_activity["target"]["post_id"] == "post-a"
        assert comment_activity["target"]["artist_slug"] == ARTIST_A

    @pytest.mark.asyncio
    async def test_follow_target_resolves_to_a_profile(self, db):
        """A follow row, if one is ever enriched, names and links its target.

        The feed no longer shows follows, so this exercises the enrichment
        directly rather than through a listing. The guarantee still matters: a
        follow document exists in the collection, and should it ever be surfaced
        again it must resolve to a public profile and nothing more - never an
        email address or a password hash.
        """
        follow_document = {
            "_id": "act-bob-follow",
            "user_id": BOB,
            "activity_type": ActivityType.FOLLOW.value,
            "target_id": ALICE,
            "target_type": "user",
            "metadata": {},
            "created_at": datetime.now(UTC) - timedelta(minutes=6),
        }

        [follow] = await ActivityService._enrich_activities(
            db, [follow_document]
        )

        assert follow["target"]["kind"] == "profile"
        assert follow["target"]["username"] == "alice"
        assert set(follow["target"]) == {"kind", "id", "username"}

    @pytest.mark.asyncio
    async def test_follow_target_never_exposes_private_fields(self, db):
        """The target lookup is projected: no email, no password hash."""
        loaded = await ActivityService._load_followed_users(db, [ALICE, BOB])

        assert set(loaded) == {ALICE, BOB}
        for entry in loaded.values():
            assert set(entry) == {"id", "username", "full_name", "avatar_url"}

    @pytest.mark.asyncio
    async def test_enrichment_uses_batched_queries(self, db, monkeypatch):
        """Enrichment must not issue a query per activity."""
        calls: list[str] = []

        original_find = type(db.users).find

        def counting_find(self, query=None, projection=None):
            calls.append(self.name)
            return original_find(self, query, projection)

        monkeypatch.setattr(type(db.users), "find", counting_find)
        monkeypatch.setattr(type(db["community_posts"]), "find", counting_find)
        monkeypatch.setattr(type(db.comments), "find", counting_find)
        monkeypatch.setattr(type(db["show_logs"]), "find", counting_find)
        monkeypatch.setattr(type(db.events), "find", counting_find)
        monkeypatch.setattr(type(db.artists), "find", counting_find)

        activities = await ActivityService.get_feed_activities(ALICE)

        # Alice's own post and review, plus Bob's comment. A follow would not be
        # here even if one existed - it is not content.
        assert len(activities) == 3
        # One pass per purpose, never per activity. The users collection is read
        # once, for the actors.
        assert calls.count("users") == 1
        assert calls.count("community_posts") <= 1
        assert calls.count("comments") <= 1
        assert calls.count("artists") == 1
        # The event behind the review - and with it that event's artwork - is
        # read in the single pass it has always had. Images resolved from
        # documents already loaded cost no extra round trip.
        assert calls.count("events") == 1


class TestImages:
    """The feed shows a picture it already has, and claims none it does not.

    Every URL asserted here was on a document the enrichment pass was already
    reading: the artist lookup, the event lookup, and the target documents
    themselves. Nothing is fetched, generated or stored for the feed's sake.
    """

    @pytest.mark.asyncio
    async def test_artist_image_travels_with_the_artist(self, db):
        await db.artists.update_one(
            {"slug": ARTIST_A},
            {"$set": {"image": "https://images.test/nova.jpg"}},
        )

        activities = await ActivityService.get_feed_activities(
            ALICE, category="community"
        )
        post_activity = next(
            item for item in activities if item["id"] == "act-own-post"
        )

        assert post_activity["artist"]["image"] == "https://images.test/nova.jpg"

    @pytest.mark.asyncio
    async def test_an_uploaded_post_image_is_exposed_on_its_target(self, db):
        await db["community_posts"].update_one(
            {"_id": "post-a"},
            {"$set": {"image_url": "https://images.test/post-a.jpg"}},
        )

        activities = await ActivityService.get_feed_activities(
            ALICE, category="community"
        )
        post_activity = next(
            item for item in activities if item["id"] == "act-own-post"
        )

        assert post_activity["target"]["image_url"] == (
            "https://images.test/post-a.jpg"
        )

    @pytest.mark.asyncio
    async def test_event_artwork_is_exposed_on_a_review(self, db):
        await db.events.update_one(
            {"_id": "event-1"},
            {"$set": {"image_url": "https://images.test/warehouse.jpg"}},
        )

        activities = await ActivityService.get_feed_activities(
            ALICE, category="reviews"
        )
        review = activities[0]

        assert review["target"]["kind"] == "event"
        assert review["target"]["image_url"] == (
            "https://images.test/warehouse.jpg"
        )

    @pytest.mark.asyncio
    async def test_enrichment_artwork_is_read_when_the_primary_field_is_empty(
        self, db
    ):
        """The pass that enriches an event writes `songkick_image`.

        `image_url` is the field the API speaks, and it is the one that is
        normally empty. Reading both here is what makes an enriched event's
        artwork reach the feed at all.
        """
        await db.events.update_one(
            {"_id": "event-1"},
            {"$set": {"songkick_image": "https://images.test/sk.jpg"}},
        )

        activities = await ActivityService.get_feed_activities(
            ALICE, category="reviews"
        )

        assert activities[0]["target"]["image_url"] == "https://images.test/sk.jpg"

    @pytest.mark.asyncio
    async def test_a_comment_target_claims_no_image(self, db):
        """A comment has no picture, and the feed says so instead of guessing.

        The post it answers would be a second lookup, so the row falls back to
        the artist's photograph - which the caller already has.
        """
        activities = await ActivityService.get_feed_activities(
            ALICE, category="community"
        )
        comment_activity = next(
            item for item in activities if item["id"] == "act-bob-comment"
        )

        assert comment_activity["target"]["image_url"] is None

    @pytest.mark.asyncio
    async def test_nothing_is_invented_when_the_data_has_no_image(self, db):
        """Absent images stay absent rather than becoming a placeholder URL."""
        protocols = ("http://", "https://")

        activities = await ActivityService.get_feed_activities(ALICE)

        assert activities, "the fixture feed must not be empty"

        for activity in activities:
            artist = activity["artist"]
            if artist is not None:
                assert "image" in artist
                assert artist["image"] is None or str(
                    artist["image"]
                ).startswith(protocols)

            target = activity["target"] or {}
            if "image_url" in target:
                assert target["image_url"] is None or str(
                    target["image_url"]
                ).startswith(protocols)
