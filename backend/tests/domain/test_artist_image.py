"""Which image belongs to which artist.

A Songkick artist page is full of images that are not the artist: a promotional
banner, and photographs of every similar act and festival performer. Picking one of
those produces a real image of the wrong thing, which is harder to notice than a
missing image and therefore worse.

These tests pin the two properties that matter: the image must belong to this
artist, and it must be a URL that actually appears on their page.
"""
from __future__ import annotations

import pytest

from app.domain.artist_image import (
    artist_image_from_jsonld,
    is_valid_artist_image,
    pick_artist_image,
    resolve_artist_image,
)

HOST = "https://images.sk-static.com/images/media/profile_images/artists"

MARINA = "10176016"
GAL = "191574"


def url(artist_id: str, variant: str) -> str:
    return f"{HOST}/{artist_id}/{variant}"


class TestOnlyRealPhotographsAreAccepted:
    def test_an_artist_path_is_accepted(self):
        assert is_valid_artist_image(url(MARINA, "card_avatar")) is True

    def test_a_protocol_relative_url_is_accepted(self):
        assert is_valid_artist_image(
            f"//images.sk-static.com/images/media/"
            f"profile_images/artists/{MARINA}/avatar"
        ) is True

    @pytest.mark.parametrize(
        "value",
        [
            None,
            "",
            "   ",
            "not a url",
            "/relative/path.jpg",
        ],
    )
    def test_nothing_is_refused(self, value):
        assert is_valid_artist_image(value) is False

    def test_a_promotional_banner_is_refused(self):
        # The artist's page og:image points here. It is a banner, not a
        # photograph of the artist, and accepting it would pass every URL check
        # while showing the wrong thing.
        assert is_valid_artist_image(
            "http://images.sk-static.com/images/media/img/"
            "col4/20211015-130311-877292.jpg"
        ) is False

    def test_another_hosts_image_is_refused(self):
        # An embed or a tracking pixel is not an artist photograph.
        assert is_valid_artist_image(
            "https://evil.example.com/profile_images/artists/1/avatar"
        ) is False

    def test_a_concert_photo_is_refused(self):
        assert is_valid_artist_image(
            f"{HOST.rsplit('/artists', 1)[0]}"
            f"/events/43047624/huge_avatar"
        ) is False


class TestOnlyThisArtistsPhotographsAreConsidered:
    def test_another_artists_photo_is_never_chosen(self):
        # A page lists many artists. Only this artist's own path is eligible.
        chosen = pick_artist_image(
            [
                url(GAL, "huge_avatar"),
                url("9317764", "large_avatar"),
                url(MARINA, "card_avatar"),
            ],
            artist_id=MARINA,
        )

        assert chosen == url(MARINA, "card_avatar")

    def test_no_image_is_invented_when_none_belongs(self):
        assert pick_artist_image(
            [url(GAL, "huge_avatar")], artist_id=MARINA
        ) is None

    def test_a_banner_is_never_picked(self):
        assert pick_artist_image(
            [
                "http://images.sk-static.com/images/media/img/"
                "col4/20211015-130311-877292.jpg",
            ],
            artist_id=MARINA,
        ) is None

    def test_junk_entries_are_skipped(self):
        chosen = pick_artist_image(
            [None, "", 42, url(MARINA, "card_avatar")],
            artist_id=MARINA,
        )

        assert chosen == url(MARINA, "card_avatar")

    def test_nothing_supplied_means_no_image(self):
        assert pick_artist_image([], artist_id=MARINA) is None
        assert pick_artist_image(None, artist_id=MARINA) is None


class TestTheLargestPublishedPhotographWins:
    def test_huge_beats_the_others(self):
        chosen = pick_artist_image(
            [
                url(MARINA, "card_avatar"),
                url(MARINA, "large_avatar"),
                url(MARINA, "huge_avatar"),
                url(MARINA, "avatar"),
            ],
            artist_id=MARINA,
        )

        assert chosen == url(MARINA, "huge_avatar")

    def test_order_of_discovery_does_not_matter(self):
        forwards = pick_artist_image(
            [url(MARINA, "avatar"), url(MARINA, "huge_avatar")],
            artist_id=MARINA,
        )

        backwards = pick_artist_image(
            [url(MARINA, "huge_avatar"), url(MARINA, "avatar")],
            artist_id=MARINA,
        )

        assert forwards == backwards

    def test_an_unpublished_variant_is_still_this_artist(self):
        # Better than no image at all, and still genuinely theirs.
        chosen = pick_artist_image(
            [url(MARINA, "gigantic_avatar")],
            artist_id=MARINA,
        )

        assert chosen == url(MARINA, "gigantic_avatar")

    def test_a_protocol_relative_url_is_completed(self):
        chosen = pick_artist_image(
            [f"//images.sk-static.com/images/media/"
             f"profile_images/artists/{MARINA}/card_avatar"],
            artist_id=MARINA,
        )

        assert chosen.startswith("https://")


class TestThePagesOwnDescriptionIsPreferred:
    """The JSON-LD block is the page stating which image is the artist's."""

    def block(self, artist_id, name="Marina Sena", image=None):
        return {
            "@type": "MusicGroup",
            "name": name,
            "url": (
                f"https://www.songkick.com/artists/"
                f"{artist_id}-{name.lower().replace(' ', '-')}"
            ),
            "image": (
                image
                if image is not None
                else url(artist_id, "card_avatar")
            ),
        }

    def test_the_matching_block_is_used(self):
        image = artist_image_from_jsonld(
            [self.block(MARINA)], artist_id=MARINA
        )

        assert image == url(MARINA, "card_avatar")

    def test_a_block_for_another_artist_is_refused(self):
        # A page can describe several entities. One that is not this artist must
        # not contribute its photograph.
        image = artist_image_from_jsonld(
            [self.block(GAL, name="Gal Costa")], artist_id=MARINA
        )

        assert image is None

    def test_a_banner_stated_as_the_image_is_refused(self):
        image = artist_image_from_jsonld(
            [
                self.block(
                    MARINA,
                    image=(
                        "http://images.sk-static.com/images/media/"
                        "img/col4/20211015-130311-877292.jpg"
                    ),
                )
            ],
            artist_id=MARINA,
        )

        assert image is None

    def test_a_non_artist_block_is_ignored(self):
        blocks = [
            {
                "@type": "Event",
                "url": (
                    f"https://www.songkick.com/artists/{MARINA}-x"
                ),
                "image": url(MARINA, "card_avatar"),
            }
        ]

        assert artist_image_from_jsonld(
            blocks, artist_id=MARINA
        ) is None

    def test_a_list_of_images_uses_the_first_usable_one(self):
        image = artist_image_from_jsonld(
            [
                self.block(
                    MARINA,
                    image=[
                        "http://images.sk-static.com/images/media/"
                        "img/col4/banner.jpg",
                        url(MARINA, "card_avatar"),
                    ],
                )
            ],
            artist_id=MARINA,
        )

        assert image == url(MARINA, "card_avatar")

    def test_the_logo_field_is_a_usable_fallback(self):
        block = self.block(MARINA)

        block.pop("image")

        block["logo"] = url(MARINA, "card_avatar")

        assert artist_image_from_jsonld(
            [block], artist_id=MARINA
        ) == url(MARINA, "card_avatar")

    def test_a_list_wrapped_payload_is_read(self):
        image = artist_image_from_jsonld(
            [[self.block(MARINA)]], artist_id=MARINA
        )

        assert image == url(MARINA, "card_avatar")

    def test_junk_blocks_are_skipped(self):
        assert artist_image_from_jsonld(
            [None, "nonsense", {}], artist_id=MARINA
        ) is None


class TestResolvingTheOneImageToStore:
    def test_the_stated_image_wins(self):
        chosen = resolve_artist_image(
            jsonld_blocks=[
                {
                    "@type": "MusicGroup",
                    "url": (
                        "https://www.songkick.com/artists/"
                        f"{MARINA}-marina-sena"
                    ),
                    "image": url(MARINA, "card_avatar"),
                }
            ],
            page_urls=[url(MARINA, "huge_avatar")],
            artist_id=MARINA,
        )

        # The page's own statement is authoritative even though a larger
        # photograph exists elsewhere in the markup.
        assert chosen == url(MARINA, "card_avatar")

    def test_the_page_scan_is_used_when_nothing_is_stated(self):
        chosen = resolve_artist_image(
            jsonld_blocks=[],
            page_urls=[
                url(GAL, "huge_avatar"),
                url(MARINA, "large_avatar"),
            ],
            artist_id=MARINA,
        )

        assert chosen == url(MARINA, "large_avatar")

    def test_nothing_usable_means_no_image(self):
        assert resolve_artist_image(
            jsonld_blocks=[], page_urls=[], artist_id=MARINA
        ) is None

    def test_an_unusable_stated_image_falls_through_to_the_scan(self):
        chosen = resolve_artist_image(
            jsonld_blocks=[
                {
                    "@type": "MusicGroup",
                    "url": (
                        "https://www.songkick.com/artists/"
                        f"{MARINA}-marina-sena"
                    ),
                    "image": "http://images.sk-static.com/images/media/"
                             "img/col4/banner.jpg",
                }
            ],
            page_urls=[url(MARINA, "card_avatar")],
            artist_id=MARINA,
        )

        assert chosen == url(MARINA, "card_avatar")