"""One artist appearing in a festival's lineup.

A lineup entry is what Songkick actually exposes: the artist's name, the
Songkick artist identifier when the page carries one, and the artist's own
Songkick URL. The identifier is what makes the entry safe to deduplicate and to
resolve later, so it is never derived from the name and never invented.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LineupEntry(BaseModel):
    """One performer on a concrete festival event."""

    name: str

    # The Songkick artist id, taken from the artist URL. Optional because a
    # source may expose a performer without one; an entry with no id is still
    # shown, it simply cannot be resolved to a GigCrowd artist yet.
    songkick_id: Optional[str] = None

    # Songkick's own URL for the artist, without tracking parameters.
    url: Optional[str] = None

    # Songkick slug, taken from the same URL as the id.
    slug: Optional[str] = None

    image: Optional[str] = None

    genres: list[str] = Field(default_factory=list)

    # Position in the source lineup, which is the order Songkick renders.
    order: int = 0

    def identity(self) -> str:
        """The stable key used to deduplicate a lineup.

        The Songkick id when there is one, otherwise the normalized name. A
        name is only ever a fallback for deduplication, never an identifier.
        """

        if self.songkick_id:
            return f"id:{self.songkick_id}"

        return f"name:{' '.join(self.name.casefold().split())}"


def dedupe_lineup(
    entries: list[LineupEntry],
) -> list[LineupEntry]:
    """Drop repeated performers while keeping the first appearance.

    The same artist can appear twice in a source lineup, and two entries can
    carry the same id with slightly different names. The first wins because it
    is the one the source put in its own order.
    """

    seen: set[str] = set()
    result: list[LineupEntry] = []

    for entry in entries:
        key = entry.identity()

        if key in seen:
            continue

        seen.add(key)
        result.append(entry)

    for position, entry in enumerate(result):
        entry.order = position

    return result