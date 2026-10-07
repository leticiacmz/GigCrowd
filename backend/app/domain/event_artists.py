"""Which artists an event belongs to.

An event names its performers in one of two ways, and a correct answer has to
read both:

* **Direct references.** A concert carries `artist_slug` for the headline and
  `artist_slugs` for a multi-artist bill.
* **A structured lineup.** A festival date carries a `lineup` array, because a
  festival has no single performer and Songkick states them one per entry.

Reading only the first is what made an artist's history silently miss every
festival they played: `get_by_artist_slug` matched `artist_slug` and
`artist_slugs` and returned nothing for Marina Sena, who appears on the lineup
of a festival that Leticia attended.

Two rules keep this honest:

* **Only stored identity is used.** A lineup entry's Songkick id and slug are
  read, never derived from its name. An event's title is never searched for an
  artist's name, because "Marina Sena at Distrito Anhembi" would then match an
  event she did not play.
* **Membership is a set.** The same act listed twice on one bill is one
  performer of that event, not two, so every function here returns a set and the
  duplicates disappear at the source rather than being deduplicated by whatever
  happens to consume it later.
"""
from __future__ import annotations

from typing import Iterable, Optional

# The Songkick id as it appears on a lineup entry: bare digits.
#
# Artists store the same identifier in the prefixed form a Songkick artist URL
# uses, so translating between the two spellings is the only work needed to
# compare them.
EXTERNAL_ID_PREFIX = "Artist"


def bare_songkick_id(value: Optional[str]) -> Optional[str]:
    """The bare numeric part of a Songkick artist id.

    Accepts either spelling, because a caller should not have to know which form
    it happens to be holding.
    """

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if text.lower().startswith(EXTERNAL_ID_PREFIX.lower()):
        text = text[len(EXTERNAL_ID_PREFIX):]

    return text or None


def prefixed_songkick_id(value: Optional[str]) -> Optional[str]:
    """The stored form of a Songkick artist id."""

    bare = bare_songkick_id(value)

    if bare is None:
        return None

    return f"{EXTERNAL_ID_PREFIX}{bare}"


def direct_artist_slugs(event: dict) -> set[str]:
    """The artists named directly on an event.

    `artist_slug` is the single headline and `artist_slugs` the whole bill. Both
    are read because an older import may have written only one of them.
    """

    slugs: set[str] = set()

    single = event.get("artist_slug")

    if single:
        slugs.add(str(single))

    for slug in event.get("artist_slugs") or []:
        if slug:
            slugs.add(str(slug))

    return slugs


def lineup_artist_slugs(event: dict) -> set[str]:
    """The artists named by an event's structured lineup."""

    slugs: set[str] = set()

    for entry in event.get("lineup") or []:

        if not isinstance(entry, dict):
            continue

        slug = entry.get("slug")

        if slug:
            slugs.add(str(slug))

    return slugs


def lineup_songkick_ids(event: dict) -> set[str]:
    """The Songkick ids named by an event's structured lineup.

    Kept separate from the slugs because it answers a different question: a slug
    is this project's own name for an artist, while a Songkick id is the
    provider's. Both are real identifiers; neither is derived from a name.
    """

    ids: set[str] = set()

    for entry in event.get("lineup") or []:

        if not isinstance(entry, dict):
            continue

        value = entry.get("songkick_id") or entry.get("songkickId")

        bare = bare_songkick_id(value)

        if bare:
            ids.add(bare)

    return ids


def artist_slugs_of(event: dict) -> set[str]:
    """Every artist this event belongs to, by slug, as a set.

    This is the *event's* membership: who is on this bill. It is what an
    artist's own event list is built from, and a festival date legitimately
    belongs to every act on its lineup.

    It is deliberately NOT what a person's concert history is built from. See
    `personal_artist_slugs`.
    """

    return (
        direct_artist_slugs(event)
        | lineup_artist_slugs(event)
    )


def personal_artist_slugs(event: dict) -> set[str]:
    """The artists whose show this event is, for attendance purposes.

    A lineup is not a record of what someone watched. Someone can buy a
    festival ticket, walk past most of the bill and still have a good night,
    which is why attending a festival date must not add every act on it to their
    history. Only a direct artist reference on the event counts: the show this
    person says they went to was this artist's show.

    Reading the direct reference rather than the lineup also keeps a multi-act
    concert honest. A Marina Sena show whose bill lists four acts is a Marina
    Sena show; the support acts are on the bill but they are not why the event
    belongs to Marina Sena, and a past concert whose `lineup` merely mirrors its
    single `artist_slug` gains nothing by being read twice.
    """

    return direct_artist_slugs(event)


def event_artists(event: dict) -> list[str]:
    """Every artist this event belongs to, in a stable order.

    Sorted so that two runs over the same event produce the same list, which is
    what lets a caller compare or cache it.
    """

    return sorted(artist_slugs_of(event))


def artist_membership_filter(
    artist_slug: str,
    songkick_id: Optional[str] = None,
) -> dict:
    """The MongoDB clause matching every event this artist appears on.

    Both routes an event can take are covered: a direct reference, and a lineup
    entry. The lineup is matched on the Songkick id when one is known, because
    that is the identifier both systems agree on, and on the slug as well so an
    event whose lineup predates the id is still found.

    `songkick_id` may be either spelling; it is normalised here.
    """

    clauses: list[dict] = [
        {"artist_slug": artist_slug},
        {"artist_slugs": artist_slug},
        {"lineup.slug": artist_slug},
    ]

    bare = bare_songkick_id(songkick_id)

    if bare:
        clauses.append({"lineup.songkick_id": bare})
        # Some rows spell it the way a Songkick URL does.
        clauses.append({
            "lineup.songkick_id": f"{EXTERNAL_ID_PREFIX}{bare}"
        })

    return {"$or": clauses}


def count_attended_shows_per_artist(
    events: Iterable[dict],
) -> dict[str, int]:
    """How many of these events each artist actually played for this person.

    The count is of *distinct events*, so an act named twice on one bill
    contributes once and two separate concrete shows contribute twice.

    Only `personal_artist_slugs` is read, so a festival date contributes
    nothing: attending a festival is not attending every performance on it.
    """

    seen: dict[str, set[str]] = {}

    for event in events:

        event_id = str(event.get("_id") or "")

        for slug in personal_artist_slugs(event):
            seen.setdefault(slug, set()).add(event_id)

    return {
        slug: len(event_ids)
        for slug, event_ids in seen.items()
    }


def songkick_ids_across_events(
    events: Iterable[dict],
) -> dict[str, str]:
    """Map artist slug to Songkick id across a set of events.

    Every lineup entry contributes both of its identifiers, so a caller holding
    either one can find the other. Entries without a Songkick id are skipped
    rather than mapped to something invented.
    """

    found: dict[str, str] = {}

    for event in events:

        for entry in event.get("lineup") or []:

            if not isinstance(entry, dict):
                continue

            slug = entry.get("slug")

            bare = bare_songkick_id(
                entry.get("songkick_id")
                or entry.get("songkickId")
            )

            if slug and bare:
                found.setdefault(str(slug), bare)

    return found

