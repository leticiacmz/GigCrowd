"""Give artists the photograph Songkick already has for them.

Every artist in the catalogue has `image: null`, so every artist renders as a
placeholder even where Songkick publishes a real photograph. This fills those in
from Songkick and nothing else - no other image service, no image search, and no
constructed URL.

Three rules the script holds itself to:

1. An existing valid image is never overwritten. A better picture is not worth
   losing a good one, and an empty string is not worth replacing either.
2. Nothing is invented. Every URL written appears verbatim on the artist's own
   Songkick page, and is scoped to that artist's ID in the path.
3. Nothing is deleted. An artist Songkick has no usable photograph for is left
   exactly as it is, with a placeholder doing the work.

Bounded by `--limit`, paced by `--delay`, idempotent, and dry-run by default:

    python -m app.scripts.backfill_artist_images
    python -m app.scripts.backfill_artist_images --apply
    python -m app.scripts.backfill_artist_images --verify
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, ".")

from datetime import UTC, datetime

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import settings
from app.core.logger import get_logger
from app.domain.artist_image import is_valid_artist_image
from app.providers.songkick.client import SongkickClient

logger = get_logger("backfill_artist_images")


def has_usable_image(artist: dict) -> bool:
    """Whether this artist already shows something.

    A stored URL is only honoured when it looks like a real image, so a blank or a
    malformed value counts as missing and gets filled in.
    """

    image = (artist.get("image") or "").strip()

    if not image:
        return False

    return image.lower().startswith(("http://", "https://", "//"))


async def read_artists(database) -> list[dict]:
    return await database.artists.find({}).sort("slug", 1).to_list(
        length=5000
    )


async def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the images (without this, nothing is changed)",
    )

    parser.add_argument(
        "--verify",
        action="store_true",
        help="report what is stored now, and change nothing",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="how many artists to visit in one run",
    )

    parser.add_argument(
        "--delay",
        type=float,
        default=1.5,
        help="seconds between artists, as politeness toward Songkick",
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "replace an existing image. Off by default, because an existing "
            "image is never worse than a missing one"
        ),
    )

    args = parser.parse_args()

    client = AsyncIOMotorClient(
        settings.MONGODB_URL, tz_aware=True
    )

    database = client[settings.DATABASE_NAME]

    artists = await read_artists(database)

    already = [a for a in artists if has_usable_image(a)]

    missing = [a for a in artists if not has_usable_image(a)]

    print("=" * 72)
    print("STATE")
    print("=" * 72)
    print(f"   artists            : {len(artists)}")
    print(f"   with an image      : {len(already)}")
    print(f"   without an image   : {len(missing)}")

    if args.verify:

        print()
        print("=" * 72)
        print("STORED IMAGES")
        print("=" * 72)

        for artist in artists:

            print(
                f"   {artist['slug']:18} "
                f"{str(artist.get('image') or '-')[:60]}"
            )

        client.close()
        return 0

    targets = artists if args.force else missing

    if not targets:

        print()
        print("Nothing to do: every artist already shows an image.")
        client.close()
        return 0

    targets = targets[: max(1, args.limit)]

    print(f"   will visit         : {len(targets)}")
    print(f"   writing            : {args.apply}")

    songkick = SongkickClient()

    found = 0
    skipped = 0
    unchanged = 0
    updates: list[tuple[str, str]] = []

    print()
    print("=" * 72)
    print("ARTISTS")
    print("=" * 72)

    for index, artist in enumerate(targets):

        slug = artist["slug"]
        name = artist["name"]

        songkick_id = (artist.get("external_ids") or {}).get(
            "songkick"
        )

        image = await songkick.get_artist_image(
            artist_id=songkick_id,
            artist_name=name,
        )

        if image is None:

            skipped += 1

            print(
                f"   {slug:18} no image published by "
                f"Songkick; left as it is"
            )

        elif not is_valid_artist_image(image):

            # Defensive: the reader should never produce one of these, and storing
            # it anyway would put a bad URL in the catalogue.
            skipped += 1

            print(
                f"   {slug:18} refused a non-photograph "
                f"URL: {image[:50]}"
            )

        else:

            found += 1

            if has_usable_image(artist):

                unchanged += 1

                print(
                    f"   {slug:18} already has an image; "
                    f"not replacing it"
                )

            else:

                updates.append((slug, image))

                print(f"   {slug:18} -> {image}")

        if index + 1 < len(targets) and args.delay:

            await asyncio.sleep(args.delay)

    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"   images found       : {found}")
    print(f"   no image available : {skipped}")
    print(f"   left alone         : {unchanged}")
    print(f"   to write           : {len(updates)}")

    if not args.apply:

        print()
        print("Dry run. Pass --apply to write.")
        client.close()
        return 0

    written = 0
    moment = datetime.now(UTC)

    for slug, image in updates:

        result = await database.artists.update_one(
            {"slug": slug, "$or": [
                {"image": None},
                {"image": ""},
                {"image": {"$exists": False}},
            ]},
            {"$set": {"image": image, "updated_at": moment}},
        )

        if result.modified_count:

            written += 1

    print(f"   written            : {written}")

    print()
    print("=" * 72)
    print("VERIFY")
    print("=" * 72)

    after = await read_artists(database)

    for artist in after:

        print(
            f"   {artist['slug']:18} "
            f"{str(artist.get('image') or '-')[:60]}"
        )

    print()
    print(f"   with an image now  : "
          f"{sum(1 for a in after if has_usable_image(a))}"
          f"/{len(after)}")

    client.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))