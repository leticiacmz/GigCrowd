"""Make every announced artist on a festival lineup a real GigCrowd artist.

A festival announces far more artists than the catalogue has imported, and the
lineup used to render each of them as a name with a note underneath saying it
was not on GigCrowd yet. That is honest but it is also useless: a person reading
a poster wants to press the name.

So this turns an announced performer into an artist. The rules are narrow
because the failure mode is not a missing link, it is a *wrong* one that has
been written into the catalogue and will outlive the fix:

* **Songkick id decides identity.** The id is the one identifier the source and
  this catalogue share. A name never decides, because two different artists can
  share one, and matching on it links a bill to the wrong band.
* **No fuzzy matching, no first-result fallback.** Either the source stated an
  id and that id names exactly one artist, or nothing happens. A "close enough"
  match is a guess with a permanent record attached.
* **No Spotify.** The two id spaces are unrelated. Borrowing across them
  silently addresses a different artist.
* **Idempotent, and it never duplicates.** The id is the key, so the same lineup
  processed a hundred times yields the same catalogue.
* **Creating an artist is not importing one.** A new artist is a stub with a
  name, an id and a slug. It gets no `last_synced_at`, so nothing here marks it
  as needing a gigography fetch and nothing here fetches one. Artist creation
  and `ArtistSyncJob` stay separate responsibilities - which is exactly the
  separation that keeps a page view from writing to the database.

Nothing in this module runs on a read. It is called from the import path and
from an explicit command, never from `GET /artists/{slug}` or any other page
load.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from app.core.logger import get_logger
from app.repositories.artist_repository import ArtistRepository
from app.services.lineup_artist_resolver import (
    LineupArtistResolver,
    stored_id_of,
)

logger = get_logger("lineup_import")


@dataclass
class LineupImportReport:
    """What one pass over a lineup did, counted from what actually happened."""

    entries: int = 0
    entries_with_songkick_id: int = 0
    entries_without_songkick_id: int = 0
    resolved_existing: int = 0
    created: int = 0
    skipped_no_id: int = 0
    failed: int = 0
    failures: list[dict] = field(default_factory=list)

    #: Entries whose Songkick identity could not be established, so no artist
    #: was created for them. Counted separately from failures: a refusal is a
    #: correct answer about a performer, not a malfunction, and conflating the
    #: two would make a healthy pass look broken.
    rejected: int = 0
    rejections: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "lineup_entries": self.entries,
            "entries_with_songkick_id": (
                self.entries_with_songkick_id
            ),
            "entries_without_songkick_id": (
                self.entries_without_songkick_id
            ),
            "already_imported": self.resolved_existing,
            "created": self.created,
            "skipped_without_a_songkick_id": (
                self.skipped_no_id
            ),
            "rejected_unverifiable_identity": self.rejected,
            "failed": self.failed,
        }

    def summary(self) -> str:
        return (
            f"entries={self.entries} "
            f"already_imported={self.resolved_existing} "
            f"created={self.created} "
            f"skipped_no_id={self.skipped_no_id} "
            f"rejected={self.rejected} "
            f"failed={self.failed}"
        )


def _entry_fields(entry: Any) -> tuple[str, Optional[str], Optional[str], list[str]]:
    """The four things this module will accept from a lineup entry.

    Lineup entries arrive as domain objects from one path and as raw documents
    from another, so reading them through one function is what keeps the import
    and the resolver from disagreeing about which entry is which.
    """

    def read(name: str):
        if isinstance(entry, dict):
            return entry.get(name)

        return getattr(entry, name, None)

    name = str(read("name") or "").strip()

    songkick_id = read("songkick_id")

    if not songkick_id:
        # A lineup written before ids were stored carries the camelCase form.
        songkick_id = read("songkickId")

    image = read("image")

    genres = read("genres")

    if isinstance(genres, str):
        genres = [genres]

    if not isinstance(genres, list):
        genres = []

    return (
        name,
        str(songkick_id).strip() if songkick_id else None,
        str(image) if image else None,
        [str(genre) for genre in genres if genre],
    )


class LineupArtistImporter:
    """Turn announced performers into artists, by validated Songkick id only."""

    def __init__(
        self,
        artist_repository: ArtistRepository,
        delay_seconds: float = 0,
        verifier=None,
        validate: bool = True,
    ):
        self.artist_repository = artist_repository

        self.resolver = LineupArtistResolver(
            artist_repository
        )

        # No gigography is fetched here, and none may be: creating an artist and
        # importing one are different jobs, and this is the create side. The one
        # outbound request this module may make is the identity check below,
        # which reads a single artist page and writes nothing to Songkick.
        self.verifier = verifier

        # Whether a candidate id must be checked against the artist's own page
        # before a record is created. On by default and there for a reason: an
        # unverified id writes a permanent, linkable record that claims an
        # identity nobody established. It exists so tests can exercise the write
        # path without a network, and for a deliberate offline backfill.
        self.validate = validate

        # No outbound request is made beyond the identity check, so there is
        # little to be polite about. The knob spreads those checks out.
        self.delay_seconds = delay_seconds

    async def ensure_for_entries(
        self,
        entries: Iterable[Any],
    ) -> LineupImportReport:
        """Make sure every entry with a Songkick id has an artist.

        Entries already in the catalogue are counted, not touched. Entries with
        no id are counted and skipped: there is no honest way to decide who they
        are, and inventing an identity for them is worse than leaving the name
        unlinked.
        """

        report = LineupImportReport()

        materialised = list(entries)

        report.entries = len(materialised)

        # One query for the whole lineup rather than one per performer. A
        # thirty-act festival would otherwise cost thirty round trips.
        wanted_ids = []

        for entry in materialised:
            _, songkick_id, _, _ = _entry_fields(entry)

            if songkick_id:
                report.entries_with_songkick_id += 1

                wanted_ids.append(stored_id_of(songkick_id))

            else:
                report.entries_without_songkick_id += 1

        already = (
            await self.resolver.resolve(wanted_ids)
            if wanted_ids
            else {}
        )

        seen: set[str] = set()

        for index, entry in enumerate(materialised):
            (
                name,
                songkick_id,
                image,
                genres,
            ) = _entry_fields(entry)

            if not songkick_id:
                report.skipped_no_id += 1

                continue

            key = stored_id_of(songkick_id)

            if key in already:
                report.resolved_existing += 1

                continue

            # The same act can be announced twice on one bill. Creating it once
            # is not enough: without this the second pass would find nothing to
            # resolve against, because the new record is not visible until the
            # write lands, and would create a duplicate.
            if key in seen:
                report.resolved_existing += 1

                continue

            if not name:
                report.skipped_no_id += 1

                continue

            # --------------------------------------------------
            # Validate the identity
            # --------------------------------------------------
            #
            # The name on a poster is not an identity and a numeric id off a
            # festival page is not proof of one. Songkick reassigns ids, and a
            # venue or festival page carries the same numeric shape as an artist
            # URL, so an id read off a page without checking it can address a
            # different act entirely.
            #
            # Creating an Artist on an unverified id writes a permanent record
            # that every festival announcing that name will link to, and nothing
            # in the stored document would say the identity was never checked. So
            # the page is read first, and a refusal means no record at all.
            # --------------------------------------------------

            identity = None

            if self.validate:

                if self.verifier is None:
                    from app.services.songkick_artist_verifier import (
                        SongkickArtistVerifier,
                    )

                    self.verifier = SongkickArtistVerifier()

                identity = await self.verifier.verify(
                    key,
                    name=name,
                )

                if not identity.valid:
                    # Not an error: an identity that cannot be established is a
                    # performer we render as a name, which is honest. Counted so
                    # it is visible rather than silently dropped.
                    report.rejected += 1
                    report.rejections.append(
                        {
                            "songkick_id": key,
                            "name": name,
                            "reason": identity.reason,
                        }
                    )

                    seen.add(key)

                    continue

                if (
                    self.delay_seconds
                    and index
                    and index + 1 < len(materialised)
                ):
                    await asyncio.sleep(
                        self.delay_seconds
                    )

            # The artist's own page is the authority on who they are and what
            # they look like. A poster's spelling and a poster's thumbnail are
            # both that page's rendering of the same fact.
            canonical_name = (
                identity.canonical_name if identity else name
            ) or name

            canonical_image = (
                (identity.image if identity else None) or image
            )

            try:
                _, created = (
                    await self.artist_repository
                    .ensure_by_songkick_id(
                        key,
                        canonical_name,
                        image=canonical_image,
                        genres=genres,
                    )
                )

            except Exception as exc:
                # One bad name must not abandon the rest of the bill.
                logger.warning(
                    f"[LINEUP IMPORT] could not ensure "
                    f"{name!r} ({key}): {exc}"
                )

                report.failed += 1

                report.failures.append(
                    {"songkick_id": key, "name": name}
                )

                continue

            seen.add(key)

            if created:
                report.created += 1

            else:
                report.resolved_existing += 1

            if (
                self.delay_seconds
                and index
                and index + 1 < len(materialised)
            ):
                await asyncio.sleep(
                    self.delay_seconds
                )

        logger.info(
            f"[LINEUP IMPORT] {report.summary()}"
        )

        return report

    async def ensure_for_festival(
        self,
        series_id: str,
    ) -> LineupImportReport:
        """Make sure every artist announced across one festival's dates exists.

        Every edition's lineup is read first and then handled as one set, because
        a festival's bill is usually the same across its dates and treating each
        edition separately would ask the same question once per night.
        """

        events = self.artist_repository.db.events

        # One query for the whole series, projecting only the lineup. A festival
        # has a handful of editions, so this is bounded by the series rather than
        # by the catalogue.
        editions = await events.find(
            {"festival.series_id": str(series_id)},
            {"lineup": 1},
        ).to_list(length=None)

        seen: dict[str, dict] = {}

        for document in editions:
            for entry in document.get("lineup") or []:
                (
                    name,
                    songkick_id,
                    image,
                    genres,
                ) = _entry_fields(entry)

                if not songkick_id or not name:
                    continue

                key = stored_id_of(songkick_id)

                # First mention wins, so an edition that names the act slightly
                # differently does not overwrite the spelling the series is
                # known by.
                seen.setdefault(
                    key,
                    {
                        "name": name,
                        "songkick_id": key,
                        "image": image,
                        "genres": genres,
                    },
                )

        return await self.ensure_for_entries(
            seen.values()
        )
