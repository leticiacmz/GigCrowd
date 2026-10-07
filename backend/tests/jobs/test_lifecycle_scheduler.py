"""The lifecycle pass on the real scheduler.

The enrichment job and the lifecycle job share one tick, one switch and one
status endpoint. What has to hold is that neither can stop the other, and that
the lifecycle stays off unless somebody asks for it.
"""
from __future__ import annotations

from typing import Any, Optional

import pytest

from app.jobs.scheduler import EnrichmentScheduler


class Boom(RuntimeError):
    pass


def scheduler_with(
    *,
    job_runner=None,
    lifecycle_runner=None,
    lifecycle_enabled: bool = False,
    service: Any = object(),
) -> EnrichmentScheduler:
    return EnrichmentScheduler(
        enabled=False,
        service_factory=lambda: service,
        job_runner=job_runner or (lambda svc, config: None),
        lifecycle_enabled=lifecycle_enabled,
        lifecycle_runner=lifecycle_runner,
    )


class TestTheLifecycleIsOffByDefault:
    @pytest.mark.asyncio
    async def test_it_does_not_run_when_it_was_not_switched_on(self):
        calls: list[str] = []

        scheduler = scheduler_with(
            lifecycle_enabled=False,
            lifecycle_runner=lambda *_: calls.append("ran"),
        )

        await scheduler.run()

        assert calls == []

    def test_it_is_off_unless_configuration_says_otherwise(self):
        from app.config import settings

        # A development database must never start notifying people by accident.
        assert settings.EVENT_LIFECYCLE_SCHEDULER_ENABLED is False
        assert settings.EVENT_LIFECYCLE_SCHEDULER_BATCH_SIZE > 0
        assert settings.EVENT_LIFECYCLE_SCHEDULER_LOOKBACK_HOURS > 0

    @pytest.mark.asyncio
    async def test_it_does_run_once_switched_on(self):
        calls: list[str] = []

        scheduler = scheduler_with(
            lifecycle_enabled=True,
            lifecycle_runner=lambda *_: calls.append("ran"),
        )

        await scheduler.run()

        assert calls == ["ran"]

    def test_the_status_reports_it(self):
        status = scheduler_with(
            lifecycle_enabled=True
        ).get_status()

        assert status["lifecycle"]["enabled"] is True
        assert "batch_size" in status["lifecycle"]
        assert status["lifecycle"]["last_run"] is None


class TestTheTwoJobsDoNotBlockEachOther:
    @pytest.mark.asyncio
    async def test_a_failed_enrichment_pass_still_runs_the_lifecycle(self):
        # A dead Songkick request must not stop prompts that are already
        # overdue for real people.
        calls: list[str] = []

        async def broken(*_args):
            raise Boom("songkick is down")

        scheduler = scheduler_with(
            job_runner=broken,
            lifecycle_enabled=True,
            lifecycle_runner=lambda *_: calls.append("lifecycle"),
        )

        # The failure is contained rather than propagated.
        assert await scheduler.run() is None

        assert calls == ["lifecycle"]

    @pytest.mark.asyncio
    async def test_a_failed_lifecycle_pass_does_not_lose_the_enrichment_result(
        self,
    ):
        async def enrichment(*_args):
            return "enrichment-result"

        def broken_lifecycle(*_args):
            raise Boom("notifications collection is down")

        scheduler = scheduler_with(
            job_runner=enrichment,
            lifecycle_enabled=True,
            lifecycle_runner=broken_lifecycle,
        )

        result = await scheduler.run()

        assert result == "enrichment-result"

    @pytest.mark.asyncio
    async def test_a_failed_lifecycle_pass_is_not_swallowed_silently(
        self,
        caplog,
    ):
        def broken_lifecycle(*_args):
            raise Boom("notifications collection is down")

        scheduler = scheduler_with(
            lifecycle_enabled=True,
            lifecycle_runner=broken_lifecycle,
        )

        await scheduler.run()

        assert any(
            "lifecycle pass failed" in record.message
            for record in caplog.records
        )


class TestWhatThePassDidIsVisible:
    @pytest.mark.asyncio
    async def test_the_last_lifecycle_pass_is_reported(self):
        class Result:
            @staticmethod
            def as_dict() -> dict:
                return {"notified": 3, "failed": 0}

        scheduler = scheduler_with(
            lifecycle_enabled=True,
            lifecycle_runner=lambda *_: None,
        )

        scheduler.last_lifecycle_result = Result.as_dict()

        status = scheduler.get_status()

        assert status["lifecycle"]["last_run"] == {
            "notified": 3,
            "failed": 0,
        }
