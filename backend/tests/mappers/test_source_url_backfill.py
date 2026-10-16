"""The mapper must not persist a provider claim with no address to check.

A payload may arrive with a `source` block that states the provider and the
event id but no URL - that is exactly the shape `_enrich_event_with_search_data`
writes when the search document has no URL - while the payload itself carries
a perfectly usable one, or a festival block that does. The block used to be
trusted wholesale, the row was stored addressless, and the provenance rule
then hid it from every future listing.

These tests pin the defensive backfill: what it takes, what it refuses, and
what it never replaces.
"""
from datetime import UTC, datetime

from app.domain.event_provenance import (
    classify,
    is_trustworthy_upcoming,
)
from app.mappers.songkick_event_mapper import SongkickEventMapper


EVENT_URL = (
    "https://www.songkick.com/festivals/1235-lollapalooza/"
    "id/43456086-lollapalooza-2027"
)

FESTIVAL_URL = "https://www.songkick.com/festivals/1235-lollapalooza"

FUTURE = datetime(2027, 3, 12, tzinfo=UTC)


def payload(**extra) -> dict:
    data = {
        "songkick_id": "43456086",
        "name": "David Guetta at Lollapalooza 2027",
        "event_type": "FestivalInstance",
        "url": EVENT_URL,
    }
    data.update(extra)
    return data


def map_payload(data: dict):
    event, _ = SongkickEventMapper.to_domain(data, ["david-guetta"])
    return event


def test_a_source_block_without_a_url_is_backfilled_from_the_payload():
    event = map_payload(
        payload(
            source={
                "provider": "songkick",
                "event_id": "43456086",
            },
        )
    )

    assert event.source["url"] == EVENT_URL
    # The rest of the block is carried through untouched.
    assert event.source["provider"] == "songkick"
    assert event.source["event_id"] == "43456086"


def test_a_festival_block_supplies_the_address_when_the_payload_has_none():
    """The shape the diagnosis found: `festival.url` was written, `source`
    was not - so the festival block's address is the next candidate."""

    event = map_payload(
        payload(
            url=None,
            source={"provider": "songkick", "event_id": "43456086"},
            festival={"series_id": "1235", "url": FESTIVAL_URL},
        )
    )

    assert event.source["url"] == FESTIVAL_URL


def test_an_address_already_on_the_source_block_is_never_replaced():
    kept = "https://www.songkick.com/events/999-kept"

    event = map_payload(
        payload(
            source={
                "provider": "songkick",
                "event_id": "43456086",
                "url": kept,
            },
        )
    )

    assert event.source["url"] == kept


def test_a_relative_payload_address_is_not_stored():
    """Only the shape a browser can open becomes a source address."""

    event = map_payload(
        payload(
            url="/events/43456086",
            source={"provider": "songkick", "event_id": "43456086"},
        )
    )

    assert not event.source.get("url")


def test_a_payload_without_a_source_block_keeps_the_default_shape():
    """The default branch behaves as it always did, now address-validated."""

    event = map_payload(payload())

    assert event.source["provider"] == "songkick"
    assert event.source["external_id"] == "43456086"
    assert event.source["url"] == EVENT_URL


def test_a_default_shape_never_stores_a_relative_address():
    event = map_payload(payload(url="/events/43456086"))

    assert event.source["provider"] == "songkick"
    assert not event.source.get("url")


def test_the_backfilled_block_reads_as_a_verified_future_event():
    """The mapper's own output, judged by the rule that gates listings."""

    event = map_payload(
        payload(
            source={"provider": "songkick", "event_id": "43456086"},
        )
    )

    document = {
        "external_ids": event.external_ids,
        "source": event.source,
        "starts_at": FUTURE,
    }

    assert classify(document) == "songkick"
    assert is_trustworthy_upcoming(document)[0] is True
