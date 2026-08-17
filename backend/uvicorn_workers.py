import asyncio
import sys

# =====================================================
# Windows Event Loop Policy for Playwright
# =====================================================
# Playwright requires subprocess support on Windows.
# The default SelectorEventLoop doesn't support subprocesses,
# so we use ProactorEventLoopPolicy on Windows.
# This is called by uvicorn workers during startup.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())