import asyncio
import argparse
import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote

from playwright.async_api import async_playwright


SONGKICK_BASE_URL = "https://www.songkick.com"

OUTPUT_DIR = Path("songkick_data")
RAW_DIR = OUTPUT_DIR / "raw"
GIGOGRAPHY_RAW_DIR = RAW_DIR / "gigography"


class SongkickScraper:

    def __init__(self, headless: bool = False):
        self.headless = headless

    # ======================================================================
    # UTILITÁRIOS
    # ======================================================================

    @staticmethod
    def normalize_url(url: str) -> str:
        if not url:
            return ""

        return url.split("#")[0].rstrip("/")

    @staticmethod
    def normalize_text(value: str) -> str:
        if not value:
            return ""

        value = re.sub(r"\s+", " ", value)

        return value.strip()

    @staticmethod
    def extract_artist_id(url: str):
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
    def extract_artist_slug(url: str):
        if not url:
            return None

        match = re.search(
            r"/artists/\d+-([^/?#]+)",
            url,
        )

        if match:
            return match.group(1)

        return None

    @staticmethod
    def extract_concert_id(url: str):
        """
        Exemplo:

        /concerts/43251607-demi-lovato-at-suhai-music-hall

        -> 43251607
        """

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
    def extract_festival_data(url: str):
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

    @staticmethod
    def extract_event_reference(url: str):
        """
        Identifica se a URL corresponde a:

        - concert
        - festival
        """

        if not url:
            return {
                "event_type": None,
                "event_id": None,
                "festival_series_id": None,
            }

        concert_id = (
            SongkickScraper.extract_concert_id(url)
        )

        if concert_id:

            return {
                "event_type": "concert",
                "event_id": concert_id,
                "festival_series_id": None,
            }

        festival_data = (
            SongkickScraper.extract_festival_data(
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

    @staticmethod
    def is_artist_page(
        url: str,
        artist_id: str,
        artist_slug: str,
    ) -> bool:

        parsed = urlparse(url)

        expected_path = (
            f"/artists/{artist_id}-{artist_slug}"
        )

        actual_path = parsed.path.rstrip("/")

        return actual_path == expected_path

    @staticmethod
    def is_gigography_page(
        url: str,
        artist_id: str,
        artist_slug: str,
    ) -> bool:

        parsed = urlparse(url)

        expected_path = (
            f"/artists/{artist_id}-{artist_slug}/gigography"
        )

        actual_path = parsed.path.rstrip("/")

        return actual_path == expected_path

    # ======================================================================
    # JSON-LD
    # ======================================================================

    @staticmethod
    def parse_json_ld_script(
        script_content: str,
    ):
        if not script_content:
            return []

        if not script_content.strip():
            return []

        try:

            data = json.loads(
                script_content
            )

        except json.JSONDecodeError:

            return []

        if isinstance(data, dict):

            graph = data.get("@graph")

            if isinstance(graph, list):

                data = graph

            else:

                data = [data]

        if not isinstance(data, list):
            return []

        events = []

        for item in data:

            if not isinstance(item, dict):
                continue

            event_type = item.get("@type")

            if event_type == "MusicEvent":

                events.append(item)

            elif isinstance(
                event_type,
                list,
            ):

                if "MusicEvent" in event_type:

                    events.append(item)

        return events

    async def extract_json_ld_events_from_li(
        self,
        event_li,
    ):
        """
        Extrai JSON-LD somente do elemento do evento atual.
        """

        scripts = await event_li.locator(
            'script[type="application/ld+json"]'
        ).all_text_contents()

        events = []

        for script_content in scripts:

            events.extend(
                self.parse_json_ld_script(
                    script_content
                )
            )

        return events

    # ======================================================================
    # PÁGINA DO ARTISTA
    # ======================================================================

    async def scrape_artist_page(
        self,
        page,
        artist_url: str,
        artist_id: str,
        artist_slug: str,
    ):
        """
        Abre a página principal do artista e extrai:

        - informações básicas do artista
        - nome
        - URL
        - Songkick ID
        - slug
        - quantidade de eventos informada pelo Songkick
        - descrição/bio quando disponível
        - imagem quando disponível
        - links externos quando disponíveis

        IMPORTANTE:

        Este método também garante que a página principal do artista
        esteja efetivamente aberta antes da extração do UPCOMING.
        """

        print("\n")
        print("=" * 80)
        print("PÁGINA DO ARTISTA")
        print("=" * 80)

        print(
            f"Artist URL: "
            f"{artist_url}"
        )

        try:

            response = await page.goto(
                artist_url,
                wait_until="domcontentloaded",
                timeout=60_000,
            )

        except Exception as exc:

            print(
                f"Erro navegando para página do artista: "
                f"{exc}"
            )

            raise

        final_url = page.url

        print(
            f"Final URL: "
            f"{final_url}"
        )

        if response:

            print(
                f"Status: "
                f"{response.status}"
            )

        if not self.is_artist_page(
            final_url,
            artist_id,
            artist_slug,
        ):

            print(
                "AVISO: URL final não corresponde "
                "exatamente à página esperada do artista."
            )

        # ------------------------------------------------------------------
        # SALVA HTML RAW
        # ------------------------------------------------------------------

        html = await page.content()

        artist_raw_file = (
            RAW_DIR
            / f"{artist_id}_{artist_slug}_artist.html"
        )

        artist_raw_file.write_text(
            html,
            encoding="utf-8",
        )

        print(
            f"HTML da página do artista salvo em: "
            f"{artist_raw_file}"
        )

        # ------------------------------------------------------------------
        # RESULTADO BASE
        # ------------------------------------------------------------------

        artist_data = {
            "songkick_id": str(artist_id),
            "primary_key_id": int(artist_id),
            "name": None,
            "name_exact": None,
            "display_name": None,
            "slug": artist_slug,
            "url": final_url,
            "number_of_events": None,
            "description": None,
            "image": None,
            "external_links": [],
        }

        # ------------------------------------------------------------------
        # TITLE
        # ------------------------------------------------------------------

        title = await page.title()

        if title:

            title = self.normalize_text(
                title
            )

            artist_data["page_title"] = title

        # ------------------------------------------------------------------
        # H1
        # ------------------------------------------------------------------

        h1 = page.locator(
            "h1"
        ).first

        if await h1.count():

            try:

                h1_text = (
                    await h1.inner_text()
                )

                h1_text = self.normalize_text(
                    h1_text
                )

                if h1_text:

                    artist_data["name"] = (
                        h1_text
                    )

                    artist_data["name_exact"] = (
                        h1_text
                    )

                    artist_data["display_name"] = (
                        h1_text
                    )

            except Exception:
                pass

        # ------------------------------------------------------------------
        # META DESCRIPTION
        # ------------------------------------------------------------------

        meta_description = page.locator(
            'meta[name="description"]'
        ).first

        if await meta_description.count():

            description = (
                await meta_description.get_attribute(
                    "content"
                )
            )

            if description:

                artist_data["description"] = (
                    self.normalize_text(
                        description
                    )
                )

        # ------------------------------------------------------------------
        # OG IMAGE
        # ------------------------------------------------------------------

        og_image = page.locator(
            'meta[property="og:image"]'
        ).first

        if await og_image.count():

            image_url = (
                await og_image.get_attribute(
                    "content"
                )
            )

            if image_url:

                artist_data["image"] = (
                    urljoin(
                        SONGKICK_BASE_URL,
                        image_url,
                    )
                )

        # ------------------------------------------------------------------
        # JSON-LD DA PÁGINA
        # ------------------------------------------------------------------

        json_ld_scripts = await page.locator(
            'script[type="application/ld+json"]'
        ).all_text_contents()

        json_ld_artist = None

        for script_content in json_ld_scripts:

            if not script_content:
                continue

            try:

                data = json.loads(
                    script_content
                )

            except json.JSONDecodeError:

                continue

            candidates = []

            if isinstance(data, dict):

                graph = data.get("@graph")

                if isinstance(graph, list):

                    candidates.extend(
                        graph
                    )

                else:

                    candidates.append(
                        data
                    )

            elif isinstance(data, list):

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

                if (
                    item_type == "MusicGroup"
                    or item_type == "Person"
                    or item_type == "MusicArtist"
                ):

                    json_ld_artist = (
                        item
                    )

                    break

                if isinstance(
                    item_type,
                    list,
                ):

                    if any(
                        value in item_type
                        for value in [
                            "MusicGroup",
                            "MusicArtist",
                            "Person",
                        ]
                    ):

                        json_ld_artist = (
                            item
                        )

                        break

            if json_ld_artist:
                break

        if json_ld_artist:

            json_name = json_ld_artist.get(
                "name"
            )

            if json_name:

                artist_data["name"] = (
                    self.normalize_text(
                        str(json_name)
                    )
                )

                artist_data["name_exact"] = (
                    self.normalize_text(
                        str(json_name)
                    )
                )

                artist_data["display_name"] = (
                    self.normalize_text(
                        str(json_name)
                    )
                )

            json_description = (
                json_ld_artist.get(
                    "description"
                )
            )

            if json_description:

                artist_data["description"] = (
                    self.normalize_text(
                        str(json_description)
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

                artist_data["image"] = (
                    urljoin(
                        SONGKICK_BASE_URL,
                        json_image,
                    )
                )

            elif isinstance(
                json_image,
                dict,
            ):

                json_image_url = (
                    json_image.get(
                        "url"
                    )
                )

                if json_image_url:

                    artist_data["image"] = (
                        urljoin(
                            SONGKICK_BASE_URL,
                            json_image_url,
                        )
                    )

            same_as = (
                json_ld_artist.get(
                    "sameAs"
                )
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

        # ------------------------------------------------------------------
        # LINKS EXTERNOS
        # ------------------------------------------------------------------

        external_links = []

        links = page.locator(
            "a[href]"
        )

        link_count = await links.count()

        for index in range(
            link_count
        ):

            link = links.nth(
                index
            )

            href = await link.get_attribute(
                "href"
            )

            if not href:
                continue

            href = urljoin(
                SONGKICK_BASE_URL,
                href,
            )

            if not href.startswith(
                "http"
            ):

                continue

            if (
                "songkick.com"
                in urlparse(
                    href
                ).netloc.lower()
            ):

                continue

            if href not in external_links:

                external_links.append(
                    href
                )

        if external_links:

            for link in external_links:

                if link not in artist_data[
                    "external_links"
                ]:

                    artist_data[
                        "external_links"
                    ].append(
                        link
                    )

        # ------------------------------------------------------------------
        # QUANTIDADE DE EVENTOS
        # ------------------------------------------------------------------

        number_of_events = None

        # Tentativa 1:
        # atributos/data presentes no HTML.

        event_count_selectors = [
            '[data-event-count]',
            '[data-number-of-events]',
            '.artist-events-count',
            '.event-count',
            '.number-of-events',
        ]

        for selector in event_count_selectors:

            locator = page.locator(
                selector
            ).first

            if await locator.count() == 0:
                continue

            for attribute in [
                "data-event-count",
                "data-number-of-events",
            ]:

                value = await locator.get_attribute(
                    attribute
                )

                if value:

                    match = re.search(
                        r"\d[\d,\.]*",
                        value,
                    )

                    if match:

                        number_of_events = int(
                            re.sub(
                                r"[^\d]",
                                "",
                                match.group(0),
                            )
                        )

                        break

            if number_of_events is not None:
                break

        # ------------------------------------------------------------------
        # Tentativa 2:
        # texto da página procurando padrões de eventos.
        # ------------------------------------------------------------------

        if number_of_events is None:

            body_text = ""

            try:

                body_text = await page.locator(
                    "body"
                ).inner_text()

                body_text = self.normalize_text(
                    body_text
                )

            except Exception:
                body_text = ""

            patterns = [
                r"([\d,\.]+)\s+events?",
                r"([\d,\.]+)\s+shows?",
                r"([\d,\.]+)\s+concerts?",
            ]

            for pattern in patterns:

                match = re.search(
                    pattern,
                    body_text,
                    flags=re.IGNORECASE,
                )

                if match:

                    number_text = (
                        match.group(1)
                    )

                    number_text = re.sub(
                        r"[^\d]",
                        "",
                        number_text,
                    )

                    if number_text:

                        number_of_events = int(
                            number_text
                        )

                        break

        artist_data[
            "number_of_events"
        ] = number_of_events

        # ------------------------------------------------------------------
        # FALLBACK DE NOME
        # ------------------------------------------------------------------

        if not artist_data.get(
            "name"
        ):

            artist_data["name"] = (
                artist_slug.replace(
                    "-",
                    " ",
                ).title()
            )

            artist_data["name_exact"] = (
                artist_data["name"]
            )

            artist_data["display_name"] = (
                artist_data["name"]
            )

        # ------------------------------------------------------------------
        # DEBUG
        # ------------------------------------------------------------------

        print("\nInformações encontradas na página:")

        print(
            f"Nome: "
            f"{artist_data.get('name')}"
        )

        print(
            f"Songkick ID: "
            f"{artist_data.get('songkick_id')}"
        )

        print(
            f"Slug: "
            f"{artist_data.get('slug')}"
        )

        print(
            f"Eventos: "
            f"{artist_data.get('number_of_events')}"
        )

        print(
            f"Imagem: "
            f"{artist_data.get('image')}"
        )

        print(
            f"External links: "
            f"{len(artist_data.get('external_links', []))}"
        )

        return artist_data

    # ======================================================================
    # PARSE EVENTO
    # ======================================================================

    @staticmethod
    def parse_event(
        event: dict,
        page_url: str,
    ) -> dict:

        location = event.get(
            "location",
            {},
        )

        if not isinstance(location, dict):
            location = {}

        address = location.get(
            "address",
            {},
        )

        if not isinstance(address, dict):
            address = {}

        geo = location.get(
            "geo",
            {},
        )

        if not isinstance(geo, dict):
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

        reference = (
            SongkickScraper.extract_event_reference(
                event_url
            )
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

    # ======================================================================
    # UPCOMING
    # ======================================================================

    async def extract_upcoming_events(
        self,
        page,
        page_url: str,
    ):

        print("\n")
        print("=" * 80)
        print("EXTRAINDO UPCOMING")
        print("=" * 80)

        selector = (
            "#coming-up "
            "ol.artist-calendar-summary "
            "li.event-listing-item"
        )

        event_items = page.locator(
            selector
        )

        total_items = (
            await event_items.count()
        )

        print(
            f"Upcoming <li> encontrados: "
            f"{total_items}"
        )

        events = []

        for index in range(
            total_items
        ):

            event_li = event_items.nth(
                index
            )

            event_link = event_li.locator(
                "a.event-details"
            ).first

            if await event_link.count() == 0:

                print(
                    f"[UPCOMING #{index + 1}] "
                    "Sem link de evento."
                )

                continue

            href = await event_link.get_attribute(
                "href"
            )

            if not href:
                continue

            event_url = urljoin(
                SONGKICK_BASE_URL,
                href,
            )

            classes = (
                await event_link.get_attribute(
                    "class"
                )
                or ""
            )

            is_festival = (
                "festival"
                in classes.split()
                or "/festivals/"
                in event_url
            )

            primary_detail = None
            secondary_detail = None

            primary_locator = event_link.locator(
                ".primary-detail"
            ).first

            if await primary_locator.count():

                primary_detail = (
                    await primary_locator.inner_text()
                ).strip()

            secondary_locator = event_link.locator(
                ".secondary-detail"
            ).first

            if await secondary_locator.count():

                secondary_detail = (
                    await secondary_locator.inner_text()
                ).strip()

            time_locator = event_li.locator(
                "time"
            ).first

            dom_start_date = None

            if await time_locator.count():

                dom_start_date = (
                    await time_locator.get_attribute(
                        "datetime"
                    )
                )

            json_ld_events = (
                await self.extract_json_ld_events_from_li(
                    event_li
                )
            )

            if json_ld_events:

                parsed = self.parse_event(
                    json_ld_events[0],
                    page_url,
                )

            else:

                reference = (
                    self.extract_event_reference(
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

            # --------------------------------------------------------------
            # FESTIVAL
            # --------------------------------------------------------------

            if is_festival:

                reference = (
                    self.extract_event_reference(
                        event_url
                    )
                )

                festival_name = (
                    secondary_detail
                    or parsed.get(
                        "name"
                    )
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

            # --------------------------------------------------------------
            # RSVP
            # --------------------------------------------------------------

            rsvp_text = None

            rsvp_locator = event_li.locator(
                ".event-rsvps"
            ).first

            if await rsvp_locator.count():

                rsvp_text = (
                    await rsvp_locator.inner_text()
                ).strip()

            parsed["rsvp_text"] = (
                rsvp_text
            )

            # --------------------------------------------------------------
            # IMAGE
            # --------------------------------------------------------------

            image_locator = event_li.locator(
                ".event-image"
            ).first

            if await image_locator.count():

                image_url = (
                    await image_locator.get_attribute(
                        "src"
                    )
                )

                data_src = (
                    await image_locator.get_attribute(
                        "data-src"
                    )
                )

                parsed["event_image"] = (
                    image_url
                    or data_src
                )

                parsed["event_image_alt"] = (
                    await image_locator.get_attribute(
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
                f"Upcoming #{index + 1}: "
                f"{parsed.get('event_type')} | "
                f"{parsed.get('songkick_id')} | "
                f"{parsed.get('name')}"
            )

        # --------------------------------------------------------------
        # DEDUP
        # --------------------------------------------------------------

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
                    event.get("url")
                    or event.get("name")
                )

                if key:

                    unique[key] = event

        events = list(
            unique.values()
        )

        print(
            f"\nUpcoming únicos: "
            f"{len(events)}"
        )

        return events

    # ======================================================================
    # GIGOGRAPHY - EVENTOS
    # ======================================================================

    async def extract_gigography_events(
        self,
        page,
        page_url: str,
    ):
        """
        Estrutura real da Songkick:

        <ul class="event-listings artist-focus">

            <li class="with-date">
                separador de data
            </li>

            <li title="...">
                EVENTO
            </li>

        Portanto:

            ul.event-listings.artist-focus > li[title]

        é o seletor dos eventos reais.
        """

        selector = (
            "ul.event-listings.artist-focus "
            "> li[title]"
        )

        event_items = page.locator(
            selector
        )

        total_items = (
            await event_items.count()
        )

        print(
            f"Eventos reais encontrados na gigography: "
            f"{total_items}"
        )

        date_headers = page.locator(
            "ul.event-listings.artist-focus "
            "> li.with-date"
        )

        print(
            f"Separadores de data ignorados: "
            f"{await date_headers.count()}"
        )

        events = []

        for index in range(
            total_items
        ):

            event_li = event_items.nth(
                index
            )

            # ----------------------------------------------------------
            # LINK
            # ----------------------------------------------------------

            event_link = event_li.locator(
                "a[href]"
            ).filter(
                has=event_li.locator(
                    "strong"
                )
            ).first

            if await event_link.count() == 0:

                event_link = event_li.locator(
                    "p.artists.summary a"
                ).first

            if await event_link.count() == 0:

                event_link = event_li.locator(
                    'a[href*="/concerts/"], '
                    'a[href*="/festivals/"]'
                ).first

            if await event_link.count() == 0:

                print(
                    f"[GIGOGRAPHY EVENT #{index + 1}] "
                    "Sem link de evento."
                )

                continue

            href = await event_link.get_attribute(
                "href"
            )

            if not href:
                continue

            event_url = urljoin(
                SONGKICK_BASE_URL,
                href,
            )

            reference = (
                self.extract_event_reference(
                    event_url
                )
            )

            # ----------------------------------------------------------
            # JSON-LD
            # ----------------------------------------------------------

            json_ld_events = (
                await self.extract_json_ld_events_from_li(
                    event_li
                )
            )

            if json_ld_events:

                parsed = self.parse_event(
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

            # ----------------------------------------------------------
            # DATA
            # ----------------------------------------------------------

            time_locator = event_li.locator(
                "time"
            ).first

            if await time_locator.count():

                dom_start_date = (
                    await time_locator.get_attribute(
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

            # ----------------------------------------------------------
            # ARTISTA
            # ----------------------------------------------------------

            artist_locator = event_li.locator(
                "p.artists.summary"
            ).first

            artist_text = None

            if await artist_locator.count():

                artist_text = (
                    await artist_locator.inner_text()
                ).strip()

            # ----------------------------------------------------------
            # VENUE
            # ----------------------------------------------------------

            venue_locator = event_li.locator(
                ".venue-name"
            ).first

            venue_name = None
            venue_url = None

            if await venue_locator.count():

                venue_name = (
                    await venue_locator.inner_text()
                ).strip()

                venue_link = venue_locator.locator(
                    "a"
                ).first

                if await venue_link.count():

                    venue_url = (
                        await venue_link.get_attribute(
                            "href"
                        )
                    )

                    if venue_url:

                        venue_url = urljoin(
                            SONGKICK_BASE_URL,
                            venue_url,
                        )

            # ----------------------------------------------------------
            # LOCAL
            # ----------------------------------------------------------

            location_locator = event_li.locator(
                "p.location"
            ).first

            city_region_country = None
            street_address = None

            if await location_locator.count():

                location_text = (
                    await location_locator.inner_text()
                ).strip()

                location_text = re.sub(
                    r"\s+",
                    " ",
                    location_text,
                )

                city_region_country = (
                    location_text
                )

                street_locator = location_locator.locator(
                    ".street-address"
                ).first

                if await street_locator.count():

                    street_address = (
                        await street_locator.inner_text()
                    ).strip()

            # ----------------------------------------------------------
            # COMPLETA VENUE
            # ----------------------------------------------------------

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

            # ----------------------------------------------------------
            # FESTIVAL
            # ----------------------------------------------------------

            is_festival = (
                reference["event_type"]
                == "festival"
            )

            if is_festival:

                festival_name = (
                    parsed.get("name")
                    or artist_text
                )

                parsed["event_type"] = (
                    "festival"
                )

                parsed["is_festival"] = True

                parsed["festival"] = {
                    "id": (
                        reference["event_id"]
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

            # ----------------------------------------------------------
            # NOME
            # ----------------------------------------------------------

            if not parsed.get(
                "name"
            ):

                parsed["name"] = (
                    artist_text
                    or venue_name
                )

            # ----------------------------------------------------------
            # SOURCE
            # ----------------------------------------------------------

            parsed["source"] = (
                "songkick_gigography"
            )

            parsed["primary_detail"] = (
                city_region_country
            )

            parsed["secondary_detail"] = (
                venue_name
            )

            # ----------------------------------------------------------
            # DEBUG
            # ----------------------------------------------------------

            print(
                f"Event #{index + 1}: "
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

    # ======================================================================
    # PRÓXIMA PÁGINA DA GIGOGRAPHY
    # ======================================================================

    async def get_next_gigography_url(
        self,
        page,
    ):
        """
        Usa a paginação REAL do Songkick.
        """

        next_link = page.locator(
            'div.pagination '
            'a.next_page[rel="next"]'
        ).first

        if await next_link.count() == 0:

            next_link = page.locator(
                "div.pagination "
                "a.next_page"
            ).first

        if await next_link.count() == 0:

            return None

        class_name = (
            await next_link.get_attribute(
                "class"
            )
            or ""
        )

        if "disabled" in class_name.split():

            return None

        href = await next_link.get_attribute(
            "href"
        )

        if not href:

            return None

        return urljoin(
            SONGKICK_BASE_URL,
            href,
        )

    # ======================================================================
    # GIGOGRAPHY PAGINADA
    # ======================================================================

    async def scrape_gigography(
        self,
        page,
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
            f"{artist_id}-{artist_slug}"
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
                + (
                    "?"
                    + urlparse(
                        current_url
                    ).query
                    if urlparse(
                        current_url
                    ).query
                    else ""
                )
            )

            if normalized_url in visited_urls:

                print(
                    "\nURL já visitada. "
                    "Interrompendo para evitar loop."
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
                f"Requested URL: "
                f"{current_url}"
            )

            try:

                response = await page.goto(
                    current_url,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )

            except Exception as exc:

                print(
                    f"Erro navegando para página "
                    f"{page_number}: {exc}"
                )

                break

            final_url = page.url

            print(
                f"Final URL: "
                f"{final_url}"
            )

            if response:

                print(
                    f"Status: "
                    f"{response.status}"
                )

            # --------------------------------------------------------------
            # REDIRECT PARA ARTISTA
            # --------------------------------------------------------------

            if self.is_artist_page(
                final_url,
                artist_id,
                artist_slug,
            ):

                print(
                    "\nSongkick redirecionou "
                    "para a página principal."
                )

                break

            # --------------------------------------------------------------
            # GARANTE GIGOGRAPHY
            # --------------------------------------------------------------

            if not self.is_gigography_page(
                final_url,
                artist_id,
                artist_slug,
            ):

                print(
                    "\nURL final não é "
                    "gigography."
                )

                break

            # --------------------------------------------------------------
            # SALVA RAW
            # --------------------------------------------------------------

            html = await page.content()

            raw_file = (
                GIGOGRAPHY_RAW_DIR
                / f"page_{page_number}.html"
            )

            raw_file.write_text(
                html,
                encoding="utf-8",
            )

            print(
                f"HTML salvo em: "
                f"{raw_file}"
            )

            # --------------------------------------------------------------
            # EXTRAI EVENTOS
            # --------------------------------------------------------------

            page_events = (
                await self.extract_gigography_events(
                    page,
                    final_url,
                )
            )

            print(
                f"\nEventos encontrados nesta página: "
                f"{len(page_events)}"
            )

            # --------------------------------------------------------------
            # DEDUPLICAÇÃO
            # --------------------------------------------------------------

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

                if key in events_by_id:

                    duplicate_events += 1

                    continue

                events_by_id[key] = (
                    event
                )

                new_events += 1

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

            pages_scraped += 1

            # --------------------------------------------------------------
            # PRÓXIMA PÁGINA
            # --------------------------------------------------------------

            next_url = (
                await self.get_next_gigography_url(
                    page
                )
            )

            if next_url:

                print(
                    f"\nPróxima página encontrada: "
                    f"{next_url}"
                )

            else:

                print(
                    "\nNenhuma próxima página encontrada."
                )

                print(
                    "Fim da gigography."
                )

            current_url = next_url

        # ==================================================================
        # FINAL
        # ==================================================================

        events = list(
            events_by_id.values()
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

        festival_count = sum(
            1
            for event in events
            if event.get(
                "event_type"
            ) == "festival"
        )

        print(
            f"Festivais encontrados: "
            f"{festival_count}"
        )

        return (
            events,
            pages_scraped,
        )

    # ======================================================================
    # MERGE
    # ======================================================================

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

            if (
                merged.get(key)
                is None
                or merged.get(key)
                == ""
                or merged.get(key)
                == []
                or merged.get(key)
                == {}
            ):

                merged[key] = value

        if new_event.get(
            "festival"
        ):

            merged["festival"] = (
                new_event[
                    "festival"
                ]
            )

        return merged

    # ======================================================================
    # CONSOLIDAÇÃO
    # ======================================================================

    @classmethod
    def consolidate_events(
        cls,
        upcoming_events,
        gigography_events,
    ):

        events_by_id = {}

        # --------------------------------------------------------------
        # UPCOMING
        # --------------------------------------------------------------

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

            events_by_id[key] = (
                event
            )

        # --------------------------------------------------------------
        # GIGOGRAPHY
        # --------------------------------------------------------------

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

    # ======================================================================
    # SCRAPER COMPLETO
    # ======================================================================

    async def search_artist(
        self,
        artist_name: str,
    ):

        print("=" * 80)
        print("SONGKICK SCRAPER")
        print("=" * 80)

        print(
            f"\nArtista pesquisado: "
            f"{artist_name}"
        )

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

        async with async_playwright() as playwright:

            browser = await playwright.chromium.launch(
                headless=self.headless
            )

            context = await browser.new_context(
                viewport={
                    "width": 1440,
                    "height": 900,
                },
                locale="en-US",
            )

            page = await context.new_page()

            try:

                # ==========================================================
                # 1. PESQUISA DO ARTISTA
                # ==========================================================

                print("\n")
                print("=" * 80)
                print("PESQUISA DO ARTISTA")
                print("=" * 80)

                search_url = (
                    f"{SONGKICK_BASE_URL}"
                    f"/api/universal_search"
                    f"?query={quote(artist_name)}"
                )

                print(
                    f"Search endpoint: "
                    f"{search_url}"
                )

                await page.goto(
                    SONGKICK_BASE_URL,
                    wait_until="domcontentloaded",
                    timeout=60_000,
                )

                response = await page.evaluate(
                    """
                    async (url) => {

                        const response = await fetch(
                            url,
                            {
                                method: "GET",
                                credentials: "include",
                                headers: {
                                    "Accept":
                                        "application/json"
                                }
                            }
                        );

                        return {
                            status: response.status,
                            body: await response.text()
                        };
                    }
                    """,
                    search_url,
                )

                print(
                    f"Search status: "
                    f"{response['status']}"
                )

                if response["status"] != 200:

                    raise Exception(
                        "Songkick universal_search "
                        f"retornou {response['status']}"
                    )

                raw_data = json.loads(
                    response["body"]
                )

                search_raw_file = (
                    RAW_DIR
                    / f"{artist_name.replace(' ', '_')}_search.json"
                )

                search_raw_file.write_text(
                    json.dumps(
                        raw_data,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                # ==========================================================
                # 2. ENCONTRA ARTISTA
                # ==========================================================

                attributes = (
                    raw_data
                    .get("data", {})
                    .get("attributes", {})
                )

                search_results = (
                    attributes
                    .get("search_results", {})
                )

                artists = (
                    search_results
                    .get("artists", [])
                )

                selected_artist = None

                for result in artists:

                    document = result.get(
                        "document",
                        {},
                    )

                    name = document.get(
                        "name",
                        "",
                    )

                    if (
                        name.lower()
                        == artist_name.lower()
                    ):

                        selected_artist = (
                            document
                        )

                        break

                if (
                    not selected_artist
                    and artists
                ):

                    selected_artist = (
                        artists[0]
                        .get(
                            "document",
                            {},
                        )
                    )

                if not selected_artist:

                    raise Exception(
                        f"Artista não encontrado: "
                        f"{artist_name}"
                    )

                artist_id = str(
                    selected_artist.get(
                        "primary_key_id"
                    )
                )

                songkick_artist_id = (
                    selected_artist.get(
                        "id"
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

                # ==========================================================
                # 3. URL DO ARTISTA
                # ==========================================================

                artist_url = (
                    f"{SONGKICK_BASE_URL}"
                    f"/artists/"
                    f"{artist_id}-{artist_slug}/"
                )

                # ==========================================================
                # 4. PÁGINA DO ARTISTA
                # ==========================================================

                artist_page_data = (
                    await self.scrape_artist_page(
                        page,
                        artist_url,
                        artist_id,
                        artist_slug,
                    )
                )

                # ==========================================================
                # INFORMAÇÕES FINAIS DO ARTISTA
                # ==========================================================

                artist_name_from_page = (
                    artist_page_data.get(
                        "name"
                    )
                    or selected_artist.get(
                        "name"
                    )
                    or artist_name
                )

                number_of_events = (
                    artist_page_data.get(
                        "number_of_events"
                    )
                )

                if number_of_events is None:

                    number_of_events = (
                        selected_artist.get(
                            "number_of_events"
                        )
                    )

                print("\nArtista:")

                print(
                    f"Nome: "
                    f"{artist_name_from_page}"
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
                    f"Eventos informados pelo Songkick: "
                    f"{number_of_events}"
                )

                # ==========================================================
                # 5. UPCOMING
                #
                # IMPORTANTE:
                #
                # scrape_artist_page() já abriu a página correta.
                # Portanto agora extract_upcoming_events() procura
                # #coming-up na página do artista.
                # ==========================================================

                upcoming_events = (
                    await self.extract_upcoming_events(
                        page,
                        artist_page_data.get(
                            "url"
                        )
                        or page.url,
                    )
                )

                # ==========================================================
                # 6. GIGOGRAPHY
                # ==========================================================

                (
                    gigography_events,
                    pages_scraped,
                ) = await self.scrape_gigography(
                    page,
                    artist_id,
                    artist_slug,
                )

                # ==========================================================
                # 7. CONSOLIDAÇÃO
                # ==========================================================

                print("\n")
                print("=" * 80)
                print("CONSOLIDAÇÃO")
                print("=" * 80)

                final_events = (
                    self.consolidate_events(
                        upcoming_events,
                        gigography_events,
                    )
                )

                # ==========================================================
                # 8. ORDENAÇÃO
                # ==========================================================

                final_events.sort(
                    key=lambda event: (
                        event.get(
                            "start_date"
                        )
                        or ""
                    ),
                    reverse=True,
                )

                # ==========================================================
                # 9. CONTADORES
                # ==========================================================

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

                # ==========================================================
                # 10. ARTISTA FINAL
                # ==========================================================

                artist_result = {
                    "id": (
                        songkick_artist_id
                        or f"Artist{artist_id}"
                    ),

                    "primary_key_id": int(
                        artist_id
                    ),

                    "songkick_id": (
                        str(artist_id)
                    ),

                    "name": (
                        artist_name_from_page
                    ),

                    "name_exact": (
                        artist_page_data.get(
                            "name_exact"
                        )
                        or artist_name_from_page
                    ),

                    "display_name": (
                        artist_page_data.get(
                            "display_name"
                        )
                        or artist_name_from_page
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

                    "official_image_source": (
                        "spotify"
                    ),
                }

                # ==========================================================
                # 11. RESULTADO
                # ==========================================================

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

                # ==========================================================
                # 12. SALVA
                # ==========================================================

                safe_name = "".join(
                    char
                    if char.isalnum()
                    else "_"
                    for char in artist_name
                )

                parsed_file = (
                    OUTPUT_DIR
                    / f"{safe_name}_parsed.json"
                )

                parsed_file.write_text(
                    json.dumps(
                        result,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                # ==========================================================
                # 13. RESUMO
                # ==========================================================

                print("\n")
                print("=" * 80)
                print("RESUMO FINAL")
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
                    f"\nUpcoming: "
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

                print("\n" + "=" * 80)
                print(
                    "SCRAPER FINALIZADO"
                )
                print("=" * 80)

                return result

            finally:

                print(
                    "\nFechando navegador..."
                )

                await browser.close()


# ==========================================================================
# RUN
# ==========================================================================

async def run(
    artist_name: str,
    headless: bool = False,
):

    scraper = SongkickScraper(
        headless=headless
    )

    return await scraper.search_artist(
        artist_name
    )


# ==========================================================================
# CLI
# ==========================================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Songkick scraper com "
            "informações do artista + "
            "upcoming + gigography paginada."
        )
    )

    parser.add_argument(
        "artist",
        nargs="?",
        default="Demi Lovato",
        help="Nome do artista.",
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help=(
            "Executa o navegador "
            "sem interface."
        ),
    )

    args = parser.parse_args()

    asyncio.run(
        run(
            args.artist,
            args.headless,
        )
    )


if __name__ == "__main__":
    main()