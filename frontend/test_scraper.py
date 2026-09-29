import asyncio
import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote

from bs4 import BeautifulSoup
from curl_cffi.requests import AsyncSession


################################################################################
#
# SONGKICK - CURL_CFFI SCRAPER COMPLETO
#
# SEM PLAYWRIGHT
# SEM CHROMIUM
# SEM NAVEGADOR
#
# Fluxo:
#
# 1. Universal Search
# 2. Página principal do artista
# 3. UPCOMING real
# 4. Gigography completa
# 5. Paginação automática
# 6. JSON-LD
# 7. Concertos
# 8. Festivais
# 9. Live Streams
# 10. Deduplicação
# 11. Consolidação
#
################################################################################


SONGKICK_BASE_URL = "https://www.songkick.com"

OUTPUT_DIR = Path("songkick_data")
RAW_DIR = OUTPUT_DIR / "raw"
GIGOGRAPHY_RAW_DIR = RAW_DIR / "gigography"

DEFAULT_ARTIST = "Halsey"


################################################################################
# HEADERS
################################################################################


CHROME_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US",
    "referer": "https://www.songkick.com/",
    "origin": "https://www.songkick.com",
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


################################################################################
# SCRAPER
################################################################################


class SongkickScraper:

    def __init__(self):
        self.session = None

    # =========================================================================
    # DIRETÓRIOS
    # =========================================================================

    @staticmethod
    def prepare_directories():

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        RAW_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        GIGOGRAPHY_RAW_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

    # =========================================================================
    # UTILITÁRIOS
    # =========================================================================

    @staticmethod
    def normalize_text(
        value: str | None,
    ) -> str:

        if not value:
            return ""

        return re.sub(
            r"\s+",
            " ",
            str(value),
        ).strip()

    @staticmethod
    def normalize_url(
        url: str | None,
    ) -> str:

        if not url:
            return ""

        return (
            str(url)
            .split("#")[0]
            .rstrip("/")
        )

    @staticmethod
    def safe_filename(
        value: str,
    ) -> str:

        return "".join(
            char
            if char.isalnum()
            else "_"
            for char in value
        )

    @staticmethod
    def extract_artist_id(
        url: str | None,
    ):

        if not url:
            return None

        match = re.search(
            r"/artists/(\d+)(?:-|/|$)",
            url,
        )

        if match:
            return match.group(1)

        return None

    @staticmethod
    def extract_artist_slug(
        url: str | None,
    ):

        if not url:
            return None

        match = re.search(
            r"/artists/\d+-([^/?#]+)",
            url,
        )

        if match:
            return match.group(1)

        return None

    # =========================================================================
    # EVENT IDS
    # =========================================================================

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

        """
        Exemplo:

        /live-stream-concerts/39702338-geazy

        -> 39702338
        """

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

        """
        Exemplo:

        /festivals/1325-rock-in-rio/id/42907787-rock-in-rio-2026

        Retorna:

        {
            "series_id": "1325",
            "event_id": "42907787"
        }
        """

        if not url:
            return None

        match = re.search(
            r"/festivals/(\d+)-[^/]+/id/(\d+)(?:-|/|$|\?)",
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

        """
        Reconhece:

        - /concerts/
        - /live-stream-concerts/
        - /festivals/.../id/...
        """

        if not url:
            return {
                "event_type": None,
                "event_id": None,
                "festival_series_id": None,
            }

        # ---------------------------------------------------------------------
        # CONCERT
        # ---------------------------------------------------------------------

        concert_id = cls.extract_concert_id(
            url
        )

        if concert_id:

            return {
                "event_type": "concert",
                "event_id": concert_id,
                "festival_series_id": None,
            }

        # ---------------------------------------------------------------------
        # LIVE STREAM
        # ---------------------------------------------------------------------

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

        # ---------------------------------------------------------------------
        # FESTIVAL
        # ---------------------------------------------------------------------

        festival_data = (
            cls.extract_festival_data(
                url
            )
        )

        if festival_data:

            return {
                "event_type": "festival",
                "event_id": festival_data["event_id"],
                "festival_series_id": (
                    festival_data["series_id"]
                ),
            }

        return {
            "event_type": None,
            "event_id": None,
            "festival_series_id": None,
        }

    # =========================================================================
    # HTML / JSON-LD
    # =========================================================================

    @staticmethod
    def parse_json_ld_script(
        script_content: str,
    ) -> list:

        if not script_content:
            return []

        script_content = script_content.strip()

        if not script_content:
            return []

        try:

            data = json.loads(
                script_content
            )

        except json.JSONDecodeError:

            return []

        if isinstance(data, dict):

            graph = data.get(
                "@graph"
            )

            if isinstance(
                graph,
                list,
            ):

                data = graph

            else:

                data = [
                    data
                ]

        if not isinstance(
            data,
            list,
        ):

            return []

        events = []

        for item in data:

            if not isinstance(
                item,
                dict,
            ):

                continue

            event_type = item.get(
                "@type"
            )

            if event_type == "MusicEvent":

                events.append(
                    item
                )

            elif isinstance(
                event_type,
                list,
            ):

                if "MusicEvent" in event_type:

                    events.append(
                        item
                    )

        return events

    @classmethod
    def extract_json_ld_events_from_element(
        cls,
        element,
    ) -> list:

        events = []

        scripts = element.select(
            'script[type="application/ld+json"]'
        )

        for script in scripts:

            text = script.get_text(
                strip=True
            )

            events.extend(
                cls.parse_json_ld_script(
                    text
                )
            )

        return events

    # =========================================================================
    # PARSE EVENT
    # =========================================================================

    @classmethod
    def parse_event(
        cls,
        event: dict,
        page_url: str,
    ) -> dict:

        location = event.get(
            "location",
            {},
        )

        if not isinstance(
            location,
            dict,
        ):

            location = {}

        address = location.get(
            "address",
            {},
        )

        if not isinstance(
            address,
            dict,
        ):

            address = {}

        geo = location.get(
            "geo",
            {},
        )

        if not isinstance(
            geo,
            dict,
        ):

            geo = {}

        performers = event.get(
            "performer",
            [],
        )

        if isinstance(
            performers,
            dict,
        ):

            performers = [
                performers
            ]

        parsed_performers = []

        for performer in performers:

            if not isinstance(
                performer,
                dict,
            ):

                continue

            parsed_performers.append(
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

        offers = event.get(
            "offers",
            [],
        )

        if isinstance(
            offers,
            dict,
        ):

            offers = [
                offers
            ]

        parsed_offers = []

        for offer in offers:

            if not isinstance(
                offer,
                dict,
            ):

                continue

            parsed_offers.append(
                {
                    "@type": offer.get(
                        "@type"
                    ),
                    "url": offer.get(
                        "url"
                    ),
                }
            )

        raw_url = (
            event.get("url")
            or event.get("@id")
        )

        event_url = None

        if raw_url:

            event_url = str(
                raw_url
            ).split("?")[0]

            event_url = urljoin(
                SONGKICK_BASE_URL,
                event_url,
            )

        reference = cls.extract_event_reference(
            event_url
        )

        event_id = reference[
            "event_id"
        ]

        parsed = {
            "id": event_id,
            "songkick_id": event_id,
            "event_type": reference[
                "event_type"
            ],
            "url": event_url,
            "name": event.get(
                "name"
            ),
            "original_name": event.get(
                "name"
            ),
            "start_date": event.get(
                "startDate"
            ),
            "end_date": event.get(
                "endDate"
            ),
            "event_status": event.get(
                "eventStatus"
            ),
            "event_attendance_mode": event.get(
                "eventAttendanceMode"
            ),
            "description": event.get(
                "description"
            ),
            "venue": {
                "name": location.get(
                    "name"
                ),
                "url": location.get(
                    "sameAs"
                ),
                "address": {
                    "street": address.get(
                        "streetAddress"
                    ),
                    "city": address.get(
                        "addressLocality"
                    ),
                    "region": address.get(
                        "addressRegion"
                    ),
                    "postal_code": address.get(
                        "postalCode"
                    ),
                    "country": address.get(
                        "addressCountry"
                    ),
                },
                "latitude": geo.get(
                    "latitude"
                ),
                "longitude": geo.get(
                    "longitude"
                ),
            },
            "performers": parsed_performers,
            "offers": parsed_offers,
            "songkick_image": event.get(
                "image"
            ),
            "source_page": page_url,
            "raw": event,
        }

        # ---------------------------------------------------------------------
        # FESTIVAL
        # ---------------------------------------------------------------------

        if (
            reference["event_type"]
            == "festival"
        ):

            parsed["festival"] = {
                "id": reference[
                    "event_id"
                ],
                "series_id": reference[
                    "festival_series_id"
                ],
                "name": None,
                "url": event_url,
            }

        else:

            parsed["festival"] = None

        return parsed

    # =========================================================================
    # ARTIST PAGE
    # =========================================================================

    @classmethod
    def parse_artist_page(
        cls,
        html: str,
        artist_url: str,
        artist_id: str,
        artist_slug: str,
    ) -> dict:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        artist_data = {
            "songkick_id": str(
                artist_id
            ),
            "primary_key_id": int(
                artist_id
            ),
            "name": None,
            "name_exact": None,
            "display_name": None,
            "slug": artist_slug,
            "url": artist_url,
            "number_of_events": None,
            "description": None,
            "image": None,
            "external_links": [],
        }

        # ---------------------------------------------------------------------
        # TITLE
        # ---------------------------------------------------------------------

        title = soup.title

        if title:

            title_text = cls.normalize_text(
                title.get_text()
            )

            if title_text:

                artist_data["page_title"] = (
                    title_text
                )

        # ---------------------------------------------------------------------
        # H1
        # ---------------------------------------------------------------------

        h1 = soup.find(
            "h1"
        )

        if h1:

            text = cls.normalize_text(
                h1.get_text()
            )

            if text:

                artist_data["name"] = text
                artist_data["name_exact"] = text
                artist_data["display_name"] = text

        # ---------------------------------------------------------------------
        # DESCRIPTION
        # ---------------------------------------------------------------------

        meta_description = soup.select_one(
            'meta[name="description"]'
        )

        if meta_description:

            description = (
                meta_description.get(
                    "content"
                )
            )

            if description:

                artist_data["description"] = (
                    cls.normalize_text(
                        description
                    )
                )

        # ---------------------------------------------------------------------
        # IMAGE
        # ---------------------------------------------------------------------

        og_image = soup.select_one(
            'meta[property="og:image"]'
        )

        if og_image:

            image_url = og_image.get(
                "content"
            )

            if image_url:

                artist_data["image"] = urljoin(
                    SONGKICK_BASE_URL,
                    image_url,
                )

        # ---------------------------------------------------------------------
        # JSON-LD ARTIST
        # ---------------------------------------------------------------------

        scripts = soup.select(
            'script[type="application/ld+json"]'
        )

        json_ld_artist = None

        for script in scripts:

            content = script.get_text(
                strip=True
            )

            if not content:
                continue

            try:

                data = json.loads(
                    content
                )

            except json.JSONDecodeError:

                continue

            candidates = []

            if isinstance(
                data,
                dict,
            ):

                graph = data.get(
                    "@graph"
                )

                if isinstance(
                    graph,
                    list,
                ):

                    candidates.extend(
                        graph
                    )

                else:

                    candidates.append(
                        data
                    )

            elif isinstance(
                data,
                list,
            ):

                candidates.extend(
                    data
                )

            for item in candidates:

                if not isinstance(
                    item,
                    dict,
                ):

                    continue

                item_type = item.get(
                    "@type"
                )

                if item_type in {
                    "MusicGroup",
                    "MusicArtist",
                    "Person",
                }:

                    json_ld_artist = item

                    break

                if isinstance(
                    item_type,
                    list,
                ):

                    if any(
                        value
                        in item_type
                        for value in (
                            "MusicGroup",
                            "MusicArtist",
                            "Person",
                        )
                    ):

                        json_ld_artist = item

                        break

            if json_ld_artist:
                break

        if json_ld_artist:

            json_name = json_ld_artist.get(
                "name"
            )

            if json_name:

                normalized = cls.normalize_text(
                    str(json_name)
                )

                artist_data["name"] = normalized
                artist_data["name_exact"] = normalized
                artist_data["display_name"] = normalized

            json_description = (
                json_ld_artist.get(
                    "description"
                )
            )

            if json_description:

                artist_data["description"] = (
                    cls.normalize_text(
                        str(
                            json_description
                        )
                    )
                )

            json_image = (
                json_ld_artist.get(
                    "image"
                )
            )

            if isinstance(
                json_image,
                str,
            ):

                artist_data["image"] = urljoin(
                    SONGKICK_BASE_URL,
                    json_image,
                )

            elif isinstance(
                json_image,
                dict,
            ):

                image_url = json_image.get(
                    "url"
                )

                if image_url:

                    artist_data["image"] = (
                        urljoin(
                            SONGKICK_BASE_URL,
                            image_url,
                        )
                    )

            same_as = json_ld_artist.get(
                "sameAs"
            )

            if isinstance(
                same_as,
                str,
            ):

                same_as = [
                    same_as
                ]

            if isinstance(
                same_as,
                list,
            ):

                artist_data["external_links"] = [
                    value
                    for value in same_as
                    if isinstance(
                        value,
                        str,
                    )
                ]

        # ---------------------------------------------------------------------
        # EVENT COUNT
        # ---------------------------------------------------------------------

        body_text = cls.normalize_text(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        patterns = [
            r"([\d,\.]+)\s+events?",
            r"([\d,\.]+)\s+shows?",
            r"([\d,\.]+)\s+concerts?",
        ]

        number_of_events = None

        for pattern in patterns:

            match = re.search(
                pattern,
                body_text,
                flags=re.IGNORECASE,
            )

            if match:

                number_text = re.sub(
                    r"[^\d]",
                    "",
                    match.group(1),
                )

                if number_text:

                    number_of_events = int(
                        number_text
                    )

                    break

        artist_data[
            "number_of_events"
        ] = number_of_events

        # ---------------------------------------------------------------------
        # FALLBACK
        # ---------------------------------------------------------------------

        if not artist_data.get(
            "name"
        ):

            fallback_name = (
                artist_slug
                .replace(
                    "-",
                    " ",
                )
                .title()
            )

            artist_data["name"] = (
                fallback_name
            )

            artist_data["name_exact"] = (
                fallback_name
            )

            artist_data["display_name"] = (
                fallback_name
            )

        return artist_data

    # =========================================================================
    # UPCOMING
    # =========================================================================

    @classmethod
    def extract_upcoming_events(
        cls,
        html: str,
        page_url: str,
    ) -> list:

        print("\n")
        print("=" * 80)
        print("EXTRAINDO UPCOMING")
        print("=" * 80)

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        # =====================================================================
        # IMPORTANTE
        #
        # Não pegamos todos os links da página.
        #
        # Pegamos SOMENTE o container:
        #
        # #coming-up
        #
        # Isso evita:
        #
        # - events near you
        # - recommended events
        # - relacionados
        # - resultados da busca
        #
        # =====================================================================

        coming_up = soup.select_one(
            "#coming-up"
        )

        if not coming_up:

            print(
                "Container #coming-up não encontrado."
            )

            return []

        event_items = coming_up.select(
            "li.event-listing-item"
        )

        print(
            f"Upcoming <li> encontrados: "
            f"{len(event_items)}"
        )

        events = []

        for index, event_li in enumerate(
            event_items,
            start=1,
        ):

            # -----------------------------------------------------------------
            # EVENT LINK
            # -----------------------------------------------------------------

            event_link = event_li.select_one(
                "a.event-details"
            )

            if not event_link:

                event_link = event_li.select_one(
                    'a[href*="/concerts/"], '
                    'a[href*="/festivals/"], '
                    'a[href*="/live-stream-concerts/"]'
                )

            if not event_link:

                print(
                    f"[UPCOMING #{index}] "
                    "Sem link de evento."
                )

                continue

            href = event_link.get(
                "href"
            )

            if not href:
                continue

            event_url = urljoin(
                SONGKICK_BASE_URL,
                href,
            )

            # -----------------------------------------------------------------
            # FESTIVAL
            # -----------------------------------------------------------------

            classes = (
                event_link.get(
                    "class"
                )
                or []
            )

            is_festival = (
                "festival"
                in classes
                or "/festivals/"
                in event_url
            )

            # -----------------------------------------------------------------
            # LIVE STREAM
            # -----------------------------------------------------------------

            is_live_stream = (
                "/live-stream-concerts/"
                in event_url
            )

            # -----------------------------------------------------------------
            # DETAILS
            # -----------------------------------------------------------------

            primary_locator = event_link.select_one(
                ".primary-detail"
            )

            primary_detail = None

            if primary_locator:

                primary_detail = cls.normalize_text(
                    primary_locator.get_text()
                )

            secondary_locator = event_link.select_one(
                ".secondary-detail"
            )

            secondary_detail = None

            if secondary_locator:

                secondary_detail = cls.normalize_text(
                    secondary_locator.get_text()
                )

            # -----------------------------------------------------------------
            # DATE
            # -----------------------------------------------------------------

            time_locator = event_li.select_one(
                "time"
            )

            dom_start_date = None

            if time_locator:

                dom_start_date = (
                    time_locator.get(
                        "datetime"
                    )
                )

            # -----------------------------------------------------------------
            # JSON-LD
            # -----------------------------------------------------------------

            json_ld_events = (
                cls.extract_json_ld_events_from_element(
                    event_li
                )
            )

            if json_ld_events:

                parsed = cls.parse_event(
                    json_ld_events[0],
                    page_url,
                )

            else:

                reference = (
                    cls.extract_event_reference(
                        event_url
                    )
                )

                parsed = {
                    "id": reference[
                        "event_id"
                    ],
                    "songkick_id": reference[
                        "event_id"
                    ],
                    "event_type": reference[
                        "event_type"
                    ],
                    "url": event_url,
                    "name": (
                        secondary_detail
                        or primary_detail
                    ),
                    "original_name": None,
                    "start_date": (
                        dom_start_date
                    ),
                    "end_date": None,
                    "event_status": None,
                    "event_attendance_mode": None,
                    "description": None,
                    "venue": {
                        "name": secondary_detail,
                        "url": None,
                        "address": {
                            "street": None,
                            "city": primary_detail,
                            "region": None,
                            "postal_code": None,
                            "country": None,
                        },
                        "latitude": None,
                        "longitude": None,
                    },
                    "performers": [],
                    "offers": [],
                    "songkick_image": None,
                    "source_page": page_url,
                    "raw": None,
                    "festival": None,
                }

            # -----------------------------------------------------------------
            # NORMALIZA EVENT TYPE
            # -----------------------------------------------------------------

            if is_festival:

                reference = (
                    cls.extract_event_reference(
                        event_url
                    )
                )

                festival_name = (
                    secondary_detail
                    or parsed.get(
                        "name"
                    )
                    or primary_detail
                )

                parsed["event_type"] = (
                    "festival"
                )

                parsed["id"] = (
                    reference["event_id"]
                    or parsed.get(
                        "id"
                    )
                )

                parsed["songkick_id"] = (
                    reference["event_id"]
                    or parsed.get(
                        "songkick_id"
                    )
                )

                parsed["name"] = (
                    festival_name
                )

                parsed["festival"] = {
                    "id": (
                        reference["event_id"]
                        or parsed.get(
                            "songkick_id"
                        )
                    ),
                    "series_id": (
                        reference[
                            "festival_series_id"
                        ]
                    ),
                    "name": festival_name,
                    "url": event_url,
                }

            else:

                parsed["event_type"] = (
                    "concert"
                )

                parsed["festival"] = None

            # -----------------------------------------------------------------
            # LIVE STREAM ID
            #
            # Se o JSON-LD não conseguiu identificar o ID,
            # extraímos diretamente da URL.
            # -----------------------------------------------------------------

            if is_live_stream:

                live_stream_id = (
                    cls.extract_live_stream_id(
                        event_url
                    )
                )

                if live_stream_id:

                    parsed["id"] = (
                        live_stream_id
                    )

                    parsed["songkick_id"] = (
                        live_stream_id
                    )

                parsed["event_type"] = (
                    "concert"
                )

            # -----------------------------------------------------------------
            # DETAILS
            # -----------------------------------------------------------------

            parsed["primary_detail"] = (
                primary_detail
            )

            parsed["secondary_detail"] = (
                secondary_detail
            )

            parsed["is_festival"] = (
                parsed["event_type"]
                == "festival"
            )

            if dom_start_date:

                if not parsed.get(
                    "start_date"
                ):

                    parsed["start_date"] = (
                        dom_start_date
                    )

            # -----------------------------------------------------------------
            # RSVP
            # -----------------------------------------------------------------

            rsvp_locator = event_li.select_one(
                ".event-rsvps"
            )

            if rsvp_locator:

                parsed["rsvp_text"] = (
                    cls.normalize_text(
                        rsvp_locator.get_text()
                    )
                )

            else:

                parsed["rsvp_text"] = None

            # -----------------------------------------------------------------
            # IMAGE
            # -----------------------------------------------------------------

            image_locator = event_li.select_one(
                ".event-image"
            )

            if image_locator:

                image_url = (
                    image_locator.get(
                        "src"
                    )
                )

                data_src = (
                    image_locator.get(
                        "data-src"
                    )
                )

                parsed["event_image"] = (
                    image_url
                    or data_src
                )

                parsed["event_image_alt"] = (
                    image_locator.get(
                        "alt"
                    )
                )

            else:

                parsed["event_image"] = None
                parsed["event_image_alt"] = None

            parsed["source"] = (
                "songkick_artist_upcoming"
            )

            events.append(
                parsed
            )

            print(
                f"Upcoming #{index}: "
                f"{parsed.get('event_type')} | "
                f"ID={parsed.get('songkick_id')} | "
                f"Date={parsed.get('start_date')} | "
                f"Name={parsed.get('name')}"
            )

        # ---------------------------------------------------------------------
        # DEDUP
        # ---------------------------------------------------------------------

        unique = {}

        for event in events:

            event_id = event.get(
                "songkick_id"
            )

            if event_id:

                unique[
                    str(event_id)
                ] = event

            else:

                key = (
                    event.get(
                        "url"
                    )
                    or (
                        f"{event.get('name')}"
                        "|"
                        f"{event.get('start_date')}"
                    )
                )

                if key:

                    unique[
                        key
                    ] = event

        events = list(
            unique.values()
        )

        print(
            f"\nUpcoming únicos: "
            f"{len(events)}"
        )

        return events

    # =========================================================================
    # GIGOGRAPHY EVENT PARSER
    # =========================================================================

    @classmethod
    def extract_gigography_events(
        cls,
        html: str,
        page_url: str,
    ) -> list:

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        event_items = soup.select(
            "ul.event-listings.artist-focus "
            "> li[title]"
        )

        date_headers = soup.select(
            "ul.event-listings.artist-focus "
            "> li.with-date"
        )

        print(
            f"Eventos reais: "
            f"{len(event_items)}"
        )

        print(
            f"Separadores de data: "
            f"{len(date_headers)}"
        )

        events = []

        for index, event_li in enumerate(
            event_items,
            start=1,
        ):

            # -----------------------------------------------------------------
            # EVENT LINK
            # -----------------------------------------------------------------

            event_link = event_li.select_one(
                'a[href*="/concerts/"], '
                'a[href*="/festivals/"], '
                'a[href*="/live-stream-concerts/"]'
            )

            if not event_link:

                print(
                    f"[GIGOGRAPHY EVENT #{index}] "
                    "Sem link de evento."
                )

                continue

            href = event_link.get(
                "href"
            )

            if not href:
                continue

            event_url = urljoin(
                SONGKICK_BASE_URL,
                href,
            )

            reference = (
                cls.extract_event_reference(
                    event_url
                )
            )

            # -----------------------------------------------------------------
            # JSON-LD
            # -----------------------------------------------------------------

            json_ld_events = (
                cls.extract_json_ld_events_from_element(
                    event_li
                )
            )

            if json_ld_events:

                parsed = cls.parse_event(
                    json_ld_events[0],
                    page_url,
                )

            else:

                parsed = {
                    "id": reference[
                        "event_id"
                    ],
                    "songkick_id": reference[
                        "event_id"
                    ],
                    "event_type": reference[
                        "event_type"
                    ],
                    "url": event_url,
                    "name": None,
                    "original_name": None,
                    "start_date": None,
                    "end_date": None,
                    "event_status": None,
                    "event_attendance_mode": None,
                    "description": None,
                    "venue": {
                        "name": None,
                        "url": None,
                        "address": {
                            "street": None,
                            "city": None,
                            "region": None,
                            "postal_code": None,
                            "country": None,
                        },
                        "latitude": None,
                        "longitude": None,
                    },
                    "performers": [],
                    "offers": [],
                    "songkick_image": None,
                    "source_page": page_url,
                    "raw": None,
                    "festival": None,
                }

            # -----------------------------------------------------------------
            # DATE
            # -----------------------------------------------------------------

            time_element = event_li.select_one(
                "time"
            )

            if time_element:

                dom_start_date = (
                    time_element.get(
                        "datetime"
                    )
                )

                if dom_start_date:

                    if not parsed.get(
                        "start_date"
                    ):

                        parsed["start_date"] = (
                            dom_start_date
                        )

            # -----------------------------------------------------------------
            # ARTIST SUMMARY
            # -----------------------------------------------------------------

            artist_locator = event_li.select_one(
                "p.artists.summary"
            )

            artist_text = None

            if artist_locator:

                artist_text = cls.normalize_text(
                    artist_locator.get_text()
                )

            # -----------------------------------------------------------------
            # VENUE
            # -----------------------------------------------------------------

            venue_locator = event_li.select_one(
                ".venue-name"
            )

            venue_name = None
            venue_url = None

            if venue_locator:

                venue_name = cls.normalize_text(
                    venue_locator.get_text()
                )

                venue_link = venue_locator.select_one(
                    "a"
                )

                if venue_link:

                    venue_href = venue_link.get(
                        "href"
                    )

                    if venue_href:

                        venue_url = urljoin(
                            SONGKICK_BASE_URL,
                            venue_href,
                        )

            # -----------------------------------------------------------------
            # LOCATION
            # -----------------------------------------------------------------

            location_locator = event_li.select_one(
                "p.location"
            )

            city_region_country = None
            street_address = None

            if location_locator:

                location_text = cls.normalize_text(
                    location_locator.get_text()
                )

                city_region_country = (
                    location_text
                )

                street_locator = (
                    location_locator.select_one(
                        ".street-address"
                    )
                )

                if street_locator:

                    street_address = (
                        cls.normalize_text(
                            street_locator.get_text()
                        )
                    )

            # -----------------------------------------------------------------
            # VENUE MERGE
            # -----------------------------------------------------------------

            if venue_name:

                parsed["venue"]["name"] = (
                    venue_name
                )

            if venue_url:

                parsed["venue"]["url"] = (
                    venue_url
                )

            if street_address:

                parsed["venue"]["address"][
                    "street"
                ] = street_address

            # -----------------------------------------------------------------
            # LIVE STREAM
            # -----------------------------------------------------------------

            is_live_stream = (
                "/live-stream-concerts/"
                in event_url
            )

            if is_live_stream:

                live_stream_id = (
                    cls.extract_live_stream_id(
                        event_url
                    )
                )

                if live_stream_id:

                    parsed["id"] = (
                        live_stream_id
                    )

                    parsed["songkick_id"] = (
                        live_stream_id
                    )

                parsed["event_type"] = (
                    "concert"
                )

                parsed["is_live_stream"] = True

            else:

                parsed["is_live_stream"] = False

            # -----------------------------------------------------------------
            # FESTIVAL
            # -----------------------------------------------------------------

            is_festival = (
                reference["event_type"]
                == "festival"
            )

            if is_festival:

                festival_name = (
                    parsed.get(
                        "name"
                    )
                    or artist_text
                )

                parsed["event_type"] = (
                    "festival"
                )

                parsed["is_festival"] = True

                parsed["festival"] = {
                    "id": (
                        reference[
                            "event_id"
                        ]
                    ),
                    "series_id": (
                        reference[
                            "festival_series_id"
                        ]
                    ),
                    "name": (
                        festival_name
                    ),
                    "url": event_url,
                }

            else:

                parsed["event_type"] = (
                    "concert"
                )

                parsed["is_festival"] = False

                parsed["festival"] = None

            # -----------------------------------------------------------------
            # NAME
            # -----------------------------------------------------------------

            if not parsed.get(
                "name"
            ):

                parsed["name"] = (
                    artist_text
                    or venue_name
                )

            # -----------------------------------------------------------------
            # DETAILS
            # -----------------------------------------------------------------

            parsed["primary_detail"] = (
                city_region_country
            )

            parsed["secondary_detail"] = (
                venue_name
            )

            parsed["source"] = (
                "songkick_gigography"
            )

            # -----------------------------------------------------------------
            # DEBUG
            # -----------------------------------------------------------------

            print(
                f"Event #{index}: "
                f"{parsed.get('event_type')} | "
                f"ID={parsed.get('songkick_id')} | "
                f"Date={parsed.get('start_date')} | "
                f"Name={parsed.get('name')} | "
                f"Venue={venue_name}"
            )

            events.append(
                parsed
            )

        return events

    # =========================================================================
    # NEXT GIGOGRAPHY URL
    # =========================================================================

    @staticmethod
    def get_next_gigography_url(
        html: str,
    ):

        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        next_link = soup.select_one(
            'div.pagination a.next_page[rel="next"]'
        )

        if not next_link:

            next_link = soup.select_one(
                "div.pagination a.next_page"
            )

        if not next_link:

            return None

        classes = next_link.get(
            "class"
        ) or []

        if "disabled" in classes:

            return None

        href = next_link.get(
            "href"
        )

        if not href:

            return None

        return urljoin(
            SONGKICK_BASE_URL,
            href,
        )

    # =========================================================================
    # HTTP REQUEST
    # =========================================================================

    async def request(
        self,
        url: str,
        accept: str = "text/html,application/xhtml+xml",
    ):

        headers = dict(
            CHROME_HEADERS
        )

        headers["accept"] = accept

        start = time.perf_counter()

        response = await self.session.get(
            url,
            headers=headers,
            timeout=60,
            allow_redirects=True,
        )

        elapsed = (
            time.perf_counter()
            - start
        )

        return response, elapsed

    # =========================================================================
    # SEARCH ARTIST
    # =========================================================================

    async def search_artist(
        self,
        artist_name: str,
    ):

        print("=" * 80)
        print("SONGKICK CURL_CFFI SCRAPER")
        print("=" * 80)

        print(
            f"\nArtista: {artist_name}"
        )

        self.prepare_directories()

        async with AsyncSession(
            impersonate="chrome",
            http_version=2,
            timeout=60,
        ) as session:

            self.session = session

            # ================================================================
            # HOME
            # ================================================================

            print("\n")
            print("=" * 80)
            print("HOME")
            print("=" * 80)

            home_url = (
                f"{SONGKICK_BASE_URL}/"
            )

            home_response, home_elapsed = (
                await self.request(
                    home_url,
                    accept=(
                        "text/html,"
                        "application/xhtml+xml"
                    ),
                )
            )

            print(
                f"Status: {home_response.status_code}"
            )

            print(
                f"HTTP version: "
                f"{getattr(home_response, 'http_version', 'unknown')}"
            )

            print(
                f"Tempo: "
                f"{home_elapsed:.2f}s"
            )

            if home_response.status_code != 200:

                raise RuntimeError(
                    "Songkick home retornou "
                    f"{home_response.status_code}"
                )

            safe_name = self.safe_filename(
                artist_name
            )

            home_file = (
                RAW_DIR
                / f"{safe_name}_curl_home.html"
            )

            home_file.write_text(
                home_response.text,
                encoding="utf-8",
            )

            # ================================================================
            # UNIVERSAL SEARCH
            # ================================================================

            print("\n")
            print("=" * 80)
            print("UNIVERSAL SEARCH")
            print("=" * 80)

            search_url = (
                f"{SONGKICK_BASE_URL}"
                f"/api/universal_search"
                f"?query={quote(artist_name)}"
            )

            print(
                search_url
            )

            search_response, search_elapsed = (
                await self.request(
                    search_url,
                    accept=(
                        "application/json,"
                        "text/plain,"
                        "*/*"
                    ),
                )
            )

            print(
                f"Status: "
                f"{search_response.status_code}"
            )

            print(
                f"Tempo: "
                f"{search_elapsed:.2f}s"
            )

            if search_response.status_code != 200:

                print(
                    search_response.text[:2000]
                )

                raise RuntimeError(
                    "Songkick universal_search "
                    f"retornou "
                    f"{search_response.status_code}"
                )

            try:

                raw_data = search_response.json()

            except Exception as exc:

                raise RuntimeError(
                    "Universal search não "
                    "retornou JSON válido."
                ) from exc

            search_raw_file = (
                RAW_DIR
                / f"{safe_name}_curl_search.json"
            )

            search_raw_file.write_text(
                json.dumps(
                    raw_data,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            # ================================================================
            # SELECT ARTIST
            # ================================================================

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

            artists = (
                search_results.get(
                    "artists",
                    []
                )
            )

            selected_artist = None

            for result in artists:

                document = result.get(
                    "document",
                    {},
                )

                name = (
                    document.get(
                        "name",
                        ""
                    )
                )

                if (
                    name.lower()
                    == artist_name.lower()
                ):

                    selected_artist = (
                        document
                    )

                    break

            if not selected_artist and artists:

                selected_artist = (
                    artists[0].get(
                        "document",
                        {}
                    )
                )

            if not selected_artist:

                raise RuntimeError(
                    f"Artista não encontrado: "
                    f"{artist_name}"
                )

            artist_id = str(
                selected_artist.get(
                    "primary_key_id"
                )
            )

            artist_slug = (
                self.extract_artist_slug(
                    selected_artist.get(
                        "url",
                        "",
                    )
                )
            )

            if not artist_slug:

                artist_slug = re.sub(
                    r"[^a-z0-9]+",
                    "-",
                    artist_name.lower(),
                ).strip("-")

            artist_url = (
                f"{SONGKICK_BASE_URL}"
                f"/artists/"
                f"{artist_id}-"
                f"{artist_slug}"
            )

            number_of_events = (
                selected_artist.get(
                    "number_of_events"
                )
            )

            print(
                "\nArtista encontrado:"
            )

            print(
                f"Nome: "
                f"{selected_artist.get('name')}"
            )

            print(
                f"Songkick ID: "
                f"{artist_id}"
            )

            print(
                f"Slug: "
                f"{artist_slug}"
            )

            print(
                f"Eventos informados: "
                f"{number_of_events}"
            )

            # ================================================================
            # ARTIST PAGE
            # ================================================================

            print("\n")
            print("=" * 80)
            print("PÁGINA DO ARTISTA")
            print("=" * 80)

            print(
                artist_url
            )

            artist_response, artist_elapsed = (
                await self.request(
                    artist_url,
                    accept=(
                        "text/html,"
                        "application/xhtml+xml"
                    ),
                )
            )

            print(
                f"Status: "
                f"{artist_response.status_code}"
            )

            print(
                f"Bytes: "
                f"{len(artist_response.content)}"
            )

            print(
                f"Tempo: "
                f"{artist_elapsed:.2f}s"
            )

            if artist_response.status_code != 200:

                raise RuntimeError(
                    "Página do artista retornou "
                    f"{artist_response.status_code}"
                )

            artist_html_file = (
                RAW_DIR
                / f"{artist_id}_{artist_slug}_curl_artist.html"
            )

            artist_html_file.write_text(
                artist_response.text,
                encoding="utf-8",
            )

            artist_page_data = (
                self.parse_artist_page(
                    artist_response.text,
                    artist_url,
                    artist_id,
                    artist_slug,
                )
            )

            if (
                artist_page_data.get(
                    "number_of_events"
                )
                is not None
            ):

                number_of_events = (
                    artist_page_data[
                        "number_of_events"
                    ]
                )

            print(
                f"Upcoming container encontrado: "
                f"{BeautifulSoup(artist_response.text, 'html.parser').select_one('#coming-up') is not None}"
            )

            # ================================================================
            # UPCOMING
            # ================================================================

            upcoming_events = (
                self.extract_upcoming_events(
                    artist_response.text,
                    artist_url,
                )
            )

            # ================================================================
            # GIGOGRAPHY
            # ================================================================

            (
                gigography_events,
                pages_scraped,
            ) = await self.scrape_gigography(
                artist_id,
                artist_slug,
            )

            # ================================================================
            # CONSOLIDAÇÃO
            # ================================================================

            final_events = (
                self.consolidate_events(
                    upcoming_events,
                    gigography_events,
                )
            )

            final_events.sort(
                key=lambda event: (
                    event.get(
                        "start_date"
                    )
                    or ""
                ),
                reverse=True,
            )

            # ================================================================
            # CONTADORES
            # ================================================================

            upcoming_festivals = sum(
                1
                for event in upcoming_events
                if event.get(
                    "event_type"
                ) == "festival"
            )

            gigography_festivals = sum(
                1
                for event in gigography_events
                if event.get(
                    "event_type"
                ) == "festival"
            )

            final_festivals = sum(
                1
                for event in final_events
                if event.get(
                    "event_type"
                ) == "festival"
            )

            livestream_count = sum(
                1
                for event in final_events
                if event.get(
                    "is_live_stream"
                )
            )

            # ================================================================
            # ARTIST RESULT
            # ================================================================

            artist_result = {
                "id": (
                    selected_artist.get(
                        "id"
                    )
                    or f"Artist{artist_id}"
                ),
                "primary_key_id": int(
                    artist_id
                ),
                "songkick_id": (
                    artist_id
                ),
                "name": (
                    artist_page_data.get(
                        "name"
                    )
                    or selected_artist.get(
                        "name"
                    )
                    or artist_name
                ),
                "name_exact": (
                    artist_page_data.get(
                        "name_exact"
                    )
                    or selected_artist.get(
                        "name_exact"
                    )
                    or artist_name
                ),
                "display_name": (
                    artist_page_data.get(
                        "display_name"
                    )
                    or selected_artist.get(
                        "display_name"
                    )
                    or artist_name
                ),
                "slug": artist_slug,
                "url": (
                    artist_page_data.get(
                        "url"
                    )
                    or artist_url
                ),
                "number_of_events": (
                    number_of_events
                ),
                "description": (
                    artist_page_data.get(
                        "description"
                    )
                ),
                "songkick_image": (
                    artist_page_data.get(
                        "image"
                    )
                ),
                "external_links": (
                    artist_page_data.get(
                        "external_links",
                        []
                    )
                ),
                "popularity": (
                    selected_artist.get(
                        "popularity"
                    )
                ),
                "is_valid": (
                    selected_artist.get(
                        "is_valid"
                    )
                ),
                "is_active": (
                    selected_artist.get(
                        "is_active"
                    )
                ),
            }

            # ================================================================
            # RESULT
            # ================================================================

            result = {
                "source": "songkick",

                "artist": artist_result,

                "events_source": (
                    "songkick_artist_page"
                    "+songkick_gigography"
                ),

                "upcoming_count": len(
                    upcoming_events
                ),

                "upcoming_festival_count": (
                    upcoming_festivals
                ),

                "gigography_count": len(
                    gigography_events
                ),

                "gigography_festival_count": (
                    gigography_festivals
                ),

                "live_stream_count": (
                    livestream_count
                ),

                "pages_scraped": (
                    pages_scraped
                ),

                "events_count": len(
                    final_events
                ),

                "festival_count": (
                    final_festivals
                ),

                "events": final_events,
            }

            # ================================================================
            # SALVA
            # ================================================================

            parsed_file = (
                OUTPUT_DIR
                / f"{safe_name}_curl_full_parsed.json"
            )

            parsed_file.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            # ================================================================
            # FINAL
            # ================================================================

            print("\n")
            print("=" * 80)
            print("RESULTADO FINAL")
            print("=" * 80)

            print(
                f"\nArtista: "
                f"{artist_result['name']}"
            )

            print(
                f"Songkick ID: "
                f"{artist_id}"
            )

            print(
                f"Slug: "
                f"{artist_slug}"
            )

            print(
                f"\nEventos informados pelo Songkick: "
                f"{number_of_events}"
            )

            print(
                f"\nUpcoming reais: "
                f"{len(upcoming_events)}"
            )

            print(
                f"Upcoming festivais: "
                f"{upcoming_festivals}"
            )

            print(
                f"\nGigography: "
                f"{len(gigography_events)}"
            )

            print(
                f"Gigography festivais: "
                f"{gigography_festivals}"
            )

            print(
                f"Páginas da gigography: "
                f"{pages_scraped}"
            )

            print(
                f"\nLive Streams: "
                f"{livestream_count}"
            )

            print(
                f"\nTotal final: "
                f"{len(final_events)}"
            )

            print(
                f"Festivais no total: "
                f"{final_festivals}"
            )

            print(
                "\nArquivo salvo:"
            )

            print(
                parsed_file.resolve()
            )

            print(
                "\n" + "=" * 80
            )

            print(
                "TESTE FINALIZADO"
            )

            print(
                "=" * 80
            )

            return result

    # =========================================================================
    # GIGOGRAPHY COMPLETA
    # =========================================================================

    async def scrape_gigography(
        self,
        artist_id: str,
        artist_slug: str,
    ):

        print("\n")
        print("=" * 80)
        print("GIGOGRAPHY")
        print("=" * 80)

        first_url = (
            f"{SONGKICK_BASE_URL}"
            f"/artists/"
            f"{artist_id}-"
            f"{artist_slug}"
            f"/gigography"
        )

        events_by_id = {}

        current_url = first_url

        visited_urls = set()

        pages_scraped = 0

        while current_url:

            normalized_url = (
                self.normalize_url(
                    current_url
                )
            )

            if normalized_url in visited_urls:

                print(
                    "\nURL já visitada."
                )

                break

            visited_urls.add(
                normalized_url
            )

            page_number_match = re.search(
                r"[?&]page=(\d+)",
                current_url,
            )

            if page_number_match:

                page_number = int(
                    page_number_match.group(
                        1
                    )
                )

            else:

                page_number = 1

            print("\n")
            print("=" * 80)
            print(
                f"GIGOGRAPHY PAGE {page_number}"
            )
            print("=" * 80)

            print(
                current_url
            )

            try:

                response, elapsed = (
                    await self.request(
                        current_url,
                        accept=(
                            "text/html,"
                            "application/xhtml+xml"
                        ),
                    )
                )

            except Exception as exc:

                print(
                    f"Erro HTTP: {exc}"
                )

                break

            print(
                f"Status: "
                f"{response.status_code}"
            )

            print(
                f"Bytes: "
                f"{len(response.content)}"
            )

            print(
                f"Tempo: "
                f"{elapsed:.2f}s"
            )

            if response.status_code != 200:

                print(
                    "Página retornou erro."
                )

                break

            html = response.text

            # -----------------------------------------------------------------
            # SALVA RAW
            # -----------------------------------------------------------------

            raw_file = (
                GIGOGRAPHY_RAW_DIR
                / f"page_{page_number}_curl.html"
            )

            raw_file.write_text(
                html,
                encoding="utf-8",
            )

            # -----------------------------------------------------------------
            # EVENTOS
            # -----------------------------------------------------------------

            page_events = (
                self.extract_gigography_events(
                    html,
                    current_url,
                )
            )

            # -----------------------------------------------------------------
            # CONTADORES
            # -----------------------------------------------------------------

            page_concerts = sum(
                1
                for event in page_events
                if event.get(
                    "event_type"
                ) == "concert"
            )

            page_festivals = sum(
                1
                for event in page_events
                if event.get(
                    "event_type"
                ) == "festival"
            )

            print(
                f"Concertos: "
                f"{page_concerts}"
            )

            print(
                f"Festivais: "
                f"{page_festivals}"
            )

            # -----------------------------------------------------------------
            # DEDUP
            # -----------------------------------------------------------------

            new_events = 0
            duplicate_events = 0

            for event in page_events:

                event_id = event.get(
                    "songkick_id"
                )

                if event_id:

                    key = str(
                        event_id
                    )

                else:

                    key = (
                        event.get("url")
                        or (
                            f"{event.get('name')}"
                            "|"
                            f"{event.get('start_date')}"
                        )
                    )

                if not key:
                    continue

                if key in events_by_id:

                    duplicate_events += 1

                    continue

                events_by_id[key] = (
                    event
                )

                new_events += 1

            pages_scraped += 1

            print(
                f"Novos eventos: "
                f"{new_events}"
            )

            print(
                f"Duplicados: "
                f"{duplicate_events}"
            )

            print(
                f"Total acumulado: "
                f"{len(events_by_id)}"
            )

            # -----------------------------------------------------------------
            # NEXT PAGE
            # -----------------------------------------------------------------

            next_url = (
                self.get_next_gigography_url(
                    html
                )
            )

            print(
                f"\nPróxima página: "
                f"{next_url}"
            )

            current_url = next_url

        # =========================================================================
        # FINAL
        # =========================================================================

        events = list(
            events_by_id.values()
        )

        festival_count = sum(
            1
            for event in events
            if event.get(
                "event_type"
            ) == "festival"
        )

        print("\n")
        print("=" * 80)
        print("GIGOGRAPHY FINALIZADA")
        print("=" * 80)

        print(
            f"Páginas acessadas: "
            f"{pages_scraped}"
        )

        print(
            f"Eventos únicos: "
            f"{len(events)}"
        )

        print(
            f"Festivais: "
            f"{festival_count}"
        )

        return (
            events,
            pages_scraped,
        )

    # =========================================================================
    # MERGE
    # =========================================================================

    @staticmethod
    def merge_events(
        existing: dict,
        new_event: dict,
    ) -> dict:

        merged = dict(
            existing
        )

        for key, value in new_event.items():

            if value is None:
                continue

            if value == "":
                continue

            if value == []:
                continue

            if value == {}:
                continue

            existing_value = merged.get(
                key
            )

            if (
                existing_value is None
                or existing_value == ""
                or existing_value == []
                or existing_value == {}
            ):

                merged[key] = value

        # ---------------------------------------------------------------------
        # FESTIVAL
        # ---------------------------------------------------------------------

        if new_event.get(
            "festival"
        ):

            merged["festival"] = (
                new_event[
                    "festival"
                ]
            )

        # ---------------------------------------------------------------------
        # LIVE STREAM
        # ---------------------------------------------------------------------

        if new_event.get(
            "is_live_stream"
        ):

            merged["is_live_stream"] = True

        return merged

    # =========================================================================
    # CONSOLIDATE
    # =========================================================================

    @classmethod
    def consolidate_events(
        cls,
        upcoming_events: list,
        gigography_events: list,
    ) -> list:

        events_by_id = {}

        # ---------------------------------------------------------------------
        # UPCOMING
        # ---------------------------------------------------------------------

        for event in upcoming_events:

            event_id = event.get(
                "songkick_id"
            )

            if event_id:

                key = str(
                    event_id
                )

            else:

                key = (
                    event.get("url")
                    or (
                        f"{event.get('name')}"
                        "|"
                        f"{event.get('start_date')}"
                    )
                )

            if key:

                events_by_id[key] = (
                    event
                )

        # ---------------------------------------------------------------------
        # GIGOGRAPHY
        # ---------------------------------------------------------------------

        for event in gigography_events:

            event_id = event.get(
                "songkick_id"
            )

            if event_id:

                key = str(
                    event_id
                )

            else:

                key = (
                    event.get("url")
                    or (
                        f"{event.get('name')}"
                        "|"
                        f"{event.get('start_date')}"
                    )
                )

            if not key:
                continue

            if key in events_by_id:

                events_by_id[key] = (
                    cls.merge_events(
                        events_by_id[key],
                        event,
                    )
                )

            else:

                events_by_id[key] = (
                    event
                )

        return list(
            events_by_id.values()
        )


################################################################################
# RUN
################################################################################


async def run(
    artist_name: str,
):

    scraper = SongkickScraper()

    return await scraper.search_artist(
        artist_name
    )


################################################################################
# CLI
################################################################################


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Songkick scraper usando "
            "curl_cffi, sem Playwright."
        )
    )

    parser.add_argument(
        "artist",
        nargs="?",
        default=DEFAULT_ARTIST,
        help="Nome do artista.",
    )

    args = parser.parse_args()

    asyncio.run(
        run(
            args.artist
        )
    )


if __name__ == "__main__":
    main()