"""Which Songkick artist is this, and how do we know?

Getting this wrong is quiet: the gigography imports cleanly and simply belongs to
another act. Songkick search returns several artists per name, so the interesting
cases are all about refusing to guess.

These tests cover the resolution rules directly, with no network.
"""
from __future__ import annotations

import pytest

from app.domain.songkick_identity import (
    artist_id_from_url,
    looks_like_spotify_id,
    normalize_songkick_artist_id,
    resolve_artist_from_search,
    slug_from_artist_url,
)


def entry(artist_id, name, **extra):
    document = {"id": artist_id, "name": name, **extra}

    return {"document": document}


# Ids are strings here because that is the form resolution compares in. Songkick's
# search returns them as integers in some responses and strings in others, which
# `test_an_integer_id_in_search_results_still_matches` covers explicitly.
ARCTIC_MONKEYS = entry("520117", "Arctic Monkeys", is_valid=True)
# A tribute act and a same-named festival-only entry, both of which Songkick does
# return for this query.
ARCTIC_MONKEYS_TRIBUTE = entry("99001111", "Arctic Monkeys Tribute")
ARCTIC_MONKEYS_FESTIVAL = entry("99002222", "Arctic Monkeys")

TRUSTED_ARCTIC = "520117"


class TestRecognisingASongkickId:
    def test_a_bare_number_is_accepted(self):
        assert normalize_songkick_artist_id("520117") == "520117"

    def test_the_artist_prefix_is_accepted(self):
        # This is the form Songkick's own URLs use.
        assert normalize_songkick_artist_id("Artist520117") == "520117"

    def test_the_prefix_is_matched_case_insensitively(self):
        assert normalize_songkick_artist_id("artist520117") == "520117"

    def test_an_artist_url_yields_its_id(self):
        assert normalize_songkick_artist_id(
            "https://www.songkick.com/artists/520117-arctic-monkeys"
        ) == "520117"

    @pytest.mark.parametrize(
        "value",
        [None, "", "   "],
    )
    def test_nothing_is_not_an_id(self, value):
        assert normalize_songkick_artist_id(value) is None

    def test_prose_is_not_an_id(self):
        assert (
            normalize_songkick_artist_id("Arctic Monkeys") is None
        )

    def test_an_id_built_from_a_name_is_not_accepted(self):
        # "Artist123" is numeric, so it passes. That is deliberate: Songkick IDs
        # are numeric and there is no way to tell a fabricated one from a real
        # one without asking Songkick, which the page check does.
        assert normalize_songkick_artist_id("Artist123") == "123"


class TestSpotifyIdsAreNeverSongkickIds:
    """A Spotify ID must not be spent as a Songkick ID.

    The two ID spaces are unrelated. A Spotify ID used against Songkick either
    404s or, worse, resolves to an unrelated artist - and the events get imported
    under the wrong name.
    """

    SPOTIFY_IDS = [
        "4aXyz885Ai9JG3F9dJ1PHB",  # Arctic Monkeys on Spotify
        "1Xyo4u8uXC1ZmMpatF05PJ",  # Taylor Swift
        "0cQbJU1aAzvbEmKlnkI4W1",
    ]

    @pytest.mark.parametrize("spotify_id", SPOTIFY_IDS)
    def test_a_spotify_id_is_recognised(self, spotify_id):
        assert looks_like_spotify_id(spotify_id) is True

    @pytest.mark.parametrize("spotify_id", SPOTIFY_IDS)
    def test_a_spotify_id_yields_no_songkick_id(
        self, spotify_id
    ):
        assert normalize_songkick_artist_id(spotify_id) is None

    def test_a_numeric_id_is_never_mistaken_for_spotify(self):
        assert looks_like_spotify_id("520117") is False

    def test_the_spotify_id_does_not_decide_identity(self):
        # Given a Spotify ID as the trusted id, and search results containing the
        # right artist by name, the Spotify ID must not be accepted as an identity.
        #
        # Refusing it means there is no trusted ID at all, so resolution falls to
        # the exact-name rule - which is the correct outcome, not a silent match
        # on the Spotify ID.
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS_TRIBUTE],
            artist_name="Arctic Monkeys",
            artist_id="4aXyz885Ai9JG3F9dJ1PHB",
        )

        assert reason == "no_trusted_id_and_no_exact_name_match"
        assert document is None

    def test_a_spotify_id_cannot_pick_a_search_entry(self):
        # Even if a Spotify ID happened to collide with a Songkick-looking value
        # in the results, the Spotify ID itself never authorises a match.
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS],
            artist_name="Arctic Monkeys",
            artist_id="4aXyz885Ai9JG3F9dJ1PHB",
        )

        # No trusted ID, but an exact name match is still legitimate.
        assert reason == "matched_by_exact_name"
        assert document["id"] == "520117"

    def test_an_id_that_is_not_spotify_shaped_is_still_refused(self):
        # Belt and braces: anything unrecognisable yields no ID, so it can never
        # be used to address a Songkick page.
        assert normalize_songkick_artist_id("banana") is None


class TestTheTrustedIdDecides:
    def test_the_matching_id_wins_over_a_better_ranked_name(
        self,
    ):
        # The tribute act is listed first. The stored ID says which one this is.
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS_TRIBUTE, ARCTIC_MONKEYS],
            artist_name="Arctic Monkeys",
            artist_id=TRUSTED_ARCTIC,
        )

        assert reason == "matched_by_songkick_id"
        assert document["id"] == TRUSTED_ARCTIC

    def test_a_same_named_entry_with_another_id_is_not_taken(self):
        document, _ = resolve_artist_from_search(
            [ARCTIC_MONKEYS_FESTIVAL],
            artist_name="Arctic Monkeys",
            artist_id=TRUSTED_ARCTIC,
        )

        assert document is None

    def test_the_prefixed_stored_id_matches_a_bare_search_id(self):
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS],
            artist_name="Arctic Monkeys",
            artist_id="Artist520117",
        )

        assert reason == "matched_by_songkick_id"
        assert document["id"] == "520117"

    def test_a_known_id_absent_from_the_results_is_still_resolvable(
        self,
    ):
        # Not appearing in search results is not evidence the artist does not
        # exist. The caller addresses the artist by ID directly.
        document, reason = resolve_artist_from_search(
            [],
            artist_name="An Obscure Band",
            artist_id="12345678",
        )

        assert reason == "not_in_search_results_but_id_known"
        assert document is None

    def test_the_id_wins_even_when_the_name_matches_nothing(self):
        # The stored ID says which act this is, and the name is not consulted.
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS_TRIBUTE],
            artist_name="Totally Different Name",
            artist_id="99001111",
        )

        assert reason == "matched_by_songkick_id"
        assert document["name"] == "Arctic Monkeys Tribute"


class TestWithoutATrustedIdOnlyAnExactNameCounts:
    def test_an_exact_name_match_is_used(self):
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS_TRIBUTE, ARCTIC_MONKEYS],
            artist_name="Arctic Monkeys",
        )

        assert reason == "matched_by_exact_name"
        assert document["id"] == TRUSTED_ARCTIC

    def test_case_and_spacing_do_not_prevent_an_exact_match(self):
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS],
            artist_name="  arctic   monkeys ",
        )

        assert reason == "matched_by_exact_name"

    def test_a_near_miss_name_is_refused(self):
        # This is the case a first-result fallback would get wrong.
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS_TRIBUTE],
            artist_name="Arctic Monkeys",
        )

        assert document is None
        assert reason == "no_trusted_id_and_no_exact_name_match"

    def test_no_result_is_refused_rather_than_defaulting_to_the_first(
        self,
    ):
        document, reason = resolve_artist_from_search(
            [ARCTIC_MONKEYS_TRIBUTE, ARCTIC_MONKEYS_FESTIVAL],
            artist_name="Marina Sena",
        )

        assert document is None
        assert reason == "no_trusted_id_and_no_exact_name_match"

    def test_an_empty_result_set_is_refused(self):
        document, _ = resolve_artist_from_search(
            [], artist_name="Arctic Monkeys"
        )

        assert document is None

    def test_a_document_passed_without_the_wrapper_is_accepted(self):
        document, reason = resolve_artist_from_search(
            [{"id": "520117", "name": "Arctic Monkeys"}],
            artist_name="Arctic Monkeys",
        )

        assert reason == "matched_by_exact_name"
        assert document["name"] == "Arctic Monkeys"

    def test_junk_entries_are_skipped(self):
        document, reason = resolve_artist_from_search(
            [None, "nonsense", {}, ARCTIC_MONKEYS],
            artist_name="Arctic Monkeys",
        )

        assert reason == "matched_by_exact_name"


class TestDuplicateNames:
    """The scenario that produced a wrong catalogue in the first place."""

    def test_two_acts_with_one_name_are_distinguished_by_id(self):
        results = [
            entry("111", "Marina Sena"),
            entry("222", "Marina Sena"),
            entry("333", "Marina Sena"),
        ]

        for wanted in ("111", "222", "333"):

            document, reason = resolve_artist_from_search(
                results,
                artist_name="Marina Sena",
                artist_id=wanted,
            )

            assert reason == "matched_by_songkick_id"
            assert document["id"] == wanted

    def test_an_integer_id_in_search_results_still_matches(self):
        # Songkick's search returns `id` as an int in some responses. Comparing
        # the trusted string against it naively would miss every match and fall
        # through to the name, which is the bug this module exists to prevent.
        document, reason = resolve_artist_from_search(
            [entry(520117, "Arctic Monkeys")],
            artist_name="Arctic Monkeys",
            artist_id=TRUSTED_ARCTIC,
        )

        assert reason == "matched_by_songkick_id"
        assert document["id"] == 520117

    def test_resolution_is_stable_across_repeated_calls(self):
        # Idempotence of the decision itself: the same inputs must always pick the
        # same artist, or two syncs of one artist could disagree.
        results = [
            entry("111", "Marina Sena"),
            entry("222", "Marina Sena"),
        ]

        picks = {
            resolve_artist_from_search(
                results,
                artist_name="Marina Sena",
                artist_id="222",
            )[0]["id"]
            for _ in range(20)
        }

        assert picks == {"222"}

    def test_the_result_order_does_not_change_the_pick(self):
        forward, _ = resolve_artist_from_search(
            [entry("111", "Marina Sena"), entry("222", "Marina Sena")],
            artist_name="Marina Sena",
            artist_id="111",
        )

        reversed_order, _ = resolve_artist_from_search(
            [entry("222", "Marina Sena"), entry("111", "Marina Sena")],
            artist_name="Marina Sena",
            artist_id="111",
        )

        assert forward["id"] == reversed_order["id"] == "111"


class TestReadingAnIdBackOffAUrl:
    def test_the_id_is_read_from_a_canonical_url(self):
        assert artist_id_from_url(
            "https://www.songkick.com/artists/520117-arctic-monkeys"
        ) == "520117"

    def test_the_id_is_read_from_a_slugless_url(self):
        # Songkick serves this and redirects it, so it has to be readable.
        assert artist_id_from_url(
            "https://www.songkick.com/artists/520117"
        ) == "520117"

    def test_an_unrelated_url_has_no_artist_id(self):
        assert artist_id_from_url(
            "https://www.songkick.com/festivals/2049549-de-frue"
        ) is None

    def test_nothing_has_no_artist_id(self):
        assert artist_id_from_url(None) is None

    def test_the_canonical_slug_is_adopted(self):
        assert (
            slug_from_artist_url(
                "https://www.songkick.com/artists/520117-arctic-monkeys"
            )
            == "arctic-monkeys"
        )

    def test_a_url_without_a_slug_has_no_slug(self):
        assert (
            slug_from_artist_url(
                "https://www.songkick.com/artists/520117"
            )
            is None
        )