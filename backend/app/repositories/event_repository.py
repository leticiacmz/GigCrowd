from datetime import datetime, UTC
from typing import Iterable, Optional

from app.repositories.base import BaseRepository
from app.mappers.event_document_mapper import EventDocumentMapper
from app.domain.event import Event
from app.domain.event_artists import artist_membership_filter
from app.domain.event_provenance import (
    trusted_listing_filter,
    trusted_upcoming_filter,
)
from app.utils.ids import object_id_variants
from bson import ObjectId


# Fields a resync must never clear by writing `None` over a stored value.
#
# A gigography listing states less than an event's own page does, and routinely
# states less than an earlier extraction already obtained. Blanking these on
# every resync would make that work self-erasing. `ends_at` is deliberately here:
# a stored festival range must survive a listing that only carried a start.
# `date_source_checked_at` belongs here for the same reason - it is the marker
# that says somebody actually read the source, and losing it would demote a
# checked event back to "not checked" for every selector that reads it.
#
# The presentation fields are here for the same reason stated plainly: a
# listing that carries no description has not declared that the event has none,
# and a resync that erased the stored one would take away the only copy the
# catalogue holds. A listing that *does* carry one still corrects it, because
# a present value is written as it arrives.
#
# `festival` and `lineup` belong here for the same reason as the dates, with
# one wrinkle worth stating: their absence arrives as an empty value rather
# than as `None`. The mapper defaults a missing festival block to `None` and a
# missing lineup to `[]`, and a gigography listing routinely carries neither -
# while the stored event may hold a festival identity recovered from the
# event's own page and a lineup an earlier extraction already obtained. A
# resync that overwrote them with "nothing here" would erase them on every
# run, so an empty incoming value is treated exactly like a missing one. A
# resync that *does* carry a festival block or a lineup still corrects it.
#
# These are omitted from the update when the incoming value is `None`, not
# written as `None`. The distinction matters: writing `None` erases the stored
# value, and `$unset` would remove the field and turn a dated event back into
# an event that reads as never dated at all.
_NEVER_BLANKED_BY_A_RESYNC = frozenset(
    {
        "starts_at",
        "ends_at",
        "date_status",
        "date_source_checked_at",
        "description",
        "image_url",
        "event_status",
        "festival",
        "lineup",
    }
)

# Protected fields whose absence arrives as an empty collection instead of
# `None`. The mapper cannot emit "no lineup key" - it emits `[]` - so the
# `value is None` rule alone would let a bare listing wipe a stored lineup.
_EMPTY_IS_ABSENT = frozenset(
    {
        "lineup",
    }
)

# Fields no provider listing owns, and which a resync must not write at all.
#
# Attendance belongs to people, not to Songkick. The mapper defaults these to
# zero because it is building a new event, where zero is the honest starting
# point; on an existing event, zero is a claim - "nobody went" - that a listing
# has no standing to make. Writing it would silently erase every show log that
# points at the event, so these are dropped from the update rather than unset:
# they are always present in the incoming document, so there is no absence to
# key on. `update_attendance_counts` is the only thing that moves them.
_NEVER_OWNED_BY_A_PROVIDER = frozenset(
    {
        "going_count",
        "maybe_count",
        "went_count",
    }
)


def _without_absent_protected(
    incoming: dict,
    protected: frozenset[str],
) -> dict:
    """The `$set` half of a merge that refuses to lose a stored value.

    A `None` in the incoming document means "this listing said nothing", which
    is not the same claim as "this field is now empty". Writing it would erase
    whatever is stored, so the field is dropped from the update entirely and
    MongoDB leaves the stored value where it is. For a field in
    `_EMPTY_IS_ABSENT` an empty collection carries the same meaning, because
    the mapper has no way to emit "no lineup key" - it emits `[]`.

    Only the names in `protected` are treated this way. Everything else is
    written as it arrives, because a resync legitimately corrects a venue, a
    description or a lineup - and because only these fields are ones whose
    absence is routinely informative rather than a correction.
    """

    return {
        name: value
        for name, value in incoming.items()
        if not (
            name in protected
            and (
                value is None
                or (
                    name in _EMPTY_IS_ABSENT
                    and not value
                )
            )
        )
    }


def _is_absent_value(value) -> bool:
    """Whether an incoming value states nothing at all.

    Used for the keys inside a block that must not be written piece by
    piece with absences. `None` is the shape a parse that read nothing
    emits; an empty string, list or dict says the same thing - the source
    was asked and answered nothing. `0` and `False` are statements and
    pass through: a tracking count of zero is a figure, not silence.
    """

    if value is None:
        return True

    if isinstance(value, str):
        return not value.strip()

    if isinstance(value, (list, dict)):
        return not value

    return False


def _festival_sub_updates(festival_block) -> dict:
    """The festival fields a resync may write, keyed by dotted path.

    The block arrives whole from every parse - including one that read no
    name and therefore carries `name: None` - so writing it wholesale would
    replace the stored block with the listing's silences. Each sub-key is
    instead written under its own path (`festival.name`) only when it
    states something, which leaves the stored value for every key the
    listing did not mention, and writes nothing at all for a block that
    mentions nothing. A block that is not a dictionary is not a block and
    is dropped rather than overwriting one.
    """

    if not isinstance(festival_block, dict):
        return {}

    return {
        f"festival.{key}": value
        for key, value in festival_block.items()
        if not _is_absent_value(value)
    }


def _merge_for_resync(incoming: dict) -> dict:
    """The update document for a resync: what to `$set`, and what to add.

    Three rules are applied here, all of them about the record rather than
    about the provider that happens to be writing:

    * attendance is dropped, because a listing never measured it;
    * a protected field the listing did not state is dropped, so the stored
      value survives (see `_without_absent_protected`), and the festival
      block - which every parse sends whole - is written key by key for
      exactly the same reason (see `_festival_sub_updates`);
    * `artist_slugs` is merged additively with `$addToSet` instead of being
      replaced. The list is who the show belongs to, and the incoming half of
      a resync routinely knows fewer artists than the stored one - a
      gigography listing names the artist being browsed, while the stored set
      may already hold that artist plus lineup members resolved on an earlier
      run. Replacing it would shed valid associations every sync, and an
      empty incoming list would shed all of them. So the union is what
      persists: an association is only ever added, never dropped by a
      listing that failed to mention it.
    """

    for name in _NEVER_OWNED_BY_A_PROVIDER:
        incoming.pop(name, None)

    updates = _without_absent_protected(
        incoming,
        _NEVER_BLANKED_BY_A_RESYNC,
    )

    festival_block = updates.pop(
        "festival",
        None,
    )

    updates.update(
        _festival_sub_updates(
            festival_block,
        )
    )

    artist_slugs = updates.pop(
        "artist_slugs",
        None,
    ) or []

    updates["updated_at"] = datetime.now(UTC)

    update_document: dict = {
        "$set": updates,
    }

    if artist_slugs:
        update_document["$addToSet"] = {
            "artist_slugs": {
                "$each": artist_slugs,
            },
        }

    return update_document


class EventRepository(BaseRepository):

    def __init__(self, db):
        super().__init__(
            db,
            "events",
        )

    # ============================================================
    # GET BY ID
    # ============================================================

    async def get_by_id(
        self,
        event_id: str,
    ):

        document = await self.find_one(
            {
                "_id": ObjectId(
                    event_id
                )
            }
        )

        if not document:
            return None

        return EventDocumentMapper.to_domain(
            document
        )

    # ============================================================
    # GET BY EXTERNAL ID
    # ============================================================

    async def get_by_external_id(
        self,
        provider: str,
        external_id: str,
    ):

        document = await self.find_one(
            {
                f"external_ids.{provider}": external_id
            }
        )

        if not document:
            return None

        return EventDocumentMapper.to_domain(
            document
        )

    # ============================================================
    # GET RAW DOCUMENT BY ID
    # ============================================================

    async def get_document_by_id(
        self,
        event_id: str,
    ):

        """The stored document, for callers that read provider metadata.

        Reporting a festival means reading fields the domain `Event` does not
        model - the raw Songkick URL, the provider's own series id - so that
        answer is built from the document rather than by inventing the missing
        fields on the domain object.
        """

        if not ObjectId.is_valid(event_id):
            return None

        return await self.find_one(
            {
                "_id": ObjectId(event_id)
            }
        )

    # ============================================================
    # ARTIST MEMBERSHIP
    #
    # An event names its performers either directly (`artist_slug` /
    # `artist_slugs`) or through a structured `lineup`, which is how a festival
    # states them. Every lookup below goes through
    # `artist_membership_filter`, which covers both, so an artist cannot appear
    # on one page and vanish from another.
    # ============================================================

    @staticmethod
    def _still_ahead_dates_filter() -> dict:
        """An event that has not finished yet. Dates only, no trust check.

        Split out because a listing which mixes past and future needs the date
        predicate on its own: it has to decide what is history before it can ask
        whether a future row can be believed. Passing the combined clause would
        hand it a predicate that already answers the second question, and negating
        that answers neither.
        """

        now = datetime.now(UTC)

        return {
            "$or": [
                {"ends_at": {"$gte": now}},
                {
                    "$and": [
                        {
                            "$or": [
                                {"ends_at": {"$exists": False}},
                                {"ends_at": None},
                            ]
                        },
                        {"starts_at": {"$gte": now}},
                    ]
                },
            ]
        }

    @staticmethod
    def _still_ahead_filter() -> dict:
        """An event that has not finished yet, and can be believed."""

        return {
            "$and": [
                EventRepository._still_ahead_dates_filter(),
                # Something still to come is not the same as something real.
                #
                # An upcoming listing is the one place a future claim is made to
                # a reader, so it is where an unverifiable row has to be
                # excluded. Development fixtures stay in the database and stay
                # visible in history - they are what the development
                # environment and the manual test accounts are built on - but a
                # fixture dated next year is not an announced gig and must not
                # be presented as one.
                trusted_upcoming_filter(),
            ]
        }

    @staticmethod
    def _upcoming_filter(
        artist_slug: str,
        songkick_id: Optional[str] = None,
    ) -> dict:

        return {
            "$and": [
                artist_membership_filter(
                    artist_slug,
                    songkick_id,
                ),
                EventRepository._still_ahead_filter(),
            ]
        }

    @staticmethod
    def artist_filter(
        artist_slug: str,
        songkick_id: Optional[str] = None,
    ) -> dict:
        """Every event this artist appears on, past and future."""

        return artist_membership_filter(
            artist_slug,
            songkick_id,
        )

    # ============================================================
    # GET UPCOMING EVENTS
    # ============================================================

    async def get_by_artist_slug(
        self,
        artist_slug: str,
        songkick_id: Optional[str] = None,
    ):

        cursor = (
            self.collection
            .find(
                self._upcoming_filter(
                    artist_slug,
                    songkick_id,
                )
            )
            .sort(
                "starts_at",
                1,
            )
        )

        documents = await cursor.to_list(
            length=6
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # INSERT
    # ============================================================

    async def insert_event(
        self,
        event: Event,
    ):
        """Insert a new event, stamping the two audit fields on the way in.

        `created_at` is a property of the stored row, not of the domain value, so it
        is written here rather than carried in `Event`. A mapper that forgot it, or a
        caller that supplied its own, must not be able to decide when an event claims
        to have been imported.

        The update paths below deliberately do not touch `created_at`. They `$set` the
        domain fields and `updated_at` only, so re-importing an event records that it
        was looked at again without rewriting its history - which is what makes a
        resync safe to repeat.
        """

        document = event.model_dump(
            exclude={"id"}
        )

        moment = datetime.now(UTC)

        document["created_at"] = moment
        document["updated_at"] = moment

        await self.insert_one(
            document
        )

    # ============================================================
    # COUNTS
    # ============================================================

    async def count_by_artist_slug(
        self,
        artist_slug: str,
        songkick_id: Optional[str] = None,
    ):

        return await self.collection.count_documents(
            self.artist_filter(
                artist_slug,
                songkick_id,
            )
        )

    async def count_upcoming_by_artist_slug(
        self,
        artist_slug: str,
        songkick_id: Optional[str] = None,
    ):

        return await self.collection.count_documents(
            self._upcoming_filter(
                artist_slug,
                songkick_id,
            )
        )

    # ============================================================
    # ATTENDANCE
    # ============================================================

    async def update_attendance_counts(
        self,
        event_id: str,
        going_count: int,
        maybe_count: int,
        went_count: int,
    ):

        await self.collection.update_one(
            {
                "_id": ObjectId(
                    event_id
                )
            },
            {
                "$set": {
                    "going_count": going_count,
                    "maybe_count": maybe_count,
                    "went_count": went_count,
                }
            },
        )

    # ============================================================
    # UPCOMING BY ARTIST
    # ============================================================

    async def get_upcoming_by_artist_slug(
        self,
        artist_slug: str,
        songkick_id: Optional[str] = None,
        limit: int = 6,
    ):

        cursor = (
            self.collection
            .find(
                self._upcoming_filter(
                    artist_slug,
                    songkick_id,
                )
            )
            .sort(
                "starts_at",
                1,
            )
            .limit(limit)
        )

        documents = await cursor.to_list(
            length=limit
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # ALL EVENTS
    # ============================================================

    async def get_all_by_artist_slug(
        self,
        artist_slug: str,
        songkick_id: Optional[str] = None,
    ):

        cursor = (
            self.collection
            .find(
                {
                    "$and": [
                        self.artist_filter(
                            artist_slug,
                            songkick_id,
                        ),
                        # This listing shows history and future in one
                        # year-grouped list, so an unverifiable future event
                        # would sit in its year looking exactly like an
                        # announcement. What is already past stays: a fixture in
                        # the past makes no claim about anyone's future.
                        trusted_listing_filter(
                            self._still_ahead_dates_filter()
                        ),
                    ]
                }
            )
            .sort(
                "starts_at",
                -1,
            )
        )

        documents = await cursor.to_list(
            length=1000
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # DOCUMENTS BY ID
    # ============================================================

    async def get_documents_by_ids(
        self,
        event_ids: Iterable[str],
    ) -> list[dict]:
        """Every event behind these ids, in one query.

        Ids are matched in both storage forms, because a show log stores the id
        as a string and the event stores it as an `ObjectId`. Resolving a whole
        attendance history this way costs one request however long the history
        is, which is the point: a profile resolves its shows in a fixed number
        of queries rather than one per show.
        """

        variants: list = []

        for event_id in event_ids:

            if not event_id:
                continue

            for variant in object_id_variants(event_id):

                if variant not in variants:
                    variants.append(variant)

        if not variants:
            return []

        cursor = self.collection.find(
            {"_id": {"$in": variants}}
        )

        return await cursor.to_list(length=None)

    # ============================================================
    # LEGACY BANDsINTOWN UPDATE
    # ============================================================

    async def update_event(
        self,
        event: Event,
    ):
        """Refresh an event the legacy Bandsintown path keyed by its own id.

        The provider update above already refused to blank a stored date with a
        later `None`, and this one has to refuse it too: the invariant is about
        the record, not about which provider wrote. A weaker payload arriving
        later must not be able to turn a recovered concrete date back into a
        TBA, and attendance counters are not a listing's to reset either.

        The Bandsintown path is reachable only when a caller asks for it
        explicitly (`EventImportService.sync_artist_events(provider=...)`), but
        reachable is enough - it obeys the same rules as the path the importer
        uses by default.
        """

        bandsintown_id = event.external_ids.get(
            "bandsintown"
        )

        if not bandsintown_id:
            raise ValueError(
                "Event does not have a Bandsintown external ID."
            )

        incoming = event.model_dump(
            exclude={"id"}
        )

        await self.collection.update_one(
            {
                "external_ids.bandsintown": bandsintown_id
            },
            _merge_for_resync(
                incoming,
            ),
        )

    # ============================================================
    # LEGACY BANDsINTOWN UPSERT
    # ============================================================

    async def upsert_event(
        self,
        event: Event,
    ) -> bool:

        bandsintown_id = event.external_ids.get(
            "bandsintown"
        )

        if not bandsintown_id:
            raise ValueError(
                "Event does not have a Bandsintown external ID."
            )

        existing = await self.get_by_external_id(
            "bandsintown",
            bandsintown_id,
        )

        if existing:

            await self.update_event(
                event
            )

            return False

        await self.insert_event(
            event
        )

        return True

    # ============================================================
    # ARTIST SLUGS
    # ============================================================

    async def get_by_artist_slugs(
        self,
        artist_slugs: list[str],
    ):

        now = datetime.now(UTC)

        cursor = (
            self.collection
            .find(
                {
                    "artist_slugs": {
                        "$in": artist_slugs
                    },
                    "$or": [
                        {
                            "ends_at": {
                                "$gte": now
                            }
                        },
                        {
                            "$and": [
                                {
                                    "$or": [
                                        {
                                            "ends_at": {
                                                "$exists": False
                                            }
                                        },
                                        {
                                            "ends_at": None
                                        },
                                    ]
                                },
                                {
                                    "starts_at": {
                                        "$gte": now
                                    }
                                },
                            ]
                        },
                    ],
                }
            )
            .sort(
                "starts_at",
                1,
            )
        )

        documents = await cursor.to_list(
            length=6
        )

        return [
            EventDocumentMapper.to_domain(
                document
            )
            for document in documents
        ]

    # ============================================================
    # PROVIDER UPSERT
    # ============================================================

    async def upsert_event_by_provider(
        self,
        event: Event,
        provider: str,
    ) -> bool:

        provider_external_id = event.external_ids.get(
            provider
        )

        if not provider_external_id:

            raise ValueError(
                f"No {provider} external ID in event"
            )

        existing = await self.get_by_external_id(
            provider,
            provider_external_id,
        )

        if existing:

            await self.update_event_by_provider(
                event,
                provider,
            )

            return False

        await self.insert_event(
            event
        )

        return True

    # ============================================================
    # PROVIDER UPDATE
    # ============================================================

    async def update_event_by_provider(
        self,
        event: Event,
        provider: str,
    ):
        """Refresh an already-imported event, leaving its `created_at` alone.

        The `$set` is the domain's own fields, which do not include `created_at`, so
        an existing event keeps the moment it was first imported and only its
        `updated_at` moves. A resync is therefore a statement about the data being
        re-read, not a fresh claim that the event is new.

        A resync also never replaces a stored value with a missing one, and never
        writes attendance it did not measure.

        A gigography listing is a worse source than the event's own page, and it
        frequently states less: Songkick lists a festival date with no date on
        it even though that date has a page carrying the real range. Writing the
        listing's `None` over a date an earlier extraction already obtained would
        make that work self-erasing - every resync would put the event back in
        the incomplete state the previous run had just fixed, and the record would
        never settle. So a field the incoming event does not have leaves the
        stored one alone, and only a value the source actually states is written.

        Nor does a listing speak for attendance. Its counters are defaults it
        never measured, so they are dropped from the update entirely rather than
        written as zero. The same goes for `artist_slugs`, which is merged
        additively: a listing that names fewer artists than the stored record
        does not revoke the ones it failed to mention (see `_merge_for_resync`).
        """

        incoming = event.model_dump(
            exclude={"id"}
        )

        await self.collection.update_one(
            {
                f"external_ids.{provider}": (
                    event.external_ids[provider]
                )
            },
            _merge_for_resync(
                incoming,
            ),
        )
