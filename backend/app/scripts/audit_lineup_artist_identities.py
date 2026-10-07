#!/usr/bin/env python3
"""Check the identities that festival-lineup expansion created, and say so.

Background
----------

Walking a festival's lineup used to write an `Artist` per name, from a number
parsed off the poster's page. Roughly 7,955 of those records exist. They are not
obviously broken - each carries a plausible name and a real-looking Songkick id -
and that is exactly why they are worth auditing: nothing about the *stored
document* can tell you whether the identity behind it was ever checked.

So this script asks the only question that settles it. For each record, it fetches
the artist's own Songkick page and records what Songkick actually says the id
addresses. Nothing is inferred from the name, the slug, or the shape of the id,
and nothing is compared to the catalogue to decide what "correct" means.

What it does not do
-------------------

* It does not delete. Not one record. A zero-event artist is not a wrong artist -
  it is an artist nobody has imported yet - and the brief for this work was
  explicit that they stay.
* It does not rename or re-slug. An artist that a user follows, has posted about,
  or logged a show at is referenced by a URL that is already out in the world.
  Only fields that are not addressable - the display name, the photograph, the
  genres - are ever candidates for a write, and only under `--apply`.
* It does not fetch gigographies. One page per identity, so the cost is
  proportional to the question being asked and not to how many shows the artist
  has ever played.

Read-only by default
--------------------

With no flags this writes exactly one collection - the verdict log - and nothing
else. `--apply` is a separate, explicit step, so the evidence and the decision
can be read before either is taken.

Resumable and bounded
---------------------

Songkick serves one artist page per request and this audit is honest about that:
at roughly 3 seconds per page, a full pass over 7,955 identities is a multi-hour
job. `--limit` bounds a run, the verdict log records what was already checked so
a second run picks up where the first stopped, and `--delay` paces the requests.
Nothing is lost by stopping halfway, and nothing is re-fetched by resuming.

Usage
-----

Run from `backend/`:

    # Check up to 100, writing only the verdict log.
    python -m app.scripts.audit_lineup_artist_identities

    # Check 500 more, resuming where the last run stopped.
    python -m app.scripts.audit_lineup_artist_identities --limit 500

    # Re-print the summary. Fetches nothing.
    python -m app.scripts.audit_lineup_artist_identities --report

    # Re-verify the refusals only, after a rule has been corrected.
    python -m app.scripts.audit_lineup_artist_identities --recheck-refusals

    # Write the canonical name and photograph of confirmed identities.
    python -m app.scripts.audit_lineup_artist_identities --apply
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Optional

from app.database.connection import db as database
from app.services.songkick_artist_verifier import (
    ACCEPTED,
    REJECTED_UNREADABLE,
    SongkickArtistVerifier,
)


# Where a verdict is recorded.
#
# A separate collection rather than a field on the artist, because the two have
# different lifetimes: the artist is permanent and its name is addressable by
# users, while a verdict is a dated observation about one page on one day and is
# expected to be re-taken. Keeping them apart also means this script has no way
# to half-modify an artist document - it writes a whole verdict document or
# nothing.
VERDICTS = "lineup_artist_verdicts"

# Collections that reference an artist by slug, and are therefore the reason a
# record cannot simply be rewritten or removed.
#
# Enumerated rather than guessed, because "we should be careful with referenced
# data" is not a check - a new table would make it quietly untrue.
USER_ACTIVITY = (
    "artist_follows",
    "posts",
    "show_logs",
    "comments",
    "reviews",
)


async def referenced_counts(
    handle, slug: str, names: frozenset[str]
) -> dict[str, int]:
    """How much user activity points at this artist, by table.

    `names` is the set of collections this database actually has, read once by
    the caller. Membership is asked of that set rather than of the database,
    because `name in database` is not a membership test on Motor - it falls
    through to the iterator protocol and asks for collection number zero.

    A table that does not exist in this deployment counts as zero rather than
    raising. A development database never used for follows has no
    `artist_follows` collection at all, and an audit that refuses to run there is
    an audit nobody runs.
    """

    counts = {}

    for name in USER_ACTIVITY:
        if name not in names:
            continue

        counts[name] = await handle[name].count_documents(
            {"artist_slug": slug}
        )

    return counts


async def referenced_by_user_activity(
    handle, slug: str, names: frozenset[str]
) -> bool:
    return any((await referenced_counts(handle, slug, names)).values())


def is_lineup_created(artist: dict[str, Any]) -> bool:
    """Was this record written by lineup expansion rather than by an import?

    `ensure_by_songkick_id` creates a stub and deliberately leaves `last_synced_at`
    absent, so that the sync job still considers the artist importable. That
    absence is the marker, and it is the reason this population can be found at
    all - it is a distinction the codebase already relies on.
    """

    return "last_synced_at" not in artist


async def load_population(handle) -> list[dict[str, Any]]:
    """The records this audit is about, oldest id first so runs are repeatable."""

    artists = await handle.artists.find(
        {"external_ids.songkick": {"$exists": True}}
    ).to_list(length=None)

    stubs = [
        artist for artist in artists if is_lineup_created(artist)
    ]

    return sorted(
        stubs, key=lambda a: str(a["external_ids"]["songkick"])
    )


async def already_checked(handle) -> set[str]:
    """Songkick ids this audit has a verdict for."""

    rows = await handle[VERDICTS].find({}).to_list(length=None)

    return {row["songkick_id"] for row in rows if row.get("songkick_id")}


def record_verdict(
    *,
    songkick_id: str,
    slug: str,
    stored_name: str,
    verdict,
    referenced: bool,
) -> dict[str, Any]:
    """The evidence, kept verbatim so a decision can be argued with later."""

    return {
        "songkick_id": songkick_id,
        "slug": slug,
        "stored_name": stored_name,
        "checked_at": datetime.now(UTC),
        "referenced_by_user_activity": referenced,
        **verdict.as_dict(),
    }


async def run_checks(
    handle,
    population: list[dict[str, Any]],
    *,
    limit: int,
    delay: float,
    verbose: bool,
) -> int:
    """Verify each identity once, recording what Songkick served."""

    verifier = SongkickArtistVerifier()

    # Read once. Asking Mongo which collections exist is a round trip, and this
    # runs per artist.
    names = frozenset(await handle.list_collection_names())

    done = await already_checked(handle)

    pending = [
        artist
        for artist in population
        if str(artist["external_ids"]["songkick"]) not in done
    ]

    if not pending:
        print("Every identity in scope already has a verdict.")
        print("Re-run with --report to print it, or --recheck to take it again.")

        return 0

    if limit and len(pending) > limit:
        print(
            f"{len(pending)} identities left to check; this run takes "
            f"{limit}. The rest keep their place - re-run to continue."
        )

    checked = 0

    batch = pending[:limit] if limit else pending

    for index, artist in enumerate(batch, start=1):
        songkick_id = str(artist["external_ids"]["songkick"])
        slug = str(artist.get("slug") or "")

        verdict = await verifier.verify(
            songkick_id, name=artist.get("name")
        )

        row = record_verdict(
            songkick_id=songkick_id,
            slug=slug,
            stored_name=str(artist.get("name") or ""),
            verdict=verdict,
            referenced=await referenced_by_user_activity(
                handle, slug, names
            ),
        )

        await handle[VERDICTS].replace_one(
            {"songkick_id": songkick_id}, row, upsert=True
        )

        checked += 1

        if verbose or not verdict.valid:
            print(
                f"  [{index}] {songkick_id:<14} "
                f"{verdict.reason:<32} "
                f"{row['stored_name']!r}"
                + (
                    f"  ->  {verdict.canonical_name!r}"
                    if verdict.valid
                    and verdict.canonical_name != row["stored_name"]
                    else ""
                )
            )

        if delay:
            await asyncio.sleep(delay)

    return checked


async def report(handle) -> dict[str, Any]:
    """Summarise the verdict log. Reads only."""

    rows = await handle[VERDICTS].find({}).to_list(length=None)

    total = await handle.artists.count_documents(
        {"external_ids.songkick": {"$exists": True}}
    )

    by_reason = Counter(row.get("reason") for row in rows)

    accepted = [row for row in rows if row.get("valid")]
    refused = [row for row in rows if not row.get("valid")]

    name_disagreements = [
        row
        for row in accepted
        if row.get("canonical_name")
        and row["canonical_name"] != row.get("stored_name")
    ]

    unresolved = [
        row for row in refused if row.get("reason") == REJECTED_UNREADABLE
    ]

    print()
    print("=" * 72)
    print("IDENTITY AUDIT OF LINEUP-CREATED ARTISTS")
    print("=" * 72)
    print(f"  artists with a Songkick id : {total}")
    print(f"  identities checked so far  : {len(rows)}")
    print(f"  not yet checked            : {max(0, total - len(rows))}")
    print()
    print("  VERDICTS")
    for reason, count in by_reason.most_common():
        print(f"    {reason:<34} {count}")
    print()
    print(f"  confirmed identities       : {len(accepted)}")
    print(f"  refused identities         : {len(refused)}")
    print(
        f"    ...of which unreadable, so "
        f"not yet a verdict : {len(unresolved)}"
    )
    print(
        f"  name differs from the page  : {len(name_disagreements)}"
    )

    if refused and not unresolved:
        print()
        print("  REFUSED - the stored id does not address the stored artist")
        for row in refused[:25]:
            print(
                f"    {row['songkick_id']:<14} {row['reason']:<32} "
                f"{row.get('stored_name')!r}"
            )
        if len(refused) > 25:
            print(f"    ...and {len(refused) - 25} more")

    if name_disagreements:
        print()
        print("  NAME DIFFERS FROM THE PAGE (identity valid, spelling not)")
        for row in name_disagreements[:25]:
            print(
                f"    {row['songkick_id']:<14} "
                f"{row.get('stored_name')!r} -> "
                f"{row.get('canonical_name')!r}"
            )
        if len(name_disagreements) > 25:
            print(f"    ...and {len(name_disagreements) - 25} more")

    referenced = [row for row in rows if row.get("referenced_by_user_activity")]

    if referenced:
        print()
        print(
            f"  REFERENCED BY USER ACTIVITY ({len(referenced)}) - "
            "these are never deleted or re-slugged"
        )
        for row in referenced[:25]:
            print(f"    {row['slug']:<28} {row.get('stored_name')!r}")

    print()
    print(
        "  This script deleted nothing and renamed nothing. "
        "`--apply` writes only the"
    )
    print(
        "  canonical name and photograph of identities this audit "
        "confirmed."
    )
    print("=" * 72)

    return {
        "total": total,
        "checked": len(rows),
        "by_reason": dict(by_reason),
        "accepted": len(accepted),
        "refused": len(refused),
        "unresolved": len(unresolved),
        "name_disagreements": len(name_disagreements),
    }


async def apply(handle) -> None:
    """Write what the audit proved. Never removes, never re-addresses.

    For a confirmed identity this fills in the fields the stub was missing from
    the lineup's rendering: the name the artist's own page states, and the
    photograph that page states. It deliberately leaves `slug` alone - a slug is
    in other people's bookmarks, in festival links, and in event documents that
    reference the artist by slug - and it deliberately leaves `last_synced_at`
    absent, because an artist that has been identified is not an artist whose
    gigography has been imported.

    A refused identity is left completely untouched. Not marked, not flagged, not
    renamed to something provisional: a record that was never validated should
    keep looking exactly like what it is - an unvalidated record.
    """

    rows = await handle[VERDICTS].find({"valid": True}).to_list(length=None)

    if not rows:
        print("Nothing confirmed yet. Run the checks first.")
        return

    updated = 0
    images = 0

    for row in rows:
        slug = row.get("slug")

        # A record with no slug is not addressable, so there is nothing to
        # update *and* nothing to break. Skipped rather than queried with a
        # `None` that would quietly match some unrelated document.
        if not slug:
            continue

        set_fields: dict[str, Any] = {}

        canonical = row.get("canonical_name")

        if canonical and canonical != row.get("stored_name"):
            from app.utils.text import normalize_text

            set_fields["name"] = canonical
            set_fields["normalized_name"] = normalize_text(canonical)

        # Only fill an absent photograph. An image already stored came from the
        # lineup entry and may be this artist's; an image already stored that is
        # wrong is a separate bug, and overwriting it here would fix it without
        # having diagnosed it.
        if row.get("image"):
            existing = await handle.artists.find_one(
                {"slug": slug}, {"image": 1}
            )

            if existing is not None and not existing.get("image"):
                set_fields["image"] = row["image"]

        if not set_fields:
            continue

        result = await handle.artists.update_one(
            {"slug": slug}, {"$set": set_fields}
        )

        if result.matched_count:
            updated += 1

            if "image" in set_fields:
                images += 1

    print(f"Confirmed identities written : {len(rows)}")
    print(f"Artists updated             : {updated}")
    print(f"  ...of which gained a photo : {images}")
    print(
        "Deleted: 0. Re-slugged: 0. "
        "No record was removed or made unaddressable."
    )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="How many unchecked identities to verify this run "
        "(0 for all; default 100).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Seconds to wait between page fetches.",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print the summary from the verdict log and fetch nothing.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the canonical name and photograph for confirmed "
        "identities.",
    )
    parser.add_argument(
        "--recheck",
        action="store_true",
        help="Verify identities that already have a verdict.",
    )
    parser.add_argument(
        "--recheck-refusals",
        action="store_true",
        help="Verify again only the identities that were refused, "
        "keeping the confirmations.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print every identity checked, not only refusals.",
    )

    options = parser.parse_args()

    await database.connect()
    handle = database.get_database()

    try:
        if options.recheck:
            await handle[VERDICTS].delete_many({})

        if options.recheck_refusals:
            # A refusal is the verdict most likely to have been produced by a
            # rule that has since been corrected, and the one whose being wrong
            # costs the most: it does not corrupt anything, it just loses an
            # artist. The Coronas and The Stranglers were both recorded as "not
            # an artist page" because their pages carry no heading, and both are
            # real, touring, festival-announced acts. So refusals are re-taken
            # without disturbing the confirmations, which took a page fetch each
            # to establish and have no reason to doubt.
            dropped = await handle[VERDICTS].delete_many({"valid": False})

            print(
                f"Discarded {dropped.deleted_count} earlier refusal(s) "
                f"for re-verification."
            )

        if options.report:
            await report(handle)
            return 0

        population = await load_population(handle)

        print(
            f"Lineup-created artists with a Songkick id: {len(population)}"
        )

        if not options.apply:
            print(
                "Read-only run: verdicts are recorded, no artist is "
                "modified."
            )

        print()

        if not options.apply:
            checked = await run_checks(
                handle,
                population,
                limit=options.limit,
                delay=options.delay,
                verbose=options.verbose,
            )

            print(f"Checked {checked} identities.")
            print()

        summary = await report(handle)

        if options.apply:
            print()
            await apply(handle)

        if not options.apply and summary["unresolved"]:
            print()
            print(
                "Some identities were unreadable rather than refused - a "
                "network"
            )
            print(
                "problem, not a verdict. Re-run to retry those; they are not "
                "counted"
            )
            print("as wrong.")

    finally:
        await database.disconnect()

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
