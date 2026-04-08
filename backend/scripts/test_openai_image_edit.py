#!/usr/bin/env python3
"""Verify OpenAI images.edit (dall-e-2) from this machine.

Requires OPENAI_API_KEY. Run from repo backend/:

  cd backend && PYTHONPATH=. python scripts/test_openai_image_edit.py

Exit 0 on success, non-zero on failure or missing key.
"""

from __future__ import annotations

import asyncio
import base64
import os
import sys
from pathlib import Path

# Minimal valid PNG (1x1)
_MIN_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


async def _run() -> None:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key:
        print("ERROR: set OPENAI_API_KEY", file=sys.stderr)
        raise SystemExit(1)

    backend_root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(backend_root))

    from app.services.openai_portrait import OpenAIPortraitError, generate_openai_portrait

    out = Path(os.environ.get("OPENAI_IMAGE_TEST_OUT", "/tmp/openai_image_edit_test.png"))
    try:
        await generate_openai_portrait(
            key,
            _MIN_PNG,
            "A simple blue square in the center, flat style.",
            out,
        )
        n = out.stat().st_size
        print(f"OK: OpenAI images.edit returned an image -> {out} ({n} bytes)")
    except OpenAIPortraitError as e:
        print(f"FAIL: {e}", file=sys.stderr)
        raise SystemExit(2) from e


if __name__ == "__main__":
    asyncio.run(_run())
