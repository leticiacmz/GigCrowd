"""A festival edition, a lineup entry, and an artist performance are three
different things, and only one of them is an event.

The confusion is tempting because all three arrive on the same page. A festival's
lineup says who is playing; the festival itself has a date range; and an artist
performing at one night of that festival has a single date. Reading the first as
the third invents a concert that nobody announced - and it looks entirely
normal, because the artist really is playing the festival, on some night, at some
venue.

So the three are kept apart:

* a **festival edition** is the event: the festival, its dates, its venue;
* a **lineup entry** is participation: who was announced, with no date and no
  venue of its own;
* an **artist performance** is an event in its own right, and needs a concrete
  source that says so.

Being on a bill is not a performance date. This file holds that line.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.festival import festival_data_from_url, festival_identity
from app.domain.event_provenance import (
    PROVENANCE_SONGKICK,
    classify,
    is_trustworthy_upcoming,
)
from app.services.event_enrichment_service import (
    DATE_FROM_SOURCE,
    EventEnrichmentService,
)
from app.services.lineup_artist_importer import LineupArtistImporter
from app.services.lineup_artist_resolver import external_id_for
from tests.support.fake_mongo import FakeDatabase


class AcceptingVerifier:
    """Accepts every identity, so a test can isolate what the importer writes."""

    def __init__(self):
        self.calls = []

    async def verify(self, songkick_id, *, name=None):
        from app.services.songkick_artist_verifier import (
            ACCEPTED,
            VerifiedArtist,
        )

        from app.domain.songkick_identity import (
            normalize_songkick_artist_id,
        )

        self.calls.append(str(songkick_id))

        return VerifiedArtist(
            valid=True,
            reason=ACCEPTED,
            songkick_id=normalize_songkick_artist_id(songkick_id),
            canonical_name=name,
        )


def a_world(lineup=None, festival=None):
    database = FakeDatabase(
        {
            "artists": [],
            "events": [],
            "venues": [],
        }
    )

    return database


class TestBeingOnABillIsNotAPerformance:
    @pytest.mark.asyncio
    async def test_a_lineup_creates_an_artist_and_never_an_event(self):
        """The rule, stated as an observation about what is written.

        An announced performer becomes a linkable artist. Nothing about that
        touches the events collection, because there is no source stating that
        the performer has a date, a venue or a show of their own.
        """

        database = a_world()

        from app.repositories.artist_repository import (
            ArtistRepository,
        )

        importer = LineupArtistImporter(
            ArtistRepository(database),
            verifier=AcceptingVerifier(),
        )

        await importer.ensure_for_entries(
            [
                {
                    "name": "Tim Bernardes",
                    "songkick_id": "2668421",
                    "image": None,
                    "genres": [],
                }
            ]
        )

        assert await database.artists.count_documents({}) == 1

        # The whole point.
        assert await database.events.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_a_festival_lineup_creates_no_performance_events(self):
        database = a_world()

        from app.repositories.artist_repository import (
            ArtistRepository,
        )

        database.events.documents = [
            {
                "_id": "festival-1",
                "title": "Villa Sound 2026",
                "event_type": "FestivalInstance",
                "starts_at": "2026-03-25T20:00:00+00:00",
                "ends_at": "2026-03-27T23:59:00+00:00",
                "festival": {
                    "series_id": "44001",
                    "name": "Villa Sound",
                },
                "lineup": [
                    {
                        "name": "Tim Bernardes",
                        "songkick_id": "2668421",
                        "image": None,
                        "genres": [],
                    },
                    {
                        "name": "Marina Sena",
                        "songkick_id": "3090429",
                        "image": None,
                        "genres": [],
                    },
                ],
            }
        ]

        importer = LineupArtistImporter(
            ArtistRepository(database),
            verifier=AcceptingVerifier(),
        )

        report = await importer.ensure_for_festival("44001")

        assert report.created == 2

        # Walking a festival's whole bill produced two artists and still not one
        # new event.
        assert await database.events.count_documents({}) == 1
        assert (
            await database.events.count_documents(
                {"_id": "festival-1"}
            )
            == 1
        )


class TestAFestivalEditionIsNotAPerformance:
    def test_the_edition_carries_the_span_and_the_identity(self):
        document = {
            "title": "Villa Sound 2026",
            "event_type": "FestivalInstance",
            "starts_at": "2026-03-25T20:00:00+00:00",
            "ends_at": "2026-03-27T23:59:00+00:00",
            "festival": {
                "series_id": "44001",
                "name": "Villa Sound",
            },
            "lineup": [
                {"name": "Tim Bernardes", "songkick_id": "2668421"},
            ],
            "source": {
                "provider": "songkick",
                "url": (
                    "https://www.songkick.com/festivals/"
                    "44001-villa-sound/id/4400101"
                ),
            },
            "external_ids": {"songkick": "4400101"},
        }

        identity = festival_identity(document)

        assert identity["series_id"] == "44001"
        assert identity["name"] == "Villa Sound"

        # The full range, both ends.
        assert document["starts_at"].startswith("2026-03-25")
        assert document["ends_at"].startswith("2026-03-27")

        # And it is not attributed to a performer.
        assert document.get("artist_slugs") in (None, [])

    def test_one_url_carries_both_levels_without_conflating_them(self):
        """A festival URL names the series and the edition at once.

        Which is exactly why reading one as the other is easy: the same URL
        answers "which festival" and "which night".
        """

        url = (
            "https://www.songkick.com/festivals/"
            "44001-villa-sound/id/4400101"
        )

        data = festival_data_from_url(url)

        assert data["series_id"] == "44001"
        assert data["event_id"] == "4400101"


class TestTheAddressStatesTheSeries:
    """The festival block is one place the series is stated; not the only one.

    An imported festival date can arrive with its festival block unwritten -
    the listing gave a date, a title and a source address and nothing else -
    and it is still the same edition of the same festival. The series in its
    own Songkick address is what says so, which is the same structured signal
    the metadata URLs are read with.
    """

    def test_a_festival_date_without_a_block_still_states_its_series(self):
        document = {
            "title": "Rio de Janeiro, Brazil Rock In Rio",
            "event_type": "FestivalInstance",
            "festival": None,
            "source": {
                "provider": "songkick",
                "external_id": "42907787",
                "url": (
                    "https://www.songkick.com/festivals/"
                    "1325-rock-in-rio/id/42907787-rock-in-rio-2026"
                ),
            },
        }

        identity = festival_identity(document)

        assert identity["series_id"] == "1325"

        # The name is display-only, and the source gave none here. It is not
        # invented from the slug or the title to fill a header.
        assert identity["name"] is None

        # The address the series was read from is the URL of record.
        assert identity["url"] == document["source"]["url"]

    def test_stored_metadata_decides_before_the_address(self):
        """The address is a fallback for a missing block, not a second opinion."""

        document = {
            "title": "Marina Sena Mada 2025",
            "event_type": "FestivalInstance",
            "festival": {
                "series_id": "298683",
                "name": "Mada 2025",
                "url": (
                    "https://www.songkick.com/festivals/"
                    "298683-mada/id/42538034-mada-2025"
                ),
            },
            "source": {
                "provider": "songkick",
                "external_id": "42538034",
                # A different series entirely: stored metadata must win.
                "url": (
                    "https://www.songkick.com/festivals/"
                    "1325-rock-in-rio/id/42907787-rock-in-rio-2026"
                ),
            },
        }

        identity = festival_identity(document)

        assert identity["series_id"] == "298683"
        assert identity["name"] == "Mada 2025"

    def test_a_concert_address_never_states_a_series(self):
        """A show at a place named after a festival is still a show.

        Only a festival address carries the series segment, so ordinary event
        addresses cannot produce an identity no matter what they are called.
        """

        document = {
            "title": "Agnes Nunes @ Rock in Rio Hall",
            "event_type": "Concert",
            "festival": None,
            "source": {
                "provider": "songkick",
                "external_id": "39116370",
                "url": (
                    "https://www.songkick.com/concerts/"
                    "39116370-agnes-nunes-at-rock-in-rio-hall"
                ),
            },
        }

        assert festival_identity(document) is None


class TestAPerformanceNeedsItsOwnSource:
    def test_a_performance_date_is_never_taken_from_the_festival_range(self):
        """The specific error this prevents.

        An artist on a three-night festival has one night. Storing the festival's
        whole span as that artist's show claims three performances, and shows up
        on the artist's page as a three-day engagement they never agreed to.
        """

        stored = {"starts_at": None, "ends_at": None}

        # The source states one night for this performance.
        patch = EventEnrichmentService.apply_patch(
            stored,
            {
                "start_date": "2026-03-26T21:00:00+00:00",
                "end_date": "2026-03-26T23:59:00+00:00",
                "festival": {
                    "series_id": "44001",
                    "name": "Villa Sound",
                    # Wider, and deliberately present.
                    "start_date": "2026-03-25T20:00:00+00:00",
                    "end_date": "2026-03-27T23:59:00+00:00",
                },
            },
        )

        assert patch["starts_at"] == "2026-03-26T21:00:00+00:00"
        assert patch["ends_at"] == "2026-03-26T23:59:00+00:00"

        # The festival's range is not written into the schedule, and the stored
        # identity carries no dates at all.
        if "festival" in patch:
            assert "start_date" not in patch["festival"]
            assert "end_date" not in patch["festival"]

    def test_a_lineup_entry_alone_carries_no_date(self):
        """A name and an id. Nothing that could become a schedule."""

        entry = {
            "name": "Tim Bernardes",
            "songkick_id": "2668421",
            "url": (
                "https://www.songkick.com/artists/2668421-tim-bernardes"
            ),
        }

        for field in ("start_date", "end_date", "starts_at", "ends_at"):
            assert field not in entry

    def test_an_artist_appearance_without_a_source_is_not_an_upcoming_gig(self):
        """What the reader would be told if it slipped through.

        A performance invented from a lineup would carry no source to check, so
        the provenance rule refuses it - which is the last line of defence for a
        mistake the importer no longer makes.
        """

        invented = {
            "title": "Tim Bernardes at Villa Sound",
            "event_type": "Concert",
            "starts_at": datetime(2027, 3, 26, 21, 0, tzinfo=UTC),
            "source": {"provider": "songkick"},
            "external_ids": {"songkick": "1"},
        }

        assert classify(invented) == "unknown"

        trustworthy, reason = is_trustworthy_upcoming(invented)

        assert trustworthy is False
        assert "no source to verify" in reason


class TestRealPerformancesAreStillReal:
    def test_a_genuine_songkick_concert_is_trustworthy(self):
        """The other half of the rule.

        Refusing to invent performances is only correct if real ones are allowed
        through. A concrete Songkick page for a named artist is exactly what an
        artist performance looks like, and it stays.
        """

        performance = {
            "title": "Tim Bernardes at Sala Buenos Aires",
            "event_type": "Concert",
            "starts_at": datetime(2027, 3, 26, 21, 0, tzinfo=UTC),
            "artist_slugs": ["tim-bernardes"],
            "source": {
                "provider": "songkick",
                "url": (
                    "https://www.songkick.com/concerts/"
                    "4400102-tim-bernardes"
                ),
                "provenance": PROVENANCE_SONGKICK,
            },
            "external_ids": {"songkick": "4400102"},
        }

        trustworthy, reason = is_trustworthy_upcoming(performance)

        assert trustworthy is True
        assert reason == "verified_songkick_provenance"

    @pytest.mark.asyncio
    async def test_a_lineup_entry_still_resolves_to_its_artist(self):
        """Participation is still linkable.

        Refusing to invent a performance date must not cost the ability to link a
        name - that is the whole reason the artist is created.
        """

        database = FakeDatabase(
            {
                "artists": [
                    {
                        "name": "Tim Bernardes",
                        "slug": "tim-bernardes",
                        "external_ids": {
                            "songkick": external_id_for("2668421"),
                        },
                    }
                ],
                "events": [],
            }
        )

        from app.repositories.artist_repository import (
            ArtistRepository,
        )
        from app.services.lineup_artist_resolver import (
            LineupArtistResolver,
        )

        resolver = LineupArtistResolver(ArtistRepository(database))

        resolved = await resolver.resolve(["2668421"])

        assert resolved == {"2668421": "tim-bernardes"}

        assert DATE_FROM_SOURCE == "source"
