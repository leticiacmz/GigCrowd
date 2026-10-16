"""A lease that only one worker holds, across processes.

Equivalent work can be started from several places at once - an import
request, the scheduler, a second backend process - and the coordination this
project already has does not span processes: an artist's initialization
claim covers one path, and the scheduler's `_running` flag covers one
process. This adds the one thing missing: a named lease whose ownership is
decided by an atomic document update in the same MongoDB the catalogue
lives in. No new infrastructure, no new service - a collection beside the
others, holding one document per named piece of work.

Three properties the lease holds itself to:

* **One holder.** Acquiring is an atomic claim (`find_one_and_update` on the
  expired-or-own clause, then an insert guarded by the primary key), so two
  processes racing for the same key leave exactly one winner.
* **A dead holder does not block forever.** Every lease expires at a known
  moment; a worker that died while holding it is taken over by the next
  attempt, which finds `expires_at` in the past. The lease is a freshness
  bound, not a promise - callers choose a TTL longer than the longest run
  they expect.
* **Ownership is an opaque token.** A takeover's owner differs from the
  stale worker's, so the stale worker cannot release the new owner's lease
  and its late writes can be recognised and refused.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Optional

from pymongo import ReturnDocument


class WorkLock:
    """One named lease. An instance is one worker's view of it."""

    def __init__(
        self,
        collection,
        key: str,
        ttl_seconds: int = 900,
        owner: Optional[str] = None,
    ):
        self.collection = collection
        self.key = str(key)
        self.ttl_seconds = int(ttl_seconds)
        self.owner = owner or uuid.uuid4().hex

    # ============================================================
    # CLAIMING
    # ============================================================

    async def acquire(self) -> bool:
        """Take the lease, or report that somebody else holds it.

        An existing lease is taken over only when it has expired (or is
        already ours, which makes re-acquire idempotent). A fresh lease held
        by somebody else returns `False` without waiting: the caller reuses
        what is already stored, which is the point of the coordination.
        """

        now = datetime.now(UTC)
        expires_at = now + timedelta(
            seconds=self.ttl_seconds
        )

        claimed = await self.collection.find_one_and_update(
            {
                "_id": self.key,
                "$or": [
                    {"expires_at": {"$lte": now}},
                    {"owner": self.owner},
                ],
            },
            {
                "$set": {
                    "owner": self.owner,
                    "expires_at": expires_at,
                    "acquired_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )

        if claimed is not None:
            return True

        existing = await self.collection.find_one(
            {"_id": self.key}
        )

        if existing is not None:
            # Held, and fresh. The other holder wins.
            return False

        try:

            await self.collection.insert_one(
                {
                    "_id": self.key,
                    "owner": self.owner,
                    "expires_at": expires_at,
                    "acquired_at": now,
                }
            )

            return True

        except Exception:
            # Two processes found no lease and inserted at the same instant.
            # The primary key makes exactly one of them real; the loser
            # reports the lease as taken rather than waiting.
            return False

    # ============================================================
    # HOLDING
    # ============================================================

    async def still_owned(self) -> bool:
        """Whether this worker's token is the one on the lease right now."""

        document = await self.collection.find_one(
            {"_id": self.key, "owner": self.owner},
            {"_id": 1},
        )

        return document is not None

    async def refresh(self) -> bool:
        """Extend the lease while the work is still going.

        A long run renews its own claim, so a slow-but-alive worker is never
        taken over for being slow. A worker that stopped renewing is the one
        the lease is designed to recover from.
        """

        result = await self.collection.update_one(
            {"_id": self.key, "owner": self.owner},
            {
                "$set": {
                    "expires_at": datetime.now(UTC)
                    + timedelta(seconds=self.ttl_seconds)
                }
            },
        )

        return result.matched_count == 1

    async def release(self) -> bool:
        """Drop the lease, but only if this worker still holds it.

        Releasing after a takeover would delete the new owner's lease, so the
        owner token travels with the delete.
        """

        result = await self.collection.delete_one(
            {"_id": self.key, "owner": self.owner}
        )

        return result.deleted_count == 1
