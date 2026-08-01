from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.core.byok_security import PROVIDER_BASE_URLS, validate_provider_base_url
from backend.app.services.byok_provider import call_chat_completion


async def run() -> int:
    if os.getenv("RUN_BYOK_REAL_SMOKE") != "1":
        print("SKIPPED: set RUN_BYOK_REAL_SMOKE=1 to enable the single real-provider call.")
        return 0

    provider = os.getenv("BYOK_SMOKE_PROVIDER", "").strip().lower()
    model = os.getenv("BYOK_SMOKE_MODEL", "").strip()
    api_key = os.getenv("BYOK_SMOKE_API_KEY", "").strip()
    raw_base_url = os.getenv("BYOK_SMOKE_BASE_URL", "").strip() or PROVIDER_BASE_URLS.get(provider, "")
    if not provider or not model or not api_key or not raw_base_url:
        print("ERROR: BYOK_SMOKE_PROVIDER, BYOK_SMOKE_MODEL and BYOK_SMOKE_API_KEY are required.")
        return 2

    base_url = validate_provider_base_url(provider, raw_base_url)
    reply, elapsed_ms = await call_chat_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        history=[{"role": "user", "content": "Reply with OK."}],
        verification=True,
    )
    print(f"SUCCESS provider={provider} model={model} elapsed_ms={elapsed_ms} reply_chars={len(reply)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run()))
    except Exception as exc:
        print(f"ERROR: real provider smoke failed safely ({type(exc).__name__}).")
        raise SystemExit(1)
