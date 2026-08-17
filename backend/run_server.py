import sys
import os

# =====================================================
# Windows Event Loop Policy for Playwright
# =====================================================
# Import before uvicorn to ensure policy is set for all workers
import uvicorn_workers

# =====================================================
# Uvicorn Entry Point
# =====================================================
if __name__ == "__main__":
    import uvicorn
    # Use loop="asyncio" to ensure event loop policy is respected
    # Run without reload for testing - reload causes event loop policy issues
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False, loop="asyncio")