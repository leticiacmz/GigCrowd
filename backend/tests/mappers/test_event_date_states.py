"""What the client is told about a date, and about whether anybody asked.

`date_status` alone cannot carry the distinction that matters to a reader: an
event that has never been checked and an event whose source was read and had
nothing to say both look like "no date" unless the read time travels beside the
status. Storage already holds both fields, so this is about the mapping being
honest rather than about inventing a state.
"""
from __future__ import annotations

from datetime import UTC, datetime

from app.mappers.event_document_mapper import EventDocumentMapper
from app.mappers.event_response_mapper import EventResponseMapper


def read(document: dict):
    return EventResponseMapper.from_domain(
        EventDocumentMapper.to_domain(document),
        None,
    )


A_DOCUMENT = {
    "_id": "650000000000000000000001",
    "title": "Marina Sena at Electric Brixton",
    "venue_slug": "electric-brixton",
    "artist_slug": "marina-sena",
    "artist_slugs": ["marina-sena"],
}


class TestTheThreeDateStatesAreToldApart:
    def test_a_concrete_source_date_says_so(self):
        response = read(
            {
                **A_DOCUMENT,
                "starts_at": datetime(2026, 10, 30, 18, 30, tzinfo=UTC),
                "date_status": "source",
            }
        )

        assert response.starts_at == datetime(
            2026, 10, 30, 18, 30, tzinfo=UTC
        )
        assert response.date_status == "source"

    def test_checked_and_unavailable_carries_its_timestamp(self):
        """A finished answer, and the proof that it is finished."""

        checked_at = datetime(2026, 10, 7, 4, 48, tzinfo=UTC)

        response = read(
            {
                **A_DOCUMENT,
                "date_status": "unavailable",
                "date_source_checked_at": checked_at,
            }
        )

        assert response.starts_at is None
        assert response.date_status == "unavailable"
        assert response.date_source_checked_at == checked_at

    def test_never_checked_is_not_reported_as_unavailable(self):
        """The read-time fallback asserted a verdict storage never made.

        `None` for both fields is the only shape that says "nobody has looked":
        it cannot be mistaken for a checked event, because a checked event
        carries the timestamp that proves somebody did.
        """

        response = read(A_DOCUMENT)

        assert response.starts_at is None
        assert response.date_status is None
        assert response.date_source_checked_at is None

    def test_a_document_before_the_status_existed_keeps_its_date(self):
        """A dated row has an answer whoever wrote it."""

        response = read(
            {
                **A_DOCUMENT,
                "starts_at": datetime(2026, 10, 30, 18, 30, tzinfo=UTC),
            }
        )

        assert response.date_status == "source"
        assert response.date_source_checked_at is None
