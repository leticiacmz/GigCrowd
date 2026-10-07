"""Resolving a lineup entry to the GigCrowd artist it names.

A festival announces far more artists than GigCrowd has imported, so most lineup
entries have no page to link to. The job here is to link the ones that can be
linked *correctly* and to leave every other one alone.

The rule is deliberately narrow, because a wrong link is worse than no link:

    Songkick artist id  ->  Artist.external_ids.songkick  ->  GigCrowd slug

The Songkick id is the one identifier both systems agree on, and it is already
stored on every lineup entry. A name is never used to decide identity: two
different artists can share a name, and matching on one would link a festival
bill to the wrong band. So an entry whose id is not imported resolves to nothing
and is rendered as a plain name, which is honest.

Three properties are worth stating plainly, because each of them is a way this
could quietly go wrong:

* **Read-only.** Nothing here writes to the lineup. Resolution happens when a
  page is read, so a slug can never go stale behind a rename or a re-import.
* **Ambiguity is not resolved, it is reported.** If two imported artists claim
  the same Songkick id - which would mean a duplicated import - that id
  resolves to nothing. Picking one would be a coin flip presented as a fact.
* **Bounded.** A whole festival's lineup resolves in one query, not one per
  artist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.core.logger import get_logger

logger = get_logger("lineup_resolution")

# Artists store the id in the form that appears in a Songkick artist URL, while
# a lineup entry carries the bare numeric part. Both are the same identifier, and
# translating between them is the whole of the format difference.
EXTERNAL_ID_PREFIX = "Artist"


def external_id_for(lineup_songkick_id: str) -> str:
    """The stored form of a lineup entry's Songkick id.

    An id that is already in the stored form is passed through unchanged, so a
    caller never has to know which form it happens to be holding.
    """

    text = str(lineup_songkick_id).strip()

    if not text:
        return ""

    if text.lower().startswith(EXTERNAL_ID_PREFIX.lower()):
        return EXTERNAL_ID_PREFIX + text[len(EXTERNAL_ID_PREFIX):]

    return f"{EXTERNAL_ID_PREFIX}{text}"


def stored_id_of(external_id: str) -> str:
    """The bare numeric part of a stored Songkick id."""

    text = str(external_id).strip()

    if text.lower().startswith(EXTERNAL_ID_PREFIX.lower()):
        return text[len(EXTERNAL_ID_PREFIX):]

    return text


@dataclass
class LineupResolutionReport:
    """How much of the stored lineup can be linked, and why not.

    Every figure is counted from the documents as they are stored. The report is
    a measurement, not a repair: running it changes nothing.
    """

    entries: int = 0
    entries_with_songkick_id: int = 0
    entries_without_songkick_id: int = 0
    distinct_songkick_ids: int = 0
    resolved_ids: int = 0
    unresolved_ids: int = 0
    ambiguous_ids: int = 0
    resolved_entries: int = 0
    unresolved_entries: int = 0
    ambiguous_entries: int = 0
    ambiguous_detail: list[dict] = field(default_factory=list)
    unresolved_sample: list[dict] = field(default_factory=list)
    imported_artists: int = 0
    artists_with_songkick_id: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "lineup_entries": self.entries,
            "entries_with_songkick_id": self.entries_with_songkick_id,
            "entries_without_songkick_id": self.entries_without_songkick_id,
            "distinct_songkick_ids": self.distinct_songkick_ids,
            "resolved_distinct_ids": self.resolved_ids,
            "unresolved_distinct_ids": self.unresolved_ids,
            "ambiguous_distinct_ids": self.ambiguous_ids,
            "resolved_entries": self.resolved_entries,
            "unresolved_entries": self.unresolved_entries,
            "ambiguous_entries": self.ambiguous_entries,
            "imported_artists": self.imported_artists,
            "artists_with_songkick_id": self.artists_with_songkick_id,
        }

    def summary(self) -> str:
        return (
            f"entries={self.entries} "
            f"with_songkick_id={self.entries_with_songkick_id} "
            f"resolved_entries={self.resolved_entries} "
            f"unresolved_entries={self.unresolved_entries} "
            f"ambiguous_entries={self.ambiguous_entries} "
            f"distinct_ids={self.distinct_songkick_ids} "
            f"resolved_ids={self.resolved_ids} "
            f"unresolved_ids={self.unresolved_ids} "
            f"ambiguous_ids={self.ambiguous_ids}"
        )


class LineupArtistResolver:
    """Maps Songkick artist ids to the GigCrowd pages that exist for them."""

    def __init__(self, artist_repository):
        self.artist_repository = artist_repository

    # ============================================================
    # RESOLVING
    # ============================================================

    async def resolve(
        self,
        songkick_ids: Iterable[str],
    ) -> dict[str, str]:
        """Songkick id to GigCrowd slug, for the ids that resolve unambiguously.

        The key is the bare numeric id, which is the form a lineup entry
        carries. An id with no imported artist is absent from the result, and so
        is one that more than one artist claims.
        """

        ids = {
            str(value).strip()
            for value in songkick_ids
            if value and str(value).strip()
        }

        if not ids or self.artist_repository is None:
            return {}

        external_ids = [
            external_id_for(value) for value in ids
        ]

        documents = await (
            self.artist_repository.collection.find(
                {
                    "external_ids.songkick": {
                        "$in": external_ids
                    }
                },
                {
                    "slug": 1,
                    "name": 1,
                    "external_ids.songkick": 1,
                },
            ).to_list(length=None)
        )

        return self._index(documents)

    @staticmethod
    def _index(
        documents: list[dict],
    ) -> dict[str, str]:
        """Reduce the matching artists to a lookup, dropping any ambiguity.

        Two artists holding the same Songkick id is a duplicated import rather
        than two real identities, and it is not this module's job to decide
        which one is real. Both are dropped, so a duplicated import degrades to
        an unlinked name instead of to a confidently wrong link.
        """

        by_external: dict[str, list[str]] = {}

        for document in documents:

            external = (
                document.get("external_ids") or {}
            ).get("songkick")

            slug = document.get("slug")

            if not external or not slug:
                continue

            by_external.setdefault(
                str(external), []
            ).append(str(slug))

        resolved: dict[str, str] = {}

        for external, slugs in by_external.items():

            unique = set(slugs)

            if len(unique) == 1:

                resolved[
                    stored_id_of(external)
                ] = unique.pop()

                continue

            logger.warning(
                f"[LINEUP] Songkick id {external!r} is claimed by "
                f"{len(unique)} imported artists {sorted(unique)}; "
                "it will not be linked"
            )

        return resolved

    # ============================================================
    # MEASURING
    # ============================================================

    async def report(
        self,
        db,
        unresolved_sample: int = 10,
    ) -> LineupResolutionReport:
        """Measure how much of the stored lineup can be linked.

        This is the observability half of the module and it is entirely
        read-only: it walks the lineups, resolves them and reports the totals.
        Running it twice returns the same numbers, which is what makes it safe
        to run before and after any change and compare.
        """

        report = LineupResolutionReport()

        entries = await self._lineup_entries(db)

        report.entries = len(entries)

        counts: dict[str, int] = {}

        for entry in entries:

            songkick_id = entry.get("songkick_id")

            if songkick_id:
                report.entries_with_songkick_id += 1
            else:
                report.entries_without_songkick_id += 1

            counts[str(songkick_id or "")] = (
                counts.get(str(songkick_id or ""), 0) + 1
            )

        ids = {
            key for key in counts if key
        }

        report.distinct_songkick_ids = len(ids)

        report.imported_artists = await (
            self.artist_repository.collection.count_documents({})
        )

        report.artists_with_songkick_id = await (
            self.artist_repository.collection.count_documents(
                {
                    # `$exists` is stated explicitly rather than left to how a
                    # given engine treats a missing field inside `$nin`. The
                    # question is "does this artist carry a Songkick id", and
                    # only the presence of the field answers it.
                    "external_ids.songkick": {
                        "$exists": True,
                        "$nin": [None, ""],
                    }
                }
            )
        )

        if not ids:
            return report

        external_ids = [
            external_id_for(value) for value in ids
        ]

        documents = await (
            self.artist_repository.collection.find(
                {
                    "external_ids.songkick": {
                        "$in": external_ids
                    }
                },
                {
                    "slug": 1,
                    "name": 1,
                    "external_ids.songkick": 1,
                },
            ).to_list(length=None)
        )

        # Which stored ids are claimed by more than one artist.
        claimants: dict[str, set[str]] = {}

        for document in documents:

            external = (
                document.get("external_ids") or {}
            ).get("songkick")

            if external and document.get("slug"):
                claimants.setdefault(
                    str(external), set()
                ).add(str(document["slug"]))

        ambiguous = {
            stored_id_of(external)
            for external, slugs in claimants.items()
            if len(slugs) > 1
        }

        resolved = self._index(documents)

        report.resolved_ids = len(resolved)
        report.ambiguous_ids = len(ambiguous)
        report.unresolved_ids = (
            report.distinct_songkick_ids
            - report.resolved_ids
            - report.ambiguous_ids
        )

        names: dict[str, str] = {}

        # Counted per distinct id and multiplied by that id's own occurrences,
        # rather than once per entry. Walking the entries and adding the
        # occurrence count each time would count an id that appears five times
        # as twenty-five, and the totals would exceed the number of entries.
        for songkick_id, occurrences in counts.items():

            if not songkick_id:
                continue

            if songkick_id in resolved:
                report.resolved_entries += occurrences
                continue

            if songkick_id in ambiguous:
                report.ambiguous_entries += occurrences
                continue

            report.unresolved_entries += occurrences

        for entry in entries:

            songkick_id = str(entry.get("songkick_id") or "")

            if not songkick_id or songkick_id in resolved:
                continue

            if songkick_id in ambiguous:
                continue

            names.setdefault(songkick_id, entry.get("name"))

        report.ambiguous_detail = [
            {
                "songkick_id": songkick_id,
                "slugs": sorted(
                    claimants.get(
                        external_id_for(songkick_id), set()
                    )
                ),
            }
            for songkick_id in sorted(ambiguous)[:20]
        ]

        report.unresolved_sample = [
            {"songkick_id": key, "name": names.get(key)}
            for key in sorted(names)
        ]

        logger.info(f"[LINEUP] {report.summary()}")

        return report

    async def _lineup_entries(
        self,
        db,
    ) -> list[dict]:
        """Every stored lineup entry, flattened out of the events collection.

        The projection keeps only the two fields resolution needs, so the report
        does not carry images and URLs it will never read.
        """

        pipeline = [
            {"$unwind": "$lineup"},
            {
                "$project": {
                    "_id": 0,
                    "name": "$lineup.name",
                    "songkick_id": {
                        "$ifNull": [
                            "$lineup.songkick_id",
                            "$lineup.songkickId",
                        ]
                    },
                }
            },
        ]

        cursor = db.events.aggregate(pipeline)

        entries: list[dict] = []

        async for item in cursor:

            entries.append(item)

        return entries
