"""A festival's source address must survive enrichment that read no URL.

The enrichment that joins a search document onto an event used to write
`source["url"]` only when the *search document itself* carried one. A search
document without a URL - the shape the Lollapalooza 2027 listings arrived in -
produced `source = {provider, event_id}` and nothing else, while the same
event's own JSON-LD address sat on the payload and was happily written into
`festival.url` by the same function. The provenance rule is right to hide a
future event whose provider cannot be checked, so the address the payload
already states has to reach the source.

These tests pin the shapes involved: a search document with an absolute URL,
one with only a relative `uri`, one with none at all, and none at all on
either side.
"""
from datetime import UTC, datetime

from app.domain.event_provenance import (
    classify,
    is_trustworthy_upcoming,
)
from app.providers.songkick.client import SongkickClient


EVENT_ID = "43456086"

EVENT_URL = (
    "https://www.songkick.com/festivals/1235-lollapalooza/"
    "id/43456086-lollapalooza-2027"
)

FUTURE = datetime(2027, 3, 12, tzinfo=UTC)


def base_event(**extra) -> dict:
    event = {
        "songkick_id": EVENT_ID,
        "name": "David Guetta at Lollapalooza 2027",
        "url": EVENT_URL,
        "is_festival": True,
    }
    event.update(extra)
    return event


def enrich(event: dict, search_document: dict) -> dict:
    return SongkickClient._enrich_event_with_search_data(
        event,
        {EVENT_ID: search_document},
    )


def test_a_search_document_with_a_url_still_stamps_the_source():
    """The long-standing shape: the search document states the address."""

    enriched = enrich(
        base_event(),
        {
            "name": "Lollapalooza 2027",
            "url": EVENT_URL + "?utm_source=feed",
        },
    )

    source = enriched["source"]

    assert source["provider"] == "songkick"
    assert source["event_id"] == EVENT_ID
    # Query strings are not part of the address of record.
    assert source["url"] == EVENT_URL


def test_a_search_document_without_a_url_falls_back_to_the_event_address():
    """The Lollapalooza 2027 case: no URL on the search document at all.

    The JSON-LD listing read for the event carries its own Songkick address,
    and that address has to reach the source - otherwise the row stores a
    provider with nothing to check it against and the trust rule hides a
    future event the catalogue actually holds.
    """

    enriched = enrich(
        base_event(),
        {"name": "Lollapalooza 2027"},
    )

    assert enriched["source"]["url"] == EVENT_URL


def test_a_relative_uri_on_the_search_document_is_not_stored():
    """Songkick's search documents also carry relative `uri` values.

    Storing one would render as a link into GigCrowd itself, and the
    provenance rule would still refuse it - so the chain skips it and lands
    on the absolute address the event itself states.
    """

    enriched = enrich(
        base_event(),
        {
            "name": "Lollapalooza 2027",
            "uri": "/festivals/1235-lollapalooza/id/43456086",
        },
    )

    source = enriched["source"]

    assert source["url"] == EVENT_URL
    assert not source["url"].startswith("/")


def test_an_already_stored_source_address_is_not_replaced():
    """A payload that already carries an address keeps the one it carries."""

    kept = "https://www.songkick.com/events/999-kept"

    enriched = enrich(
        base_event(source={"provider": "songkick", "event_id": EVENT_ID, "url": kept}),
        {"name": "Lollapalooza 2027"},
    )

    assert enriched["source"]["url"] == kept


def test_no_address_anywhere_still_stamps_provider_and_id():
    """With nothing to state, nothing is invented: only the identity lands."""

    event = {
        "songkick_id": EVENT_ID,
        "name": "David Guetta at Lollapalooza 2027",
        "is_festival": True,
    }

    enriched = enrich(event, {"name": "Lollapalooza 2027"})

    source = enriched["source"]

    assert source["provider"] == "songkick"
    assert source["event_id"] == EVENT_ID
    assert not source.get("url")


def test_the_backfilled_source_is_trusted_for_a_future_event():
    """End to end with the rule that hides rows: address present -> shown."""

    enriched = enrich(
        base_event(),
        {"name": "Lollapalooza 2027"},
    )

    document = {
        "external_ids": {"songkick": EVENT_ID},
        "source": enriched["source"],
        "starts_at": FUTURE,
    }

    assert classify(document) == "songkick"

    verdict, reason = is_trustworthy_upcoming(document)
    assert verdict is True
    assert reason == "verified_songkick_provenance"


def test_the_same_event_without_the_fallback_is_hidden():
    """The counterfactual: the block the enrichment used to write.

    Pinned so the fix cannot be removed while the symptom - future rows the
    listing refuses to show - stays invisible in tests.
    """

    document = {
        "external_ids": {"songkick": EVENT_ID},
        "source": {"provider": "songkick", "event_id": EVENT_ID},
        "starts_at": FUTURE,
    }

    verdict, reason = is_trustworthy_upcoming(document)
    assert verdict is False
    assert "no source" in reason
