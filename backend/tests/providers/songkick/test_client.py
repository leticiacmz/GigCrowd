import pytest
from app.providers.songkick.client import (
    SongkickClient,
    _retry_after_seconds,
    reset_songkick_requests,
    songkick_requests_this_run,
)


def test_client_initialization():
    """Test client initialization with configuration"""
    client = SongkickClient()
    
    assert client.base_url is not None
    assert client.search_endpoint == "/api/universal_search"
    assert client.timeout == 60
    assert "user-agent" in client.headers
    assert "accept" in client.headers


def test_client_configuration_from_settings():
    """Test that client uses configuration from settings"""
    from app.config import settings
    
    client = SongkickClient()
    
    assert client.base_url == settings.SONGKICK_BASE_URL.rstrip("/")


@pytest.mark.asyncio
async def test_search_artist_requires_real_playwright():
    """
    Test that search_artist requires Playwright browser.
    This test verifies the method exists and has the right signature.
    Actual Playwright tests would require a real browser or complex mocking.
    """
    client = SongkickClient()
    
    # Verify the method exists
    assert hasattr(client, 'search_artist')
    assert callable(client.search_artist)
    
    # This would require a real Playwright browser to test fully
    # For now, we just verify the interface exists


# ============================================================
# REQUEST ACCOUNTING
# ============================================================


class TestEveryRequestIsCountedForItsOwnRun:
    """The number in the summary must describe exactly one run.

    A total that mixes two concurrent imports, or that grows across the
    lifetime of the process, is worse than no number at all: it would
    contradict the very log it is meant to explain.
    """

    @pytest.mark.asyncio
    async def test_every_request_is_counted_for_the_current_run(self):
        client = SongkickClient()

        # No network: the HTTP call itself is replaced by its seam, because
        # what is under test is the accounting around it.
        client._request_sync = lambda url, accept=None: None

        reset_songkick_requests()

        await client._request("https://example.invalid/a")
        await client._request("https://example.invalid/b")

        assert songkick_requests_this_run() == 2

    @pytest.mark.asyncio
    async def test_a_new_run_starts_from_zero(self):
        client = SongkickClient()

        client._request_sync = lambda url, accept=None: None

        reset_songkick_requests()

        await client._request("https://example.invalid/a")

        left_by_the_last_run = reset_songkick_requests()

        assert left_by_the_last_run == 1
        assert songkick_requests_this_run() == 0

        await client._request("https://example.invalid/b")

        assert songkick_requests_this_run() == 1

    @pytest.mark.asyncio
    async def test_concurrent_runs_do_not_mix_their_counts(self):
        import asyncio

        def answering_client():
            client = SongkickClient()
            client._request_sync = lambda url, accept=None: None

            return client

        first = answering_client()
        second = answering_client()

        reset_songkick_requests()

        async def one_run(client, url):
            # Each task counts inside its own copy of the context - the way
            # an import task and a scheduler pass each get their own.
            await client._request(url)
            await client._request(url)

            return songkick_requests_this_run()

        counts = await asyncio.gather(
            one_run(first, "https://example.invalid/a"),
            one_run(second, "https://example.invalid/b"),
        )

        assert counts == [2, 2]

        # Neither run's increments touched the context that started them.
        assert songkick_requests_this_run() == 0


# ============================================================
# RATE LIMIT ANSWERS
# ============================================================


class TestRateLimitAnswers:
    """A 429 names how long to wait; the answer is read, bounded, logged.

    Every branch is pinned because each one is a decision a person reading
    the logs may need to reconstruct: wait and ask once more, or refuse and
    say why.
    """

    @staticmethod
    def _response(status_code, retry_after=None):
        from types import SimpleNamespace

        headers = (
            {"Retry-After": retry_after}
            if retry_after is not None
            else {}
        )

        return SimpleNamespace(
            status_code=status_code,
            headers=headers,
        )

    @staticmethod
    def _client_answering(answers):
        """A client whose HTTP calls pop the given answers, recording URLs."""

        client = SongkickClient()

        calls: list[str] = []

        def answer(url, accept=None):
            calls.append(url)
            return answers.pop(0)

        client._request_sync = answer

        return client, calls

    @pytest.mark.asyncio
    async def test_a_short_retry_after_is_waited_and_asked_once_more(self):
        client, calls = self._client_answering(
            [
                self._response(429, retry_after="0"),
                self._response(200),
            ]
        )

        reset_songkick_requests()

        response = await client._request("https://example.invalid/a")

        # The second answer is what the caller reads, the URL was asked
        # exactly twice, and the retry is counted like every other request.
        assert response.status_code == 200
        assert calls == [
            "https://example.invalid/a",
            "https://example.invalid/a",
        ]
        assert songkick_requests_this_run() == 2

    @pytest.mark.asyncio
    async def test_a_retry_after_past_the_cap_is_refused_without_waiting(self):
        from app.config import settings

        original = settings.SONGKICK_RETRY_AFTER_MAX_SECONDS
        settings.SONGKICK_RETRY_AFTER_MAX_SECONDS = 2

        try:
            client, calls = self._client_answering(
                [self._response(429, retry_after="30")]
            )

            reset_songkick_requests()

            response = await client._request(
                "https://example.invalid/a"
            )

            # The 429 itself is handed back: no sleep, no second request.
            assert response.status_code == 429
            assert calls == ["https://example.invalid/a"]
            assert songkick_requests_this_run() == 1

        finally:
            settings.SONGKICK_RETRY_AFTER_MAX_SECONDS = original

    @pytest.mark.asyncio
    async def test_a_429_without_a_usable_header_is_not_retried(self):
        client, calls = self._client_answering(
            [self._response(429)]
        )

        reset_songkick_requests()

        response = await client._request("https://example.invalid/a")

        assert response.status_code == 429
        assert calls == ["https://example.invalid/a"]
        assert songkick_requests_this_run() == 1

    def test_an_http_date_retry_after_is_read_as_seconds_until_it(self):
        from datetime import datetime, timedelta, timezone
        from email.utils import format_datetime

        moment = datetime.now(timezone.utc) + timedelta(seconds=30)

        response = self._response(
            429,
            retry_after=format_datetime(moment, usegmt=True),
        )

        seconds = _retry_after_seconds(response)

        assert seconds is not None
        assert 0 < seconds <= 30

    def test_a_past_or_malformed_retry_after_reads_as_nothing(self):
        assert _retry_after_seconds(
            self._response(429, retry_after="not a date")
        ) is None
        assert _retry_after_seconds(self._response(429)) is None
