"""Google Veo3 video generation via Vertex AI.

Uses the same GCP service account as Vertex Imagen/Gemini image.
Veo3 API: predictLongRunning -> poll operation -> extract video.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.services.vertex_imagen import _access_token_sync, _credentials_path

logger = logging.getLogger(__name__)

VEO3_MODEL = "veo-3.0-generate-preview"
VEO3_DEFAULT_REGION = "us-central1"
POLL_INTERVAL = 10
MAX_POLL_ATTEMPTS = 60


class Veo3Error(Exception):
    pass


def _predict_url(project: str, region: str) -> str:
    return (
        f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{region}/publishers/google/models/{VEO3_MODEL}:predictLongRunning"
    )


def _operation_url(region: str, operation_name: str) -> str:
    return f"https://{region}-aiplatform.googleapis.com/v1/{operation_name}"


async def _get_token(settings: Settings) -> str:
    cred_path = _credentials_path(settings)
    if not cred_path:
        raise Veo3Error(
            "No GCP service account JSON found. "
            "Set GOOGLE_TTS_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS."
        )
    return await asyncio.to_thread(_access_token_sync, cred_path)


def _veo3_region(settings: Settings) -> str:
    regions = (settings.vertex_imagen_regions or "").strip()
    if regions:
        return regions.split(",")[0].strip()
    return VEO3_DEFAULT_REGION


async def generate_video_from_image(
    settings: Settings,
    image_bytes: bytes,
    prompt: str,
    *,
    duration_seconds: int = 8,
    aspect_ratio: str = "16:9",
) -> Path:
    """Generate a video from an image + prompt using Veo3.

    Returns the path to the generated video file.
    """
    project = (settings.vertex_imagen_project_id or "").strip()
    if not project:
        raise Veo3Error("VERTEX_IMAGEN_PROJECT is not set")

    region = _veo3_region(settings)
    token = await _get_token(settings)

    job_id = uuid.uuid4().hex[:12]
    output_dir = settings.artifact_root / f"veo3_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"video_{job_id}.mp4"

    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    body: dict[str, Any] = {
        "instances": [
            {
                "prompt": prompt,
                "image": {
                    "bytesBase64Encoded": image_b64,
                    "mimeType": "image/png",
                },
            }
        ],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": min(duration_seconds, 15),
        },
    }

    timeout = httpx.Timeout(60.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        url = _predict_url(project, region)
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=body,
        )

        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                err = resp.json().get("error", {})
                detail = err.get("message", detail)
            except Exception:
                pass
            raise Veo3Error(f"Veo3 prediction failed ({resp.status_code}): {detail}")

        data = resp.json()
        operation_name = data.get("name")
        if not operation_name:
            raise Veo3Error("Veo3 response missing operation name")

        logger.info("Veo3 operation started: %s", operation_name)

        for poll in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)

            token = await _get_token(settings)
            poll_url = _operation_url(region, operation_name)
            poll_resp = await client.get(
                poll_url,
                headers={"Authorization": f"Bearer {token}"},
            )

            if poll_resp.status_code >= 400:
                logger.warning("Veo3 poll HTTP %s: %s", poll_resp.status_code, poll_resp.text[:300])
                continue

            poll_data = poll_resp.json()

            if poll_data.get("done"):
                error = poll_data.get("error")
                if error:
                    raise Veo3Error(f"Veo3 operation failed: {error.get('message', str(error))}")

                response = poll_data.get("response", {})
                predictions = response.get("predictions", [])
                if not predictions:
                    raise Veo3Error("Veo3 returned no predictions")

                video_data = predictions[0].get("video", {})
                video_b64 = video_data.get("bytesBase64Encoded")
                if not video_b64:
                    video_uri = video_data.get("gcsUri") or predictions[0].get("gcsUri")
                    if video_uri:
                        logger.info("Veo3 output at GCS: %s (download not yet implemented)", video_uri)
                        raise Veo3Error(
                            f"Veo3 returned GCS URI instead of inline bytes: {video_uri}. "
                            "GCS download support needs to be added."
                        )
                    raise Veo3Error("Veo3 prediction has no video bytes or GCS URI")

                video_bytes = base64.b64decode(video_b64)
                out_path.write_bytes(video_bytes)
                logger.info("Veo3 video written: %s (%d bytes)", out_path.name, len(video_bytes))
                return out_path

        raise Veo3Error(f"Veo3 operation timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s")


async def generate_video_from_prompt(
    settings: Settings,
    prompt: str,
    *,
    duration_seconds: int = 8,
    aspect_ratio: str = "16:9",
) -> Path:
    """Generate a video from text prompt only (no source image) using Veo3."""
    project = (settings.vertex_imagen_project_id or "").strip()
    if not project:
        raise Veo3Error("VERTEX_IMAGEN_PROJECT is not set")

    region = _veo3_region(settings)
    token = await _get_token(settings)

    job_id = uuid.uuid4().hex[:12]
    output_dir = settings.artifact_root / f"veo3_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"video_{job_id}.mp4"

    body: dict[str, Any] = {
        "instances": [
            {
                "prompt": prompt,
            }
        ],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": min(duration_seconds, 15),
        },
    }

    timeout = httpx.Timeout(60.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        url = _predict_url(project, region)
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json=body,
        )

        if resp.status_code >= 400:
            detail = resp.text[:500]
            try:
                err = resp.json().get("error", {})
                detail = err.get("message", detail)
            except Exception:
                pass
            raise Veo3Error(f"Veo3 prediction failed ({resp.status_code}): {detail}")

        data = resp.json()
        operation_name = data.get("name")
        if not operation_name:
            raise Veo3Error("Veo3 response missing operation name")

        logger.info("Veo3 text-to-video operation started: %s", operation_name)

        for poll in range(MAX_POLL_ATTEMPTS):
            await asyncio.sleep(POLL_INTERVAL)

            token = await _get_token(settings)
            poll_url = _operation_url(region, operation_name)
            poll_resp = await client.get(
                poll_url,
                headers={"Authorization": f"Bearer {token}"},
            )

            if poll_resp.status_code >= 400:
                logger.warning("Veo3 poll HTTP %s: %s", poll_resp.status_code, poll_resp.text[:300])
                continue

            poll_data = poll_resp.json()

            if poll_data.get("done"):
                error = poll_data.get("error")
                if error:
                    raise Veo3Error(f"Veo3 operation failed: {error.get('message', str(error))}")

                response = poll_data.get("response", {})
                predictions = response.get("predictions", [])
                if not predictions:
                    raise Veo3Error("Veo3 returned no predictions")

                video_data = predictions[0].get("video", {})
                video_b64 = video_data.get("bytesBase64Encoded")
                if not video_b64:
                    video_uri = video_data.get("gcsUri") or predictions[0].get("gcsUri")
                    if video_uri:
                        raise Veo3Error(
                            f"Veo3 returned GCS URI instead of inline bytes: {video_uri}."
                        )
                    raise Veo3Error("Veo3 prediction has no video bytes or GCS URI")

                video_bytes = base64.b64decode(video_b64)
                out_path.write_bytes(video_bytes)
                logger.info("Veo3 text-to-video written: %s (%d bytes)", out_path.name, len(video_bytes))
                return out_path

        raise Veo3Error(f"Veo3 operation timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s")
