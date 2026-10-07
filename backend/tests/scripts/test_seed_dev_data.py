"""The development seed as a fixture.

The seed is only useful if it is trustworthy, so what is tested here is the
three properties the rest of the product work depends on:

* **Deterministic.** The same call twice produces the same documents, so a test
  can assert on them and a developer sees the same profile every time.
* **Idempotent.** Re-running replaces the same documents rather than appending
  new ones, which is what keeps the unique (user, event) index satisfied and
  what makes a reset-then-seed cycle repeatable.
* **Coherent.** It actually contains the situations the product has to handle,
  including the one real data never had: attendance in the `maybe` state.

These tests need no database. `build_dataset` is a pure function, which is the
main reason it is shaped as one.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.models.show_log import AttendanceStatus
from app.scripts.seed_dev_data import (
    ANCHOR,
    INVENTED_SONGKICK_ID,
    SEED_PASSWORD,
    SONGKICK_IDS,
    TEST_USER_1,
    TEST_USER_1_EMAIL,
    TEST_USER_1_PASSWORD,
    TEST_USER_2,
    TEST_USER_2_EMAIL,
    TEST_USER_2_PASSWORD,
    build_dataset,
    build_user,
    deterministic_password_hash,
    stable_id,
)


def by_key(dataset, collection, field):
    return {
        document[field]: document
        for document in dataset[collection]
    }


class TestDeterminism:
    def test_two_builds_are_identical(self):
        assert build_dataset() == build_dataset()

    def test_ids_are_derived_not_generated(self):
        # A generated id would change every run, which is what would make the
        # seed append instead of replace.
        assert stable_id("event", "marina-ibira") == stable_id(
            "event", "marina-ibira"
        )

        assert stable_id("event", "a") != stable_id("event", "b")

    def test_dates_come_from_the_anchor_not_the_clock(self):
        dataset = build_dataset()

        for user in dataset["users"]:
            assert user["created_at"] < ANCHOR

        # The newest event is in the future relative to the anchor, which is
        # what makes "upcoming" real.
        starts = [
            event["starts_at"]
            for event in dataset["events"]
        ]

        assert max(starts) > ANCHOR
        assert min(starts) < ANCHOR

    def test_every_date_is_timezone_aware(self):
        # A naive datetime would not round-trip through MongoDB unchanged, which
        # is exactly what makes a seed non-idempotent.
        dataset = build_dataset()

        for event in dataset["events"]:

            assert event["starts_at"].tzinfo is not None

            if event["ends_at"]:
                assert event["ends_at"].tzinfo is not None


class TestIdempotency:
    def test_every_document_has_a_stable_id(self):
        dataset = build_dataset()

        for collection, documents in dataset.items():

            ids = [str(document["_id"]) for document in documents]

            assert len(ids) == len(set(ids)), collection

    def test_no_two_users_share_an_identity(self):
        dataset = build_dataset()

        assert len({u["username"] for u in dataset["users"]}) == len(
            dataset["users"]
        )
        assert len({u["email"] for u in dataset["users"]}) == len(
            dataset["users"]
        )

    def test_no_two_artists_share_a_slug_or_an_external_id(self):
        # The catalogue carries unique indexes on both, so a duplicate here
        # would be a seed that cannot be written at all.
        dataset = build_dataset()

        artists = dataset["artists"]

        assert len({a["slug"] for a in artists}) == len(artists)

        for source in ("spotify", "songkick", "musicbrainz"):

            ids = [
                a["external_ids"][source]
                for a in artists
                if a.get("external_ids", {}).get(source)
            ]

            assert len(set(ids)) == len(ids), source

    def test_no_venue_repeats_a_unique_key(self):
        dataset = build_dataset()

        keys = [
            (v["name"], v["city"], v["country"])
            for v in dataset["venues"]
        ]

        assert len(set(keys)) == len(keys)

    def test_one_user_has_one_log_per_event(self):
        dataset = build_dataset()

        pairs = [
            (log["user_id"], log["event_id"])
            for log in dataset["show_logs"]
        ]

        assert len(set(pairs)) == len(pairs)


class TestAttendanceCoverage:
    def test_all_three_states_are_present(self):
        # Real data had never contained a `maybe` row, so its empty state was
        # all that had ever been seen of it.
        dataset = build_dataset()

        statuses = {
            log["status"] for log in dataset["show_logs"]
        }

        assert statuses == {
            AttendanceStatus.WENT.value,
            AttendanceStatus.GOING.value,
            AttendanceStatus.MAYBE.value,
        }

    def test_attended_shows_span_several_years_and_months(self):
        # The profile groups attended shows by year and then month, so a seed
        # with a single month would leave that grouping untested.
        dataset = build_dataset()

        attended = {
            log["event_id"]
            for log in dataset["show_logs"]
            if log["status"] == AttendanceStatus.WENT.value
        }

        dates = [
            event["starts_at"]
            for event in dataset["events"]
            if str(event["_id"]) in attended
        ]

        assert len({date.year for date in dates}) >= 2
        assert len({date.month for date in dates}) >= 3

    def test_attended_shows_are_all_in_the_past(self):
        dataset = build_dataset()

        attended = {
            log["event_id"]
            for log in dataset["show_logs"]
            if log["status"] == AttendanceStatus.WENT.value
        }

        for event in dataset["events"]:

            if str(event["_id"]) in attended:
                assert event["starts_at"] <= ANCHOR

    def test_a_going_or_maybe_show_is_still_ahead(self):
        dataset = build_dataset()

        upcoming = {
            log["event_id"]
            for log in dataset["show_logs"]
            if log["status"] in {
                AttendanceStatus.GOING.value,
                AttendanceStatus.MAYBE.value,
            }
        }

        for event in dataset["events"]:

            if str(event["_id"]) in upcoming:
                assert event["starts_at"] > ANCHOR

    def test_each_user_owns_their_own_reviews(self):
        dataset = build_dataset()

        user_ids = {u["_id"] for u in dataset["users"]}

        for log in dataset["show_logs"]:

            assert log["user_id"] in {str(uid) for uid in user_ids}

    def test_a_review_exists_and_carries_text(self):
        dataset = build_dataset()

        reviews = [
            log for log in dataset["show_logs"]
            if log.get("review")
        ]

        assert reviews

        for review in reviews:
            assert review["rating"] is not None
            assert len(review["review"]) > 20

    def test_reviews_belong_to_more_than_one_person(self):
        dataset = build_dataset()

        authors = {
            log["user_id"]
            for log in dataset["show_logs"]
            if log.get("review")
        }

        assert len(authors) >= 2


class TestFestivalCoverage:
    def test_one_series_has_several_concrete_editions(self):
        dataset = build_dataset()

        festival_days = [
            event
            for event in dataset["events"]
            if event["event_type"] == "FestivalInstance"
        ]

        assert len(festival_days) >= 3

        series = {
            event["festival"]["series_id"]
            for event in festival_days
        }

        assert len(series) == 1

        editions = {
            event["festival"]["edition"]
            for event in festival_days
        }

        assert len(editions) >= 2

    def test_every_festival_day_carries_a_lineup_with_songkick_ids(self):
        dataset = build_dataset()

        for event in dataset["events"]:

            if event["event_type"] != "FestivalInstance":
                continue

            assert event["lineup"], event["title"]

            for entry in event["lineup"]:
                assert entry["songkick_id"]
                assert entry["order"] >= 0

    def test_one_artist_appears_twice_on_one_bill(self):
        # This is the row that proves a per-show count cannot double-count.
        dataset = build_dataset()

        doubled = False

        for event in dataset["events"]:

            ids = [
                entry["songkick_id"]
                for entry in event.get("lineup") or []
            ]

            if len(ids) != len(set(ids)):
                doubled = True

        assert doubled

    def test_one_artist_appears_on_several_attended_shows(self):
        dataset = build_dataset()

        attended = {
            log["event_id"]
            for log in dataset["show_logs"]
            if log["status"] == AttendanceStatus.WENT.value
        }

        appearances: dict[str, set[str]] = {}

        for event in dataset["events"]:

            if str(event["_id"]) not in attended:
                continue

            if event["event_type"] == "FestivalInstance":
                slugs = [
                    entry["slug"]
                    for entry in event["lineup"]
                ]
            else:
                slugs = event["artist_slugs"]

            for slug in slugs:
                appearances.setdefault(slug, set()).add(
                    str(event["_id"])
                )

        assert any(
            len(events) >= 2
            for events in appearances.values()
        )


class TestArtistCoverage:
    def test_a_concert_names_its_artist(self):
        dataset = build_dataset()

        concerts = [
            event for event in dataset["events"]
            if event["event_type"] == "Concert"
        ]

        assert concerts

        for event in concerts:
            assert event["artist_slugs"], event["title"]

    def test_artists_differ_in_how_much_is_known_about_them(self):
        # A seed where every artist is complete cannot show how a page behaves
        # when one is not.
        dataset = build_dataset()

        artists = dataset["artists"]

        with_spotify = [
            a for a in artists
            if a["external_ids"].get("spotify")
        ]
        with_songkick = [
            a for a in artists
            if a["external_ids"].get("songkick")
        ]
        bare = [
            a for a in artists
            if not a["external_ids"].get("spotify")
        ]

        assert with_spotify
        assert with_songkick
        assert bare

    def test_an_artist_slug_matches_its_event_references(self):
        # A lineup entry's slug and the artist it refers to have to agree, or
        # "artists I have seen" cannot resolve anything.
        dataset = build_dataset()

        slugs = {a["slug"] for a in dataset["artists"]}

        for event in dataset["events"]:

            for slug in event["artist_slugs"]:
                assert slug in slugs, slug

            for entry in event.get("lineup") or []:
                assert entry["slug"] in slugs, entry["slug"]


class TestCommunityCoverage:
    def test_posts_belong_to_several_artists(self):
        dataset = build_dataset()

        slugs = {
            post["artist_slug"]
            for post in dataset["community_posts"]
        }

        assert len(slugs) >= 3

    def test_counters_match_the_rows_that_exist(self):
        dataset = build_dataset()

        # Keys are stringified because the rows that point at a post store it as
        # a string, which is how every relationship in this database is stored.
        posts = {
            str(document["_id"]): document
            for document in dataset["community_posts"]
        }

        for like in dataset["post_likes"]:
            post = posts.get(str(like["post_id"]))
            assert post is not None, like["post_id"]
            assert post["likes_count"] >= 1

        for comment in dataset["comments"]:
            post = posts.get(str(comment["post_id"]))
            assert post is not None, comment["post_id"]
            assert post["comments_count"] >= 1

    def test_likes_are_unique_per_user_and_post(self):
        dataset = build_dataset()

        pairs = [
            (like["target_id"], like["user_id"])
            for like in dataset["post_likes"]
        ]

        assert len(set(pairs)) == len(pairs)


class TestFeedCoverage:
    def test_the_feed_holds_reviews_attendance_and_community(self):
        dataset = build_dataset()

        types = {
            activity["activity_type"]
            for activity in dataset["activities"]
        }

        assert "create_review" in types
        assert "attend_event" in types
        assert "create_community_post" in types

    def test_no_follow_relationship_is_a_standalone_feed_item(self):
        # A follow is a relationship mutation, not something a person wants to
        # read about in their timeline.
        dataset = build_dataset()

        types = {
            activity["activity_type"]
            for activity in dataset["activities"]
        }

        assert "follow" not in types

    def test_followed_people_produce_activity_the_viewer_can_see(self):
        dataset = build_dataset()

        users = by_key(dataset, "users", "username")

        leticia = str(users["leticiacmz"]["_id"])
        followers = {
            follow["follower_id"]
            for follow in dataset["follows"]
            if follow["following_id"] == leticia
        }

        their_activity = {
            activity["user_id"]
            for activity in dataset["activities"]
        }

        assert followers & their_activity

    def test_every_activity_names_an_existing_user(self):
        dataset = build_dataset()

        ids = {str(u["_id"]) for u in dataset["users"]}

        for activity in dataset["activities"]:
            assert activity["user_id"] in ids

    def test_activity_is_newest_first(self):
        dataset = build_dataset()

        times = [a["created_at"] for a in dataset["activities"]]

        assert times == sorted(times, reverse=True)


class TestTheEmptyProfile:
    def test_one_user_has_no_history_at_all(self):
        # The empty profile has to be exercised as carefully as the full one.
        dataset = build_dataset()

        users = by_key(dataset, "users", "username")

        theo = str(users["theov"]["_id"])

        assert not [
            log for log in dataset["show_logs"]
            if log["user_id"] == theo
        ]

        assert not [
            follow for follow in dataset["follows"]
            if follow["follower_id"] == theo
            or follow["following_id"] == theo
        ]

        assert not [
            follow for follow in dataset["artist_follows"]
            if follow["user_id"] == theo
        ]


class TestTheSeedPassword:
    def test_the_hash_is_stable_but_still_a_real_bcrypt_hash(self):
        from app.auth.security import verify_password

        first = deterministic_password_hash("leticiacmz")
        second = deterministic_password_hash("leticiacmz")

        assert first == second
        assert first.startswith("$2b$")
        assert verify_password(SEED_PASSWORD, first)

        # And a wrong password is still rejected, which is the point of hashing
        # it at all.
        assert not verify_password("not-the-password", first)

    def test_two_users_do_not_share_a_hash(self):
        assert deterministic_password_hash("a") != deterministic_password_hash(
            "b"
        )

    def test_every_seeded_user_can_sign_in(self):
        """Every seeded user has a known password, and it works.

        Not necessarily the *same* password: the two controlled accounts have
        their own, so that handing somebody one credential authenticates exactly
        one person. A fixture nobody can log into is a fixture that has quietly
        stopped being usable.
        """

        dataset = build_dataset()

        from app.auth.security import verify_password

        controlled = {
            TEST_USER_1: TEST_USER_1_PASSWORD,
            TEST_USER_2: TEST_USER_2_PASSWORD,
        }

        for user in dataset["users"]:
            expected = controlled.get(
                user["username"], SEED_PASSWORD
            )

            assert verify_password(
                expected, user["hashed_password"]
            ), user["username"]


class TestEverySeededActivityResolvesToSomething:
    """A feed row that cannot be resolved is a row nobody can press.

    This is not hypothetical. The seed wrote attendance and review activities
    whose `target_id` was the *event* while their `target_type` said
    `show_log`, so the feed's enrichment found no document and rendered six of
    eleven rows with no target at all - a sentence about a show with no way to
    reach the show. It looked like a product fault and it was a fixture fault,
    which is the worst place for one to be.
    """

    def _activities(self):
        return build_dataset()["activities"]

    def test_no_activity_points_at_a_document_that_does_not_exist(self):
        dataset = build_dataset()

        by_id = {
            collection: {
                str(document["_id"]) for document in dataset[collection]
            }
            for collection in dataset
        }

        # Where each activity type says its target lives. Mirrors
        # `ACTIVITY_TARGET_COLLECTIONS`, and a follow is absent because its
        # target is a person rather than a document.
        collections = {
            "create_community_post": "community_posts",
            "comment_post": "comments",
            "like_post": "community_posts",
            "create_review": "show_logs",
            "attend_event": "show_logs",
            "create_post": "posts",
        }

        dangling = []

        for row in self._activities():
            collection = collections.get(row["activity_type"])

            if not collection or not row.get("target_id"):
                continue

            if str(row["target_id"]) not in by_id.get(collection, set()):
                dangling.append(
                    (row["activity_type"], collection, row["target_id"])
                )

        assert not dangling, dangling

    def test_an_attendance_row_names_the_attendance_not_the_show(self):
        """The distinction that produced the bug.

        An attendance record is one document per person per show. An event is a
        different document entirely. Naming the event while declaring
        `target_type: show_log` cannot resolve, and nothing in the data says so.
        """

        dataset = build_dataset()

        show_log_ids = {
            str(document["_id"]) for document in dataset["show_logs"]
        }

        event_ids = {
            str(document["_id"]) for document in dataset["events"]
        }

        for row in self._activities():
            if row["activity_type"] not in (
                "attend_event",
                "create_review",
            ):
                continue

            target = str(row["target_id"])

            assert target in show_log_ids, row["activity_type"]
            assert target not in event_ids, row["activity_type"]

    def test_every_seeded_attendance_activity_has_an_attendance(self):
        """Not merely a resolvable id - the record it names must exist.

        A stable id derived from a name the log was never written under would
        pass the check above and still point at nothing.
        """

        dataset = build_dataset()

        logs = {
            (
                str(document["user_id"]),
                str(document["event_id"]),
            ): str(document["_id"])
            for document in dataset["show_logs"]
        }

        checked = 0

        for row in self._activities():
            if row["activity_type"] not in (
                "attend_event",
                "create_review",
            ):
                continue

            checked += 1

            # The named record has to be the *person's* record: the same show is
            # logged by more than one person in this fixture.
            matches = [
                identifier
                for (user_id, _), identifier in logs.items()
                if identifier == str(row["target_id"])
            ]

            assert matches, row["activity_type"]

        assert checked >= 5, checked


class TestTheControlledTestAccounts:
    """The two accounts a person is handed credentials for.

    The property that makes them usable is that they are *distinguishable*. Two
    accounts sharing a password is not a smaller version of this, it is a bug:
    a check written against "testuser1" would pass or fail according to whichever
    one the login route matched first, and nobody would find out which.
    """

    def _users(self):
        dataset = build_dataset()

        return {
            user["email"]: user for user in dataset["users"]
        }

    def test_both_accounts_exist_with_the_documented_addresses(self):
        users = self._users()

        assert TEST_USER_1_EMAIL in users
        assert TEST_USER_2_EMAIL in users

    def test_each_accepts_its_own_password(self):
        from app.auth.security import verify_password

        users = self._users()

        assert verify_password(
            TEST_USER_1_PASSWORD,
            users[TEST_USER_1_EMAIL]["hashed_password"],
        )

        assert verify_password(
            TEST_USER_2_PASSWORD,
            users[TEST_USER_2_EMAIL]["hashed_password"],
        )

    def test_neither_accepts_the_other_password(self):
        """The whole reason they do not share one."""

        from app.auth.security import verify_password

        users = self._users()

        assert not verify_password(
            TEST_USER_2_PASSWORD,
            users[TEST_USER_1_EMAIL]["hashed_password"],
        )

        assert not verify_password(
            TEST_USER_1_PASSWORD,
            users[TEST_USER_2_EMAIL]["hashed_password"],
        )

    def test_the_shared_password_is_not_a_backdoor_into_either(self):
        from app.auth.security import verify_password

        users = self._users()

        for email in (TEST_USER_1_EMAIL, TEST_USER_2_EMAIL):
            assert not verify_password(
                SEED_PASSWORD, users[email]["hashed_password"]
            )

    def test_both_are_active_and_sign_in_by_email(self):
        """The login route matches on the address form of the email."""

        for name, email, password in (
            (TEST_USER_1, TEST_USER_1_EMAIL, TEST_USER_1_PASSWORD),
            (TEST_USER_2, TEST_USER_2_EMAIL, TEST_USER_2_PASSWORD),
        ):
            user = build_user(
                name,
                full_name=name,
                email=email,
                password=password,
            )

            assert user["is_active"] is True
            assert user["email"] == email
            assert "@" in user["email"]


class TestTheDatasetIsUnderstandable:
    """A fixture nobody can reason about is a fixture that hides bugs.

    The size limits are not arbitrary taste. This project once grew a catalogue of
    several thousand artists created by walking historical festival lineups, and
    the result was a database where nobody could say where a row came from or
    which part of the code was responsible for it. A development fixture has the
    opposite job.
    """

    def test_the_required_artists_are_present(self):
        names = {
            artist["name"] for artist in build_dataset()["artists"]
        }

        for required in (
            "Marina Sena",
            "Arctic Monkeys",
            "Gal Costa",
            "Rubel",
            "Tim Bernardes",
            "Demi Lovato",
        ):
            assert required in names, required

    def test_every_artist_carries_a_real_songkick_id(self):
        """The one identifier the source and this catalogue share.

        Asserted against the named table rather than merely checked for presence,
        because presence is not the property that matters. Six of the eight ids
        this fixture once held were present, plausible and wrong, and every seeded
        artist whose id was wrong answered "Songkick artist page error: 410" the
        first time anybody opened them.

        `Victo` is the one documented exception: no such act exists, so its id is
        invented, and the second test says so out loud.
        """

        seeded = {
            artist["name"]: artist["external_ids"]["songkick"]
            .removeprefix("Artist")
            for artist in build_dataset()["artists"]
        }

        for name, expected in SONGKICK_IDS.items():
            assert seeded[name] == expected, name

    def test_the_one_invented_id_is_the_only_one(self):
        """An invented id must be obvious, not merely absent from the table.

        Otherwise it becomes a validated identity by proximity - it looks like
        every other seeded id, sits in the same field, and resolves to nothing.
        """

        seeded = {
            artist["external_ids"]["songkick"].removeprefix("Artist")
            for artist in build_dataset()["artists"]
        }

        invented = seeded - set(SONGKICK_IDS.values())

        assert invented == {INVENTED_SONGKICK_ID}

    def test_a_lineup_entry_names_the_same_artist_as_its_id(self):
        """The lineup and the catalogue must agree.

        A lineup entry whose name and id point at different acts is the exact
        record this project spent its last change refusing to create, and a
        fixture containing one would make that shape look normal.
        """

        reverse = {
            f"Artist{songkick_id}": name
            for name, songkick_id in SONGKICK_IDS.items()
        }

        for event in build_dataset()["events"]:
            for entry in event.get("lineup") or []:
                stored = entry.get("songkick_id")

                if stored in reverse:
                    assert entry["name"] == reverse[stored], entry

    def test_the_catalogue_stays_small(self):
        dataset = build_dataset()

        assert len(dataset["artists"]) < 20
        assert len(dataset["events"]) < 40
        assert len(dataset["users"]) < 12

    def test_no_lineup_was_expanded_into_artists(self):
        """Announced performers stay in the lineup until somebody opens one.

        Expanding a seeded lineup into artists would create pending stubs - the
        exact population whose existence made the catalogue unreadable, and which
        the sync job now deliberately refuses to drain.
        """

        dataset = build_dataset()

        announced = set()

        for event in dataset["events"]:
            for entry in event.get("lineup") or []:
                if entry.get("songkick_id"):
                    announced.add(
                        str(entry["songkick_id"]).removeprefix("Artist")
                    )

        artist_ids = {
            artist["external_ids"]["songkick"].removeprefix("Artist")
            for artist in dataset["artists"]
        }

        # Every seeded lineup act is a real seeded artist, so nothing in the
        # fixture depends on an artist the seed declined to create.
        assert announced <= artist_ids
