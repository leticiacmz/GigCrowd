"""One named piece of work, held by exactly one worker.

The lease exists because the coordination this project already has does not
span processes: an artist's initialization claim covers one path and a
scheduler's in-process flag covers one process, while an import request and
another process can still start the same scrape. These tests pin the three
properties the rest of the design leans on - one holder, an expiring claim
so a dead worker cannot block forever, and ownership as an opaque token -
against the same fake database the rest of the suite uses, so nothing here
depends on MongoDB being reachable.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.services.work_lock import WorkLock
from tests.support.fake_mongo import FakeDatabase


def lease(database=None, key: str = "artist_sync:one", **kwargs) -> WorkLock:
    """A worker's view of one lease, over the shared fake database."""

    database = database or FakeDatabase()

    return WorkLock(database.work_locks, key, **kwargs)


class TestAcquiring:
    @pytest.mark.asyncio
    async def test_the_first_worker_takes_a_free_lease(self):
        lock = lease()

        assert await lock.acquire() is True

        stored = await lock.collection.find_one({"_id": "artist_sync:one"})

        assert stored is not None
        assert stored["owner"] == lock.owner
        assert stored["expires_at"] > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_a_second_worker_is_refused_while_the_lease_is_fresh(self):
        # Both workers look at the same lease: one shared database, two views.
        database = FakeDatabase()
        first = lease(database)
        second = lease(database)

        assert await first.acquire() is True
        assert await second.acquire() is False

        stored = await first.collection.find_one({"_id": "artist_sync:one"})

        # The refusal took nothing: the first owner still holds it.
        assert stored["owner"] == first.owner

    @pytest.mark.asyncio
    async def test_reacquiring_your_own_lease_is_idempotent(self):
        lock = lease()

        assert await lock.acquire() is True
        assert await lock.acquire() is True

    @pytest.mark.asyncio
    async def test_two_different_keys_do_not_contend(self):
        database = FakeDatabase()
        first = lease(database, key="artist_sync:one")
        second = lease(database, key="artist_sync:two")

        assert await first.acquire() is True
        assert await second.acquire() is True


class TestExpiring:
    @pytest.mark.asyncio
    async def test_an_expired_lease_is_taken_over(self):
        database = FakeDatabase()
        dead = WorkLock(database.work_locks, "k", ttl_seconds=600)
        successor = lease(database, key="k")

        assert await dead.acquire() is True

        # The holder died: its lease ages past the TTL nobody renewed.
        await database.work_locks.update_one(
            {"_id": "k"},
            {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}},
        )

        assert await successor.acquire() is True

        stored = await database.work_locks.find_one({"_id": "k"})
        assert stored["owner"] == successor.owner

    @pytest.mark.asyncio
    async def test_a_stale_worker_cannot_release_its_successors_lease(self):
        database = FakeDatabase()
        dead = WorkLock(database.work_locks, "k", ttl_seconds=600)
        successor = lease(database, key="k")

        await dead.acquire()
        await database.work_locks.update_one(
            {"_id": "k"},
            {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}},
        )
        assert await successor.acquire() is True

        # The dead worker's late cleanup must not drop the new owner's claim.
        assert await dead.release() is False

        stored = await database.work_locks.find_one({"_id": "k"})
        assert stored["owner"] == successor.owner

    @pytest.mark.asyncio
    async def test_a_live_worker_extends_its_own_lease(self):
        lock = lease(ttl_seconds=60)

        await lock.acquire()
        await database_with_older_expiry(lock)

        assert await lock.refresh() is True

        stored = await lock.collection.find_one({"_id": "artist_sync:one"})
        assert stored["expires_at"] > datetime.now(UTC)

    @pytest.mark.asyncio
    async def test_a_worker_that_stopped_renewing_does_not_refresh(self):
        database = FakeDatabase()
        lock = WorkLock(database.work_locks, "k", ttl_seconds=600)
        successor = lease(database, key="k")

        await lock.acquire()
        await database.work_locks.update_one(
            {"_id": "k"},
            {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}},
        )
        await successor.acquire()

        assert await lock.refresh() is False


class TestOwnership:
    @pytest.mark.asyncio
    async def test_ownership_is_answered_by_the_token(self):
        database = FakeDatabase()
        lock = WorkLock(database.work_locks, "k", ttl_seconds=600)
        other = lease(database, key="k")

        await lock.acquire()
        assert await lock.still_owned() is True

        await database.work_locks.update_one(
            {"_id": "k"},
            {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}},
        )
        await other.acquire()

        assert await lock.still_owned() is False
        assert await other.still_owned() is True

    @pytest.mark.asyncio
    async def test_releasing_drops_the_document(self):
        lock = lease()

        await lock.acquire()

        assert await lock.release() is True
        assert await lock.collection.find_one({"_id": "artist_sync:one"}) is None
        # A second release has nothing left to drop.
        assert await lock.release() is False


async def database_with_older_expiry(lock: WorkLock) -> None:
    """Age the lease a little, as wall-clock time would."""

    await lock.collection.update_one(
        {"_id": lock.key},
        {
            "$set": {
                "expires_at": datetime.now(UTC) - timedelta(seconds=1),
            }
        },
    )
