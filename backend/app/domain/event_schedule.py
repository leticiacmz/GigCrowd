"""When an event happens.

Imported events are inconsistent about dates. A concert carries `starts_at`, a
multi-day festival carries `ends_at` on top of it, and a number of rows synced
from providers without a usable date carry neither. Every rule about
attendance, "has this already happened?" and the date recorded on a show log
therefore resolves through this module, so there is exactly one definition of
an event's schedule and a missing date is reported instead of crashing whoever
asked about it.

The functions accept both the `Event` domain object and a raw stored document,
so the mappers, the services and the statistics all share one answer.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Optional

# Message returned to the caller when an event carries no date at all. It is
# phrased as a product decision (the event is not ready to be logged) rather
# than as a server fault, because that is what it is.
EVENT_DATE_UNAVAILABLE = (
    "This event has no confirmed date yet, so attendance cannot be recorded."
)


class EventDateUnavailable(ValueError):
    """The event has no date, so it cannot be compared against "now".

    Subclasses `ValueError` because that is the exception the show-log routes
    already translate into a deliberate 400 instead of a 500.
    """

    def __init__(
        self,
        message: str = EVENT_DATE_UNAVAILABLE,
    ):
        super().__init__(message)


def _field(event: Any, name: str) -> Any:
    """Read a field from a domain object or a raw document."""
    if event is None:
        return None

    if isinstance(event, dict):
        return event.get(name)

    return getattr(event, name, None)


def as_utc(value: Any) -> Optional[datetime]:
    """Normalise a stored date into an aware UTC datetime.

    Dates imported from providers arrive both timezone-aware and naive, so a
    naive value is read as UTC rather than compared against an aware value,
    which would raise.
    """
    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def event_date(event: Any) -> Optional[datetime]:
    """The event's own date: when it starts, or when it ends if it has no start.

    This is the instant stored on a show log, so it answers "which date is this
    show?" rather than "is it over?".
    """
    starts_at = as_utc(_field(event, "starts_at"))

    if starts_at is not None:
        return starts_at

    return as_utc(_field(event, "ends_at"))


def event_reference_date(event: Any) -> Optional[datetime]:
    """The instant that says whether an event is over.

    A festival that is still running has not happened yet, so the later of the
    two dates decides. For a concert both dates describe the same evening, so
    this is simply its start.
    """
    dates = [
        moment
        for moment in (
            as_utc(_field(event, "starts_at")),
            as_utc(_field(event, "ends_at")),
        )
        if moment is not None
    ]

    if not dates:
        return None

    return max(dates)


def has_event_date(event: Any) -> bool:
    """Whether the event carries any usable date."""
    return event_reference_date(event) is not None


def is_past(event: Any, now: Optional[datetime] = None) -> bool:
    """Whether the event has already happened.

    An event with no date is never reported as past: there is no evidence that
    it happened, and guessing would let someone record attendance to an event
    that is still being announced.
    """
    reference = event_reference_date(event)

    if reference is None:
        return False

    return reference < (now or datetime.now(UTC))


def is_upcoming(event: Any, now: Optional[datetime] = None) -> bool:
    """Whether the event still has a date in front of it."""
    reference = event_reference_date(event)

    if reference is None:
        return False

    return reference >= (now or datetime.now(UTC))


def require_event_date(event: Any) -> datetime:
    """The event's reference date, or a controlled failure when it has none."""
    reference = event_reference_date(event)

    if reference is None:
        raise EventDateUnavailable()

    return reference
