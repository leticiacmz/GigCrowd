"""Genre comes from artists, and text and genre compose in one query.

Two properties are load-bearing here, and both are easy to get subtly wrong:

* **A genre is never inferred from an event title.** "Rock in Rio" is a place and
  "Boiler Room" is a venue; a filter that reads either as a genre returns
  confident nonsense. So the genre list is built from what artists say about
  themselves, and an event appears under a genre only because one of its artists
  carries it.

* **Both filters are the same query.** Composing them in the client means paging
  over rows the reader will never see, so the count in the header disagrees with
  the list under it and "next page" skips. Here they are one `find`, and `total`
  is counted from it.

The paging tests matter for a specific reason: several events routinely share one
instant - a festival with three dates all at midnight on the 1st - so the cursor
needs a tie-break or the boundary row comes back on the next page and a reader
scrolls forever seeing the same show at the bottom.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import pytest
from bson import ObjectId

from app.repositories.artist_repository import ArtistRepository
from app.repositories.event_repository import EventRepository
from app.repositories.venue_repository import VenueRepository
from app.services.event_search_service import (
    EventSearchService,
    escape_regex,
    normalize_genre,
)
from tests.support.fake_mongo import FakeDatabase

# "Not stated", as distinct from `None`, which means "stored as null".
_UNDATED = object()


def an_artist(
    slug: str,
    genres: list[str] | None = None,
    **extra,
) -> dict:
    return {
        "_id": str(ObjectId()),
        "name": slug.replace("-", " ").title(),
        "slug": slug,
        "normalized_name": slug.replace("-", " "),
        "external_ids": {},
        "genres": genres or [],
        "image": None,
        **extra,
    }


def an_event(
    title: str,
    artist_slugs: list[str],
    *,
    starts_at: Any = _UNDATED,
    ends_at: Any = None,
    ident: Any = None,
    **extra,
) -> dict:
    """One upcoming event, from a real Songkick page.

    The source URL is not decoration: an upcoming listing refuses anything that
    claims a provider without offering a page to check, so an event with only
    `{"provider": "songkick"}` is excluded - correctly. Written with the shape a
    real import produces so these tests exercise the search rather than the
    provenance rules by accident.

    `starts_at` defaults to something in the future and can be overridden with
    `None` to mean genuinely undated, which is a different thing and needs a
    sentinel - `None` as a default would silently turn every "undated" test into
    an "upcoming" one.
    """

    if starts_at is _UNDATED:
        starts_at = datetime.now(UTC) + timedelta(days=30)

    songkick_id = str(extra.get("_songkick_id") or 5550000 + (id(title) % 900))

    source = extra.pop("source", None) or {
        "provider": "songkick",
        "external_id": songkick_id,
        "url": (
            f"https://www.songkick.com/concerts/"
            f"{songkick_id}-a-real-show"
        ),
        "event_id": songkick_id,
        "provenance": "songkick",
    }

    return {
        # A real ObjectId, as stored. The cursor's tie-break compares `_id`
        # values, and comparing an ObjectId to a string would be a mismatch the
        # double refuses rather than one production ever sees.
        "_id": ident or ObjectId(),
        "title": title,
        "event_type": "Concert",
        "venue_slug": "a-venue",
        "artist_slug": artist_slugs[0] if artist_slugs else "",
        "artist_slugs": artist_slugs,
        "starts_at": starts_at,
        "ends_at": ends_at,
        "date_status": "source",
        "lineup": [],
        "location": None,
        "external_ids": {"songkick": songkick_id},
        "source": source,
        "festival": None,
        **extra,
    }


def a_service(
    artists: list[dict],
    events: list[dict],
) -> EventSearchService:
    database = FakeDatabase(
        {
            "artists": artists,
            "events": events,
            "venues": [
                {
                    "slug": "a-venue",
                    "name": "The Crocodile",
                    "city": "Seattle",
                    "country": "US",
                }
            ],
        }
    )

    return EventSearchService(
        EventRepository(database),
        VenueRepository(database),
        ArtistRepository(database),
    )


class TestGenresComeFromArtists:
    @pytest.mark.asyncio
    async def test_the_list_is_built_from_stated_genres(self):
        service = a_service(
            [
                an_artist("marina-sena", ["MPB", "Pop"]),
                an_artist("tim-bernardes", ["MPB"]),
                an_artist("arctic-monkeys", ["alternative rock"]),
            ],
            [],
        )

        genres = await service.genres()

        # One entry per genre, most artists first, alphabetical within a count.
        # The tie-break is asserted because a list that reshuffled itself between
        # two reads would be a filter nobody could choose from reliably.
        #
        # Note `Alternative Rock` and `alternative rock` are one entry: the filter
        # already matches case-insensitively, so offering both spellings would be
        # two options that select the same artists.
        assert [row["name"] for row in genres] == [
            "MPB",
            "alternative rock",
            "Pop",
        ]

        # Counted per artist, which is what keeps the list stable as gigs are
        # added. Counting events would make the filter reshuffle itself under a
        # reader who is about to choose from it.
        assert genres[0] == {"name": "MPB", "artists": 2}

    @pytest.mark.asyncio
    async def test_two_spellings_of_one_genre_are_one_option(self):
        """The count beside an option has to be the truth.

        Grouping by the stored string offered `pop` and `Pop` as separate
        choices, each with its own number, while the filter behind them selected
        the same artists either way. One of those numbers was wrong and a reader
        had no way to tell which.
        """

        service = a_service(
            [
                an_artist("a", ["pop"]),
                an_artist("b", ["pop"]),
                an_artist("c", ["Pop"]),
            ],
            [],
        )

        genres = await service.genres()

        assert len(genres) == 1

        # The commonest spelling is the one shown: two artists write it lower
        # case, which is also what Songkick and Spotify publish.
        assert genres[0]["name"] == "pop"
        assert genres[0]["artists"] == 3

    @pytest.mark.asyncio
    async def test_the_option_selects_exactly_what_its_count_says(self):
        """End to end: pick the option, and the filter agrees with the number.

        This is the check that would have caught the two spellings, and it is the
        one worth keeping - a filter whose label and behaviour disagree is worse
        than a filter with no label.
        """

        service = a_service(
            [
                an_artist("a", ["pop"]),
                an_artist("b", ["Pop"]),
                an_artist("c", ["rock"]),
            ],
            [],
        )

        for option in await service.genres():

            selected = await service.genre_slugs(
                option["name"]
            )

            assert len(selected) == option["artists"], option

    @pytest.mark.asyncio
    async def test_an_artist_with_no_genres_contributes_nothing(self):
        service = a_service([an_artist("mystery")], [])

        assert await service.genres() == []

    @pytest.mark.asyncio
    async def test_a_genre_in_a_title_is_never_offered(self):
        """The failure this rule exists to prevent.

        "Rock in Rio" and "Boiler Room" are places. A filter that offered them
        would look sensible and return the wrong shows.
        """

        service = a_service(
            [],
            [
                an_event("Rock in Rio", ["marina-sena"]),
                an_event("Boiler Room", ["tim-bernardes"]),
            ],
        )

        assert await service.genres() == []

    @pytest.mark.asyncio
    async def test_an_event_appears_under_the_genres_of_its_artists(self):
        service = a_service(
            [
                an_artist("marina-sena", ["MPB"]),
                an_artist("arctic-monkeys", ["Alternative Rock"]),
            ],
            [
                an_event(
                    "Marina Sena at The Crocodile",
                    ["marina-sena"],
                ),
                an_event(
                    "Arctic Monkeys at The Crocodile",
                    ["arctic-monkeys"],
                ),
            ],
        )

        result = await service.search(genre="MPB")

        assert result["total"] == 1
        assert (
            result["events"][0]["title"]
            == "Marina Sena at The Crocodile"
        )

    @pytest.mark.asyncio
    async def test_the_genre_match_ignores_case_and_needs_the_whole_name(self):
        """`post-punk` must not be a hit for a search of `punk`.

        A partial match here would quietly include the wrong shows, which is the
        one thing a genre filter cannot afford: the reader would narrow to
        something and get something else.
        """

        service = a_service(
            [
                an_artist("the-cure", ["Post-Punk"]),
                an_artist("some-punk-band", ["Punk Rock"]),
            ],
            [
                an_event("The Cure", ["the-cure"]),
                an_event("Some Punk Band", ["some-punk-band"]),
            ],
        )

        # Spelled differently, still the same genre.
        lower = await service.search(genre="post-punk")

        assert lower["total"] == 1

        # A prefix of a real genre matches nothing.
        partial = await service.search(genre="post")

        assert partial["total"] == 0

    @pytest.mark.asyncio
    async def test_a_genre_nobody_carries_answers_with_nothing(self):
        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [an_event("Marina Sena", ["marina-sena"])],
        )

        result = await service.search(genre="Polka")

        assert result["total"] == 0
        assert result["events"] == []
        assert result["next_cursor"] is None


class TestTextAndGenreCompose:
    @pytest.mark.asyncio
    async def test_both_filters_apply_together(self):
        """The point of composing them in one query.

        Filtering in the client would page over rows the reader never sees, so the
        header count and the list would disagree.
        """

        service = a_service(
            [
                an_artist("marina-sena", ["MPB"]),
                an_artist("tim-bernardes", ["Indie"]),
                an_artist("arctic-monkeys", ["Indie"]),
            ],
            [
                an_event(
                    "Marina Sena at The Crocodile",
                    ["marina-sena"],
                ),
                an_event(
                    "Marina Sena Elsewhere",
                    ["marina-sena"],
                ),
                an_event(
                    "Tim Bernardes Elsewhere",
                    ["tim-bernardes"],
                ),
            ],
        )

        everything = await service.search()
        genre_only = await service.search(genre="MPB")
        text_only = await service.search(q="Marina")
        both = await service.search(q="Marina", genre="MPB")

        assert everything["total"] == 3
        assert genre_only["total"] == 2
        assert text_only["total"] == 2
        assert both["total"] == 2

        # Narrowing by both cannot widen by either.
        assert (
            both["total"]
            <= genre_only["total"]
            <= everything["total"]
        )

    @pytest.mark.asyncio
    async def test_the_search_matches_the_artist_not_just_the_title(self):
        """`radiohead` is not a slug, so matching slugs against it finds nothing.

        The text is matched against the artists that own the slugs an event
        carries, which is what makes searching for a band find its dates.
        """

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Some Festival",
                    ["marina-sena"],
                ),
            ],
        )

        by_artist = await service.search(q="Marina Sena")

        assert by_artist["total"] == 1

    @pytest.mark.asyncio
    async def test_a_search_that_matches_nothing_says_so(self):
        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [an_event("Marina Sena", ["marina-sena"])],
        )

        result = await service.search(q="Nobody At All")

        assert result["total"] == 0
        assert result["events"] == []

    @pytest.mark.asyncio
    async def test_search_text_is_not_a_regular_expression(self):
        """A band name is not a pattern.

        `AC/DC` and `Mr. Bungle` are ordinary searches. Escaping is what stops a
        parenthesis from being a syntax error that surfaces as a failed request.
        """

        service = a_service(
            [an_artist("ac-dc", ["Rock"])],
            [an_event("AC/DC", ["ac-dc"])],
        )

        assert (await service.search(q="AC/DC"))["total"] == 1
        assert (await service.search(q="("))["total"] == 0
        assert escape_regex("a(b") == r"a\(b"

    def test_genres_are_normalised(self):
        assert normalize_genre("  MPB  ") == "MPB"
        assert normalize_genre("") is None
        assert normalize_genre(None) is None
        assert normalize_genre("   ") is None


class TestWhatIsListed:
    @pytest.mark.asyncio
    async def test_past_events_are_left_out_by_default(self):
        """A list of "what is on" cannot answer its question with old news."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Last Night",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=1)
                    ),
                ),
                an_event(
                    "Next Month",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=30)
                    ),
                ),
            ],
        )

        assert (await service.search())["total"] == 1

        with_past = await service.search(include_past=True)

        assert with_past["total"] == 2

    @pytest.mark.asyncio
    async def test_an_undated_event_is_not_listed_as_upcoming(self):
        """Undated is not "about to happen".

        Listing it would put a record whose date nobody has recovered at the top
        of a list of things that are about to happen.
        """

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Never Dated",
                    ["marina-sena"],
                    starts_at=None,
                ),
            ],
        )

        assert (await service.search())["total"] == 0

        assert (
            await service.search(include_past=True)
        )["total"] == 1


class TestWhatMayBePresentedAsUpcoming:
    """A future claim has to be one that can be believed.

    These are the rows a visitor reads as "this is on". A development fixture
    carries a plausible future date, a Songkick-shaped URL and a Songkick-shaped
    id, and is otherwise indistinguishable from an import - so without the
    provenance rule every fixture reads as an announced gig, which is exactly
    the claim it is not making.
    """

    @pytest.mark.asyncio
    async def test_a_real_songkick_future_event_is_listed(self):
        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Marina Sena at The Crocodile",
                    ["marina-sena"],
                )
            ],
        )

        result = await service.search()

        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_a_development_fixture_is_not_listed_as_upcoming(self):
        """The bug this closes.

        Seven fixtures dated 2026 and 2027 were being presented on the events
        page as real concerts for artists who are not touring, while the artist
        pages - which apply the same rule - correctly showed nothing.
        """

        service = a_service(
            [an_artist("gal-costa", ["MPB"])],
            [
                an_event(
                    "Gal Costa at Auditorio Ibirapuera",
                    ["gal-costa"],
                    source={
                        "provider": "songkick",
                        "external_id": "9900109",
                        "url": (
                            "https://www.songkick.com/concerts/"
                            "9900109-gal-costa"
                        ),
                        "event_id": "9900109",
                        "provenance": "fixture",
                    },
                )
            ],
        )

        assert (await service.search())["total"] == 0

    @pytest.mark.asyncio
    async def test_a_fixture_written_before_provenance_is_still_excluded(self):
        """Recognised by its id, which is why the id block exists.

        Rows written before provenance was recorded carry no `provenance` field
        at all. An id in our own fixture block identifies them anyway, so the
        rule does not depend on a field that older rows do not have.
        """

        service = a_service(
            [an_artist("gal-costa", ["MPB"])],
            [
                an_event(
                    "Gal Costa at Auditorio Ibirapuera",
                    ["gal-costa"],
                    _songkick_id="9900109",
                )
            ],
        )

        assert (await service.search())["total"] == 0

    @pytest.mark.asyncio
    async def test_an_event_claiming_a_provider_with_no_page_is_excluded(self):
        """Nothing to check means nothing can be concluded."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Some Show",
                    ["marina-sena"],
                    source={"provider": "songkick"},
                )
            ],
        )

        assert (await service.search())["total"] == 0

    @pytest.mark.asyncio
    async def test_an_event_claiming_a_page_on_another_host_is_excluded(self):
        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Some Show",
                    ["marina-sena"],
                    source={
                        "provider": "songkick",
                        "url": "https://example.test/show",
                    },
                )
            ],
        )

        assert (await service.search())["total"] == 0

    @pytest.mark.asyncio
    async def test_a_fixture_is_still_reachable_as_history(self):
        """Hiding a future fixture must not hide a past one.

        The trust rule is about claims on the future. A finished fixture makes no
        claim about anyone's plans, and the development database and the manual
        test accounts are built on it.
        """

        service = a_service(
            [an_artist("gal-costa", ["MPB"])],
            [
                an_event(
                    "Gal Costa Last Year",
                    ["gal-costa"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=400)
                    ),
                    source={
                        "provider": "songkick",
                        "external_id": "9900109",
                        "url": (
                            "https://www.songkick.com/concerts/"
                            "9900109-gal-costa"
                        ),
                        "provenance": "fixture",
                    },
                )
            ],
        )

        assert (await service.search())["total"] == 0

        history = await service.search(include_past=True)

        assert history["total"] == 1

    @pytest.mark.asyncio
    async def test_include_past_does_not_open_the_future(self):
        """The one variant of this endpoint that could bypass the rule.

        `include_past=true` exists to reach back into history, but it queried
        with no date clause at all - so the same request that made last year's
        shows reachable also showed a fixture dated next year as an announced
        gig. Reaching back must not mean believing everything ahead.
        """

        service = a_service(
            [
                an_artist("gal-costa", ["MPB"]),
                an_artist("marina-sena", ["MPB"]),
            ],
            [
                an_event(
                    "Gal Costa Last Year",
                    ["gal-costa"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=400)
                    ),
                    source={
                        "provider": "songkick",
                        "external_id": "9900109",
                        "url": (
                            "https://www.songkick.com/concerts/"
                            "9900109-gal-costa"
                        ),
                        "provenance": "fixture",
                    },
                ),
                an_event(
                    "Gal Costa Next Year",
                    ["gal-costa"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=400)
                    ),
                    source={
                        "provider": "songkick",
                        "external_id": "9900110",
                        "url": (
                            "https://www.songkick.com/concerts/"
                            "9900110-gal-costa"
                        ),
                        "provenance": "fixture",
                    },
                ),
                an_event(
                    "Marina Sena Next Month",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=30)
                    ),
                ),
            ],
        )

        everything = await service.search(include_past=True)

        titles = [
            row["title"]
            for row in everything["events"]
        ]

        assert "Gal Costa Last Year" in titles
        assert "Marina Sena Next Month" in titles
        assert "Gal Costa Next Year" not in titles
        assert everything["total"] == 2

    @pytest.mark.asyncio
    async def test_the_artist_page_and_this_list_agree(self):
        """A search more permissive than the page it links to is not a search.

        This is the discrepancy that let the phantom concerts be visible: the
        repository's upcoming listing applied the provenance rule and this
        endpoint did not, so an artist page showed nothing while the catalogue
        showed nine phantom gigs for the same records.
        """

        from app.domain.event_provenance import (
            trusted_upcoming_filter,
        )

        service = a_service(
            [an_artist("gal-costa", ["MPB"])],
            [
                an_event(
                    "Gal Costa at Auditorio Ibirapuera",
                    ["gal-costa"],
                    source={
                        "provider": "songkick",
                        "external_id": "9900109",
                        "url": (
                            "https://www.songkick.com/concerts/"
                            "9900109-gal-costa"
                        ),
                        "provenance": "fixture",
                    },
                )
            ],
        )

        listed = await service.search()

        repository_view = await service.event_repository.collection.count_documents(
            {
                "artist_slugs": "gal-costa",
                **trusted_upcoming_filter(),
            }
        )

        assert listed["total"] == repository_view


class TestPaging:
    @pytest.mark.asyncio
    async def test_pages_do_not_repeat_or_skip(self):
        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    f"Show {index:02d}",
                    ["marina-sena"],
                    # From tomorrow, not from today: `days=0` is "now", and the
                    # list only shows what is still ahead, so an event stamped
                    # at the current instant is already excluded by the time the
                    # query runs.
                    starts_at=(
                        datetime.now(UTC)
                        + timedelta(days=index + 1)
                    ),
                    ident=ObjectId(),
                )
                for index in range(7)
            ],
        )

        seen: list[str] = []
        cursor: Any = None

        for _ in range(10):

            page = await service.search(
                limit=3,
                before=cursor["date"] if cursor else None,
                before_id=cursor["id"] if cursor else None,
            )

            seen.extend(row["id"] for row in page["events"])

            cursor = page["next_cursor"]

            if not cursor:
                break

        assert len(seen) == 7
        assert len(set(seen)) == 7

    @pytest.mark.asyncio
    async def test_several_events_sharing_one_instant_do_not_repeat(self):
        """The case a tie-break exists for.

        Festival editions very often land on the same midnight, so several events
        share an instant. Without the `_id` tie-break the boundary row comes back
        on the next page and a reader scrolls forever seeing the same show.
        """

        same_instant = datetime(2027, 3, 25, 0, 0, tzinfo=UTC)

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    f"Villa Sound Day {day}",
                    ["marina-sena"],
                    starts_at=same_instant,
                )
                for day in (1, 2, 3)
            ],
        )

        first = await service.search(limit=2)

        assert len(first["events"]) == 2

        second = await service.search(
            limit=10,
            before=first["next_cursor"]["date"],
            before_id=first["next_cursor"]["id"],
        )

        returned = [
            row["title"]
            for row in first["events"] + second["events"]
        ]

        assert len(returned) == len(set(returned)) == 3

    @pytest.mark.asyncio
    async def test_the_last_page_has_no_cursor(self):
        """Null is the only signal a client needs to stop."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Only Show",
                    ["marina-sena"],
                )
            ],
        )

        page = await service.search(limit=20)

        assert page["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_a_filter_held_still_pages(self):
        """The cursor walks the filtered set, not the whole catalogue.

        If paging ignored the genre, "next page" would land the reader on shows
        they had filtered out.
        """

        service = a_service(
            [
                an_artist("marina-sena", ["MPB"]),
                an_artist("tim-bernardes", ["Indie"]),
            ],
            [
                an_event(
                    f"MPB Show {index:02d}",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC)
                        + timedelta(days=index + 1)
                    ),
                    ident=ObjectId(),
                )
                for index in range(5)
            ]
            + [
                an_event(
                    f"Indie Show {index:02d}",
                    ["tim-bernardes"],
                    starts_at=(
                        datetime.now(UTC)
                        + timedelta(days=100 + index)
                    ),
                    ident=ObjectId(),
                )
                for index in range(5)
            ],
        )

        first = await service.search(genre="MPB", limit=3)

        second = await service.search(
            genre="MPB",
            limit=10,
            before=first["next_cursor"]["date"],
            before_id=first["next_cursor"]["id"],
        )

        titles = [
            row["title"]
            for row in first["events"] + second["events"]
        ]

        assert len(titles) == 5

        assert all(
            title.startswith("MPB Show") for title in titles
        )


class TestReadingOrder:
    """What is still to come reads soonest first; what has been reads newest first.

    Two sorted readings of one result set, not a scoring engine. Somebody
    looking for the next show should not scroll past next year's dates to find
    this month's, and somebody looking for a show they remember should meet the
    nearest one in time before the one from three years earlier - while both
    remain in the same list, in the same total, walked by the same cursor.
    """

    @pytest.mark.asyncio
    async def test_upcoming_is_read_soonest_first(self):
        """The next show is the first answer to "what is on"."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Far Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=300)
                    ),
                ),
                an_event(
                    "Soon Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=10)
                    ),
                ),
                an_event(
                    "Middle Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=100)
                    ),
                ),
            ],
        )

        result = await service.search()

        assert [
            row["title"]
            for row in result["events"]
        ] == [
            "Soon Show",
            "Middle Show",
            "Far Show",
        ]

    @pytest.mark.asyncio
    async def test_a_lookup_reads_what_is_to_come_before_what_has_been(self):
        """A historical row from yesterday does not outrank next year's show.

        Neither a single descending sort (which buries this month's dates under
        next year's) nor a single ascending one (which puts yesterday's show at
        the top of a lookup) answers both questions.
        """

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "History",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=1)
                    ),
                ),
                an_event(
                    "Next Year",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=300)
                    ),
                ),
                an_event(
                    "This Season",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=30)
                    ),
                ),
            ],
        )

        result = await service.search(include_past=True)

        assert [
            row["title"]
            for row in result["events"]
        ] == [
            "This Season",
            "Next Year",
            "History",
        ]

    @pytest.mark.asyncio
    async def test_history_reads_most_recent_first(self):
        """Of what has been, the nearest in time is the most worth showing."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Long Ago",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=400)
                    ),
                ),
                an_event(
                    "Last Week",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=7)
                    ),
                ),
                an_event(
                    "Last Season",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=150)
                    ),
                ),
                an_event(
                    "Soon",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=10)
                    ),
                ),
            ],
        )

        result = await service.search(include_past=True)

        assert [
            row["title"]
            for row in result["events"]
        ] == [
            "Soon",
            "Last Week",
            "Last Season",
            "Long Ago",
        ]

    @pytest.mark.asyncio
    async def test_the_cursor_walks_both_passes_without_repeating_or_skipping(self):
        """The page that stops in one pass continues in the other.

        The two passes meet inside one cursor: a page that ends in the upcoming
        half must continue into the historical half from its most recent row,
        and a cursor sitting in the historical half must not climb back into
        what is still to come.
        """

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    f"Future {index}",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC)
                        + timedelta(days=index + 1)
                    ),
                    ident=ObjectId(),
                )
                for index in range(3)
            ]
            + [
                an_event(
                    f"Past {index}",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC)
                        - timedelta(days=index + 1)
                    ),
                    ident=ObjectId(),
                )
                for index in range(4)
            ],
        )

        titles: list[str] = []
        cursor: Any = None

        for _ in range(10):

            page = await service.search(
                include_past=True,
                limit=2,
                before=cursor["date"] if cursor else None,
                before_id=cursor["id"] if cursor else None,
            )

            titles.extend(
                row["title"]
                for row in page["events"]
            )

            cursor = page["next_cursor"]

            if not cursor:
                break

        assert titles == [
            "Future 0",
            "Future 1",
            "Future 2",
            "Past 0",
            "Past 1",
            "Past 2",
            "Past 3",
        ]

    @pytest.mark.asyncio
    async def test_the_provenance_rule_survives_a_cursor_page_without_text(self):
        """Page two is not a looser query than page one.

        The cursor clause appends to what the query already carries, so the
        trust rule that hides an uncheckable future claim on the first page is
        still in force on the second. The text-free request is the one where a
        cursor clause written as a replacement used to wipe it, and a phantom
        row was one page away from reading as an announced gig.
        """

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Real Far Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=500)
                    ),
                    ident=ObjectId(),
                ),
                an_event(
                    "Phantom Further Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=600)
                    ),
                    ident=ObjectId(),
                    source={
                        "provider": "songkick",
                        "external_id": "9900109",
                        "url": (
                            "https://www.songkick.com/concerts/"
                            "9900109-a-phantom"
                        ),
                        "event_id": "9900109",
                        "provenance": "fixture",
                    },
                ),
                an_event(
                    "Old Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=30)
                    ),
                    ident=ObjectId(),
                ),
            ],
        )

        titles: list[str] = []
        cursor: Any = None

        for _ in range(10):

            page = await service.search(
                include_past=True,
                limit=1,
                before=cursor["date"] if cursor else None,
                before_id=cursor["id"] if cursor else None,
            )

            titles.extend(
                row["title"]
                for row in page["events"]
            )

            cursor = page["next_cursor"]

            if not cursor:
                break

        assert titles == [
            "Real Far Show",
            "Old Show",
        ]


class TestTheFollowedList:
    """The personalized page is the browse query with a membership list.

    One source of truth for follows, one for events, one set of rules: the
    page a signed-in reader lands on cannot be more permissive than the public
    page it stands in for, and an empty follow list must never widen into
    "every event" - which is the failure this parameter exists to prevent.
    """

    @pytest.mark.asyncio
    async def test_only_the_followed_artists_shows_appear(self):
        service = a_service(
            [
                an_artist("marina-sena", ["MPB"]),
                an_artist("tim-bernardes", ["Indie"]),
            ],
            [
                an_event("Marina Show", ["marina-sena"]),
                an_event("Tim Show", ["tim-bernardes"]),
            ],
        )

        result = await service.search(
            artist_slugs=["marina-sena"]
        )

        assert [
            row["title"]
            for row in result["events"]
        ] == ["Marina Show"]

        assert result["total"] == 1

    @pytest.mark.asyncio
    async def test_following_nobody_is_an_empty_page(self):
        """No follows states itself; it does not become the whole catalogue."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [an_event("Marina Show", ["marina-sena"])],
        )

        result = await service.search(artist_slugs=[])

        assert result["events"] == []
        assert result["total"] == 0
        assert result["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_it_is_still_upcoming_only_and_read_soonest_first(self):
        """The same provenance rule and the same reading order as the browse list.

        A personalized page that hid a fixture, or that read history before
        what is on, would be answering a different question from the one the
        page replaced.
        """

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Last Year",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) - timedelta(days=400)
                    ),
                ),
                an_event(
                    "Far Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=200)
                    ),
                ),
                an_event(
                    "Soon Show",
                    ["marina-sena"],
                    starts_at=(
                        datetime.now(UTC) + timedelta(days=5)
                    ),
                ),
            ],
        )

        result = await service.search(
            artist_slugs=["marina-sena"]
        )

        assert [
            row["title"]
            for row in result["events"]
        ] == [
            "Soon Show",
            "Far Show",
        ]

        assert result["total"] == 2


class TestWhatARowCarries:
    @pytest.mark.asyncio
    async def test_a_row_has_the_venue_and_the_artists(self):
        """Enough to scan a list without assembling a whole event per row."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Marina Sena at The Crocodile",
                    ["marina-sena"],
                )
            ],
        )

        row = (await service.search())["events"][0]

        assert row["title"] == "Marina Sena at The Crocodile"
        assert row["venue"]["city"] == "Seattle"
        assert row["artists"][0]["name"] == "Marina Sena"
        assert row["artists"][0]["genres"] == ["MPB"]
        assert row["id"]

    @pytest.mark.asyncio
    async def test_a_festival_row_keeps_its_series(self):
        """So a list row can be badged as a festival without a second request."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Villa Sound 2026",
                    ["marina-sena"],
                    event_type="FestivalInstance",
                    festival={
                        "series_id": "44001",
                        "name": "Villa Sound",
                    },
                )
            ],
        )

        row = (await service.search())["events"][0]

        assert row["festival"] == {
            "name": "Villa Sound",
            "series_id": "44001",
        }

    @pytest.mark.asyncio
    async def test_a_festival_range_is_not_narrowed_to_its_first_night(self):
        """The row carries the span the source stated."""

        service = a_service(
            [an_artist("marina-sena", ["MPB"])],
            [
                an_event(
                    "Villa Sound 2026",
                    ["marina-sena"],
                    event_type="FestivalInstance",
                    starts_at=datetime(
                        2027, 3, 25, 20, 0, tzinfo=UTC
                    ),
                    ends_at=datetime(
                        2027, 3, 27, 23, 59, tzinfo=UTC
                    ),
                )
            ],
        )

        row = (await service.search())["events"][0]

        assert row["starts_at"].day == 25
        assert row["ends_at"].day == 27
