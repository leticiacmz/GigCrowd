"""Is this Songkick identifier really an artist, and can we prove it?

A festival lineup is a list of names and links, and a link is not an identity. A
lineup entry can carry an id that resolves, and still not mean what the name
beside it says: Songkick reassigns ids, a venue page and an artist page share a
numeric shape, and a parser that reads an id off whatever page it was handed
will happily hand back a number that addresses something else entirely.

Creating an `Artist` from such an id is not a small mistake. The catalogue is
permanent, the record is linkable from every festival that announced the name,
and nothing in the stored document records that the identity was never checked.
So the check happens *before* the write, and a failure is a refusal rather than a
best effort.

What is verified, and why each step matters:

1. The candidate is recognisably a Songkick artist id at all. A Spotify id, a
   slug, a festival series number or arbitrary text is refused here, before any
   request is made.
2. The concrete artist page is fetched. A 404 or 410 means the identity does not
   exist, which is not the same as "not found in a search result" and must not
   be retried as one.
3. The page that was *served* carries the same id as the one requested. Songkick
   redirects a decorative slug to the canonical artist, so a wrong slug is fine -
   but a redirect to a *different* artist means the id does not name what was
   asked for, and that is the exact failure this module exists to catch.
4. The page states a name for the artist it is about. Every source the page
   publishes is consulted, strongest first - its heading, the structured block
   that names this id, its social card, its document title - because Songkick
   does not render every artist page the same way. See
   `app/domain/artist_page_statement.py`.
5. The name the page states is taken as canonical. The lineup's spelling is a
   poster's rendering of a name; the artist page is the artist's own.

Only after all five does a caller have a trustworthy identity. The verifier
never writes anything - it returns a verdict and the facts that justify it, so
the decision is recorded wherever the caller chooses to record it.

A note on what this costs when it is wrong
------------------------------------------

The obvious way to fail is to accept a number that addresses somebody else, and
the steps above are largely about preventing that. The quieter failure is
refusing a real artist, and it deserves more attention than it usually gets,
because it destroys nothing: two touring acts announced on a festival poster,
checked against the live site, were rejected as "not an artist profile" purely
because their pages carry no `<h1>`. Nothing downstream looked wrong. The artists
had simply stopped existing.

That is why step 4 is a *search* for the artist rather than a demand for one
particular element, and why the sources are tried strongest-first with none of
them mandatory. A rule that has only ever been seen rejecting obvious rubbish
has not been tested - it might also be rejecting the truth.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.logger import get_logger
from app.domain.artist_page_statement import artist_page_statement
from app.domain.songkick_identity import (
    artist_id_from_url,
    normalize_songkick_artist_id,
)
from app.providers.songkick.client import SongkickClient, SongkickNotFound

logger = get_logger("songkick_artist_verifier")


# Why an identity was refused. Kept as named values rather than prose so a caller
# can count them, and so a test can assert on the reason instead of on a message.
REJECTED_NOT_AN_ID = "not_a_songkick_artist_id"
REJECTED_NO_PAGE = "no_artist_page"
REJECTED_WRONG_ARTIST = "page_served_a_different_artist"
REJECTED_NOT_AN_ARTIST_PAGE = "page_is_not_an_artist_profile"
REJECTED_UNREADABLE = "page_could_not_be_read"

ACCEPTED = "verified"


def _normalized_name(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


@dataclass
class VerifiedArtist:
    """The verdict, and the facts that justify it.

    `valid` is the only field a caller must check. The rest exist so a refusal
    can be explained instead of merely counted, and so a caller that *does* trust
    the identity gets the canonical name and photograph rather than the lineup's
    rendering of them.
    """

    valid: bool = False
    reason: str = REJECTED_NOT_AN_ID

    songkick_id: Optional[str] = None
    canonical_name: Optional[str] = None
    slug: Optional[str] = None
    image: Optional[str] = None

    #: The name the caller supplied, kept so a mismatch can be reported. A
    #: different spelling is not a rejection - Songkick's own page is the
    #: authority on the name - but a wholly different act is worth reporting.
    requested_name: Optional[str] = None
    name_agrees: Optional[bool] = None
    served_url: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reason": self.reason,
            "songkick_id": self.songkick_id,
            "canonical_name": self.canonical_name,
            "slug": self.slug,
            "image": self.image,
            "requested_name": self.requested_name,
            "name_agrees": self.name_agrees,
            "served_url": self.served_url,
        }


@dataclass
class SongkickArtistVerifier:
    """Checks a candidate Songkick artist id against the artist's own page.

    Holds a client so a caller validating a whole lineup pays for one instance,
    and caches nothing: an identity that was valid five minutes ago is re-checked
    rather than remembered, because a cache would turn "we checked this once"
    into "we believe this forever", which is the property being fixed.
    """

    client: Optional[SongkickClient] = None

    request_delay_seconds: float = 0

    _client: SongkickClient = field(init=False, repr=False, default=None)

    def __post_init__(self):
        self._client = self.client or SongkickClient()

    async def verify(
        self,
        songkick_id: Any,
        *,
        name: Optional[str] = None,
    ) -> VerifiedArtist:
        """Check one identity. Never raises; a failure is a verdict."""

        requested = str(name).strip() if name else None

        # 1. Recognisably a Songkick artist id. A Spotify id must never be read
        # as one: the shapes differ, and borrowing across the two id spaces
        # silently addresses a different artist entirely.
        trusted = normalize_songkick_artist_id(songkick_id)

        if not trusted:
            return VerifiedArtist(
                valid=False,
                reason=REJECTED_NOT_AN_ID,
                requested_name=requested,
            )

        slug_part = re.sub(
            r"[^a-z0-9]+", "-", (requested or "").lower()
        ).strip("-")

        url = (
            "https://www.songkick.com/artists/"
            f"{trusted}-{slug_part}"
        )

        # 2. The concrete page. A 404/410 means the id names nothing.
        try:
            page = await self._client.get_artist_page(url)

        except SongkickNotFound:
            return VerifiedArtist(
                valid=False,
                reason=REJECTED_NO_PAGE,
                songkick_id=trusted,
                requested_name=requested,
                served_url=url,
            )

        except Exception as exc:
            # A transport failure is not evidence about the identity. It is
            # reported as unreadable so a caller can retry it rather than
            # treating a timeout as a verdict.
            logger.warning(
                f"[VERIFY] could not read {url}: {exc}"
            )

            return VerifiedArtist(
                valid=False,
                reason=REJECTED_UNREADABLE,
                songkick_id=trusted,
                requested_name=requested,
                served_url=url,
            )

        served_url = str(page.get("final_url") or url)

        # 3. The artist actually served must be the artist asked for.
        served_id = artist_id_from_url(served_url)

        if served_id != trusted:
            logger.info(
                f"[VERIFY] {trusted} served {served_id} instead; "
                f"refusing the identity"
            )

            return VerifiedArtist(
                valid=False,
                reason=REJECTED_WRONG_ARTIST,
                songkick_id=trusted,
                requested_name=requested,
                served_url=served_url,
            )

        html = page.get("html") or ""

        # 4 and 5. An artist profile, and the name it states.
        #
        # Note what is *not* required here. Songkick does not render every artist
        # page the same way, and a page with no `<h1>` is not a page about
        # something other than the artist - The Coronas and The Stranglers were
        # both served as real artist pages carrying no heading at all, and a
        # reader that treated the heading as mandatory refused two touring
        # artists as not real. The reader consults every source the site
        # publishes and accepts a name from any of them.
        statement = artist_page_statement(html, trusted)

        if not statement.name:
            return VerifiedArtist(
                valid=False,
                reason=REJECTED_NOT_AN_ARTIST_PAGE,
                songkick_id=trusted,
                requested_name=requested,
                served_url=served_url,
            )

        canonical = statement.name

        if not statement.names_this_artist:
            logger.info(
                f"[VERIFY] {trusted} stated {canonical!r} only in its "
                f"document title; accepting on that basis"
            )

        agrees = (
            None
            if not requested
            else _normalized_name(canonical)
            == _normalized_name(requested)
        )

        from app.domain.songkick_identity import slug_from_artist_url

        return VerifiedArtist(
            valid=True,
            reason=ACCEPTED,
            songkick_id=trusted,
            canonical_name=canonical,
            slug=slug_from_artist_url(served_url) or slug_part or None,
            image=self._artist_image(html, trusted),
            requested_name=requested,
            name_agrees=agrees,
            served_url=served_url,
        )

    # ============================================================
    # READING THE PAGE
    # ============================================================

    @staticmethod
    def _artist_image(
        html: str,
        artist_id: str,
    ) -> Optional[str]:
        """The photograph the page states for this artist, if it states one.

        Delegates to the shared resolver rather than re-reading the markup. That
        resolver already matches the structured block by the artist id inside
        its own URL, which is what keeps a page describing several entities from
        contributing the wrong picture.
        """

        if not html:
            return None

        import json

        from bs4 import BeautifulSoup

        from app.domain.artist_image import artist_image_from_jsonld

        soup = BeautifulSoup(html, "html.parser")

        blocks = []

        for tag in soup.find_all(
            "script", attrs={"type": "application/ld+json"}
        ):
            try:
                blocks.append(json.loads(tag.string or ""))
            except (TypeError, ValueError):
                continue

        return artist_image_from_jsonld(
            blocks,
            artist_id=artist_id,
        )
