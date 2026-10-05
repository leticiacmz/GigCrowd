"""Where an event came from, and whether that can be believed.

A date being valid says the event is dated. It does not say the event is real.
A development fixture can carry a perfectly plausible future date and a
Songkick-shaped URL that 404s, and the stored document is otherwise
indistinguishable from a real import - which is how a show for an artist who is
not touring ends up presented as an upcoming gig.

So provenance is recorded rather than inferred at read time, and an event that
claims to come from a provider has to be able to show it.

Three origins, and only three:

* `songkick` - read from a Songkick page. The page is the evidence.
* `fixture` - written by this project's development seed. Real enough to
  develop against, explicitly not a claim about the world. A festival running
  into next year is a fixture, not an announcement.
* `unknown` - claims a provider but carries no source to check, so nothing can
  be concluded either way. Never treated as real.

The rules are deliberately about *provenance*, never about an artist. Gal Costa
is not special-cased, and neither is anyone else: a fixture stays a fixture
whatever it is called, and a real Songkick event stays real.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

PROVENANCE_SONGKICK = "songkick"
PROVENANCE_FIXTURE = "fixture"
PROVENANCE_UNKNOWN = "unknown"

PROVENANCES = (
    PROVENANCE_SONGKICK,
    PROVENANCE_FIXTURE,
    PROVENANCE_UNKNOWN,
)

# The Songkick id block the development seed writes its own events into.
#
# Declared once, here, and imported by the seed, so there is a single answer to
# "which ids are ours?". It exists because the seed needs deterministic ids for
# fixtures, and a real Songkick artist id is the only shape the rest of the
# system knows how to read. Keeping the block narrow and declared means
# identifying a fixture is a lookup rather than a guess.
DEV_FIXTURE_ID_PREFIX = "9900"


def synthetic_songkick_id(value: Any) -> bool:
    """Whether this identifier belongs to the development fixture block.

    Used to recognise rows the seed already wrote before provenance was recorded,
    so they can be labelled without touching anything real.
    """

    if value is None:
        return False

    text = str(value)

    if text.lower().startswith("artist"):
        text = text[len("artist"):]

    return text.startswith(DEV_FIXTURE_ID_PREFIX)


def classify(document: dict) -> str:
    """The provenance of a stored event document.

    Read from what is stored, in a fixed order, so the same document always
    classifies the same way. A recorded `provenance` is believed - it was written
    deliberately - and only its absence falls through to inference.

    The fixture id block is checked before the URL shape, and the order matters.
    A fixture has to carry a provider name and a provider-shaped URL to be usable
    at all, so testing the URL first classified every fixture as an import - and
    a 2026 show for an artist who is not touring read as an announced gig. A
    specific identifier is stronger evidence than a generic URL shape, so it is
    read first.
    """

    recorded = (document.get("source") or {}).get("provenance")

    if recorded in PROVENANCES:
        return recorded

    source = document.get("source") or {}

    provider = source.get("provider")
    url = source.get("url") or ""
    songkick_id = (document.get("external_ids") or {}).get("songkick")

    if synthetic_songkick_id(songkick_id):
        return PROVENANCE_FIXTURE

    # A concrete URL on the provider's own host is the evidence. Anything else -
    # a URL on another host, or none at all - cannot be checked by anyone.
    if provider == "songkick" and url.startswith(
        "https://www.songkick.com/"
    ):
        return PROVENANCE_SONGKICK

    if provider or url:
        return PROVENANCE_UNKNOWN

    return PROVENANCE_UNKNOWN


def has_concrete_source(document: dict) -> bool:
    """Whether this event's claim can be checked against a source."""

    url = (document.get("source") or {}).get("url") or ""

    return url.startswith("https://www.songkick.com/")


def reaches_into_the_future(
    document: dict,
    now: Optional[datetime] = None,
) -> bool:
    """Whether this event claims to happen after now."""

    moment = now or datetime.now(UTC)

    for field in ("ends_at", "starts_at"):
        value = document.get(field)

        if isinstance(value, datetime) and value > moment:
            return True

    return False


def is_trustworthy_upcoming(
    document: dict,
    now: Optional[datetime] = None,
) -> tuple[bool, str]:
    """Whether a future-dated event may be presented as a real upcoming show.

    Returns the verdict and the reason, because a bare boolean hides the
    difference between "we know this is ours" and "we cannot tell".

    A future event has to survive two questions. Does it have a concrete source
    to check? And is that source the real provider rather than this project's own
    fixture data? A fixture passes the first and fails the second, which is the
    whole point: its date is as good as the fixture's, and it is not a claim
    about what anyone is playing.
    """

    provenance = classify(document)

    if not reaches_into_the_future(document, now):
        return True, "not_upcoming"

    if provenance == PROVENANCE_FIXTURE:
        return (
            False,
            "development fixture, not a provider event",
        )

    if not has_concrete_source(document):
        return (
            False,
            "claims a provider but has no source to verify",
        )

    if provenance != PROVENANCE_SONGKICK:
        return (
            False,
            f"unverifiable provenance {provenance!r}",
        )

    return True, "verified_songkick_provenance"
