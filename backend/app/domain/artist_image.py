"""Which image is this artist's photograph?

A Songkick artist page carries a great many images: the artist's own avatar at
several sizes, promotional banners, and photographs of every similar artist and
every act on the same festival. Picking the wrong one produces a real image of
the wrong thing, which is worse than no image because nothing looks broken.

Two facts about Songkick make this reliable, and both were checked against the
live site rather than assumed:

1. The page states the artist as a JSON-LD `MusicGroup` whose `url` contains that
   artist's own public Songkick ID. So the artist can be matched to their block by
   ID rather than by name, position or image size.

2. Artist photographs live under a path that also carries the public ID:
   `.../profile_images/artists/{artist_id}/{variant}`. Every other image on the
   page - banners, other artists - is either under a different path or under a
   different ID.

The page's `og:image` is deliberately never used. It is a promotional banner
(`/images/media/img/col4/...`), not a photograph of the artist, so it would
satisfy "has an image" while showing the wrong thing.

Nothing here invents a URL. Candidates are only ever URLs that actually appear on
the page; the code chooses among them rather than rewriting a path to a size that
was never offered.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

# Songkick's own image host. Allowing any host would let a page's tracking pixel
# or a third-party embed pass as an artist photograph.
SONGKICK_IMAGE_HOST = "images.sk-static.com"

# An artist's own photograph, by size, best first.
_IMAGE_PATH = re.compile(
    r"(?:https?:)?//" + re.escape(SONGKICK_IMAGE_HOST) + r"/images/media/"
    r"profile_images/artists/(\d+)/([a-z_]+)",
    re.IGNORECASE,
)

# The variants Songkick publishes, best first. "huge" is the largest, which suits
# a profile header; "avatar" is the bare one used in listings.
VARIANT_PREFERENCE = (
    "huge_avatar",
    "large_avatar",
    "card_avatar",
    "avatar",
)


def _absolute(url: str) -> str:
    if url.startswith("//"):
        return f"https:{url}"

    return url


def is_valid_artist_image(url: Any) -> bool:
    """Whether this URL is one we are willing to show as an artist's photograph.

    Requires Songkick's image host and a path that names an artist. Anything else
    is refused, including an empty string, so a caller cannot persist a blank that
    then reads as "we looked and found nothing" instead of "we never looked".
    """

    if not url or not isinstance(url, str):
        return False

    text = url.strip()

    if not text or not text.lower().startswith(("http://", "https://", "//")):
        return False

    return (
        SONGKICK_IMAGE_HOST in text
        and "/profile_images/artists/" in text
    )


def pick_artist_image(
    urls: Iterable[Any],
    *,
    artist_id: Optional[str] = None,
) -> Optional[str]:
    """The best available photograph for one artist.

    Only URLs whose path carries `artist_id` are considered, so a page listing
    twenty other artists cannot contribute a photograph to this one. Among those,
    the largest published variant wins, and the result is a URL that genuinely
    appeared on the page.

    Returns None when there is nothing usable, which callers must treat as "no
    image found" rather than an image to record.
    """

    wanted = str(artist_id) if artist_id else None

    found: dict[str, str] = {}

    for candidate in urls or []:

        if not candidate or not isinstance(candidate, str):
            continue

        match = _IMAGE_PATH.search(candidate)

        if match is None:
            continue

        found_id, variant = match.group(1), match.group(2).lower()

        if wanted and found_id != wanted:
            continue

        url = _absolute(candidate.strip())

        # Keep the first sighting of a variant; the path is the same either way.
        found.setdefault(variant, url)

    for variant in VARIANT_PREFERENCE:

        if variant in found:
            return found[variant]

    # An unpublished variant is still this artist's photograph, so it beats no
    # image at all - but it must not outrank a published one.
    for variant, url in sorted(found.items()):

        if is_valid_artist_image(url):
            return url

    return None


def _flatten(value: Any):
    """Yield every mapping in a payload, however deeply it is nested.

    Songkick wraps its structured data in a list, and sometimes a list inside that
    list, so the shape cannot be assumed. Flattening here means a caller can hand
    over whatever the parser produced without having to normalise it first.
    """

    if isinstance(value, (list, tuple)):

        for item in value:
            yield from _flatten(item)

        return

    if isinstance(value, dict):

        graph = value.get("@graph")

        if isinstance(graph, (list, tuple)):

            for item in graph:
                yield from _flatten(item)

        yield value


def artist_image_from_jsonld(
    blocks: Iterable[Any],
    *,
    artist_id: Optional[str] = None,
) -> Optional[str]:
    """The image from the page's own description of this artist.

    Prefers the JSON-LD `MusicGroup` block because it is the one place the page
    states "this artist, with this photograph" rather than merely linking an image
    that happens to be nearby. The block is matched on the artist ID inside its own
    URL, so a page describing several entities cannot contribute the wrong one.
    """

    for block in _flatten(blocks):

        if not isinstance(block, dict):
            continue

        block_type = block.get("@type")

        types = (
            block_type
            if isinstance(block_type, list)
            else [block_type]
        )

        if not any(
            str(value).lower() in ("musicgroup", "person", "performer")
            for value in types
        ):
            continue

        if artist_id:

            url = str(block.get("url") or block.get("@id") or "")

            if f"/{artist_id}" not in url:
                continue

        for key in ("image", "logo"):

            value = block.get(key)

            for candidate in (
                value if isinstance(value, list) else [value]
            ):

                if is_valid_artist_image(candidate):

                    return _absolute(candidate.strip())

    return None


def resolve_artist_image(
    *,
    jsonld_blocks: Iterable[Any] = (),
    page_urls: Iterable[Any] = (),
    artist_id: Optional[str] = None,
) -> Optional[str]:
    """The one image to store for an artist, or None.

    The page's own statement first, then the largest photograph actually published
    for this artist. Both sources are the same page, and neither can supply an
    image belonging to somebody else.
    """

    stated = artist_image_from_jsonld(
        jsonld_blocks, artist_id=artist_id
    )

    if stated and is_valid_artist_image(stated):
        return stated

    return pick_artist_image(page_urls, artist_id=artist_id)