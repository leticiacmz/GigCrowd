"""The inventory's promises, asserted against a fake database.

An audit of a production database is only trustworthy if it cannot write to
it, so the load-bearing promise is tested first and directly: a run over a
fake database whose every write method raises must complete normally. The
remaining tests pin the classifications that plan the repair work - what
counts as *confirmed* versus *needs analysis* - because a census that
over-claims (calling every unexplained slug a fault) would authorise repairs
the evidence does not support.

The known legacy formats are exercised on purpose: `Artist12345` versus bare
digits, `songkickId` versus `songkick_id`, `artist_slug` versus
`artist_slugs`, absent versus stored-null `last_synced_at`, and string
versus `ObjectId` identifiers. Each one silently changes a count if ignored.
"""
from __future__ import annotations

from datetime import datetime

import pytest
from bson import ObjectId

from app.scripts.inventory_atlas import (
    collect,
    is_festival_type,
    lineup_songkick_ids,
    render,
    songkick_digits,
    stored_artist_slugs,
)
from tests.support.fake_mongo import FakeCollection, FakeDatabase


def a_world(**collections):
    return FakeDatabase(collections)


def an_event(**overrides):
    return {
        "_id": ObjectId(),
        "title": "A Show",
        "event_type": "Concert",
        "starts_at": None,
        "venue_slug": "some-venue",
        "artist_slugs": ["some-artist"],
        **overrides,
    }


def artist(slug, songkick, **extra):
    document = {
        "_id": ObjectId(),
        "slug": slug,
        "external_ids": {"songkick": songkick},
    }
    document.update(extra)
    return document


@pytest.mark.asyncio
class TestItNeverWrites:
    """The load-bearing promise, tested directly rather than described."""

    @pytest.mark.parametrize(
        "method",
        [
            "insert_one",
            "update_one",
            "update_many",
            "delete_one",
            "delete_many",
            "find_one_and_update",
        ],
    )
    async def test_every_write_method_raises_and_the_run_still_completes(
        self, method, monkeypatch
    ):
        """A full census over a world whose writes are impossible.

        If any code path in `collect` reached for a write, the run would
        raise - which is precisely the failure this test exists to catch,
        rather than a write quietly succeeding against a real database.
        """

        def refuse(self, *args, **kwargs):
            raise AssertionError(
                f"the inventory called the write method {method!r}"
            )

        monkeypatch.setattr(FakeCollection, method, refuse)

        world = a_world(
            events=[an_event()],
            artists=[artist("a-artist", "Artist1")],
            show_logs=[],
            activities=[],
            venues=[],
        )

        report = await collect(world)

        assert report["events"]["total"] == 1

    async def test_the_report_says_so_in_words(self):
        world = a_world()

        text = render(await collect(world))

        assert "Nothing was written" in text
        assert "read-only" in text


@pytest.mark.asyncio
class TestEventTypesAreCountedAsStored:
    async def test_every_spelling_is_its_own_row(self):
        """The canonical-type migration plans from these counts, so the
        census must not normalise them into one bucket."""

        world = a_world(
            events=[
                an_event(event_type="Concert"),
                an_event(event_type="Concert"),
                an_event(event_type="FestivalInstance"),
                an_event(event_type="festival"),
            ]
        )

        report = await collect(world)

        assert report["events"]["by_event_type"] == {
            "Concert": 2,
            "FestivalInstance": 1,
            "festival": 1,
        }

    async def test_a_document_with_no_type_is_counted_as_unset(self):
        world = a_world(events=[an_event(event_type=None)])

        report = await collect(world)

        assert report["events"]["by_event_type"] == {"<unset>": 1}

@pytest.mark.asyncio
class TestDuplicateEventsAreMeasuredNotAssumed:
    async def test_two_events_one_songkick_id_is_a_group(self):
        world = a_world(
            events=[
                an_event(external_ids={"songkick": "42949062"}),
                an_event(external_ids={"songkick": "42949062"}),
                an_event(external_ids={"songkick": "1"}),
            ]
        )

        report = await collect(world)

        duplicates = report["events"]["songkick_duplicates"]
        assert duplicates["groups"] == 1
        assert duplicates["events_involved"] == 2
        assert duplicates["sample"][0]["songkick_id"] == "42949062"

    async def test_events_without_a_songkick_id_never_group(self):
        """A missing id is not a shared id; treating it as one would report
        the entire undated backlog as duplicates of each other."""

        world = a_world(events=[an_event(), an_event()])

        report = await collect(world)

        assert report["events"]["songkick_duplicates"]["groups"] == 0


@pytest.mark.asyncio
class TestFestivalEditionsAndSeries:
    async def test_editions_group_by_series_and_gaps_are_separate(self):
        world = a_world(
            events=[
                an_event(festival={"series_id": "99", "name": "Rock In Rio"}),
                an_event(festival={"series_id": "99", "name": "Rock In Rio"}),
                an_event(festival={"name": "No Series Yet"}),
            ]
        )

        report = await collect(world)
        festivals = report["festivals"]

        assert festivals["editions_total"] == 3
        assert festivals["series_count"] == 1
        # Without a series id the edition can never join a series page, so it
        # is a structural gap and is counted apart from the grouped series.
        assert festivals["editions_without_series_id"] == 1
        assert festivals["largest_series"] == [
            {"series_id": "99", "editions": 2}
        ]

    async def test_the_spelling_divergence_is_reported_both_ways(self):
        """`event_type` and the festival block can disagree, and the page
        tests disagree with each other about which one wins."""

        world = a_world(
            events=[
                an_event(
                    event_type="FestivalInstance",
                    festival={"series_id": "1"},
                ),
                an_event(event_type="festival"),
            ]
        )

        report = await collect(world)
        festivals = report["festivals"]

        assert festivals["type_says_festival_but_no_block"] == 1
        assert festivals["block_present_but_type_not_festival"] == 0


class TestLegacyFormatsAreRead:
    """The format knowledge, as pure functions.

    Kept out of the async classes on purpose: these need no database, and a
    synchronous test carrying an asyncio mark is a warning every run.
    """

    def test_the_festival_test_matches_the_backend_word_not_the_spelling(self):
        assert is_festival_type("FestivalInstance") is True
        assert is_festival_type("festival") is True
        assert is_festival_type("Concert") is False
        assert is_festival_type(None) is False

    def test_lineup_ids_honour_both_key_spellings(self):
        lineup = [
            {"songkick_id": "10"},
            {"songkickId": "20"},
            {"name": "no id at all"},
        ]

        assert lineup_songkick_ids(lineup) == ["10", "20"]

    def test_digits_are_reduced_from_either_artist_spelling(self):
        assert songkick_digits("Artist12345") == "12345"
        assert songkick_digits("12345") == "12345"
        assert songkick_digits("not-an-id") is None
        assert songkick_digits(None) is None

    def test_the_singular_transitional_slug_counts_as_stored(self):
        assert stored_artist_slugs({"artist_slug": "old-style"}) == {
            "old-style"
        }


@pytest.mark.asyncio
class TestLineupVersusArtistSlugs:
    async def test_a_resolved_lineup_artist_missing_from_artist_slugs_is_confirmed(self):
        """The read-time resolver will link this artist, so the stored list
        is provably behind the stored lineup. That is a fact, not a hunch."""

        world = a_world(
            artists=[
                artist("headliner", "Artist10"),
                artist("support-act", "Artist20"),
            ],
            events=[
                an_event(
                    festival={"series_id": "99"},
                    artist_slugs=["headliner"],
                    lineup=[
                        {"name": "Headliner", "songkick_id": "10"},
                        {"name": "Support", "songkick_id": "20"},
                    ],
                )
            ],
        )

        report = await collect(world)
        lineup = report["festivals"]["lineup_vs_artist_slugs"]

        assert lineup["editions_with_resolvable_lineup"] == 1
        assert (
            lineup["confirmed_lineup_artist_missing_from_artist_slugs"] == 1
        )
        assert lineup["confirmed_samples"][0][
            "missing_from_artist_slugs"
        ] == ["support-act"]
        assert lineup["needs_analysis_slugs_with_no_lineup_id"] == 0

    async def test_the_initiating_artist_in_artist_slugs_is_not_a_fault(self):
        """The importer always adds the artist who started the sync. A slug
        with no lineup id behind it is therefore a question, never a finding
        on its own - calling it one would authorise rewriting every edition."""

        world = a_world(
            artists=[
                artist("the-starter", "Artist30"),
                artist("resolvable", "Artist40"),
            ],
            events=[
                an_event(
                    festival={"series_id": "99"},
                    artist_slugs=["the-starter", "resolvable"],
                    lineup=[{"name": "Resolvable", "songkick_id": "40"}],
                ),
            ],
        )

        report = await collect(world)
        lineup = report["festivals"]["lineup_vs_artist_slugs"]

        assert lineup["confirmed_lineup_artist_missing_from_artist_slugs"] == 0
        assert lineup["needs_analysis_slugs_with_no_lineup_id"] == 1
        assert lineup["needs_analysis_samples"][0][
            "slugs_with_no_lineup_id"
        ] == ["the-starter"]

    async def test_both_songkick_id_spellings_resolve(self):
        """Artists store `Artist10`; lineup entries store `10`. Matching only
        one spelling would report the entire legacy catalogue as unresolved."""

        world = a_world(
            artists=[artist("legacy-artist", "Artist10")],
            events=[
                an_event(
                    festival={"series_id": "99"},
                    artist_slugs=["legacy-artist"],
                    lineup=[{"name": "Legacy", "songkick_id": "10"}],
                )
            ],
        )

        report = await collect(world)

        assert (
            report["festivals"]["lineup_vs_artist_slugs"][
                "confirmed_lineup_artist_missing_from_artist_slugs"
            ]
            == 0
        )

    async def test_the_camelcase_lineup_key_still_resolves(self):
        world = a_world(
            artists=[artist("camel-legacy", "Artist10")],
            events=[
                an_event(
                    festival={"series_id": "99"},
                    artist_slugs=["camel-legacy"],
                    lineup=[{"name": "Legacy", "songkickId": "10"}],
                )
            ],
        )

        report = await collect(world)

        assert (
            report["festivals"]["lineup_vs_artist_slugs"][
                "confirmed_lineup_artist_missing_from_artist_slugs"
            ]
            == 0
        )

    async def test_an_ambiguous_songkick_id_is_not_resolved_by_guessing(self):
        world = a_world(
            artists=[
                artist("claimant-one", "Artist50"),
                artist("claimant-two", "Artist50"),
            ],
            events=[
                an_event(
                    festival={"series_id": "99"},
                    artist_slugs=[],
                    lineup=[{"name": "Ambiguous", "songkick_id": "50"}],
                )
            ],
        )

        report = await collect(world)

        assert report["artists"]["ambiguous_songkick_ids"] == 1
        # Unresolved, so it can neither confirm nor deny anything.
        assert (
            report["festivals"]["lineup_vs_artist_slugs"][
                "confirmed_lineup_artist_missing_from_artist_slugs"
            ]
            == 0
        )


@pytest.mark.asyncio
class TestMissingDatesAndVenues:
    async def test_a_venue_in_either_field_generation_counts_as_present(self):
        world = a_world(
            events=[
                an_event(venue_slug="the-hall", location=None),
                an_event(venue_slug=None, location={"city": "London"}),
                an_event(venue_slug=None, location=None),
            ]
        )

        report = await collect(world)

        # Only the third event has no venue reference at all.
        assert report["events"]["missing_venue_reference"] == 1

    async def test_missing_start_dates_are_counted_apart(self):
        world = a_world(
            events=[
                an_event(starts_at=None),
                an_event(starts_at=datetime(2026, 6, 1)),
            ]
        )

        report = await collect(world)

        assert report["events"]["missing_start_date"] == 1


@pytest.mark.asyncio
class TestActivitiesPointingAtThingsThatAreGone:
    async def test_a_show_log_that_no_longer_exists_is_a_confirmed_orphan(self):
        log_id = ObjectId()
        world = a_world(
            activities=[
                {
                    "_id": ObjectId(),
                    "activity_type": "create_review",
                    "target_id": str(log_id),
                    "target_type": "show_log",
                }
            ],
            show_logs=[],
        )

        report = await collect(world)

        assert report["activities"]["show_log_missing"] == 1

    async def test_a_missing_event_behind_a_live_show_log_is_confirmed(self):
        """The activity keeps its link to the show log; only the event is
        gone. This is the population the feed snapshot will have to serve."""

        log_id = ObjectId()
        world = a_world(
            activities=[
                {
                    "_id": ObjectId(),
                    "activity_type": "attend_event",
                    "target_id": str(log_id),
                    "target_type": "show_log",
                }
            ],
            show_logs=[{"_id": log_id, "event_id": "64b0deadbeefdeadbeefdead"}],
            events=[an_event()],
        )

        report = await collect(world)

        assert report["activities"]["event_missing"] == 1
        assert report["activities"]["show_log_missing"] == 0

    async def test_both_id_spellings_are_matched(self):
        """`target_id` is stored as a string while `_id` is an ObjectId; a
        comparison that ignored that would report every row as orphaned."""

        log_id = ObjectId()
        world = a_world(
            activities=[
                {
                    "_id": ObjectId(),
                    "activity_type": "create_review",
                    "target_id": str(log_id),
                    "target_type": "show_log",
                }
            ],
            show_logs=[{"_id": log_id, "event_id": "64b0deadbeefdeadbeefdead"}],
            events=[an_event(_id=ObjectId("64b0deadbeefdeadbeefdead"))],
        )

        report = await collect(world)

        assert report["activities"]["show_log_missing"] == 0
        assert report["activities"]["event_missing"] == 0

    async def test_a_row_that_is_not_about_a_show_log_is_left_alone(self):
        world = a_world(
            activities=[
                {
                    "_id": ObjectId(),
                    "activity_type": "create_community_post",
                    "target_id": "post-1",
                    "target_type": "community_post",
                }
            ],
            show_logs=[],
        )

        report = await collect(world)

        assert report["activities"]["show_log_missing"] == 0
        assert report["activities"]["by_type"] == {
            "create_community_post": 1
        }


@pytest.mark.asyncio
class TestTheLegacyFeedCollection:
    async def test_an_absent_collection_reports_zero_not_a_crash(self):
        world = a_world()

        report = await collect(world)

        assert report["feed_activities"]["total"] == 0

    async def test_documents_are_counted_and_only_their_keys_are_reported(self):
        """Field *names* are safe to print; values from a social collection
        are not, and the samples must never become a data leak."""

        world = a_world(
            feed_activities=[
                {"_id": ObjectId(), "actor_id": "user-1", "metadata": {}}
            ]
        )

        report = await collect(world)
        text = render(report)

        assert report["feed_activities"]["total"] == 1
        assert any(
            "actor_id" in shape
            for shape in report["feed_activities"]["field_shapes"]
        )
        assert "user-1" not in text


@pytest.mark.asyncio
class TestArtistPopulation:
    async def test_absent_and_stored_null_last_synced_are_both_never_synced(self):
        """A stub with `last_synced_at: null` still needs importing; the
        census reports both generations apart so neither is hidden."""

        world = a_world(
            artists=[
                artist("stub-a", "Artist1"),
                artist("stub-b", "Artist2", last_synced_at=None),
                artist("synced", "Artist3", last_synced_at="2026-01-01"),
            ]
        )

        report = await collect(world)
        artists = report["artists"]

        assert artists["total"] == 3
        assert artists["synced"] == 1
        assert artists["never_synced_key_absent"] == 1
        assert artists["never_synced_stored_null"] == 1

    async def test_the_fallback_slug_shape_is_counted_and_sampled(self):
        world = a_world(
            artists=[
                artist("artist-976211", "Artist976211"),
                artist("demi-lovato", "Artist976212"),
            ]
        )

        report = await collect(world)

        assert report["artists"]["fallback_slugs"] == 1
        assert report["artists"]["fallback_slug_samples"] == [
            "artist-976211"
        ]

    async def test_an_artist_with_no_songkick_id_is_counted(self):
        world = a_world(artists=[{"_id": ObjectId(), "slug": "local-band"}])

        report = await collect(world)

        assert report["artists"]["without_songkick_id"] == 1


@pytest.mark.asyncio
class TestVenuesAreNotAssumedToBeTheSamePlace:
    async def test_the_same_name_in_different_cities_is_information(self):
        """Two cities both have a Camden Theatre. Reporting that as a fault
        would send someone to merge two genuinely different venues."""

        world = a_world(
            venues=[
                {"name": "Camden Theatre", "city": "London", "country": "UK"},
                {
                    "name": "Camden Theatre",
                    "city": "Camden",
                    "country": "US",
                },
            ]
        )

        report = await collect(world)
        venues = report["venues"]

        assert venues["same_name_different_places"] == 1
        assert venues["same_name_same_place"] == 0

    async def test_the_same_name_in_the_same_place_needs_analysis(self):
        """The unique (name, city, country) index should prevent this, so
        its presence is a question - about the data *and* about the index."""

        world = a_world(
            venues=[
                {"name": "The Hall", "city": "Leeds", "country": "UK"},
                {"name": "the hall ", "city": "Leeds", "country": "UK"},
            ]
        )

        report = await collect(world)

        assert report["venues"]["same_name_same_place"] == 1

    async def test_a_venue_without_a_place_is_counted(self):
        world = a_world(venues=[{"name": "Nowhere"}])

        report = await collect(world)

        assert report["venues"]["missing_city_or_country"] == 1


@pytest.mark.asyncio
class TestIndexes:
    async def test_a_driver_that_cannot_report_them_does_not_break_the_run(self):
        """`FakeCollection` has no `index_information`, which is exactly the
        shape of a driver surface that cannot answer. The census reports that
        instead of refusing to run."""

        world = a_world()

        report = await collect(world)

        assert report["indexes"]["events"] == {
            "available": False,
            "indexes": {},
        }

    async def test_when_they_can_be_read_they_are_listed(self):
        class IndexedCollection(FakeCollection):
            async def index_information(self):
                return {
                    "slug_1": {"key": [("slug", 1)]},
                    "songkick_1": {"key": [("external_ids.songkick", 1)]},
                }

        world = a_world()
        world._collections["artists"] = IndexedCollection("artists", [])

        report = await collect(world)

        assert report["indexes"]["artists"]["available"] is True
        assert report["indexes"]["artists"]["indexes"]["slug_1"] == [
            ("slug", 1)
        ]
