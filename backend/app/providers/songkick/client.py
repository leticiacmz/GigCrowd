import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urljoin

from curl_cffi import requests
from bs4 import BeautifulSoup

from app.config import settings
from app.core.logger import get_logger


logger = get_logger("songkick_client")


class SongkickClient:

    def __init__(self):
        self.base_url = (
            settings.SONGKICK_BASE_URL.rstrip("/")
        )

        self.search_endpoint = (
            "/api/universal_search"
        )

        self.timeout = 60

        self.headers = {
            "accept": (
                "application/json, "
                "text/plain, */*"
            ),
            "accept-language": "en-US",
            "referer": (
                f"{self.base_url}/"
            ),
            "origin": self.base_url,
            "user-agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/148.0.0.0 Safari/537.36"
            ),
            "sec-ch-ua": (
                '"Not/A)Brand";v="99", '
                '"Chromium";v="148", '
                '"Google Chrome";v="148"'
            ),
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "priority": "u=1, i",
        }

    # ============================================================
    # HTTP
    # ============================================================

    def _request_sync(
        self,
        url: str,
        *,
        accept: str = (
            "text/html,application/xhtml+xml"
        ),
    ):
        headers = dict(self.headers)
        headers["accept"] = accept

        logger.debug(
            f"curl_cffi GET {url}"
        )

        response = requests.get(
            url,
            headers=headers,
            impersonate="chrome",
            timeout=self.timeout,
            allow_redirects=True,
        )

        return response

    async def _request(
        self,
        url: str,
        *,
        accept: str = (
            "text/html,application/xhtml+xml"
        ),
    ):
        return await asyncio.to_thread(
            self._request_sync,
            url,
            accept=accept,
        )

    # ============================================================
    # UNIVERSAL SEARCH
    # ============================================================

    async def search_artist(
        self,
        artist_name: str,
    ) -> dict:

        logger.info(
            f"Searching Songkick for: {artist_name}"
        )

        endpoint = (
            f"{self.base_url}"
            f"{self.search_endpoint}"
            f"?query={quote(artist_name)}"
        )

        response = await self._request(
            endpoint,
            accept=(
                "application/json, "
                "text/plain, */*"
            ),
        )

        logger.info(
            "Songkick universal_search status="
            f"{response.status_code}"
        )

        if response.status_code != 200:
            logger.error(
                "Songkick API returned "
                f"{response.status_code}"
            )

            logger.error(
                response.text[:2000]
            )

            raise Exception(
                "Songkick API error: "
                f"{response.status_code}"
            )

        try:
            data = response.json()

        except Exception as exc:

            logger.error(
                "Songkick response is not valid JSON"
            )

            logger.error(
                response.text[:2000]
            )

            raise Exception(
                "Invalid JSON returned by Songkick"
            ) from exc

        return data

    async def search_artist_full(
        self,
        artist_name: str,
    ) -> dict:

        raw_data = await self.search_artist(
            artist_name
        )

        attributes = (
            raw_data
            .get("data", {})
            .get("attributes", {})
        )

        search_results = (
            attributes.get(
                "search_results",
                {},
            )
        )

        artists = search_results.get(
            "artists",
            [],
        )

        events = search_results.get(
            "events",
            [],
        )

        past_events = search_results.get(
            "past_events",
            [],
        )

        top_results = search_results.get(
            "top_results",
            [],
        )

        logger.info(
            "Songkick search results: "
            f"{len(artists)} artists, "
            f"{len(events)} future events, "
            f"{len(past_events)} past events, "
            f"{len(top_results)} top results"
        )

        logger.info(
            "Universal search future events raw: %s",
            json.dumps(
                events,
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )

        return {
            "raw": raw_data,
            "artists": artists,
            "events": events,
            "past_events": past_events,
            "top_results": top_results,
        }

    # ============================================================
    # ARTIST PAGE
    # ============================================================

    async def get_artist_page(
        self,
        artist_url: str,
    ) -> dict:

        logger.info(
            "Fetching Songkick artist page: "
            f"{artist_url}"
        )

        response = await self._request(
            artist_url
        )

        if response.status_code != 200:
            raise Exception(
                "Songkick artist page error: "
                f"{response.status_code}"
            )

        analysis = self._analyze_artist_page(
            response.text,
            artist_url,
        )

        logger.info(
            "Artist page parsed: "
            f"upcoming={len(analysis['upcoming_events'])}, "
            f"festivals={len(analysis['upcoming_festivals'])}"
        )

        return {
            "url": artist_url,
            "status": response.status_code,
            "html": response.text,
            "upcoming_events": (
                analysis["upcoming_events"]
            ),
            "upcoming_festivals": (
                analysis["upcoming_festivals"]
            ),
        }

    # ============================================================
    # GIGOGRAPHY
    # ============================================================

    async def get_gigography(
        self,
        artist_url: str,
    ) -> dict:

        gigography_url = (
            artist_url.rstrip("/")
            + "/gigography"
        )

        logger.info(
            "Starting Songkick gigography: "
            f"{gigography_url}"
        )

        all_events = []
        seen_ids = set()
        page_number = 1
        current_url = gigography_url

        while current_url:

            logger.info(
                f"Fetching gigography page "
                f"{page_number}: {current_url}"
            )

            response = await self._request(
                current_url
            )

            if response.status_code != 200:
                raise Exception(
                    "Songkick gigography error: "
                    f"{response.status_code}"
                )

            parsed = (
                self._parse_gigography_page(
                    response.text,
                    current_url,
                    page_number,
                )
            )

            page_events = parsed["events"]

            new_events = 0
            duplicates = 0

            for event in page_events:

                identity = (
                    self._event_identity(
                        event
                    )
                )

                if identity is None:
                    identity = (
                        self._livestream_identity(
                            event
                        )
                    )

                if identity in seen_ids:
                    duplicates += 1
                    continue

                seen_ids.add(identity)

                all_events.append(event)
                new_events += 1

            logger.info(
                f"Gigography page {page_number}: "
                f"{len(page_events)} events, "
                f"{new_events} new, "
                f"{duplicates} duplicates"
            )

            current_url = (
                parsed.get("next_url")
            )

            page_number += 1

        festivals = [
            event
            for event in all_events
            if event.get("is_festival")
        ]

        logger.info(
            "Gigography completed: "
            f"{page_number - 1} pages, "
            f"{len(all_events)} unique events, "
            f"{len(festivals)} festivals"
        )

        return {
            "events": all_events,
            "festivals": festivals,
            "pages": page_number - 1,
        }

    # ============================================================
    # COMPLETE ARTIST SCRAPE
    # ============================================================

    async def scrape_artist(
        self,
        artist_name: str,
    ) -> dict:

        logger.info(
            "Starting complete Songkick scrape: "
            f"{artist_name}"
        )

        search_data = (
            await self.search_artist_full(
                artist_name
            )
        )

        artist_info = self._find_artist(
            search_data["artists"],
            artist_name,
        )

        if not artist_info:
            raise ValueError(
                "Artist not found on Songkick: "
                f"{artist_name}"
            )

        document = artist_info.get(
            "document",
            artist_info,
        )

        artist_id = (
            document.get(
                "primary_key_id"
            )
            or self._numeric_artist_id(
                document.get("id")
            )
        )

        artist_slug = (
            self._extract_artist_slug(
                document,
                artist_name,
            )
        )

        artist_url = (
            f"{self.base_url}/artists/"
            f"{artist_id}-{artist_slug}"
        )

        logger.info(
            "Resolved artist: "
            f"{document.get('name')} "
            f"(id={artist_id}, "
            f"slug={artist_slug})"
        )

        artist_page = (
            await self.get_artist_page(
                artist_url
            )
        )

        gigography = (
            await self.get_gigography(
                artist_url
            )
        )

        upcoming_events = (
            artist_page["upcoming_events"]
        )

        upcoming_festivals = (
            artist_page["upcoming_festivals"]
        )

        raw_gigography_events = (
            gigography["events"]
        )

        # --------------------------------------------------------
        # UPCOMING IDENTITIES
        # --------------------------------------------------------

        upcoming_identities = set()

        for event in (
            upcoming_events
            + upcoming_festivals
        ):

            identity = (
                self._event_identity(
                    event
                )
            )

            if identity is None:
                identity = (
                    self._livestream_identity(
                        event
                    )
                )

            upcoming_identities.add(
                identity
            )

        logger.info(
            "Upcoming identities detected: "
            f"{len(upcoming_identities)}"
        )

        # --------------------------------------------------------
        # FILTER GIGOGRAPHY
        # --------------------------------------------------------

        gigography_events = []

        removed_upcoming_from_gigography = 0

        for event in raw_gigography_events:

            identity = (
                self._event_identity(
                    event
                )
            )

            if identity is None:
                identity = (
                    self._livestream_identity(
                        event
                    )
                )

            if identity in upcoming_identities:

                removed_upcoming_from_gigography += 1

                logger.info(
                    "[UPCOMING FILTER] Removing "
                    "event from gigography because "
                    "it is currently upcoming: "
                    f"id={event.get('songkick_id')} | "
                    f"type={event.get('event_type')} | "
                    f"name={event.get('name')} | "
                    f"start={event.get('start_date')} | "
                    f"end={event.get('end_date')}"
                )

                continue

            gigography_events.append(
                event
            )

        logger.info(
            "[UPCOMING FILTER] Gigography filtered: "
            f"original={len(raw_gigography_events)}, "
            f"removed_upcoming="
            f"{removed_upcoming_from_gigography}, "
            f"historical={len(gigography_events)}"
        )

        # --------------------------------------------------------
        # MERGE EVENTS
        #
        # First merge the artist-page representations.
        # After that, enrich the resulting events with the
        # canonical information from universal_search.
        # --------------------------------------------------------

        merged_events = []
        seen = set()

        for event in (
            upcoming_events
            + upcoming_festivals
            + gigography_events
        ):

            identity = (
                self._event_identity(
                    event
                )
            )

            if identity is None:
                identity = (
                    self._livestream_identity(
                        event
                    )
                )

            if identity in seen:
                continue

            seen.add(identity)

            merged_events.append(
                event
            )

        # --------------------------------------------------------
        # ENRICH WITH UNIVERSAL SEARCH
        #
        # The artist page often contains an artist-specific
        # representation of a festival:
        #
        #   "Demi Lovato @ Barra Olympic Park..."
        #
        # universal_search contains the canonical festival
        # representation:
        #
        #   "Rock In Rio 2026"
        #
        # We therefore use universal_search as the enrichment
        # source instead of allowing the JSON-LD representation
        # to overwrite the canonical festival information.
        # --------------------------------------------------------

        search_event_index = (
            self._build_search_event_index(
                search_data
            )
        )

        enriched_events = []

        for event in merged_events:

            enriched_event = (
                self._enrich_event_with_search_data(
                    event,
                    search_event_index,
                )
            )

            enriched_events.append(
                enriched_event
            )

        merged_events = enriched_events

        live_streams = [
            event
            for event in merged_events
            if event.get(
                "is_live_stream"
            )
        ]

        festivals = [
            event
            for event in merged_events
            if event.get(
                "is_festival"
            )
        ]

        logger.info(
            "Complete Songkick scrape finished: "
            f"{len(merged_events)} total events, "
            f"{len(upcoming_events)} upcoming, "
            f"{len(gigography_events)} historical gigography, "
            f"{len(live_streams)} livestreams, "
            f"{len(festivals)} festivals"
        )

        return {
            "artist": {
                "id": artist_id,
                "slug": artist_slug,
                "name": document.get("name"),
                "url": artist_url,
                "raw": document,
            },

            "search": search_data,

            "upcoming": upcoming_events,

            "upcoming_festivals": (
                upcoming_festivals
            ),

            "gigography": gigography_events,

            "gigography_festivals": [
                event
                for event in gigography_events
                if event.get("is_festival")
            ],

            "events": merged_events,

            "live_streams": live_streams,

            "festivals": festivals,

            "pages": gigography["pages"],

            "total_events": len(
                merged_events
            ),
        }

    # ============================================================
    # UNIVERSAL SEARCH EVENT INDEX
    # ============================================================

    @classmethod
    def _build_search_event_index(
        cls,
        search_data: dict,
    ) -> dict[str, dict]:

        """
        Build an index of Songkick event documents returned by
        universal_search.

        The same event can appear in different structures, so
        we normalize all available event-like documents into a
        single lookup by Songkick event ID.
        """

        index: dict[str, dict] = {}

        candidate_sections = (
            "events",
            "past_events",
            "top_results",
        )

        for section_name in candidate_sections:

            section = search_data.get(
                section_name,
                [],
            )

            if not isinstance(
                section,
                list,
            ):
                continue

            for item in section:

                document = (
                    item.get(
                        "document",
                        item,
                    )
                    if isinstance(
                        item,
                        dict,
                    )
                    else None
                )

                if not isinstance(
                    document,
                    dict,
                ):
                    continue

                event_id = (
                    cls._extract_search_event_id(
                        document
                    )
                )

                if not event_id:
                    continue

                index[event_id] = document

        logger.info(
            "Songkick universal_search event index: "
            f"{len(index)} events"
        )

        return index

    @classmethod
    def _extract_search_event_id(
        cls,
        document: dict,
    ) -> str | None:

        candidates = [
            document.get(
                "primary_key_id"
            ),
            document.get(
                "event_id"
            ),
            document.get(
                "id"
            ),
        ]

        for candidate in candidates:

            if candidate is None:
                continue

            value = str(candidate)

            numeric_id = (
                cls._numeric_event_id(
                    value
                )
            )

            if numeric_id:
                return numeric_id

        url = (
            document.get("url")
            or document.get("uri")
            or document.get("web_url")
        )

        reference = (
            cls.extract_event_reference(
                str(url)
                if url
                else None
            )
        )

        return reference.get(
            "event_id"
        )

    @staticmethod
    def _numeric_event_id(
        value: str | None,
    ) -> str | None:

        if not value:
            return None

        value = str(value)

        patterns = [
            r"Event(\d+)$",
            r"FestivalInstance(\d+)$",
            r"Concert(\d+)$",
            r"LiveStream(\d+)$",
            r"/id/(\d+)",
            r"/concerts/(\d+)",
            r"/live-stream-concerts/(\d+)",
        ]

        for pattern in patterns:

            match = re.search(
                pattern,
                value,
                flags=re.IGNORECASE,
            )

            if match:
                return match.group(1)

        if value.isdigit():
            return value

        return None

    # ============================================================
    # EVENT ENRICHMENT
    # ============================================================

    @classmethod
    def _enrich_event_with_search_data(
        cls,
        event: dict,
        search_event_index: dict[str, dict],
    ) -> dict:

        if not isinstance(
            event,
            dict,
        ):
            return event

        event_id = (
            event.get("songkick_id")
            or event.get("id")
        )

        if event_id is None:
            return event

        event_id = str(event_id)

        search_document = (
            search_event_index.get(
                event_id
            )
        )

        if not search_document:
            return event

        # --------------------------------------------------------
        # Only enrich actual festivals.
        #
        # universal_search contains much more authoritative
        # festival information than the artist-page JSON-LD.
        # --------------------------------------------------------

        is_festival = (
            event.get("is_festival")
            or cls._is_search_festival(
                search_document
            )
        )

        if not is_festival:
            return event

        enriched = dict(event)

        enriched["is_festival"] = True
        enriched["event_type"] = "festival"

        # --------------------------------------------------------
        # Canonical festival name
        # --------------------------------------------------------

        canonical_name = (
            cls._first_non_empty(
                search_document.get("name"),
                search_document.get("title"),
            )
        )

        if canonical_name:
            enriched["name"] = canonical_name
            enriched["original_name"] = canonical_name

        # --------------------------------------------------------
        # Dates
        #
        # Keep the artist-page dates when universal_search does
        # not provide them.
        # --------------------------------------------------------

        search_start = (
            cls._first_non_empty(
                search_document.get("date"),
                search_document.get("start_date"),
                search_document.get("startDate"),
            )
        )

        search_end = (
            cls._first_non_empty(
                search_document.get("end_date"),
                search_document.get("endDate"),
            )
        )

        if search_start:
            enriched["start_date"] = search_start

        if search_end:
            enriched["end_date"] = search_end

        # --------------------------------------------------------
        # URL
        # --------------------------------------------------------

        search_url = (
            cls._first_non_empty(
                search_document.get("url"),
                search_document.get("web_url"),
                search_document.get("uri"),
            )
        )

        if search_url:
            enriched["url"] = (
                str(search_url)
                .split("?")[0]
            )

        # --------------------------------------------------------
        # Venue / location
        # --------------------------------------------------------

        venue_name = (
            cls._first_non_empty(
                search_document.get(
                    "venue_name"
                ),
                search_document.get(
                    "venue"
                ),
            )
        )

        if venue_name:

            current_venue = (
                enriched.get("venue")
            )

            if not isinstance(
                current_venue,
                dict,
            ):
                current_venue = {}

            current_venue = dict(
                current_venue
            )

            current_venue["name"] = (
                venue_name
            )

            enriched["venue"] = (
                current_venue
            )

        location = (
            cls._build_search_location(
                search_document
            )
        )

        if location:
            enriched["location"] = location

        # --------------------------------------------------------
        # Festival metadata
        # --------------------------------------------------------

        festival = (
            cls._build_festival_metadata(
                search_document,
                event,
            )
        )

        if festival:
            enriched["festival"] = festival

        # --------------------------------------------------------
        # Source metadata
        # --------------------------------------------------------

        source = (
            enriched.get("source")
        )

        if not isinstance(
            source,
            dict,
        ):
            source = {}

        source = dict(source)

        source.update(
            {
                "provider": "songkick",
                "event_id": event_id,
            }
        )

        if search_url:
            source["url"] = (
                str(search_url)
                .split("?")[0]
            )

        enriched["source"] = source

        logger.info(
            "[EVENT ENRICHMENT] Festival enriched: "
            f"id={event_id} | "
            f"name={enriched.get('name')} | "
            f"series="
            f"{festival.get('series_id') if festival else None} | "
            f"artists="
            f"{len(festival.get('artists', [])) if festival else 0}"
        )

        return enriched

    @classmethod
    def _build_festival_metadata(
        cls,
        search_document: dict,
        original_event: dict,
    ) -> dict:

        series_id = (
            cls._extract_festival_series_id(
                search_document,
                original_event,
            )
        )

        name = (
            cls._first_non_empty(
                search_document.get("name"),
                search_document.get("title"),
                original_event.get("name"),
            )
        )

        edition = (
            cls._extract_festival_edition(
                name
            )
        )

        url = (
            cls._first_non_empty(
                search_document.get("url"),
                search_document.get("web_url"),
                search_document.get("uri"),
                original_event.get("url"),
            )
        )

        tracking_count = (
            cls._first_non_none(
                search_document.get(
                    "number_of_users_tracking"
                ),
                search_document.get(
                    "tracking_count"
                ),
            )
        )

        artist_ids = (
            cls._extract_artist_ids(
                search_document
            )
        )

        artists = (
            cls._extract_festival_artists(
                search_document
            )
        )

        festival = {
            "series_id": series_id,
            "name": name,
            "edition": edition,
            "url": (
                str(url).split("?")[0]
                if url
                else None
            ),
            "tracking_count": tracking_count,
            "artist_ids": artist_ids,
            "artists": artists,
        }

        # Preserve useful canonical Songkick fields when present.

        full_name = (
            search_document.get(
                "full_name"
            )
        )

        if full_name:
            festival["full_name"] = (
                full_name
            )

        if (
            search_document.get(
                "event_type"
            )
            is not None
        ):
            festival["event_type"] = (
                search_document.get(
                    "event_type"
                )
            )

        if (
            search_document.get(
                "is_flagged_as_ended"
            )
            is not None
        ):
            festival["is_flagged_as_ended"] = (
                search_document.get(
                    "is_flagged_as_ended"
                )
            )

        return festival

    @classmethod
    def _extract_festival_series_id(
        cls,
        search_document: dict,
        original_event: dict,
    ) -> str | None:

        candidates = [
            search_document.get(
                "series_id"
            ),
            search_document.get(
                "festival_series_id"
            ),
            original_event.get(
                "festival_series_id"
            ),
        ]

        for candidate in candidates:

            if candidate is None:
                continue

            value = str(candidate).strip()

            if value:
                return value

        url = (
            search_document.get("url")
            or original_event.get("url")
        )

        festival_data = (
            cls.extract_festival_data(
                str(url)
                if url
                else None
            )
        )

        if festival_data:
            return festival_data.get(
                "series_id"
            )

        return None

    @staticmethod
    def _extract_festival_edition(
        name: str | None,
    ) -> str | None:

        if not name:
            return None

        match = re.search(
            r"\b(19|20)\d{2}\b",
            str(name),
        )

        if match:
            return match.group(0)

        return None

    @classmethod
    def _extract_artist_ids(
        cls,
        search_document: dict,
    ) -> list[str]:

        candidates = [
            search_document.get(
                "artist_ids"
            ),
            search_document.get(
                "artists_ids"
            ),
        ]

        for value in candidates:

            if not isinstance(
                value,
                list,
            ):
                continue

            result = []

            for artist_id in value:

                if artist_id is None:
                    continue

                numeric_id = (
                    cls._numeric_artist_id(
                        artist_id
                    )
                )

                if numeric_id:
                    result.append(
                        numeric_id
                    )

            return list(
                dict.fromkeys(result)
            )

        return []

    @classmethod
    def _extract_festival_artists(
        cls,
        search_document: dict,
    ) -> list[dict]:

        """
        Songkick's universal_search payload can expose artist
        information in different shapes.

        We preserve names/IDs whenever the payload actually
        contains them. We intentionally do not fabricate artist
        names from IDs.
        """

        candidates = [
            search_document.get(
                "artists"
            ),
            search_document.get(
                "performers"
            ),
            search_document.get(
                "artist"
            ),
        ]

        for value in candidates:

            if not isinstance(
                value,
                list,
            ):
                continue

            artists = []

            for artist in value:

                if isinstance(
                    artist,
                    str,
                ):

                    name = artist.strip()

                    if name:
                        artists.append(
                            {
                                "name": name
                            }
                        )

                    continue

                if not isinstance(
                    artist,
                    dict,
                ):
                    continue

                document = artist.get(
                    "document",
                    artist,
                )

                if not isinstance(
                    document,
                    dict,
                ):
                    continue

                artist_id = (
                    document.get(
                        "primary_key_id"
                    )
                    or document.get("id")
                    or document.get(
                        "artist_id"
                    )
                )

                artist_name = (
                    document.get("name")
                    or document.get(
                        "display_name"
                    )
                )

                artist_item = {}

                if artist_id is not None:

                    numeric_id = (
                        cls._numeric_artist_id(
                            artist_id
                        )
                    )

                    if numeric_id:
                        artist_item["id"] = (
                            numeric_id
                        )

                if artist_name:

                    artist_item["name"] = (
                        str(
                            artist_name
                        ).strip()
                    )

                artist_url = (
                    document.get("url")
                )

                if artist_url:
                    artist_item["url"] = (
                        str(
                            artist_url
                        ).split("?")[0]
                    )

                if artist_item:
                    artists.append(
                        artist_item
                    )

            if artists:
                return cls._deduplicate_artist_metadata(
                    artists
                )

        return []

    @staticmethod
    def _deduplicate_artist_metadata(
        artists: list[dict],
    ) -> list[dict]:

        result = []
        seen = set()

        for artist in artists:

            identity = (
                artist.get("id")
                or artist.get("name")
            )

            if not identity:
                continue

            identity = str(
                identity
            ).lower()

            if identity in seen:
                continue

            seen.add(identity)
            result.append(artist)

        return result

    @classmethod
    def _build_search_location(
        cls,
        search_document: dict,
    ) -> dict:

        location = {}

        city = (
            cls._first_non_empty(
                search_document.get(
                    "city_name"
                ),
                search_document.get(
                    "city"
                ),
            )
        )

        country = (
            cls._first_non_empty(
                search_document.get(
                    "country_name"
                ),
                search_document.get(
                    "country"
                ),
            )
        )

        latitude = (
            search_document.get(
                "latitude"
            )
        )

        longitude = (
            search_document.get(
                "longitude"
            )
        )

        geolocation = (
            search_document.get(
                "geolocation"
            )
        )

        if (
            geolocation
            and (
                latitude is None
                or longitude is None
            )
        ):

            coordinates = (
                cls._parse_geolocation(
                    geolocation
                )
            )

            if coordinates:

                latitude = (
                    coordinates[0]
                )

                longitude = (
                    coordinates[1]
                )

        if city:
            location["city"] = city

        if country:
            location["country"] = country

        if latitude is not None:

            try:
                location["latitude"] = (
                    float(latitude)
                )
            except (
                TypeError,
                ValueError,
            ):
                pass

        if longitude is not None:

            try:
                location["longitude"] = (
                    float(longitude)
                )
            except (
                TypeError,
                ValueError,
            ):
                pass

        return location

    @staticmethod
    def _parse_geolocation(
        value: Any,
    ) -> tuple[float, float] | None:

        if isinstance(
            value,
            str,
        ):

            parts = [
                part.strip()
                for part in value.split(",")
            ]

            if len(parts) != 2:
                return None

            try:
                return (
                    float(parts[0]),
                    float(parts[1]),
                )
            except (
                TypeError,
                ValueError,
            ):
                return None

        if isinstance(
            value,
            (list, tuple),
        ) and len(value) >= 2:

            try:
                return (
                    float(value[0]),
                    float(value[1]),
                )
            except (
                TypeError,
                ValueError,
            ):
                return None

        return None

    @staticmethod
    def _is_search_festival(
        document: dict,
    ) -> bool:

        event_type = (
            document.get(
                "event_type"
            )
        )

        if str(
            event_type or ""
        ).lower() in {
            "festival",
            "festivalinstance",
        }:
            return True

        return bool(
            document.get(
                "series_id"
            )
            or document.get(
                "festival_series_id"
            )
        )

    @staticmethod
    def _first_non_empty(
        *values,
    ):
        for value in values:

            if value is None:
                continue

            if isinstance(
                value,
                str,
            ):

                if value.strip():
                    return value

            else:
                return value

        return None

    @staticmethod
    def _first_non_none(
        *values,
    ):
        for value in values:
            if value is not None:
                return value

        return None

    # ============================================================
    # ARTIST PAGE PARSER
    # ============================================================

    @classmethod
    def _analyze_artist_page(
        cls,
        html: str,
        source_url: str,
    ) -> dict:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        upcoming_events = []
        upcoming_festivals = []

        # --------------------------------------------------------
        # SONGKICK #coming-up
        # --------------------------------------------------------

        coming_up = soup.select_one(
            "#coming-up"
        )

        coming_up_references = []

        if coming_up:

            anchors = coming_up.find_all(
                "a",
                href=True,
            )

            logger.info(
                "[UPCOMING DEBUG] "
                f"#coming-up found with "
                f"{len(anchors)} links"
            )

            seen_references = set()

            for anchor in anchors:

                href = anchor.get(
                    "href"
                )

                if not href:
                    continue

                absolute_url = urljoin(
                    source_url,
                    href,
                )

                reference = (
                    cls.extract_event_reference(
                        absolute_url
                    )
                )

                event_id = reference.get(
                    "event_id"
                )

                if not event_id:
                    continue

                identity = (
                    reference.get(
                        "event_type"
                    ),
                    event_id,
                )

                if identity in seen_references:
                    continue

                seen_references.add(
                    identity
                )

                name = (
                    anchor.get_text(
                        " ",
                        strip=True,
                    )
                    or None
                )

                coming_up_references.append(
                    {
                        "event_type": (
                            reference.get(
                                "event_type"
                            )
                        ),
                        "event_id": event_id,
                        "festival_series_id": (
                            reference.get(
                                "festival_series_id"
                            )
                        ),
                        "name": name,
                        "url": (
                            absolute_url
                            .split("?")[0]
                        ),
                    }
                )

            logger.info(
                "[UPCOMING DEBUG] "
                "#coming-up event references="
                f"{len(coming_up_references)}"
            )

            for reference in coming_up_references:

                logger.info(
                    "[UPCOMING DEBUG] "
                    "COMING-UP REF | "
                    f"type={reference['event_type']} | "
                    f"id={reference['event_id']} | "
                    f"series={reference['festival_series_id']} | "
                    f"name={reference['name']} | "
                    f"url={reference['url']}"
                )

        else:

            logger.warning(
                "[UPCOMING DEBUG] "
                "#coming-up section NOT FOUND"
            )

        # --------------------------------------------------------
        # JSON-LD
        # --------------------------------------------------------

        all_jsonld_events = []
        all_jsonld_festivals = []

        for script in soup.find_all(
            "script",
            type="application/ld+json",
        ):

            try:

                value = json.loads(
                    script.string
                    or script.get_text()
                )

            except Exception:
                continue

            cls._extract_jsonld_events(
                value,
                source_url,
                all_jsonld_events,
                all_jsonld_festivals,
                upcoming_only=False,
            )

        logger.info(
            "[UPCOMING DEBUG] "
            "JSON-LD parsed: "
            f"{len(all_jsonld_events)} concerts/events, "
            f"{len(all_jsonld_festivals)} festivals"
        )

        # --------------------------------------------------------
        # INDEX JSON-LD BY SONGKICK EVENT ID
        # --------------------------------------------------------

        jsonld_by_identity = {}

        for event in (
            all_jsonld_events
            + all_jsonld_festivals
        ):

            identity = (
                cls._event_identity(
                    event
                )
            )

            if identity is None:
                continue

            jsonld_by_identity[
                identity
            ] = event

        # --------------------------------------------------------
        # AUTHORITATIVE UPCOMING EVENTS
        # --------------------------------------------------------

        coming_up_identities = set()

        for reference in coming_up_references:

            identity = (
                "id",
                str(
                    reference["event_id"]
                ),
            )

            coming_up_identities.add(
                identity
            )

            matching_event = (
                jsonld_by_identity.get(
                    identity
                )
            )

            if not matching_event:

                logger.warning(
                    "[UPCOMING DEBUG] "
                    "NO JSON-LD MATCH | "
                    f"type={reference['event_type']} | "
                    f"id={reference['event_id']} | "
                    f"name={reference['name']} | "
                    f"url={reference['url']}"
                )

                continue

            logger.info(
                "[UPCOMING DEBUG] "
                "JSON-LD MATCH | "
                f"type={matching_event.get('event_type')} | "
                f"id={matching_event.get('songkick_id')} | "
                f"name={matching_event.get('name')} | "
                f"start={matching_event.get('start_date')} | "
                f"end={matching_event.get('end_date')} | "
                "upcoming=True "
                "(authoritative #coming-up)"
            )

            if matching_event.get(
                "is_festival"
            ):

                upcoming_festivals.append(
                    matching_event
                )

            else:

                upcoming_events.append(
                    matching_event
                )

        # --------------------------------------------------------
        # FALLBACK
        # --------------------------------------------------------

        for event in all_jsonld_events:

            identity = (
                cls._event_identity(
                    event
                )
            )

            if identity in coming_up_identities:
                continue

            if not cls._is_upcoming_event(
                event
            ):
                continue

            upcoming_events.append(
                event
            )

        for event in all_jsonld_festivals:

            identity = (
                cls._event_identity(
                    event
                )
            )

            if identity in coming_up_identities:
                continue

            if not cls._is_upcoming_event(
                event
            ):
                continue

            upcoming_festivals.append(
                event
            )

        # --------------------------------------------------------
        # DEDUPLICATE
        # --------------------------------------------------------

        upcoming_events = (
            cls._deduplicate_events(
                upcoming_events
            )
        )

        upcoming_festivals = (
            cls._deduplicate_events(
                upcoming_festivals
            )
        )

        # --------------------------------------------------------
        # FINAL UPCOMING DEBUG
        # --------------------------------------------------------

        logger.info(
            "[UPCOMING DEBUG] "
            "Final upcoming result: "
            f"{len(upcoming_events)} concerts/events, "
            f"{len(upcoming_festivals)} festivals"
        )

        for event in (
            upcoming_events
            + upcoming_festivals
        ):

            logger.info(
                "[UPCOMING DEBUG] "
                "FINAL | "
                f"type={event.get('event_type')} | "
                f"id={event.get('songkick_id')} | "
                f"name={event.get('name')} | "
                f"start={event.get('start_date')} | "
                f"end={event.get('end_date')}"
            )

        return {
            "upcoming_events": (
                upcoming_events
            ),
            "upcoming_festivals": (
                upcoming_festivals
            ),
        }

    # ============================================================
    # GIGOGRAPHY PARSER
    # ============================================================

    @classmethod
    def _parse_gigography_page(
        cls,
        html: str,
        source_url: str,
        page_number: int,
    ) -> dict:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        events = []

        # --------------------------------------------------------
        # 1. JSON-LD
        # --------------------------------------------------------

        jsonld_events = []

        for script in soup.find_all(
            "script",
            type="application/ld+json",
        ):

            try:

                value = json.loads(
                    script.string
                    or script.get_text()
                )

            except Exception:
                continue

            cls._extract_jsonld_events(
                value,
                source_url,
                jsonld_events,
                [],
                upcoming_only=False,
            )

        logger.debug(
            f"Gigography page {page_number}: "
            f"JSON-LD events="
            f"{len(jsonld_events)}"
        )

        events.extend(
            jsonld_events
        )

        # --------------------------------------------------------
        # 2. HTML EVENT LINKS
        # --------------------------------------------------------

        html_events = (
            cls._extract_html_event_links(
                soup,
                source_url,
            )
        )

        logger.debug(
            f"Gigography page {page_number}: "
            f"HTML event references="
            f"{len(html_events)}"
        )

        # --------------------------------------------------------
        # Merge HTML references with JSON-LD.
        # --------------------------------------------------------

        events = (
            cls._merge_event_sources(
                events,
                html_events,
            )
        )

        logger.info(
            f"Gigography page {page_number}: "
            f"final events={len(events)}"
        )

        # --------------------------------------------------------
        # NEXT PAGE
        # --------------------------------------------------------

        next_url = (
            cls._extract_next_page_url(
                soup,
                source_url,
                page_number,
            )
        )

        if next_url:

            logger.debug(
                f"Gigography page {page_number}: "
                f"next={next_url}"
            )

        else:

            logger.debug(
                f"Gigography page {page_number}: "
                "no next page"
            )

        return {
            "page_number": page_number,
            "events": cls._deduplicate_events(
                events
            ),
            "next_url": next_url,
        }

    # ============================================================
    # HTML EVENT EXTRACTION
    # ============================================================

    @classmethod
    def _extract_html_event_links(
        cls,
        soup: BeautifulSoup,
        source_url: str,
    ) -> list[dict]:

        events = []
        seen = set()

        for anchor in soup.find_all(
            "a",
            href=True,
        ):

            href = anchor.get(
                "href"
            )

            if not href:
                continue

            absolute_url = urljoin(
                source_url,
                href,
            )

            reference = (
                cls.extract_event_reference(
                    absolute_url
                )
            )

            if not reference.get(
                "event_id"
            ):
                continue

            identity = (
                reference["event_type"],
                reference["event_id"],
            )

            if identity in seen:
                continue

            seen.add(identity)

            name = (
                anchor.get_text(
                    " ",
                    strip=True,
                )
                or None
            )

            events.append(
                {
                    "id": reference[
                        "event_id"
                    ],
                    "songkick_id": reference[
                        "event_id"
                    ],
                    "event_type": (
                        reference[
                            "event_type"
                        ]
                        or "concert"
                    ),
                    "url": (
                        absolute_url
                        .split("?")[0]
                    ),
                    "name": name,
                    "original_name": name,
                    "start_date": None,
                    "end_date": None,
                    "event_status": None,
                    "event_attendance_mode": None,
                    "description": None,
                    "venue": None,
                    "performers": [],
                    "offers": [],
                    "songkick_image": None,
                    "source_page": source_url,
                    "raw": {
                        "source": "html",
                        "href": absolute_url,
                    },
                    "festival": None,
                    "is_festival": (
                        reference[
                            "event_type"
                        ]
                        == "festival"
                    ),
                    "is_live_stream": (
                        "/live-stream-concerts/"
                        in absolute_url
                    ),
                    "source": (
                        "songkick_gigography"
                    ),
                    "primary_detail": (
                        "Live Stream"
                        if "/live-stream-concerts/"
                        in absolute_url
                        else None
                    ),
                    "secondary_detail": None,
                }
            )

        return events

    # ============================================================
    # MERGE EVENT SOURCES
    # ============================================================

    @classmethod
    def _merge_event_sources(
        cls,
        primary_events: list[dict],
        fallback_events: list[dict],
    ) -> list[dict]:

        result = []
        by_identity = {}

        # --------------------------------------------------------
        # Primary source = JSON-LD
        # --------------------------------------------------------

        for event in primary_events:

            identity = (
                cls._event_identity(
                    event
                )
            )

            if identity is None:
                identity = (
                    cls._livestream_identity(
                        event
                    )
                )

            if identity in by_identity:
                continue

            by_identity[identity] = event

            result.append(
                event
            )

        # --------------------------------------------------------
        # Fallback = HTML
        # --------------------------------------------------------

        for fallback in fallback_events:

            identity = (
                cls._event_identity(
                    fallback
                )
            )

            if identity is None:
                identity = (
                    cls._livestream_identity(
                        fallback
                    )
                )

            if identity not in by_identity:

                by_identity[
                    identity
                ] = fallback

                result.append(
                    fallback
                )

        return result

    # ============================================================
    # NEXT PAGE
    # ============================================================

    @classmethod
    def _extract_next_page_url(
        cls,
        soup: BeautifulSoup,
        source_url: str,
        page_number: int,
    ) -> str | None:

        # --------------------------------------------------------
        # rel="next"
        # --------------------------------------------------------

        for link in soup.find_all(
            "a",
            href=True,
        ):

            rel = link.get(
                "rel"
            )

            if isinstance(
                rel,
                str,
            ):

                rel_values = [
                    rel.lower()
                ]

            else:

                rel_values = [
                    str(value).lower()
                    for value in (
                        rel or []
                    )
                ]

            if "next" in rel_values:

                return urljoin(
                    source_url,
                    link["href"],
                )

        # --------------------------------------------------------
        # Explicit pagination URL
        # --------------------------------------------------------

        candidates = []

        for link in soup.find_all(
            "a",
            href=True,
        ):

            href = link.get(
                "href"
            )

            if not href:
                continue

            absolute = urljoin(
                source_url,
                href,
            )

            if (
                "/gigography"
                not in absolute
            ):
                continue

            match = re.search(
                r"[?&]page=(\d+)",
                absolute,
            )

            if not match:
                continue

            page = int(
                match.group(1)
            )

            if page > page_number:

                candidates.append(
                    (
                        page,
                        absolute,
                    )
                )

        if candidates:

            candidates.sort(
                key=lambda item: item[0]
            )

            return candidates[0][1]

        return None

    # ============================================================
    # JSON-LD EVENT EXTRACTION
    # ============================================================

    @classmethod
    def _extract_jsonld_events(
        cls,
        data: Any,
        source_url: str,
        events: list,
        festivals: list,
        upcoming_only: bool,
    ):

        if isinstance(
            data,
            list,
        ):

            for item in data:

                cls._extract_jsonld_events(
                    item,
                    source_url,
                    events,
                    festivals,
                    upcoming_only,
                )

            return

        if not isinstance(
            data,
            dict,
        ):
            return

        graph = data.get(
            "@graph"
        )

        if isinstance(
            graph,
            list,
        ):

            for item in graph:

                cls._extract_jsonld_events(
                    item,
                    source_url,
                    events,
                    festivals,
                    upcoming_only,
                )

        event_type = data.get(
            "@type"
        )

        if isinstance(
            event_type,
            list,
        ):

            is_event = (
                "MusicEvent"
                in event_type
                or "Event"
                in event_type
            )

        else:

            is_event = (
                event_type
                in {
                    "MusicEvent",
                    "Event",
                }
            )

        if not is_event:
            return

        event = (
            cls._jsonld_to_event(
                data,
                source_url,
            )
        )

        if not event:
            return

        if upcoming_only:

            if not cls._is_upcoming_event(
                event
            ):
                return

        if event.get(
            "is_festival"
        ):

            festivals.append(
                event
            )

        else:

            events.append(
                event
            )

    # ============================================================
    # JSON-LD NORMALIZATION
    # ============================================================

    @classmethod
    def _jsonld_to_event(
        cls,
        data: dict,
        source_url: str,
    ) -> dict | None:

        url = data.get(
            "url"
        )

        if not url:

            location = data.get(
                "location"
            )

            if isinstance(
                location,
                dict,
            ):

                url = location.get(
                    "url"
                )

        if url:
            url = url.split("?")[0]

        start_date = data.get(
            "startDate"
        )

        reference = (
            cls.extract_event_reference(
                url
            )
        )

        event_id = reference.get(
            "event_id"
        )

        if not event_id:

            event_id = (
                cls._extract_event_id_from_data(
                    data
                )
            )

            logger.debug(
                "JSON-LD event without "
                "recognizable Songkick ID: "
                f"{url}"
            )

        event_type = reference.get(
            "event_type"
        )

        if event_type is None:

            event_type = (
                "festival"
                if cls._is_festival_url(url)
                else "concert"
            )

        if not start_date:
            return None

        attendance_mode = (
            data.get(
                "eventAttendanceMode"
            )
        )

        is_live_stream = (
            "OnlineEventAttendanceMode"
            in str(
                attendance_mode or ""
            )
            or (
                url
                and "/live-stream-concerts/"
                in url
            )
        )

        performers = []

        raw_performers = data.get(
            "performer",
            [],
        )

        if isinstance(
            raw_performers,
            dict,
        ):

            raw_performers = [
                raw_performers
            ]

        for performer in (
            raw_performers
        ):

            if not isinstance(
                performer,
                dict,
            ):
                continue

            performers.append(
                {
                    "name": performer.get(
                        "name"
                    ),
                    "type": performer.get(
                        "@type"
                    ),
                    "genre": performer.get(
                        "genre",
                        [],
                    ),
                    "same_as": performer.get(
                        "sameAs"
                    ),
                }
            )

        location = data.get(
            "location",
            {},
        )

        venue = None

        if isinstance(
            location,
            dict,
        ):

            venue = {
                "name": location.get(
                    "name"
                ),
                "url": location.get(
                    "url"
                ),
                "address": location.get(
                    "address"
                ),
            }

        name = data.get(
            "name"
        )

        return {
            "id": event_id,
            "songkick_id": event_id,
            "event_type": event_type,
            "url": url,
            "name": name,
            "original_name": name,
            "start_date": start_date,
            "end_date": data.get(
                "endDate"
            ),
            "event_status": data.get(
                "eventStatus"
            ),
            "event_attendance_mode":
                attendance_mode,
            "description": data.get(
                "description"
            ),
            "venue": venue,
            "performers": performers,
            "offers": data.get(
                "offers",
                [],
            ),
            "songkick_image": data.get(
                "image"
            ),
            "source_page": source_url,
            "raw": data,
            "festival": (
                data
                if event_type == "festival"
                else None
            ),
            "is_festival": (
                event_type == "festival"
            ),
            "is_live_stream": (
                is_live_stream
            ),
            "source": (
                "songkick_artist_page"
                if (
                    "artists/"
                    in source_url
                    and "/gigography"
                    not in source_url
                )
                else "songkick_gigography"
            ),
            "primary_detail": (
                "Live Stream"
                if is_live_stream
                else None
            ),
            "secondary_detail": None,
        }

    # ============================================================
    # EVENT REFERENCES
    # ============================================================

    @staticmethod
    def extract_concert_id(
        url: str | None,
    ):

        if not url:
            return None

        match = re.search(
            r"/concerts/(\d+)(?:-|/|$|\?)",
            url,
        )

        if match:
            return match.group(1)

        return None

    @staticmethod
    def extract_live_stream_id(
        url: str | None,
    ):

        if not url:
            return None

        match = re.search(
            r"/live-stream-concerts/(\d+)(?:-|/|$|\?)",
            url,
        )

        if match:
            return match.group(1)

        return None

    @staticmethod
    def extract_festival_data(
        url: str | None,
    ):

        if not url:
            return None

        festival_match = re.search(
            r"/festivals/(\d+)(?:-[^/]+)?",
            url,
        )

        if not festival_match:
            return None

        series_id = festival_match.group(1)

        event_match = re.search(
            r"/id/(\d+)",
            url,
        )

        return {
            "series_id": series_id,
            "event_id": (
                event_match.group(1)
                if event_match
                else None
            ),
        }

    @classmethod
    def extract_event_reference(
        cls,
        url: str | None,
    ) -> dict:

        if not url:

            return {
                "event_type": None,
                "event_id": None,
                "festival_series_id": None,
            }

        # --------------------------------------------------------
        # CONCERT
        # --------------------------------------------------------

        concert_id = (
            cls.extract_concert_id(
                url
            )
        )

        if concert_id:

            return {
                "event_type": "concert",
                "event_id": concert_id,
                "festival_series_id": None,
            }

        # --------------------------------------------------------
        # LIVE STREAM
        # --------------------------------------------------------

        live_stream_id = (
            cls.extract_live_stream_id(
                url
            )
        )

        if live_stream_id:

            return {
                "event_type": "concert",
                "event_id": live_stream_id,
                "festival_series_id": None,
            }

        # --------------------------------------------------------
        # FESTIVAL
        # --------------------------------------------------------

        festival_data = (
            cls.extract_festival_data(
                url
            )
        )

        if festival_data:

            return {
                "event_type": "festival",
                "event_id": (
                    festival_data["event_id"]
                ),
                "festival_series_id": (
                    festival_data["series_id"]
                ),
            }

        return {
            "event_type": None,
            "event_id": None,
            "festival_series_id": None,
        }

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _extract_event_id_from_data(
        data: dict,
    ) -> str | None:

        candidates = [
            data.get("identifier"),
            data.get("@id"),
        ]

        for value in candidates:

            if not value:
                continue

            reference = (
                SongkickClient.extract_event_reference(
                    str(value)
                )
            )

            if reference.get(
                "event_id"
            ):

                return reference[
                    "event_id"
                ]

        return None

    @staticmethod
    def _is_festival_url(
        url: str | None,
    ) -> bool:

        if not url:
            return False

        return (
            "/festivals/" in url
            or "/festival/" in url
        )

    @staticmethod
    def _parse_datetime(
        value: str | None,
    ) -> datetime | None:

        if not value:
            return None

        try:

            normalized = value.replace(
                "Z",
                "+00:00",
            )

            parsed = datetime.fromisoformat(
                normalized
            )

            if parsed.tzinfo is None:

                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )

            return parsed

        except (
            TypeError,
            ValueError,
        ):

            return None

    @staticmethod
    def _is_date_only(
        value: str | None,
    ) -> bool:

        if not isinstance(
            value,
            str,
        ):
            return False

        return bool(
            re.fullmatch(
                r"\d{4}-\d{2}-\d{2}",
                value.strip(),
            )
        )

    @classmethod
    def _is_upcoming_event(
        cls,
        event: dict,
    ) -> bool:

        now = datetime.now(
            timezone.utc
        )

        start_value = event.get(
            "start_date"
        )

        end_value = event.get(
            "end_date"
        )

        # --------------------------------------------------------
        # Multi-day event with date-only end date.
        # --------------------------------------------------------

        if (
            isinstance(
                end_value,
                str,
            )
            and cls._is_date_only(
                end_value
            )
        ):

            try:

                end_date = datetime.strptime(
                    end_value.strip(),
                    "%Y-%m-%d",
                ).date()

                return (
                    end_date
                    >= now.date()
                )

            except ValueError:
                pass

        # --------------------------------------------------------
        # Normal timezone-aware end date.
        # --------------------------------------------------------

        end_date = cls._parse_datetime(
            end_value
        )

        if end_date is not None:
            return end_date >= now

        # --------------------------------------------------------
        # Date-only start date.
        # --------------------------------------------------------

        if (
            isinstance(
                start_value,
                str,
            )
            and cls._is_date_only(
                start_value
            )
        ):

            try:

                start_date = datetime.strptime(
                    start_value.strip(),
                    "%Y-%m-%d",
                ).date()

                return (
                    start_date
                    >= now.date()
                )

            except ValueError:
                pass

        # --------------------------------------------------------
        # Normal start date.
        # --------------------------------------------------------

        start_date = cls._parse_datetime(
            start_value
        )

        if start_date is not None:
            return start_date >= now

        return True

    @staticmethod
    def _event_identity(
        event: dict,
    ):

        event_id = (
            event.get(
                "songkick_id"
            )
            or event.get("id")
        )

        if event_id is not None:

            return (
                "id",
                str(event_id),
            )

        return None

    @staticmethod
    def _livestream_identity(
        event: dict,
    ):

        url = event.get(
            "url"
        )

        if url:

            return (
                "url",
                url.split("?")[0],
            )

        return (
            "fallback",
            event.get("name"),
            event.get("start_date"),
        )

    @staticmethod
    def _deduplicate_events(
        events: list,
    ) -> list:

        result = []
        seen = set()

        for event in events:

            identity = (
                SongkickClient
                ._event_identity(
                    event
                )
            )

            if identity is None:

                identity = (
                    SongkickClient
                    ._livestream_identity(
                        event
                    )
                )

            if identity in seen:
                continue

            seen.add(identity)
            result.append(event)

        return result

    @staticmethod
    def _numeric_artist_id(
        artist_id: Any,
    ) -> str | None:

        if artist_id is None:
            return None

        value = str(
            artist_id
        )

        match = re.search(
            r"(\d+)$",
            value,
        )

        if match:
            return match.group(1)

        return value

    @staticmethod
    def _extract_artist_slug(
        document: dict,
        fallback_name: str,
    ) -> str:

        url = document.get(
            "url"
        )

        if url:

            match = re.search(
                r"/artists/\d+-([^/?#]+)",
                url,
            )

            if match:
                return match.group(1)

        value = (
            document.get("name")
            or fallback_name
        )

        return re.sub(
            r"[^a-z0-9]+",
            "-",
            value.lower(),
        ).strip("-")

    @staticmethod
    def _find_artist(
        artists: list,
        artist_name: str,
    ) -> dict | None:

        if not artists:
            return None

        normalized_query = (
            artist_name
            .strip()
            .lower()
        )

        for item in artists:

            document = item.get(
                "document",
                item,
            )

            name = str(
                document.get(
                    "name",
                    "",
                )
            ).strip().lower()

            if name == normalized_query:
                return item

        return artists[0]