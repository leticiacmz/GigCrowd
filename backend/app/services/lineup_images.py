"""Photos for a whole lineup, in one query.

The photo lives on the artist document; the lineup entry carries an `image`
field that import has never filled, so serving a bill with faces needs a
lookup - and one lookup per performer would be an N+1 across the hundreds of
acts a festival lists. One query answers the whole page.

Identity is the caller's to have settled first: the ids passed in are the
ones the resolver already matched unambiguously, because a photo claims *who*
this is just as a link does. Nothing here matches on a name, and an id with
no page simply gets no photo - an unverifiable face is a clean absence, not
a guess.

The image returned is the artist document's own, which import filled by its
own priority (Songkick's page first, Spotify only when Songkick had none).
An entry whose own image was ever populated keeps it: this lookup fills
empty slots, it never overwrites a photo that already exists.
"""
from __future__ import annotations

from typing import Iterable

from app.services.lineup_artist_resolver import (
    external_id_for,
    stored_id_of,
)


async def lineup_images(
    artist_repository,
    resolved_songkick_ids: Iterable[str],
) -> dict[str, str]:
    """Bare Songkick id to artist photo, for ids that already resolve.

    The keys are the bare numeric ids a lineup entry carries - the stored
    `Artist...` spelling is translated here rather than left for each caller,
    so the two spellings have one owner in this path, same as the resolver.
    """

    ids = {
        str(value).strip()
        for value in resolved_songkick_ids
        if value and str(value).strip()
    }

    if not ids or artist_repository is None:
        return {}

    documents = await (
        artist_repository.collection.find(
            {
                "external_ids.songkick": {
                    "$in": [
                        external_id_for(value)
                        for value in ids
                    ]
                }
            },
            {
                "image": 1,
                "external_ids.songkick": 1,
            },
        ).to_list(length=None)
    )

    images: dict[str, str] = {}

    for document in documents:
        image = document.get("image")

        external = (
            document.get("external_ids") or {}
        ).get("songkick")

        if image and external:
            images[stored_id_of(str(external))] = image

    return images
