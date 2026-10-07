from datetime import datetime, UTC

from typing import Optional

from bson import ObjectId
from pymongo import ASCENDING

from app.core.logger import get_logger

from app.domain.artist import Artist
from app.domain.artist_state import (
    INITIALIZED,
    INITIALIZING,
    SYNC_ERROR,
    SYNC_SUCCESS,
    SYNC_EMPTY,
    PENDING,
)

from app.mappers.artist_document_mapper import (
    ArtistDocumentMapper,
)

from app.repositories.base import BaseRepository

from app.utils.slug import generate_slug
from app.utils.text import normalize_text


logger = get_logger(
    "artist_repository"
)


# Positive evidence that a gigography fetch has already happened.
#
# Deliberately a whitelist. A blacklist - "anything that is not pending" - reads
# like the same thing and is not: an artist whose `sync_status` was written by
# something this codebase has never heard of would match it, and the scheduled
# job would then treat that artist as initialized and scrape it. Naming the
# statuses that mean "asked" means an unknown status is never selected, which is
# the direction that costs a slow refresh rather than an unbounded crawl.
INITIALIZED_QUERY = {
    "$or": [
        {"sync_status": {"$in": [SYNC_SUCCESS, SYNC_EMPTY, INITIALIZED]}},
        {"sync_status": INITIALIZING},
        # Before `sync_status` existed, a timestamp was the only record.
        {"last_synced_at": {"$ne": None}},
    ]
}


# The complement, expressed positively for the same reason: an artist is pending
# when nothing says it has been asked. No `sync_status` at all is the ordinary
# case for a lineup artist, and a stored `null` means the same thing.
PENDING_QUERY = {
    "sync_status": {"$in": [None]},
    "last_synced_at": {"$in": [None]},
}


# An artist whose gigography may be fetched right now, by a person.
#
# `error` is claimable because a failed fetch is a question that was asked and not
# answered, so asking again is a retry rather than a first time - and a retry that
# only the scheduler could perform would leave a broken artist broken until the
# next hourly tick. `initializing` is not claimable, because somebody is already
# doing it.
CLAIMABLE_STATUSES = [
    None,
    SYNC_ERROR,
]


class ArtistRepository(BaseRepository):

    def __init__(self, db):

        super().__init__(
            db,
            "artists",
        )

    async def get_by_slug(
        self,
        slug: str,
    ) -> Artist | None:

        document = await self.find_one(
            {
                "slug": slug,
            }
        )

        if not document:
            return None

        return ArtistDocumentMapper.to_domain(
            document
        )

    async def get_by_name(
        self,
        name: str,
    ) -> Artist | None:

        normalized = normalize_text(
            name
        )

        document = await self.find_one(
            {
                "normalized_name": normalized,
            }
        )

        if not document:
            return None

        return ArtistDocumentMapper.to_domain(
            document
        )

    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ) -> Artist | None:

        document = await self.find_one(
            {
                f"external_ids.{provider}": str(
                    external_id
                ),
            }
        )

        if not document:
            return None

        return ArtistDocumentMapper.to_domain(
            document
        )

    async def get_by_songkick_id(
        self,
        songkick_id: int | str,
    ) -> Artist | None:

        songkick_id = str(
            songkick_id
        )

        if not songkick_id.startswith(
            "Artist"
        ):

            songkick_id = (
                f"Artist{songkick_id}"
            )

        return await self.get_by_external_id(
            "songkick",
            songkick_id,
        )

    async def generate_unique_slug(
        self,
        name: str,
    ) -> str:

        base_slug = generate_slug(
            name
        )

        slug = base_slug

        counter = 2

        while await self.get_by_slug(
            slug
        ):

            slug = (
                f"{base_slug}-{counter}"
            )

            counter += 1

        return slug

    async def insert_artist(
        self,
        artist: Artist,
    ):

        result = await self.insert_one(
            artist.model_dump()
        )

        artist.id = str(
            result.inserted_id
        )

        return artist

    async def _slug_for(
        self,
        name: str,
        songkick_id: str,
    ) -> str:
        """A slug that is actually addressable, whatever the name looks like.

        `generate_slug` reduces a name to ASCII, so a name written in a
        non-Latin script - and Songkick has a great many, from Japanese and
        Chinese festival bills to Korean and Cyrillic - slugifies to nothing at
        all. The unique-slug loop then produces `-2`, `-3`, `-4`, which is not an
        address: a lineup of such artists renders as a grid of dead links and a
        catalogue whose slugs all collide on the same meaningless prefix.

        So when the name yields nothing, the slug is built from the Songkick id
        instead. That is not a fallback for lack of an idea - the id *is* this
        module's identity, the thing the record is keyed on and the thing that
        will never collide with another artist's. `artist-2668421` says exactly
        what `tim-bernardes` would have, and it works for every script.
        """

        # The base, not the uniquified result. `generate_unique_slug` signals an
        # empty base by returning a bare counter - `-2`, `-3` - so a leading
        # hyphen is the tell. Testing for "is it all digits" instead would
        # throw away a perfectly good slug for an artist genuinely named "1234".
        if generate_slug(str(name)):
            return await self.generate_unique_slug(name)

        base = generate_slug(str(songkick_id))

        if not base:
            base = "artist"

        return await self.generate_unique_slug(
            f"artist-{base}"
        )

    async def ensure_by_songkick_id(
        self,
        songkick_id: str,
        name: str,
        image: Optional[str] = None,
        genres: Optional[list[str]] = None,
    ) -> tuple[Artist, bool]:
        """Find or create the artist a Songkick id names. Returns `(artist, created)`.

        Identity here is the Songkick id and nothing else, because that is the
        one identifier the source and this catalogue agree on. Deciding identity
        any other way - by name, by "the first search result", by a Spotify
        match - would be a guess, and a guess that creates permanent records
        cannot be undone by deleting a page.

        So the id decides. An artist that already holds it is returned
        untouched: this never renames, re-slugs or rewrites an artist that
        exists, so running it against the same lineup a hundred times produces
        the same catalogue.

        A new artist is created as a *stub* - name, id, slug and whatever the
        source stated about the picture - and deliberately nothing else. In
        particular no `last_synced_at` is written, which is what keeps this
        distinct from an import: a stub artist is one the sync job is still free
        to import, and one nothing here has started fetching on its behalf.
        """
        from pymongo.errors import DuplicateKeyError

        normalized_id = str(songkick_id).strip()

        if not normalized_id:
            raise ValueError(
                "A Songkick artist id is required to "
                "ensure an artist"
            )

        if not normalized_id.lower().startswith(
            "artist"
        ):
            normalized_id = f"Artist{normalized_id}"

        existing = await self.get_by_external_id(
            "songkick",
            normalized_id,
        )

        if existing is not None:
            return existing, False

        artist = Artist(
            name=str(name).strip(),
            normalized_name=normalize_text(
                str(name)
            ),
            slug=await self._slug_for(name, normalized_id),
            external_ids={
                "songkick": normalized_id,
            },
            image=image,
            genres=[
                str(genre)
                for genre in (genres or [])
                if genre
            ],
        )

        # Inserted directly rather than through `insert_artist`, so the two sync
        # fields are absent from the document rather than present and null.
        #
        # The difference sounds small and is not. `last_synced_at` is the field
        # the sync job selects and orders on, and a stored `null` there is a
        # weaker, easier-to-miss version of "never synced" than an absent field -
        # a query that filters on `$ne: null` would skip this artist, and a stub
        # that reads as "already handled" is exactly how a lineup quietly becomes
        # a list of artists nobody ever imported.
        document = artist.model_dump(
            exclude={"id"}
        )

        for field_name in (
            "last_synced_at",
            "sync_status",
        ):
            document.pop(field_name, None)

        try:
            result = await self.insert_one(document)

        except DuplicateKeyError:
            # Another pass created the same artist between the read and the
            # write - two workers, or two lineups naming one act. The identity
            # is the same artist either way, so the winner's record is the
            # correct answer and a duplicate is not.
            raced = await self.get_by_external_id(
                "songkick",
                normalized_id,
            )

            if raced is not None:
                return raced, False

            raise

        artist.id = str(result.inserted_id)

        return artist, True

    async def get_all(
        self,
        limit: int = 20,
        skip: int = 0,
    ) -> list[Artist]:

        documents = await self.find_many(
            {},
            sort=[
                (
                    "normalized_name",
                    ASCENDING,
                )
            ],
            skip=skip,
            limit=limit,
        )

        return [
            ArtistDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # SYNC CANDIDATES
    # ============================================================

    async def find_needing_sync(
        self,
        stale_before: datetime,
        limit: int = 10,
    ) -> list[Artist]:
        """Initialized artists whose stored data has aged past `stale_before`.

        Never a pending one. This is the difference between a maintenance pass and
        a scrape: an artist nobody has opened has no gigography, and fetching one
        because a scheduler ticked is exactly the behaviour this whole lifecycle
        was reorganised to remove. A pending artist is initialized when a person
        imports it or opens its page, and at no other time.

        So the query requires positive evidence that a fetch has already happened:
        a `sync_status` that means "asked", or a timestamp from before `sync_status`
        existed. An artist is selected when that evidence exists *and* the data has
        since aged past the boundary.

        The batch is bounded and the order is total, because a scheduled job that
        picks the same rows in a different order each tick will either loop on the
        same few artists forever or never reach the rest. Ordering by
        `last_synced_at` ascending puts the artists that have waited longest first,
        and `_id` breaks ties so the ordering is total even for a whole batch.

        `stale_before` comes from the caller rather than being computed here so the
        query and `SynchronizationService.needs_sync` cannot disagree about the
        boundary by a rounding difference.
        """

        documents = await self.find_many(
            {
                "$and": [
                    INITIALIZED_QUERY,
                    {
                        "$or": [
                            {"last_synced_at": None},
                            {"last_synced_at": {"$lt": stale_before}},
                        ]
                    },
                ]
            },
            sort=[
                ("last_synced_at", ASCENDING),
                ("_id", ASCENDING),
            ],
            limit=max(1, int(limit)),
        )

        return [
            ArtistDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    async def find_pending(
        self,
        limit: int = 100,
    ) -> list[Artist]:
        """Artists with an established identity and no gigography yet.

        Read-only and *not* used by the scheduled job - see `find_needing_sync` for
        why. It exists so a human can ask "what is still pending?" and so the tests
        can describe the population without a scheduler in the way.
        """

        documents = await self.find_many(
            PENDING_QUERY,
            sort=[("_id", ASCENDING)],
            limit=max(1, int(limit)),
        )

        return [
            ArtistDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    async def claim_initialization(self, artist_id: str) -> bool:
        """Take exclusive responsibility for one artist's first fetch.

        Returns True for the one caller that won, False for everybody else.

        The predicate is the artist being unclaimed *and* not already looked at, so
        the claim is a compare-and-set rather than a read followed by a write. That
        matters because the loser of a race must do nothing at all: two people
        opening a cold artist at the same moment is an ordinary thing for a
        catalogue to see, and without this both would spend a full gigography
        scrape to produce the same rows.

        A crashed claim would otherwise strand the artist forever, so the claim is
        released by whatever the fetch writes afterwards - success, empty or error
        all clear it - and `release_initialization_claim` covers the case where the
        fetch could not even be started.
        """

        result = await self.collection.update_one(
            {
                "_id": ObjectId(artist_id),
                "sync_status": {"$in": CLAIMABLE_STATUSES},
                "last_synced_at": None,
            },
            {"$set": {"sync_status": INITIALIZING}},
        )

        return bool(result.matched_count)

    async def release_initialization_claim(self, artist_id: str) -> None:
        """Give up a claim without recording an outcome.

        For when the fetch could not be attempted at all - a missing provider, a
        configuration that was never wired up. The artist returns to pending, which
        is exactly what it was, and the next open will try again.
        """

        await self.collection.update_one(
            {"_id": ObjectId(artist_id), "sync_status": INITIALIZING},
            {"$set": {"sync_status": None}},
        )

    # ============================================================
    # EXTERNAL DATA
    # ============================================================

    async def update_external_data(
        self,
        artist_id: str,
        external_ids: dict[str, str],
        image: str | None,
        genres: list[str],
        popularity: int | None,
    ):
        """
        Update external provider data for an existing artist.

        This method is intentionally limited to enrichment data.

        Canonical identity fields such as name, slug and
        Songkick ID are not modified here.

        GigCrowd follower counts are not stored in the
        artists collection.
        """

        update_data = {
            "external_ids": external_ids,
            "image": image,
            "genres": genres,
            "popularity": popularity,
            "updated_at": datetime.now(UTC),
        }

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": update_data,
            },
        )

        logger.info(
            f"Updated external data for artist "
            f"{artist_id}"
        )

    async def update_spotify_data(
        self,
        artist_id: str,
        spotify_artist: Artist,
    ):
        """
        Backwards-compatible Spotify enrichment method.

        Followers are intentionally not stored.

        Prefer update_external_data() for new import flows.
        """

        spotify_id = (
            spotify_artist.external_ids.get(
                "spotify"
            )
        )

        update_data = {
            "image": spotify_artist.image,
            "genres": spotify_artist.genres,
            "popularity": spotify_artist.popularity,
            "updated_at": datetime.now(UTC),
        }

        if spotify_id:

            update_data[
                "external_ids.spotify"
            ] = spotify_id

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": update_data,
            },
        )

        logger.info(
            f"Updated Spotify data for artist "
            f"{artist_id}"
        )

    async def update_image(
        self,
        artist_id: str,
        image: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "image": image,
                    "updated_at": datetime.now(UTC),
                }
            },
        )

        logger.info(
            f"Updated image for artist "
            f"{artist_id}"
        )

    async def update_last_synced(
        self,
        artist_id: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "last_synced_at": datetime.now(UTC),
                    "sync_status": "success",
                    "updated_at": datetime.now(UTC),
                }
            },
        )

    async def update_sync_error(
        self,
        artist_id: str,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "sync_status": "error",
                    "updated_at": datetime.now(UTC),
                }
            },
        )

    async def update_sync_empty(
        self,
        artist_id: str,
    ):
        """Record a fetch that completed and found nothing.

        The timestamp is written as well as the status, because "asked, and there
        is nothing" is a completed answer and should be cached for the TTL like
        any other. An artist who genuinely has no shows listed would otherwise be
        re-fetched on every page view, forever, and would look identical in the
        logs to an artist whose fetch keeps failing.
        """

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    artist_id
                ),
            },
            {
                "$set": {
                    "last_synced_at": datetime.now(UTC),
                    "sync_status": "empty",
                    "updated_at": datetime.now(UTC),
                }
            },
        )