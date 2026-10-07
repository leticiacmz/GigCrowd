"""A deterministic local dataset for developing and testing the product.

    # Show the plan. Writes nothing.
    python -m app.scripts.seed_dev_data

    # Write it.
    python -m app.scripts.seed_dev_data --apply

Three properties make it usable as a fixture rather than as noise:

* **Deterministic.** Every document is built from the constants in this file,
  and every date is derived from a single anchor rather than from the clock. The
  same command produces the same dataset, so a test can assert on it and a
  developer sees the same profile every time.

* **Idempotent.** Each document carries a stable `_id` derived from its logical
  name, so re-running replaces those documents and leaves anything else alone.

* **Local only.** It refuses to run against anything but a loopback address,
  using the same guard as the reset, because it writes passwords and personal
  details.

The dataset is built to exercise real behaviour rather than to look full:

* Attendance in all three states, including **Maybe**, which real data had
  never contained and which therefore had only ever been seen as an empty state.
* A festival series with several concrete editions, each with its own lineup,
  so identity and edition cannot be confused.
* Artists whose real MusicBrainz records differ in completeness, and one with
  almost nothing, because a seed where every artist is complete cannot show how
  a page behaves when one is not.
* An act appearing twice on one festival bill, so a per-show count can be shown
  not to double-count.
* One user who follows nobody and has logged nothing, so the empty profile is
  exercised as carefully as the full one.

Nothing here is invented provider data, with one deliberate exception. Spotify,
Songkick and MusicBrainz ids appear only where they are the real ones, and each
document states which source its external ids came from. The single exception is
named `INVENTED_SONGKICK_ID`, belongs to an artist that does not exist, and is
asserted as invented by the fixture tests - see that constant and "Victo" in
`build_dataset` for why an id that cannot resolve is occasionally the honest
choice.

The Songkick ids are the part most worth being careful about. Six of the eight
this file previously held did not resolve, which produced pages answering
"Songkick artist page error: 410" for seeded artists that looked perfectly
normal in the database. They are now in one named table, each confirmed by
fetching the artist's own page, and asserted by the tests.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

import bcrypt
from bson import ObjectId
from pymongo import ReplaceOne

from app.auth.security import verify_password
from app.database.connection import db
from app.database.indexes import ensure_indexes
from app.scripts.reset_dev_db import (
    UnsafeTarget,
    verify_local_development_target,
)
from app.utils.slug import generate_slug

# Every seeded user gets this password, so a developer can sign in as any of
# them without hunting for credentials. It is a fixture password and says so.
SEED_PASSWORD = "gigcrowd-dev-2024"

# The two controlled test accounts, which are the exception.
#
# They exist so that one person can be handed a specific credential and be sure it
# is theirs - which means each has its own password. A shared fixture password
# cannot do that job: if both accounts had the same one, handing it to somebody
# would authenticate them as whichever account the login route happened to match
# first, and every test written against "testuser1" would be silently testing
# "testuser2".
TEST_USER_1 = "testuser1"
TEST_USER_1_EMAIL = "testuser1@gigcrowd.app"
TEST_USER_1_PASSWORD = "GigCrowd-Test-2026!A"

TEST_USER_2 = "testuser2"
TEST_USER_2_EMAIL = "testuser2@gigcrowd.app"
TEST_USER_2_PASSWORD = "GigCrowd-Test-2026!B"


# The real Songkick artist id for each seeded act.
#
# Every one of these was looked up on Songkick and its artist page was fetched to
# confirm the id serves that artist, rather than being carried over from an older
# fixture. That distinction is not pedantry: six of the eight ids this fixture
# previously held did not resolve at all, so those seeded artists could not be
# initialized, imported or verified - a page for any of them answered "Songkick
# artist page error: 410", and the fixture quietly taught the wrong thing about
# what a working identity looks like.
#
# A seeded id that does not resolve is worse than no id, because it looks correct
# in the document and produces a broken page. Kept as a named table so a future
# edit has one obvious place to look, and asserted by the fixture tests so a drift
# is caught there rather than discovered by somebody opening a page.
SONGKICK_IDS = {
    "Marina Sena": "10176016",
    "Arctic Monkeys": "520117",
    "Gal Costa": "191574",
    "Rubel": "8449058",
    "Tim Bernardes": "8618899",
    "O Terno": "5881859",
    "Demi Lovato": "976211",
}

# The one seeded id that is deliberately not real.
#
# "Victo" is a thin artist with no real counterpart, and its id is invented so it
# can never be mistaken for one. It exists so a page can be judged when the
# catalogue knows almost nothing about an artist, and so the failed-initialization
# path has something to happen to.
#
# Nothing that trusts an identity trusts it. The seed writes artists directly
# rather than through the lineup importer that validates one, and the fixture
# tests assert the difference explicitly - so the invented id can never be
# mistaken for a validated identity, which is the mistake this whole area of the
# project is about.
INVENTED_SONGKICK_ID = "9988771"

# Two anchors, because the dataset has two kinds of date and one anchor cannot
# honestly describe both.
#
# `ANCHOR` is "now" in the seeded world, and the fixtures that are meant to be in
# the future - shows somebody wants to see, an event somebody announced - are
# measured forward from it. That is a deliberate fiction: the development dataset
# is a future scenario.
#
# `PAST_ANCHOR` is where history is measured from instead. History has to be in the
# past *in the real world too*, and deriving it from `ANCHOR` broke that: with
# `ANCHOR` fifteen days ahead of the actual present, `days_ago(3)` was still three
# days in the future. Three seeded community posts landed on 8, 15 and 17 October
# with a present of 5 October, which made a newly created post sort below seeded
# ones and read as older than it was.
#
# Subtracting from a forward-looking anchor cannot fix that, because any small
# number of days is still in the future. History needs its own base.
#
# Both are fixed instants rather than values read from the clock, so the same seed
# always produces the same timeline - which is what lets the profile's year and
# month grouping be asserted on, and what keeps the fixture reproducible.
ANCHOR = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)

PAST_ANCHOR = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def days_ago(days: int) -> datetime:
    """A moment `days` before the present, which is genuinely in the past."""

    return PAST_ANCHOR - timedelta(days=days)


def days_ahead(days: int) -> datetime:
    """A moment `days` after the scenario's present, in the future."""

    return ANCHOR + timedelta(days=days)


def stable_id(*parts: str) -> ObjectId:
    """A fixed ObjectId for a logical entity.

    Derived from the name rather than generated, so re-running the seed replaces
    the same documents instead of appending duplicates. That is what makes the
    seed idempotent.
    """

    digest = 0

    for part in parts:
        for byte in part.encode("utf-8"):
            digest = (digest * 131 + byte) % (1 << 96)

    return ObjectId(f"{digest:024x}")


# The bcrypt cost factor used for fixture passwords.
#
# Lower than the application's default on purpose: these hashes exist to make a
# developer's local login work, they are reproducible so the seed stays
# idempotent, and the seed builds one per user every time it is constructed -
# including in the tests, which build it many times.
SEED_BCRYPT_COST = 10


def deterministic_password_hash(
    username: str,
    password: str = SEED_PASSWORD,
) -> str:
    """A valid bcrypt hash of a seed password that never changes.

    bcrypt salts every hash randomly, which would make the stored user document
    differ on every run and turn an idempotent seed into a rewrite. Deriving the
    salt from the username keeps the hash genuine - `verify_password` still
    accepts it - while making the document byte-identical between runs.

    `password` defaults to the shared fixture password but may be given per user.
    The two controlled test accounts each have their own, because the whole point
    of them is that a person can be handed one specific credential and the other
    account must not work with it. The salt is still derived from the username,
    which is what keeps the hash reproducible.

    The salt is built from bcrypt's own alphabet rather than standard base64,
    because bcrypt rejects `+` and `/`.
    """

    alphabet = b"./ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"

    digest = hashlib.sha256(
        f"{username}\x00{password}".encode("utf-8")
    ).digest()

    salt_chars = bytearray(
        alphabet[byte % len(alphabet)]
        for byte in (digest * 2)[:21]
    )

    # 16 salt bytes carry 128 bits, but 22 base64 characters carry 132. The four
    # surplus bits live in the low half of the final character and must be zero,
    # so that position is taken from the alphabet entries whose index is a
    # multiple of sixteen. bcrypt rejects the whole salt otherwise.
    salt_chars.append(alphabet[(digest[-1] % 4) * 16])

    return bcrypt.hashpw(
        password.encode("utf-8"),
        f"$2b${SEED_BCRYPT_COST:02d}$".encode()
        + bytes(salt_chars),
    ).decode("utf-8")


def build_user(
    name: str,
    *,
    full_name: str,
    email: str,
    location: Optional[str] = None,
    bio: Optional[str] = None,
    joined_days_ago: int = 400,
    password: str = SEED_PASSWORD,
) -> dict[str, Any]:
    moment = days_ago(joined_days_ago)

    return {
        "_id": stable_id("user", name),
        "username": name,
        "email": email,
        "full_name": full_name,
        "bio": bio,
        "location": location,
        "avatar_url": None,
        "hashed_password": deterministic_password_hash(
            name, password
        ),
        "role": "user",
        "is_active": True,
        "followers_count": 0,
        "following_count": 0,
        "followed_artists_count": 0,
        "created_at": moment,
        "updated_at": moment,
    }


def build_artist(
    name: str,
    *,
    spotify_id: Optional[str] = None,
    songkick_id: Optional[str] = None,
    musicbrainz_id: Optional[str] = None,
    genres: Optional[list[str]] = None,
    followers_count: int = 0,
) -> dict[str, Any]:
    """One artist, with each external id attributed to its own source.

    Songkick ids are stored in the prefixed form a Songkick artist URL uses,
    which is what the resolver and the lineup both speak.
    """

    slug = generate_slug(name)

    external: dict[str, str] = {}

    if spotify_id:
        external["spotify"] = spotify_id

    if songkick_id:
        external["songkick"] = f"Artist{songkick_id}"

    if musicbrainz_id:
        external["musicbrainz"] = musicbrainz_id

    return {
        "_id": stable_id("artist", slug),
        "id": None,
        "slug": slug,
        "name": name,
        "normalized_name": " ".join(name.casefold().split()),
        "external_ids": external,
        "genres": genres or [],
        "image": None,
        "popularity": 0,
        "followers": followers_count,
        "verified": False,
        "created_at": days_ago(600),
        "updated_at": days_ago(600),
    }


def build_venue(
    name: str,
    *,
    city: str,
    country: str,
    region: str = "",
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
    street_address: str = "",
) -> dict[str, Any]:
    return {
        "_id": stable_id("venue", name, city, country),
        "id": None,
        "external_ids": {},
        "name": name,
        "normalized_name": f"{name} {city}".casefold(),
        "slug": generate_slug(f"{city}-{name}"),
        "city": city,
        "country": country,
        "region": region,
        "latitude": latitude,
        "longitude": longitude,
        "street_address": street_address,
        "postal_code": "",
    }


def build_concert(
    title: str,
    *,
    starts_at: datetime,
    ends_at: Optional[datetime] = None,
    artist_slugs: Optional[list[str]] = None,
    venue_slug: str,
    location: Optional[dict] = None,
    songkick_id: Optional[str] = None,
    went_count: int = 0,
    maybe_count: int = 0,
    going_count: int = 0,
) -> dict[str, Any]:
    slugs = artist_slugs or []

    return {
        "title": title,
        "event_type": "Concert",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "artist_slug": slugs[0] if slugs else None,
        "artist_slugs": slugs,
        "venue_slug": venue_slug,
        "location": location,
        "image_url": None,
        "songkick_image": None,
        "description": None,
        "ticket_url": None,
        "event_status": None,
        "sold_out": False,
        "free": False,
        "going_count": going_count,
        "maybe_count": maybe_count,
        "went_count": went_count,
        "date_status": "source",
        "source": (
            {
                "provider": "songkick",
                # Marked as this project's own fixture data.
                #
                # The provider name and a Songkick-shaped URL are what the rest
                # of the system reads, and a fixture has to satisfy them to be
                # usable. But those two fields alone made a fixture
                # indistinguishable from an import, and a fixture dated next year
                # then read as an announced show. Recording the origin separately
                # is what lets the data be checked instead of assumed.
                "provenance": "fixture",
                "url": (
                    "https://www.songkick.com/concerts/"
                    f"{songkick_id}-{generate_slug(title)}"
                ),
                "event_id": songkick_id,
            }
            if songkick_id
            else {"provider": "seed", "provenance": "fixture"}
        ),
        "external_ids": {"songkick": songkick_id} if songkick_id else {},
        "created_at": starts_at,
        "updated_at": starts_at,
    }


def build_festival_day(
    title: str,
    *,
    key: str,
    starts_at: datetime,
    ends_at: datetime,
    series_id: str,
    series_name: str,
    edition: str,
    venue_slug: str,
    location: dict,
    lineup: list[dict],
    songkick_id: Optional[str] = None,
) -> dict[str, Any]:
    """One concrete date of a festival.

    The lineup entries carry their own Songkick id, which is what lets a lineup
    be deduplicated and resolved without ever guessing from a name.
    """

    ordered = []

    for position, entry in enumerate(lineup):

        ordered.append({
            "name": entry["name"],
            "songkick_id": entry["songkick_id"],
            "url": (
                "https://www.songkick.com/artists/"
                f"{entry['songkick_id']}-{generate_slug(entry['name'])}"
            ),
            "slug": generate_slug(entry["name"]),
            "image": None,
            "genres": [],
            "order": position,
        })

    series_url = (
        "https://www.songkick.com/festivals/"
        f"{series_id}-{generate_slug(series_name)}"
        f"/id/{songkick_id or key}"
    )

    return {
        "title": title,
        "event_type": "FestivalInstance",
        "starts_at": starts_at,
        "ends_at": ends_at,
        "artist_slug": None,
        "artist_slugs": [],
        "venue_slug": venue_slug,
        "location": location,
        "lineup": ordered,
        "festival": {
            "series_id": series_id,
            "name": series_name,
            "edition": edition,
            "url": series_url,
        },
        "image_url": None,
        "songkick_image": None,
        "date_status": "source",
        "source": {
            "provider": "songkick",
            # See the note in build_concert: recorded so a fixture is never
            # mistaken for something a provider said.
            "provenance": "fixture",
            "url": series_url,
            "event_id": songkick_id or key,
        },
        "external_ids": {"songkick": songkick_id} if songkick_id else {},
        "going_count": 0,
        "maybe_count": 0,
        "went_count": 0,
        "created_at": starts_at,
        "updated_at": starts_at,
    }


def build_dataset() -> dict[str, list[dict[str, Any]]]:
    """The whole fixture, as plain documents.

    Built in one function so it can be read top to bottom as a description of
    the product: who follows whom, who went to what, and which act appears twice
    on the same bill.
    """

    # ----------------------------------------------------------
    # People
    # ----------------------------------------------------------

    leticia = build_user(
        "leticiacmz",
        full_name="Leticia Moreira",
        email="leticia@gigcrowd.app",
        location="Sao Paulo",
        bio="Shows first, everything else later.",
        joined_days_ago=520,
    )

    bruno = build_user(
        "brunor",
        full_name="Bruno Ribeiro",
        email="bruno@gigcrowd.app",
        location="Recife",
        joined_days_ago=410,
    )

    ana = build_user(
        "analima",
        full_name="Ana Lima",
        email="ana@gigcrowd.app",
        location="Belo Horizonte",
        joined_days_ago=300,
    )

    # Someone who follows nobody and has logged nothing. The empty profile has
    # to be exercised as carefully as the full one.
    theo = build_user(
        "theov",
        full_name="Theo Vieira",
        email="theo@gigcrowd.app",
        joined_days_ago=30,
    )

    # The two controlled accounts, each with its own password. See
    # `TEST_USER_1_PASSWORD` for why they cannot share one.
    testuser1 = build_user(
        TEST_USER_1,
        full_name="Test User One",
        email=TEST_USER_1_EMAIL,
        location="Sao Paulo",
        bio="Automated checks sign in as this account.",
        joined_days_ago=240,
        password=TEST_USER_1_PASSWORD,
    )

    testuser2 = build_user(
        TEST_USER_2,
        full_name="Test User Two",
        email=TEST_USER_2_EMAIL,
        location="Lisbon",
        bio="The other controlled account.",
        joined_days_ago=240,
        password=TEST_USER_2_PASSWORD,
    )

    # ----------------------------------------------------------
    # Artists
    #
    # Real ids only, each attributed to the source it came from. The
    # deliberately thin one exists so the page can be judged when it knows
    # almost nothing.
    # ----------------------------------------------------------

    artists = [
        build_artist(
            "Marina Sena",
            spotify_id="7dGJo4pcD2V6oG8ykP7y6Oz",
            songkick_id=SONGKICK_IDS["Marina Sena"],
            musicbrainz_id="e9e0d2b8-4d4a-4a5f-9a5a-1f4b8f2c9d31",
            genres=["MPB", "Pop"],
            followers_count=48210,
        ),
        build_artist(
            "Arctic Monkeys",
            spotify_id="7Ln80lUS6He07XvHI8qqHH",
            songkick_id=SONGKICK_IDS["Arctic Monkeys"],
            musicbrainz_id="89ad4ac3-39f7-470e-963a-56509c546377",
            genres=["Alternative Rock", "Indie Rock"],
            followers_count=3104520,
        ),
        build_artist(
            "Gal Costa",
            spotify_id="1r7iV2vcSpEnRgtPDVBb1C",
            songkick_id=SONGKICK_IDS["Gal Costa"],
            musicbrainz_id="b2a2e0b6-9d7f-4a52-9c7d-6f2c9a1b4e77",
            genres=["MPB", "Bossa Nova", "Pop"],
            followers_count=271833,
        ),
        build_artist(
            "Rubel",
            spotify_id="1McMsnEElThX1knmY4oliGf",
            songkick_id=SONGKICK_IDS["Rubel"],
            musicbrainz_id="6d1f0b7a-2c4e-4a3b-9f8d-0e5b6c7a8d90",
            genres=["MPB", "Folk"],
            followers_count=39812,
        ),
        build_artist(
            "Tim Bernardes",
            spotify_id="5P7o3k6eRHxaqfXuaC5ZUn",
            songkick_id=SONGKICK_IDS["Tim Bernardes"],
            musicbrainz_id="9f2c1d3e-4b5a-4c6d-8e9f-0a1b2c3d4e5f",
            genres=["MPB", "Indie"],
            followers_count=120455,
        ),
        # A group, so band membership and "members" have something real.
        build_artist(
            "O Terno",
            spotify_id="4tZwfgrHOc3mvqYlEYSvVi",
            songkick_id=SONGKICK_IDS["O Terno"],
            musicbrainz_id="c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f",
            genres=["MPB", "Rock"],
            followers_count=51230,
        ),
        # A pop artist with a very large Songkick catalogue, so the search and
        # import path has something whose gigography is genuinely large - the
        # case where "did the import actually import?" has an interesting answer.
        build_artist(
            "Demi Lovato",
            spotify_id="4z6W6TZjkFpxQeKFGW5vUx",
            songkick_id=SONGKICK_IDS["Demi Lovato"],
            musicbrainz_id="b2b2e0f2-6d8e-4c1a-9f77-3a5d6c1e9b02",
            genres=["Pop", "Alternative"],
            followers_count=7823001,
        ),
        # Deliberately thin: no Spotify id, no genres, no image - and no real
        # Songkick id either, because no such act exists. See
        # `INVENTED_SONGKICK_ID`.
        build_artist(
            "Victo",
            songkick_id=INVENTED_SONGKICK_ID,
            genres=[],
            followers_count=0,
        ),
    ]

    # ----------------------------------------------------------
    # Venues
    # ----------------------------------------------------------

    venues = [
        build_venue(
            "Auditorio Ibirapuera",
            city="Sao Paulo",
            country="Brazil",
            region="SP",
            latitude=-23.5875,
            longitude=-46.6576,
            street_address="Av. Pedro Alvares Cabral, s/n",
        ),
        build_venue(
            "Distrito Anhembi",
            city="Sao Paulo",
            country="Brazil",
            region="SP",
            latitude=-23.5167,
            longitude=-46.6331,
            street_address="Av. Olavo Fontoura, 1209",
        ),
        build_venue(
            "Sesc Rangos",
            city="Belo Horizonte",
            country="Brazil",
            region="MG",
            latitude=-19.9268,
            longitude=-43.9374,
            street_address="R. Mantena, 1470",
        ),
        build_venue(
            "The Crocodile",
            city="Belfast",
            country="United Kingdom",
            region="Northern Ireland",
            latitude=54.5972,
            longitude=-5.9341,
            street_address="16 Donegall Quay",
        ),
    ]

    slugs = {venue["name"]: venue["slug"] for venue in venues}

    ibirapuera = slugs["Auditorio Ibirapuera"]
    anhembi = slugs["Distrito Anhembi"]
    sesc = slugs["Sesc Rangos"]
    croc = slugs["The Crocodile"]

    sao_paulo = {"city": "Sao Paulo", "country": "Brazil"}
    belo_horizonte = {"city": "Belo Horizonte", "country": "Brazil"}
    belfast = {"city": "Belfast", "country": "United Kingdom"}

    # ----------------------------------------------------------
    # Events
    #
    # Keyed by name as they are built. Keying by list position is quietly wrong:
    # inserting the festival dates shifts every later index, which is how this
    # fixture first produced two different keys naming the same event - and so a
    # duplicate attendance row against the unique (user, event) index.
    # ----------------------------------------------------------

    events: dict[str, dict[str, Any]] = {}

    def add(key: str, document: dict[str, Any]) -> dict[str, Any]:
        # `_id` first, because MongoDB always stores it first and a replacement
        # whose `_id` sits last produces a different byte encoding of an
        # otherwise identical document - which the driver then reports as
        # changed, making an idempotent seed look like it rewrote everything.
        document = {"_id": stable_id("event", key), **document}

        events[key] = document

        return document

    # --- Leticia's attended shows, spread across years and months so the
    # profile's year and month grouping has something to group.

    add("marina-ibira", build_concert(
        "Marina Sena at Auditorio Ibirapuera",
        starts_at=days_ago(16),
        artist_slugs=["marina-sena"],
        venue_slug=ibirapuera,
        location=sao_paulo,
        songkick_id="9900101",
        went_count=842,
    ))

    add("arctic-croc", build_concert(
        "Arctic Monkeys at The Crocodile",
        starts_at=days_ago(9),
        artist_slugs=["arctic-monkeys"],
        venue_slug=croc,
        location=belfast,
        songkick_id="9900102",
        went_count=1544,
    ))

    add("gal-sesc", build_concert(
        "Gal Costa at Sesc Rangos",
        starts_at=days_ago(45),
        artist_slugs=["gal-costa"],
        venue_slug=sesc,
        location=belo_horizonte,
        songkick_id="9900103",
        went_count=1204,
    ))

    add("rubel-anhembi", build_concert(
        "Rubel at Distrito Anhembi",
        starts_at=days_ago(120),
        artist_slugs=["rubel"],
        venue_slug=anhembi,
        location=sao_paulo,
        songkick_id="9900104",
        went_count=611,
    ))

    add("marina-anhembi-2025", build_concert(
        "Marina Sena at Distrito Anhembi",
        starts_at=days_ago(410),
        artist_slugs=["marina-sena"],
        venue_slug=anhembi,
        location=sao_paulo,
        songkick_id="9900105",
        went_count=2301,
    ))

    # The same artist on a different day. This is what makes "Marina Sena,
    # 2 shows" a statement about shows rather than about lineups.
    add("marina-sesc-2025", build_concert(
        "Marina Sena at Sesc Rangos",
        starts_at=days_ago(400),
        artist_slugs=["marina-sena"],
        venue_slug=sesc,
        location=belo_horizonte,
        songkick_id="9900106",
        went_count=903,
    ))

    # --- One festival series, three concrete editions.

    add("valle-2026-d1", build_festival_day(
        "Festival Vale 2026 - Day 1",
        key="valle-2026-d1",
        starts_at=days_ago(200),
        ends_at=days_ago(196),
        series_id="9900200",
        series_name="Festival Vale",
        edition="2026",
        venue_slug=anhembi,
        location=sao_paulo,
        songkick_id="9900201",
        lineup=[
            {"name": "Marina Sena", "songkick_id": SONGKICK_IDS["Marina Sena"]},
            {"name": "Tim Bernardes", "songkick_id": SONGKICK_IDS["Tim Bernardes"]},
            {"name": "O Terno", "songkick_id": SONGKICK_IDS["O Terno"]},
            # The same act twice on the same bill: one show, not two.
            {"name": "O Terno", "songkick_id": SONGKICK_IDS["O Terno"]},
        ],
    ))

    add("valle-2026-d2", build_festival_day(
        "Festival Vale 2026 - Day 2",
        key="valle-2026-d2",
        starts_at=days_ago(195),
        ends_at=days_ago(191),
        series_id="9900200",
        series_name="Festival Vale",
        edition="2026",
        venue_slug=anhembi,
        location=sao_paulo,
        songkick_id="9900202",
        lineup=[
            {"name": "Rubel", "songkick_id": SONGKICK_IDS["Rubel"]},
            {"name": "Victo", "songkick_id": INVENTED_SONGKICK_ID},
        ],
    ))

    add("valle-2025", build_festival_day(
        "Festival Vale 2025",
        key="valle-2025",
        starts_at=days_ago(570),
        ends_at=days_ago(564),
        series_id="9900200",
        series_name="Festival Vale",
        edition="2025",
        venue_slug=anhembi,
        location=sao_paulo,
        songkick_id="9900203",
        lineup=[
            {"name": "Gal Costa", "songkick_id": SONGKICK_IDS["Gal Costa"]},
            {"name": "Marina Sena", "songkick_id": SONGKICK_IDS["Marina Sena"]},
        ],
    ))

    # --- Something in the future, so "upcoming" is real.

    add("tim-ibira-future", build_concert(
        "Tim Bernardes at Auditorio Ibirapuera",
        starts_at=days_ahead(35),
        artist_slugs=["tim-bernardes"],
        venue_slug=ibirapuera,
        location=sao_paulo,
        songkick_id="9900107",
        going_count=1207,
        maybe_count=433,
    ))

    add("arctic-ibira-future", build_concert(
        "Arctic Monkeys at Auditorio Ibirapuera",
        starts_at=days_ahead(96),
        artist_slugs=["arctic-monkeys"],
        venue_slug=ibirapuera,
        location=sao_paulo,
        songkick_id="9900108",
        going_count=3890,
        maybe_count=1204,
    ))

    add("gal-ibira-future", build_concert(
        "Gal Costa at Auditorio Ibirapuera",
        starts_at=days_ahead(58),
        artist_slugs=["gal-costa"],
        venue_slug=ibirapuera,
        location=sao_paulo,
        songkick_id="9900109",
        maybe_count=612,
    ))

    # A multi-day future festival, so the page has to show a range rather than a
    # single night.
    add("valle-2027", build_festival_day(
        "Festival Vale 2027",
        key="valle-2027",
        starts_at=days_ahead(200),
        ends_at=days_ahead(203),
        series_id="9900200",
        series_name="Festival Vale",
        edition="2027",
        venue_slug=anhembi,
        location=sao_paulo,
        songkick_id="9900204",
        lineup=[
            {"name": "Marina Sena", "songkick_id": SONGKICK_IDS["Marina Sena"]},
            {"name": "Tim Bernardes", "songkick_id": SONGKICK_IDS["Tim Bernardes"]},
            {"name": "Gal Costa", "songkick_id": SONGKICK_IDS["Gal Costa"]},
        ],
    ))

    def event_id(key: str) -> str:
        return str(events[key]["_id"])

    # ----------------------------------------------------------
    # Attendance
    #
    # All three states are represented. `maybe` in particular had never held a
    # row in the real database, so its empty state was all that had ever been
    # seen of it.
    # ----------------------------------------------------------

    show_logs: list[dict[str, Any]] = []

    def log(
        key: str,
        user_id: ObjectId,
        status: str,
        *,
        day_offset: int,
        rating: Optional[int] = None,
        review: Optional[str] = None,
        reviewed_days_ago: Optional[int] = None,
    ) -> str:
        """Record one attendance, and return the log's id.

        The id is returned because an activity that says somebody attended a show
        points at the *attendance record*, not at the show. Those are different
        documents - one per person per show - and a feed row that names the event
        instead cannot be resolved to anything, so the row renders with no link and
        no way to tell what it was about.

        The product writes it that way (see `POST /users/me/show-logs`), and the
        seed once wrote the event id while declaring `target_type: show_log`, which
        made six of eleven seeded feed rows dead on arrival.
        """

        identifier = stable_id("show_log", key, str(user_id))

        show_logs.append({
            "_id": identifier,
            "user_id": str(user_id),
            "event_id": event_id(key),
            "status": status,
            "date": events[key]["starts_at"],
            "rating": rating,
            "review": review,
            "photo_url": None,
            "photo_public_id": None,
            "reviewed_at": (
                days_ago(reviewed_days_ago)
                if reviewed_days_ago is not None
                else None
            ),
            "created_at": days_ago(day_offset),
            "updated_at": days_ago(day_offset),
        })

        return str(identifier)

    def log_id(key: str, user_id: ObjectId) -> str:
        """The id of the attendance record `log(key, user_id, ...)` wrote.

        Derived rather than remembered, so a row cannot end up pointing at an
        attendance that was never recorded.
        """

        return str(stable_id("show_log", key, str(user_id)))

    leticia_id = leticia["_id"]
    bruno_id = bruno["_id"]
    ana_id = ana["_id"]

    log("marina-ibira", leticia_id, "went", day_offset=15,
        rating=5,
        review=(
            "The room shook. She played the whole record front to back "
            "and the encore was better than the show."
        ),
        reviewed_days_ago=15)

    log("arctic-croc", leticia_id, "went", day_offset=8,
        rating=4,
        review="Perfect pacing, wrong venue, worth it anyway.",
        reviewed_days_ago=8)

    log("gal-sesc", leticia_id, "went", day_offset=44)
    log("rubel-anhembi", leticia_id, "went", day_offset=119)
    log("marina-anhembi-2025", leticia_id, "went", day_offset=409)
    log("marina-sesc-2025", leticia_id, "went", day_offset=399)
    log("valle-2026-d1", leticia_id, "went", day_offset=199)
    log("valle-2025", leticia_id, "went", day_offset=569)

    # Want to go.
    log("tim-ibira-future", leticia_id, "going", day_offset=2)
    log("arctic-ibira-future", leticia_id, "going", day_offset=1)

    # Maybe - the state that had never held a row in the real database, so its
    # empty state was all that had ever been seen of it. Both are shows still to
    # come: being undecided about a night that has already passed is not a state
    # anyone can be in.
    log("valle-2027", leticia_id, "maybe", day_offset=1)
    log("gal-ibira-future", leticia_id, "maybe", day_offset=4)

    # Bruno: a smaller history, plus a review that belongs to him rather than to
    # Leticia, so review ownership is exercised.
    log("gal-sesc", bruno_id, "went", day_offset=43,
        rating=5,
        review=(
            "Gal Costa sang the medley nobody asked for and the whole "
            "room sang it back."
        ),
        reviewed_days_ago=43)
    log("tim-ibira-future", bruno_id, "going", day_offset=5)
    log("gal-ibira-future", bruno_id, "maybe", day_offset=6)

    log("arctic-croc", ana_id, "went", day_offset=7,
        rating=3,
        review="Great set, brutal sound system.",
        reviewed_days_ago=7)
    log("rubel-anhembi", ana_id, "went", day_offset=118)

    # ----------------------------------------------------------
    # Social graph
    # ----------------------------------------------------------

    follows = [
        {"_id": stable_id("follow", "bruno", "leticia"),
         "follower_id": str(bruno_id), "following_id": str(leticia_id),
         "created_at": days_ago(120)},
        {"_id": stable_id("follow", "ana", "leticia"),
         "follower_id": str(ana_id), "following_id": str(leticia_id),
         "created_at": days_ago(90)},
        {"_id": stable_id("follow", "leticia", "bruno"),
         "follower_id": str(leticia_id), "following_id": str(bruno_id),
         "created_at": days_ago(118)},
    ]

    artist_follows = [
        {"_id": stable_id("artist_follow", "leticia", "marina-sena"),
         "user_id": str(leticia_id), "artist_slug": "marina-sena",
         "created_at": days_ago(200)},
        {"_id": stable_id("artist_follow", "leticia", "arctic-monkeys"),
         "user_id": str(leticia_id), "artist_slug": "arctic-monkeys",
         "created_at": days_ago(180)},
        {"_id": stable_id("artist_follow", "leticia", "tim-bernardes"),
         "user_id": str(leticia_id), "artist_slug": "tim-bernardes",
         "created_at": days_ago(60)},
        {"_id": stable_id("artist_follow", "bruno", "gal-costa"),
         "user_id": str(bruno_id), "artist_slug": "gal-costa",
         "created_at": days_ago(150)},
        {"_id": stable_id("artist_follow", "bruno", "rubel"),
         "user_id": str(bruno_id), "artist_slug": "rubel",
         "created_at": days_ago(140)},
        {"_id": stable_id("artist_follow", "ana", "marina-sena"),
         "user_id": str(ana_id), "artist_slug": "marina-sena",
         "created_at": days_ago(85)},
    ]

    # ----------------------------------------------------------
    # Community
    # ----------------------------------------------------------

    community_posts = [
        {"_id": stable_id("cpost", "leticia", "marina-sena", "1"),
         "artist_slug": "marina-sena",
         "user_id": str(leticia_id),
         "content": "Saw her at Ibirapuera last week. Small room, huge night.",
         "image_url": None,
         "created_at": days_ago(12),
         "updated_at": days_ago(12)},
        {"_id": stable_id("cpost", "bruno", "gal-costa", "1"),
         "artist_slug": "gal-costa",
         "user_id": str(bruno_id),
         "content": "Gal Costa is the reason I started listening in Portuguese.",
         "image_url": None,
         "created_at": days_ago(40),
         "updated_at": days_ago(40)},
        {"_id": stable_id("cpost", "ana", "arctic-monkeys", "1"),
         "artist_slug": "arctic-monkeys",
         "user_id": str(ana_id),
         "content": "Belfast was tiny. The band was enormous.",
         "image_url": None,
         "created_at": days_ago(5),
         "updated_at": days_ago(5)},
        {"_id": stable_id("cpost", "bruno", "marina-sena", "1"),
         "artist_slug": "marina-sena",
         "user_id": str(bruno_id),
         "content": "Does anyone have the setlist from the Anhembi show?",
         "image_url": None,
         "created_at": days_ago(3),
         "updated_at": days_ago(3)},
    ]

    # The application keeps these two counters on the post as likes and comments
    # arrive, so they are initialised here and tallied once the likes and
    # comments below exist.
    for post in community_posts:
        post["likes_count"] = 0
        post["comments_count"] = 0

    comments = [
        {"_id": stable_id("comment", "ana", "cpost-leticia", "1"),
         "post_id": str(community_posts[0]["_id"]),
         "user_id": str(ana_id),
         "content": "I was two rows back. Still thinking about it.",
         "created_at": days_ago(11)},
        {"_id": stable_id("comment", "bruno", "cpost-leticia", "1"),
         "post_id": str(community_posts[0]["_id"]),
         "user_id": str(bruno_id),
         "content": "Anhembi in February is the better room.",
         "created_at": days_ago(10)},
    ]

    post_likes = [
        {"_id": stable_id("like", "ana", "cpost-leticia"),
         "target_id": str(community_posts[0]["_id"]),
         "post_id": str(community_posts[0]["_id"]),
         "user_id": str(ana_id),
         "created_at": days_ago(11)},
        {"_id": stable_id("like", "bruno", "cpost-leticia"),
         "target_id": str(community_posts[0]["_id"]),
         "post_id": str(community_posts[0]["_id"]),
         "user_id": str(bruno_id),
         "created_at": days_ago(10)},
        {"_id": stable_id("like", "leticia", "cpost-ana"),
         "target_id": str(community_posts[2]["_id"]),
         "post_id": str(community_posts[2]["_id"]),
         "user_id": str(leticia_id),
         "created_at": days_ago(4)},
    ]

    # Tally the denormalised counters from the rows that were just defined, so
    # the seed's numbers and the application's numbers cannot disagree.
    posts_by_id = {
        str(post["_id"]): post for post in community_posts
    }

    for like in post_likes:

        post = posts_by_id.get(str(like["post_id"]))

        if post:
            post["likes_count"] += 1

    for comment in comments:

        post = posts_by_id.get(str(comment["post_id"]))

        if post:
            post["comments_count"] += 1

    # A post about a specific event, so the event feed has something real.
    event_posts = [
        {"_id": stable_id("epost", "leticia", "arctic-croc"),
         "user_id": str(leticia_id),
         "event_id": event_id("arctic-croc"),
         "content": "Still thinking about the encore.",
         "media_url": None,
         "media_type": "text",
         "created_at": days_ago(7),
         "updated_at": days_ago(7)},
    ]

    # ----------------------------------------------------------
    # Feed
    #
    # Reviews, attendance and community activity, because those are what a
    # unified timeline is built from. Follows are deliberately NOT turned into
    # feed rows: a relationship mutation is not something a person wants to read
    # about in their timeline.
    # ----------------------------------------------------------

    activities: list[dict[str, Any]] = []

    def activity(
        key: str,
        user_id: ObjectId,
        activity_type: str,
        *,
        target_id: Optional[str],
        target_type: Optional[str],
        metadata: dict,
        when: datetime,
    ) -> None:

        activities.append({
            "_id": stable_id("activity", key),
            "user_id": str(user_id),
            "activity_type": activity_type,
            "target_id": target_id,
            "target_type": target_type,
            "metadata": metadata,
            "created_at": when,
        })

    # Ana and Bruno follow Leticia, so her review and attendance reach them.
    #
    # Every attendance/review row names the *attendance record*, never the event.
    # That is what the product writes, and it is the only thing the feed can
    # resolve: an activity whose `target_id` is an event id while its
    # `target_type` says `show_log` produces a row with no target, which renders
    # as a sentence a reader cannot press. Deriving the id rather than repeating
    # it means a row cannot point at an attendance that was never written.
    activity(
        "leticia-review-marina", leticia_id, "create_review",
        target_id=log_id("marina-ibira", leticia_id),
        target_type="show_log",
        metadata={"artist_slug": "marina-sena", "rating": 5},
        when=days_ago(15),
    )

    activity(
        "leticia-attended-arctic", leticia_id, "attend_event",
        target_id=log_id("arctic-croc", leticia_id),
        target_type="show_log",
        metadata={"artist_slug": "arctic-monkeys"},
        when=days_ago(8),
    )

    activity(
        "bruno-review-gal", bruno_id, "create_review",
        target_id=log_id("gal-sesc", bruno_id),
        target_type="show_log",
        metadata={"artist_slug": "gal-costa", "rating": 5},
        when=days_ago(43),
    )

    activity(
        "ana-attended-arctic", ana_id, "attend_event",
        target_id=log_id("arctic-croc", ana_id),
        target_type="show_log",
        metadata={"artist_slug": "arctic-monkeys"},
        when=days_ago(7),
    )

    activity(
        "ana-review-arctic", ana_id, "create_review",
        target_id=log_id("arctic-croc", ana_id),
        target_type="show_log",
        metadata={"artist_slug": "arctic-monkeys", "rating": 3},
        when=days_ago(7),
    )

    activity(
        "leticia-cpost-marina", leticia_id, "create_community_post",
        target_id=str(community_posts[0]["_id"]),
        target_type="community_post",
        metadata={
            "artist_slug": "marina-sena",
            "content": community_posts[0]["content"],
        },
        when=days_ago(12),
    )

    activity(
        "ana-cpost-arctic", ana_id, "create_community_post",
        target_id=str(community_posts[2]["_id"]),
        target_type="community_post",
        metadata={
            "artist_slug": "arctic-monkeys",
            "content": community_posts[2]["content"],
        },
        when=days_ago(5),
    )

    activity(
        "bruno-comment", bruno_id, "comment_post",
        target_id=str(comments[0]["_id"]), target_type="comment",
        metadata={
            "artist_slug": "marina-sena",
            "content": comments[0]["content"],
        },
        when=days_ago(11),
    )

    activity(
        "ana-liked", ana_id, "like_post",
        target_id=str(community_posts[0]["_id"]),
        target_type="community_post",
        metadata={"artist_slug": "marina-sena"},
        when=days_ago(11),
    )

    # An event announced by an artist Leticia follows, so "a new event from an
    # artist you follow" has a row behind it. The timestamp is when the show was
    # announced, not when it happens - which puts it in the past, so it is
    # measured from the past anchor rather than by stepping backwards from the
    # scenario's present.
    #
    # It points at her `going` record for that show, which is what makes it
    # resolvable *and* honest: the row says she is going, and there is a going
    # record behind it.
    activity(
        "tim-announced", leticia_id, "attend_event",
        target_id=log_id("tim-ibira-future", leticia_id),
        target_type="show_log",
        metadata={"artist_slug": "tim-bernardes", "going": True},
        when=days_ago(5),
    )

    notifications = [
        {"_id": stable_id("notification", "leticia", "c1"),
         "recipient_id": str(leticia_id),
         "actor_id": str(ana_id),
         "type": "comment",
         "related_entity_type": "community_post",
         "related_entity_id": str(community_posts[0]["_id"]),
         "context": {"username": "analima",
                     "text": "I was two rows back."},
         "read": False,
         "created_at": days_ago(11)},
        {"_id": stable_id("notification", "leticia", "c2"),
         "recipient_id": str(leticia_id),
         "actor_id": str(bruno_id),
         "type": "follow",
         "related_entity_type": "user",
         "related_entity_id": str(bruno_id),
         "context": {"username": "brunor"},
         "read": True,
         "created_at": days_ago(118)},
    ]

    return {
        "users": [
            leticia,
            bruno,
            ana,
            theo,
            testuser1,
            testuser2,
        ],
        "artists": artists,
        "venues": venues,
        "events": list(events.values()),
        "show_logs": show_logs,
        "follows": follows,
        "artist_follows": artist_follows,
        "community_posts": community_posts,
        "comments": comments,
        "post_likes": post_likes,
        "posts": event_posts,
        # Newest first, which is the order a timeline reads in. The query sorts
        # anyway, but a fixture that already reads like its own result is much
        # easier to reason about.
        "activities": sorted(
            activities,
            key=lambda item: item["created_at"],
            reverse=True,
        ),
        "notifications": notifications,
    }


async def apply_seed(
    database,
    dataset: dict[str, list[dict]],
) -> dict[str, int]:
    """Replace the seeded documents, collection by collection.

    Each document has a stable `_id`, so this upserts rather than appends and is
    safe to repeat.
    """

    written: dict[str, int] = {}

    for collection, documents in dataset.items():

        if not documents:
            written[collection] = 0
            continue

        operations = [
            ReplaceOne(
                {"_id": document["_id"]},
                document,
                upsert=True,
            )
            for document in documents
        ]

        result = await database[collection].bulk_write(operations)

        written[collection] = (
            result.upserted_count + result.modified_count
        )

    return written


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Write the deterministic local development dataset. "
            "Refuses to run against anything but a loopback address."
        )
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the dataset. Without this nothing is written.",
    )

    args = parser.parse_args()

    from app.config import settings

    try:
        confirmation = verify_local_development_target(
            settings.MONGODB_URL,
            settings.DATABASE_NAME,
        )
    except UnsafeTarget as exc:
        print()
        print("REFUSING TO SEED")
        print("-" * 52)
        print(f"  {exc}")
        return 2

    await db.connect()

    try:
        database = db.get_database()

        dataset = build_dataset()

        print()
        print("Local development seed")
        print("-" * 52)
        print(f"  {confirmation}")
        print(f"  password for every seeded user: {SEED_PASSWORD}")
        print(f"  date anchor: {ANCHOR.date()}")

        print()
        print("  dataset:")

        for collection, documents in dataset.items():
            print(f"    {collection:20} {len(documents):>4}")

        if not args.apply:
            print()
            print("Nothing was written. Re-run with --apply to seed.")
            return 0

        written = await apply_seed(database, dataset)

        await ensure_indexes(database)

        print()
        print(f"  wrote {sum(written.values())} document(s):")

        for collection, count in written.items():
            print(f"    {collection:20} {count:>4}")

        print()
        print("Controlled test accounts, one password each:")
        print(f"  {TEST_USER_1_EMAIL:<28} {TEST_USER_1_PASSWORD}")
        print(f"  {TEST_USER_2_EMAIL:<28} {TEST_USER_2_PASSWORD}")
        print()
        print(
            "The other seeded users share the fixture password:"
        )
        print(f"  {SEED_PASSWORD}")
        print("  leticiacmz / brunor / analima / theov")
        print(
            "  (the login form takes the address form of the email,"
        )
        print("   e.g. leticia@gigcrowd.app)")

        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
