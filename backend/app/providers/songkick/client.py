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

        headers = dict(
            self.headers
        )

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

        gigography_events = (
            gigography["events"]
        )

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

            merged_events.append(event)

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
            f"{len(gigography_events)} gigography, "
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
                upcoming_events,
                upcoming_festivals,
                upcoming_only=True,
            )

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
        # 2. HTML event links
        #
        # This is important.
        #
        # Songkick can expose event links in the page even when
        # the corresponding event is not represented in JSON-LD.
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
        #
        # JSON-LD has priority because it contains richer data.
        # HTML references fill the missing events.
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

            # ----------------------------------------------------
            # If JSON-LD does not exist for this event, we still
            # create a minimal normalized payload.
            #
            # Later JSON-LD data will replace/enrich it.
            # ----------------------------------------------------

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

            result.append(event)

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

        # --------------------------------------------------------
        # Event reference MUST come from URL.
        # --------------------------------------------------------

        reference = (
            cls.extract_event_reference(
                url
            )
        )

        event_id = reference.get(
            "event_id"
        )

        event_type = (
            reference.get(
                "event_type"
            )
        )

        # --------------------------------------------------------
        # Fallback only when URL does not contain a recognized
        # Songkick event reference.
        # --------------------------------------------------------

        if not event_id:

            event_id = (
                cls._extract_event_id_from_data(
                    data
                )
            )

        if not event_id:

            logger.debug(
                "JSON-LD event without "
                "recognizable Songkick ID: "
                f"{url}"
            )

        if not start_date:

            return None

        if event_type is None:

            event_type = (
                "festival"
                if cls._is_festival_url(
                    url
                )
                else "concert"
            )

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
            r"/live-stream-concerts/(\d+)"
            r"(?:-|/|$|\?)",
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

        match = re.search(
            r"/festivals/(\d+)-[^/]+"
            r"/id/(\d+)"
            r"(?:-|/|$|\?)",
            url,
        )

        if not match:

            return None

        return {
            "series_id": match.group(1),

            "event_id": match.group(2),
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
                    festival_data[
                        "event_id"
                    ]
                ),

                "festival_series_id": (
                    festival_data[
                        "series_id"
                    ]
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
                SongkickClient
                .extract_event_reference(
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
    def _is_upcoming_event(
        event: dict,
    ) -> bool:

        start_date = event.get(
            "start_date"
        )

        if not start_date:

            return False

        try:

            normalized = (
                start_date.replace(
                    "Z",
                    "+00:00",
                )
            )

            date = (
                datetime.fromisoformat(
                    normalized
                )
            )

            if date.tzinfo is None:

                date = date.replace(
                    tzinfo=timezone.utc
                )

            return (
                date
                >= datetime.now(
                    timezone.utc
                )
            )

        except Exception:

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