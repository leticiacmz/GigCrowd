"""What state is this artist in, and who is allowed to change it?

There are three states an artist can be in, and confusing any two of them causes
a bug that is invisible from the outside.

    PENDING       A festival announced them, their Songkick identity was checked
                  against the artist's own page, and a minimal record was written.
                  The name is real and the id is real. Nothing has been fetched
                  about their shows yet.

    INITIALIZED   A gigography has been fetched. "Fetched and found nothing" counts
                  as initialized: an artist with no shows is not an artist we have
                  not looked at yet.

    ERROR         A fetch was attempted and failed. Retryable, and deliberately
                  *not* the same as pending, so that a provider outage does not
                  look like an artist who has never been asked.

Derived from `sync_status` and `last_synced_at` rather than from a new field. The
model already carries both; adding an `availability` column beside them would mean
two sources of truth for one fact, and the one nobody remembers to update is the
one that decides whether a page performs a full gigography scrape.

Two rules follow, and they are the reason this module exists:

* **A pending artist's first page view may initialize it.** That is the only
  permitted read with a write in it, and it is bounded by a claim (see
  `ArtistRepository.claim_initialization`) so that two people opening the page at
  the same moment produce one fetch rather than two.
* **An initialized artist's page view is read-only.** Always. Re-fetching on every
  view is what made this application's artist pages unusable before: the catalogue
  depended on who happened to look, one request could spend an unbounded number of
  calls inside the provider, and a page view wrote rows nobody asked it to.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Optional

#: Identity is established; no gigography has been fetched.
PENDING = "pending"

#: A gigography fetch completed. `last_synced_at` records when.
INITIALIZED = "initialized"

#: A fetch was attempted and failed. Retryable.
ERROR = "error"

#: A fetch is in flight right now, claimed by one caller.
#:
#: Transient, and never written by anything except the claim itself. It exists so
#: that two concurrent first opens cannot both decide "nobody has claimed this".
#: Treated as initialized for every decision a reader makes, because from the
#: outside the artist *is* being handled.
INITIALIZING = "initializing"


# The `sync_status` values written by `SynchronizationService`.
SYNC_SUCCESS = "success"

#: The provider was asked and had nothing. A completed answer, so initialized.
SYNC_EMPTY = "empty"

SYNC_ERROR = "error"

#: Every value `sync_status` is allowed to hold.
#
#: Listed rather than inferred, so that a new status has to be classified
#: deliberately. An unrecognised status is treated as "not pending", which is the
#: safe direction: the worst case is a page that does not fetch, rather than a
#: page that fetches a gigography on every view.
KNOWN_SYNC_STATUSES = frozenset(
    {
        SYNC_SUCCESS,
        SYNC_EMPTY,
        SYNC_ERROR,
        INITIALIZING,
    }
)


def artist_state(artist: Any) -> str:
    """The state of one artist, from whatever fields it happens to carry.

    Accepts a domain `Artist`, a raw Mongo document, or anything with the two
    attributes, because every caller that needs this holds one or the other and
    neither should have to convert first.
    """

    status = _read(artist, "sync_status")

    # An unrecognised status is not "pending". A status this code has never seen
    # is more likely to be a newer, more complete state than a missing one, and
    # guessing "pending" would turn it into a gigography scrape on page view.
    if status is not None and status not in KNOWN_SYNC_STATUSES:
        return INITIALIZED

    if status == INITIALIZING:
        return INITIALIZING

    if status == SYNC_ERROR:
        return ERROR

    if status in (SYNC_SUCCESS, SYNC_EMPTY):
        return INITIALIZED

    # No status at all. A timestamp is the other, older way of saying "we have
    # asked"; honour it so an artist synced before `sync_status` existed is not
    # mistaken for one that never was.
    if _read(artist, "last_synced_at") is not None:
        return INITIALIZED

    return PENDING


def is_pending(artist: Any) -> bool:
    """Whether this artist has never had a gigography fetch attempted.

    Not the question the first-open path asks - that one is `may_initialize`,
    which also decides whether a retry is due yet. This is the narrower fact,
    kept separate because "nobody has ever asked" and "the last ask was lost"
    are different situations and reading them as one is what makes a provider
    outage look like a catalogue of artists nobody wants.
    """

    return artist_state(artist) == PENDING


def needs_initialization(artist: Any) -> bool:
    """Whether opening this artist is allowed to fetch.

    An artist mid-claim is left alone: somebody else is already fetching, and a
    second fetch would be the double-scrape this whole distinction exists to
    prevent.
    """

    return artist_state(artist) in (PENDING, ERROR)


def may_initialize(
    artist: Any,
    *,
    retry_cooldown: Optional[timedelta] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Whether *this* page view may fetch, counting how recently it last failed.

    `needs_initialization` says an errored artist is retryable in principle. This
    says whether to retry it right now, which is a different question.

    Without the cooldown, a permanently broken identity - an act deleted from the
    provider, an id that has been reassigned - costs one failed outbound request
    and one write on *every* page view, forever. That is a page load scraping a
    provider, which is the thing this whole model exists to stop, arrived at from
    the other direction. A cooldown makes it one attempt per TTL instead, which is
    proportionate to something that is not going to start working.

    The cooldown is read from `updated_at`, which is the only record a failed
    attempt leaves: `last_synced_at` is deliberately not written on failure,
    because a timestamp is exactly what makes an artist look initialized. So the
    field is overloaded, but only in the one state where the alternative field is
    deliberately blank, and the alternative - a new `last_attempted_at` column -
    would be a second piece of synchronization metadata to keep in step with the
    first.

    A *pending* artist is never cooled down. It has never been asked, so there is
    nothing to wait for, and delaying its first fetch would just hand the reader
    an empty page.
    """

    state = artist_state(artist)

    if state == PENDING:
        return True

    if state != ERROR:
        return False

    if retry_cooldown is None:
        return True

    last_attempt = _read(artist, "updated_at")

    if last_attempt is None:
        return True

    if last_attempt.tzinfo is None:
        last_attempt = last_attempt.replace(tzinfo=UTC)

    moment = now or datetime.now(UTC)

    return (moment - last_attempt) >= retry_cooldown


def is_initialized(artist: Any) -> bool:
    """Whether this artist's page is read-only."""

    return artist_state(artist) in (INITIALIZED, INITIALIZING)


def _read(artist: Any, field: str) -> Optional[Any]:
    """One field, from a document or an object."""

    if isinstance(artist, dict):
        return artist.get(field)

    return getattr(artist, field, None)
