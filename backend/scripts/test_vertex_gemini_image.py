#!/usr/bin/env python3
"""One-off: call Vertex Gemini image :generateContent with project .env (SA + VERTEX_IMAGEN_PROJECT).

Usage from repo root:
  python scripts/test_vertex_gemini_image.py

Optional:
  VERTEX_GEMINI_IMAGE_REGIONS=global,us-central1
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from app.config import Settings
from app.schemas import LanguageCode, ScriptPayload
from app.services.vertex_gemini_image import VertexGeminiImageError, generate_vertex_gemini_slide_images


def _minimal_script() -> ScriptPayload:
    return ScriptPayload(
        hook="Test slide one.",
        facts=["Test slide two.", "Test slide three."],
        ending="Done.",
        full_script_plain="Test slide one.\n\nTest slide two.\n\nTest slide three.\n\nDone.",
        visual_segments_en=[
            "Minimal abstract gradient poster, no text, soft blue and teal.",
            "Simple geometric shapes on white, no text, calm palette.",
            "Soft sunset horizon, no text, warm colors.",
            "Clean closing frame, subtle pattern, no text.",
        ],
    )


async def main() -> int:
    parser = argparse.ArgumentParser(description="Test Vertex Gemini image slide generation")
    parser.add_argument(
        "--out",
        type=Path,
        default=REPO / "data" / "vertex_gemini_image_test",
        help="Directory for test PNG slides",
    )
    args = parser.parse_args()

    settings = Settings()
    if not settings.vertex_gemini_image_configured():
        print(
            "vertex_gemini_image_configured() is false. Need:\n"
            "  GOOGLE_TTS_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS (file)\n"
            "  VERTEX_IMAGEN_PROJECT or GOOGLE_CLOUD_PROJECT\n"
            "  VERTEX_GEMINI_IMAGE_MODEL (default gemini-2.5-flash-image)\n"
            "  VERTEX_GEMINI_IMAGE_REGIONS or VERTEX_IMAGEN_REGIONS\n"
            "  VERTEX_GEMINI_IMAGE_FAILOVER not false\n",
            file=sys.stderr,
        )
        return 1

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    print(
        f"model={settings.vertex_gemini_image_model!r} "
        f"locations={settings.vertex_gemini_image_locations()} "
        f"project={settings.vertex_imagen_project_id!r} -> {out}"
    )
    try:
        paths = await generate_vertex_gemini_slide_images(
            settings,
            "Vertex image smoke test",
            _minimal_script(),
            LanguageCode("en"),
            out,
        )
    except VertexGeminiImageError as e:
        print("FAILED:", e, file=sys.stderr)
        return 2
    for p in paths:
        sz = p.stat().st_size if p.is_file() else 0
        print(f"ok {p.name} {sz} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
