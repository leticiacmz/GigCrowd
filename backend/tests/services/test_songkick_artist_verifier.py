"""A Songkick identifier has to be checked before it becomes an artist.

Every rule here exists because of a way the check can be skipped and the
catalogue permanently wrong. A number off a festival page is not an identity;
Songkick redirects a decorative slug to the canonical artist; a 404 is not "not
found in a search result"; and a transport failure is not a verdict.

The tests drive a stub client, so they assert the rules rather than Songkick's
current behaviour - which is the right dependency for a rule that must not
regress even if the site changes shape.
"""
from __future__ import annotations

import pytest

from app.domain.artist_page_statement import artist_page_statement
from app.providers.songkick.client import SongkickNotFound
from app.services.songkick_artist_verifier import (
    ACCEPTED,
    REJECTED_NO_PAGE,
    REJECTED_NOT_AN_ARTIST_PAGE,
    REJECTED_NOT_AN_ID,
    REJECTED_UNREADABLE,
    REJECTED_WRONG_ARTIST,
    SongkickArtistVerifier,
)


ARTIST_PAGE = """
<html><body>
  <h1>Tim Bernardes</h1>
  <script type="application/ld+json">
  {
    "@type": "MusicGroup",
    "name": "Tim Bernardes",
    "url": "https://www.songkick.com/artists/2668421-tim-bernardes",
    "image": "https://images.sk-static.com/images/media/profile_images/artists/2668421/card_avatar"
  }
  </script>
</body></html>
"""

# The shape Songkick actually serves for some artists, checked against the live
# site for The Coronas (11215) and The Stranglers (115227).
#
# No `<h1>` anywhere. The name appears in the structured data and in the document
# title, and nowhere else. A reader that requires a heading refuses two real,
# touring, festival-announced artists and reports nothing wrong while doing it.
NO_HEADING_ARTIST_PAGE = """
<html><head>
  <title>The Coronas Tickets, Tour Dates &amp; Concerts 2027 &amp; 2026
    &ndash; Songkick</title>
  <meta property="og:title" content="The Coronas">
  <meta property="og:url"
        content="https://www.songkick.com/artists/11215-coronas">
</head><body>
  <h2>Stats</h2>
  <h2>Related artists</h2>
  <script type="application/ld+json">
  [
    {
      "@type": "MusicEvent",
      "name": "The Coronas @ 3Olympia Theatre",
      "url": "https://www.songkick.com/concerts/43406464-coronas",
      "image": "https://images.sk-static.com/images/media/profile_images/artists/11215/huge_avatar"
    },
    {
      "@type": "MusicGroup",
      "name": "The Coronas",
      "url": "https://www.songkick.com/artists/11215-coronas",
      "image": "https://images.sk-static.com/images/media/profile_images/artists/11215/card_avatar"
    },
    {
      "@type": "MusicGroup",
      "name": "Bell X1",
      "url": "https://www.songkick.com/artists/29611-bell-x1",
      "image": "https://images.sk-static.com/images/media/profile_images/artists/29611/card_avatar"
    }
  ]
  </script>
</body></html>
"""


class StubClient:
    """A Songkick client that answers from a table of pages."""

    def __init__(self, pages=None, raises=None):
        self.pages = pages or {}
        self.raises = raises
        self.requested = []

    async def get_artist_page(self, url):
        self.requested.append(url)

        if self.raises is not None:
            raise self.raises

        for fragment, response in self.pages.items():
            if fragment in url:
                return response

        raise SongkickNotFound(f"no page at {url}")


def a_page(final_url="https://www.songkick.com/artists/2668421-tim-bernardes"):
    return {
        "url": final_url,
        "final_url": final_url,
        "status": 200,
        "html": ARTIST_PAGE,
        "upcoming_events": [],
        "upcoming_festivals": [],
    }


def a_verifier(client):
    return SongkickArtistVerifier(client=client)


class TestARealArtistIsAccepted:
    @pytest.mark.asyncio
    async def test_a_matching_page_verifies(self):
        verifier = a_verifier(
            StubClient({"2668421": a_page()})
        )

        result = await verifier.verify("2668421", name="Tim Bernardes")

        assert result.valid is True
        assert result.reason == ACCEPTED
        assert result.songkick_id == "2668421"
        assert result.canonical_name == "Tim Bernardes"

    @pytest.mark.asyncio
    async def test_the_prefixed_id_form_is_the_same_artist(self):
        """Artists store `Artist2668421`; a lineup entry carries `2668421`.

        Both forms name one artist, and treating them as different would create
        a second record for someone already in the catalogue.
        """

        verifier = a_verifier(
            StubClient({"2668421": a_page()})
        )

        result = await verifier.verify(
            "Artist2668421", name="Tim Bernardes"
        )

        assert result.valid is True
        assert result.songkick_id == "2668421"

    @pytest.mark.asyncio
    async def test_the_canonical_name_and_image_come_from_the_page(self):
        """The artist's own page is the authority.

        Storing the poster's spelling and the poster's thumbnail instead means
        two records for one act whenever the two disagree.
        """

        verifier = a_verifier(
            StubClient({"2668421": a_page()})
        )

        result = await verifier.verify(
            "2668421", name="tim bernardes"
        )

        assert result.canonical_name == "Tim Bernardes"
        assert result.image is not None

    @pytest.mark.asyncio
    async def test_an_artist_page_without_a_heading_is_still_an_artist(self):
        """The bug this rule was written to prevent, restated as a test.

        Songkick serves some artist pages with no `<h1>` at all - The Coronas and
        The Stranglers, verified live. A verifier that treats the heading as the
        definition of an artist page rejects them, and because a rejection
        destroys nothing rather than corrupting anything, nothing downstream
        reveals that two real touring acts were written off as not real.

        So the sources are tried strongest-first and none of them is mandatory.
        """

        verifier = a_verifier(
            StubClient(
                {
                    "11215": {
                        "url": (
                            "https://www.songkick.com/artists/11215-coronas"
                        ),
                        "final_url": (
                            "https://www.songkick.com/artists/11215-coronas"
                        ),
                        "status": 200,
                        "html": NO_HEADING_ARTIST_PAGE,
                        "upcoming_events": [],
                        "upcoming_festivals": [],
                    }
                }
            )
        )

        result = await verifier.verify("11215", name="The Coronas")

        assert result.valid is True
        assert result.reason == ACCEPTED
        assert result.canonical_name == "The Coronas"
        assert result.name_agrees is True

    @pytest.mark.asyncio
    async def test_the_name_comes_from_the_block_naming_this_artist(self):
        """Not the first artist block on the page.

        The block for a *related* artist appears on the same document, sometimes
        before the one for the subject. Reading by document order would report a
        fact about the document, and would return the name of an act that has
        nothing to do with the one being looked up.

        The related artist is deliberately placed first here, so a reader that
        walks the blocks in order answers with the wrong act.
        """

        page = """
        <html><body>
          <script type="application/ld+json">
          [
            {
              "@type": "MusicGroup",
              "name": "Bell X1",
              "url": "https://www.songkick.com/artists/29611-bell-x1"
            },
            {
              "@type": "MusicGroup",
              "name": "The Coronas",
              "url": "https://www.songkick.com/artists/11215-coronas"
            }
          ]
          </script>
        </body></html>
        """

        statement = artist_page_statement(page, "11215")

        assert statement.name == "The Coronas"
        assert statement.source == "structured_data"

    def test_an_artist_block_for_somebody_else_is_not_the_name(self):
        """Asked about 11215, a page that only describes other acts says nothing.

        This is what a related-artists strip looks like if it is the only artist
        data on the page, and answering with any of those names would attach one
        act's identity to another's id.
        """

        page = """
        <html><body>
          <script type="application/ld+json">
          [
            {
              "@type": "MusicGroup",
              "name": "Bell X1",
              "url": "https://www.songkick.com/artists/29611-bell-x1"
            },
            {
              "@type": "MusicGroup",
              "name": "Hothouse Flowers",
              "url": "https://www.songkick.com/artists/29612-hothouse-flowers"
            }
          ]
          </script>
        </body></html>
        """

        statement = artist_page_statement(page, "11215")

        assert statement.name is None

    def test_the_social_card_is_used_when_the_data_is_missing(self):
        """`og:title`, but only alongside an `og:url` naming this artist.

        On its own `og:title` is just a string near the top of the document. It
        becomes identity evidence because the URL beside it says which page the
        string is describing.
        """

        page = (
            "<html><head>"
            "<meta property='og:title' content='The Coronas'>"
            "<meta property='og:url' content="
            "'https://www.songkick.com/artists/11215-coronas'>"
            "</head><body></body></html>"
        )

        statement = artist_page_statement(page, "11215")

        assert statement.name == "The Coronas"
        assert statement.names_this_artist is True
        assert statement.source == "og_title"

    def test_a_social_card_about_another_artist_is_not_used(self):
        page = (
            "<html><head>"
            "<meta property='og:title' content='Bell X1'>"
            "<meta property='og:url' content="
            "'https://www.songkick.com/artists/29611-bell-x1'>"
            "</head><body></body></html>"
        )

        statement = artist_page_statement(page, "11215")

        # The URL says this is Bell X1's page. Reading their name off it while
        # checking artist 11215 would be the exact mistake being guarded against.
        assert statement.name != "Bell X1"

    def test_the_document_title_is_the_last_resort(self):
        """Songkick's decoration is stripped; the artist's name is what is left."""

        statement = artist_page_statement(
            "<html><head><title>The Coronas Tickets, Tour Dates &amp; "
            "Concerts 2027 &amp; 2026 &ndash; Songkick</title></head>"
            "<body></body></html>",
            "11215",
        )

        assert statement.name == "The Coronas"

        # And it is reported as weaker evidence, because the title does not say
        # the page is about this id.
        assert statement.names_this_artist is False
        assert statement.source == "document_title"

    def test_a_title_that_is_only_decoration_yields_no_name(self):
        statement = artist_page_statement(
            "<html><head><title>Songkick</title></head>"
            "<body></body></html>",
            "11215",
        )

        assert statement.name is None
        assert bool(statement) is False

    def test_a_page_with_nothing_to_say_yields_no_name(self):
        for html in ("", "   ", "<html><body><p>A venue</p></body></html>"):
            statement = artist_page_statement(html, "11215")

            assert statement.name is None
            assert statement.names_this_artist is False


class TestAnIdentityThatIsNotAnArtistIsRefused:
    @pytest.mark.asyncio
    async def test_a_spotify_id_is_refused_without_a_request(self):
        """The two id spaces are unrelated.

        A Spotify artist id is 22 base62 characters and a Songkick artist id is
        numeric. Reading one as the other addresses a different artist entirely,
        so it is refused before anything is fetched.
        """

        client = StubClient()
        verifier = a_verifier(client)

        result = await verifier.verify("0cHZbUIBIOaZJX0zvNb8Nj")

        assert result.valid is False
        assert result.reason == REJECTED_NOT_AN_ID
        assert client.requested == []

    @pytest.mark.asyncio
    async def test_a_malformed_id_is_refused_without_a_request(self):
        client = StubClient()
        verifier = a_verifier(client)

        for candidate in ("", "   ", None, "not-an-id", "../../etc/passwd"):
            result = await verifier.verify(candidate)

            assert result.valid is False
            assert result.reason == REJECTED_NOT_AN_ID

        assert client.requested == []

    @pytest.mark.asyncio
    async def test_a_festival_series_id_is_refused(self):
        """A series id is a number and an edition id is a number.

        Neither names an artist, and both would otherwise be read as one.
        """

        verifier = a_verifier(StubClient({"44001": a_page()}))

        result = await verifier.verify("44001", name="Villa Sound")

        # Numeric, so it passes the shape check, and then the page check decides.
        assert result.valid is False

    @pytest.mark.asyncio
    async def test_an_id_with_no_page_is_refused(self):
        """A 404 means the identity does not exist.

        It does not mean "not in the search results", and the two are
        opposites - conflating them is how an invented identity gets written.
        """

        verifier = a_verifier(StubClient())

        result = await verifier.verify("9999999", name="A Ghost")

        assert result.valid is False
        assert result.reason == REJECTED_NO_PAGE

    @pytest.mark.asyncio
    async def test_a_page_serving_a_different_artist_is_refused(self):
        """The failure this module exists to catch.

        Songkick reassigns ids, so a stored id can come to address somebody else
        entirely. Accepting it would give one act's name a link to another act's
        page, and nothing in the stored document would record that the identity
        was ever checked.

        Note the shape of the rejection: it is the *id* in the served URL that
        disagrees. Songkick routinely rewrites the slug while keeping the id -
        that is a redirect to the same artist and is accepted - so comparing
        slugs would reject every renamed act and let through every merged one.
        """

        verifier = a_verifier(
            StubClient(
                {
                    "10074848": a_page(
                        final_url=(
                            "https://www.songkick.com/artists/"
                            "5550001-somebody-else"
                        )
                    )
                }
            )
        )

        result = await verifier.verify("10074848", name="100 gecs")

        assert result.valid is False
        assert result.reason == REJECTED_WRONG_ARTIST

    @pytest.mark.asyncio
    async def test_a_rewritten_slug_is_still_the_same_artist(self):
        """The other side of the same rule.

        Songkick redirects a decorative slug to the canonical one, so the served
        URL routinely carries a different slug and the same id. Refusing that
        would reject every artist whose name has changed.
        """

        verifier = a_verifier(
            StubClient(
                {
                    "2668421": a_page(
                        final_url=(
                            "https://www.songkick.com/artists/"
                            "2668421-tim-bernardes-oficial"
                        )
                    )
                }
            )
        )

        result = await verifier.verify("2668421", name="Tim Bernardes")

        assert result.valid is True
        assert result.songkick_id == "2668421"

    @pytest.mark.asyncio
    async def test_a_page_that_is_not_an_artist_profile_is_refused(self):
        """Artist-shaped URL, wrong kind of page.

        A venue or festival page carries a numeric id too, and answering "200"
        to "is this an artist" would accept it.
        """

        verifier = a_verifier(
            StubClient(
                {
                    "9001": {
                        "url": "https://www.songkick.com/venues/9001-x",
                        "final_url": (
                            "https://www.songkick.com/artists/9001-x"
                        ),
                        "status": 200,
                        "html": "<html><body><p>A venue</p></body></html>",
                        "upcoming_events": [],
                        "upcoming_festivals": [],
                    }
                }
            )
        )

        result = await verifier.verify("9001", name="The Crocodile")

        assert result.valid is False
        assert result.reason == REJECTED_NOT_AN_ARTIST_PAGE

    @pytest.mark.asyncio
    async def test_a_transport_failure_is_not_a_verdict(self):
        """A timeout says nothing about the identity.

        Reported as unreadable so a caller can retry it, rather than as a
        rejection that would permanently skip a real artist.
        """

        verifier = a_verifier(
            StubClient(raises=RuntimeError("connection reset"))
        )

        result = await verifier.verify("2668421", name="Tim Bernardes")

        assert result.valid is False
        assert result.reason == REJECTED_UNREADABLE
        assert result.songkick_id == "2668421"


class TestNamesDoNotDecideIdentity:
    @pytest.mark.asyncio
    async def test_a_different_spelling_is_not_a_rejection(self):
        """Songkick's own page is the authority on the name.

        A poster's rendering and the artist's page disagreeing is normal - case,
        accents, a suffix - and storing the wrong one is a small bug, not a
        reason to refuse a real artist. So it is accepted and the canonical
        spelling is returned.
        """

        verifier = a_verifier(
            StubClient({"2668421": a_page()})
        )

        result = await verifier.verify(
            "2668421", name="Tim Bernardes (DJ Set)"
        )

        assert result.valid is True
        assert result.canonical_name == "Tim Bernardes"
        assert result.name_agrees is False

    @pytest.mark.asyncio
    async def test_an_exact_spelling_is_reported_as_agreeing(self):
        verifier = a_verifier(
            StubClient({"2668421": a_page()})
        )

        result = await verifier.verify(
            "2668421", name="Tim Bernardes"
        )

        assert result.name_agrees is True


class TestNonLatinNamesStayAddressable:
    @pytest.mark.asyncio
    async def test_a_name_that_slugifies_to_nothing_still_verifies(self):
        """The identity is the id, not the spelling of the name.

        `generate_slug` reduces a name to ASCII, so a name in a non-Latin script
        produces nothing. That is a routing problem and is solved by falling back
        to the trusted id - it is not a reason to refuse the artist.
        """

        verifier = a_verifier(
            StubClient(
                {
                    "130997": {
                        "url": "https://www.songkick.com/artists/130997",
                        "final_url": (
                            "https://www.songkick.com/artists/130997"
                        ),
                        "status": 200,
                        "html": "<html><body><h1>レミオロメン</h1></body></html>",
                        "upcoming_events": [],
                        "upcoming_festivals": [],
                    }
                }
            )
        )

        result = await verifier.verify("130997", name="レミオロメン")

        assert result.valid is True
        assert result.canonical_name == "レミオロメン"

    @pytest.mark.asyncio
    async def test_the_slug_fallback_is_still_the_trusted_id(self):
        """Kept from the earlier fix, and still correct.

        `artist-130997` is as true as `tim-bernardes` would be, and unlike a
        transliteration guess it cannot be wrong.
        """

        from app.repositories.artist_repository import ArtistRepository
        from app.utils.slug import generate_slug
        from tests.support.fake_mongo import FakeDatabase

        database = FakeDatabase({"artists": []})

        repository = ArtistRepository(database)

        assert generate_slug("レミオロメン") == ""

        slug = await repository._slug_for(
            "レミオロメン", "Artist130997"
        )

        assert slug
        assert not slug.startswith("-")
        assert "130997" in slug


class TestTheVerifierCannotImportAnything:
    def test_it_holds_no_import_path(self):
        """Validation reads one artist page and writes nothing.

        The importer would be a way to fetch a gigography, and a gigography fetch
        here would rebuild the old bug where looking at a festival page cost one
        scrape per name on the bill.
        """

        import inspect

        parameters = inspect.signature(
            SongkickArtistVerifier.__init__
        ).parameters

        for name in (
            "event_import_service",
            "synchronization_service",
            "event_repository",
            "artist_repository",
            "venue_repository",
        ):
            assert name not in parameters
