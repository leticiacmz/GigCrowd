"""Report what the stored events are missing, without touching Songkick.

Usage, from `backend/`:

    python -m app.scripts.report_event_gaps
"""
import asyncio
import sys

from app.services.event_enrichment_service import (
    EventEnrichmentService,
)


async def main() -> int:
    from app.database.connection import db
    from app.repositories.event_repository import (
        EventRepository,
    )

    await db.connect()

    try:
        service = EventEnrichmentService(
            EventRepository(db.get_database())
        )

        preview = await service.report_only()

        print("Event gap report")
        print("-" * 52)

        for key, value in preview.items():
            if key == "sample":
                continue

            print(f"  {key:26}: {value}")

        if preview["sample"]:
            print()
            print("  eligible examples:")

            for plan in preview["sample"]:
                print(
                    f"    {plan['event_id']} "
                    f"{plan['title'][:38]!r} "
                    f"missing={plan['missing']}"
                )

        return 0

    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))