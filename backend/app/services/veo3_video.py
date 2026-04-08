"""Google Veo video generation via Vertex AI.

Uses the same GCP service account as Vertex Imagen/Gemini image.
API: predictLongRunning -> poll operation -> read inline video or download from GCS.
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

VEO3_DEFAULT_REGION = "us-central1"
POLL_INTERVAL = 10
MAX_POLL_ATTEMPTS = 60
_ALLOWED_DURATIONS = (4, 6, 8)


class Veo3Error(Exception):
    pass


def _predict_url(project: str, region: str, model_id: str) -> str:
    return (
        f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{region}/publishers/google/models/{model_id}:predictLongRunning"
    )


def _fetch_predict_url(project: str, region: str, model_id: str) -> str:
    """Poll Veo LRO status (GET on the operation name returns 404; use fetchPredictOperation)."""
    return (
        f"https://{region}-aiplatform.googleapis.com/v1/projects/{project}"
        f"/locations/{region}/publishers/google/models/{model_id}:fetchPredictOperation"
    )


def _veo_model(settings: Settings) -> str:
    m = (settings.vertex_veo_model or "").strip()
    return m or "veo-3.0-generate-001"


def _veo_storage_prefix(settings: Settings, job_id: str) -> str:
    raw = (settings.vertex_veo_storage_uri or "").strip()
    if not raw:
        raise Veo3Error(
            "VERTEX_VEO_STORAGE_URI is not set. "
            "Veo on Vertex requires a GCS output prefix (e.g. gs://your-bucket/veo-jobs/). "
            "Grant the service account storage.objectAdmin (or create/write) on that bucket."
        )
    if not raw.startswith("gs://"):
        raise Veo3Error("VERTEX_VEO_STORAGE_URI must start with gs://")
    base = raw.rstrip("/") + "/"
    return f"{base}veo3_{job_id}/"


def _veo_duration_seconds(requested: int) -> int:
    """Veo 3+ accepts 4, 6, or 8 seconds only."""
    r = max(4, min(8, int(requested)))
    return min(_ALLOWED_DURATIONS, key=lambda x: abs(x - r))


def _guess_image_mime(image_bytes: bytes) -> str:
    if len(image_bytes) >= 3 and image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if len(image_bytes) >= 8 and image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    return "image/png"


def _parse_gs_uri(uri: str) -> tuple[str, str]:
    if not uri.startswith("gs://"):
        raise Veo3Error(f"Invalid GCS URI: {uri}")
    rest = uri[5:].strip()
    slash = rest.find("/")
    if slash < 0:
        raise Veo3Error(f"GCS URI must include object path: {uri}")
    bucket = rest[:slash]
    blob_path = rest[slash + 1 :]
    if not bucket or not blob_path:
        raise Veo3Error(f"Invalid GCS URI: {uri}")
    return bucket, blob_path


def _download_gcs_bytes(gs_uri: str, cred_path: str, project: str) -> bytes:
    try:
        from google.cloud import storage as gcs
        from google.oauth2 import service_account
    except ImportError as e:
        raise Veo3Error(
            "google-cloud-storage is required to read Veo output from GCS. "
            "Install: pip install google-cloud-storage"
        ) from e

    bucket_name, blob_path = _parse_gs_uri(gs_uri)
    creds = service_account.Credentials.from_service_account_file(
        cred_path,
        scopes=("https://www.googleapis.com/auth/cloud-platform",),
    )
    client = gcs.Client(project=project, credentials=creds)
    blob = client.bucket(bucket_name).blob(blob_path)
    try:
        return blob.download_as_bytes()
    except Exception as e:
        raise Veo3Error(f"Failed to download video from {gs_uri}: {e}") from e


def _extract_gcs_uri_or_b64(response: dict[str, Any]) -> tuple[str | None, str | None]:
    """From LRO response object: return (gcs_uri, base64) — at most one typically set."""
    videos = response.get("videos")
    if isinstance(videos, list) and videos:
        v0 = videos[0]
        if isinstance(v0, dict):
            uri = v0.get("gcsUri") or v0.get("gcs_uri")
            b64 = v0.get("bytesBase64Encoded")
            if uri:
                return str(uri), None
            if b64:
                return None, str(b64)

    predictions = response.get("predictions")
    if isinstance(predictions, list) and predictions:
        p0 = predictions[0]
        if isinstance(p0, dict):
            uri = p0.get("gcsUri")
            if uri:
                return str(uri), None
            video = p0.get("video")
            if isinstance(video, dict):
                u = video.get("gcsUri")
                b64 = video.get("bytesBase64Encoded")
                if u:
                    return str(u), None
                if b64:
                    return None, str(b64)

    return None, None


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


async def _await_veo_operation(
    *,
    client: httpx.AsyncClient,
    settings: Settings,
    region: str,
    project: str,
    model_id: str,
    operation_name: str,
    out_path: Path,
    log_label: str,
) -> Path:
    cred_path = _credentials_path(settings) or ""
    poll_url = _fetch_predict_url(project, region, model_id)

    for poll in range(MAX_POLL_ATTEMPTS):
        await asyncio.sleep(POLL_INTERVAL)

        token = await _get_token(settings)
        poll_resp = await client.post(
            poll_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            json={"operationName": operation_name},
        )

        if poll_resp.status_code >= 400:
            logger.warning(
                "Veo fetchPredictOperation HTTP %s: %s",
                poll_resp.status_code,
                poll_resp.text[:300],
            )
            continue

        try:
            poll_data = poll_resp.json()
        except Exception:
            logger.warning("Veo poll non-JSON: %s", poll_resp.text[:200])
            continue

        if not poll_data.get("done"):
            continue

        error = poll_data.get("error")
        if error:
            raise Veo3Error(
                f"Veo operation failed: {error.get('message', str(error))}"
            )

        inner = poll_data.get("response") or {}
        gcs_uri, video_b64 = _extract_gcs_uri_or_b64(inner)

        if gcs_uri and cred_path:
            logger.info("Veo %s: downloading %s", log_label, gcs_uri)
            video_bytes = await asyncio.to_thread(
                _download_gcs_bytes, gcs_uri, cred_path, project
            )
            out_path.write_bytes(video_bytes)
            logger.info(
                "Veo %s video written: %s (%d bytes)",
                log_label,
                out_path.name,
                len(video_bytes),
            )
            return out_path

        if video_b64:
            video_bytes = base64.b64decode(video_b64)
            out_path.write_bytes(video_bytes)
            logger.info(
                "Veo %s video written: %s (%d bytes)",
                log_label,
                out_path.name,
                len(video_bytes),
            )
            return out_path

        if gcs_uri and not cred_path:
            raise Veo3Error(
                f"Veo returned GCS URI but credentials path is missing: {gcs_uri}"
            )

        raise Veo3Error(
            "Veo returned no predictions, videos, or usable video bytes. "
            f"response keys: {list(inner.keys())[:12]}"
        )

    raise Veo3Error(
        f"Veo operation timed out after {MAX_POLL_ATTEMPTS * POLL_INTERVAL}s"
    )


async def generate_video_from_image(
    settings: Settings,
    image_bytes: bytes,
    prompt: str,
    *,
    duration_seconds: int = 8,
    aspect_ratio: str = "16:9",
) -> Path:
    """Generate a video from an image + prompt using Veo on Vertex AI."""
    project = (settings.vertex_imagen_project_id or "").strip()
    if not project:
        raise Veo3Error("VERTEX_IMAGEN_PROJECT is not set")

    region = _veo3_region(settings)
    model_id = _veo_model(settings)
    token = await _get_token(settings)

    job_id = uuid.uuid4().hex[:12]
    storage_uri = _veo_storage_prefix(settings, job_id)
    output_dir = settings.artifact_root / f"veo3_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"video_{job_id}.mp4"

    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    duration = _veo_duration_seconds(duration_seconds)
    mime_type = _guess_image_mime(image_bytes)

    body: dict[str, Any] = {
        "instances": [
            {
                "prompt": prompt,
                "image": {
                    "bytesBase64Encoded": image_b64,
                    "mimeType": mime_type,
                },
            }
        ],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": duration,
            "storageUri": storage_uri,
            "resizeMode": "pad",
        },
    }

    timeout = httpx.Timeout(60.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        url = _predict_url(project, region, model_id)
        resp = await http_client.post(
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
            raise Veo3Error(f"Veo prediction failed ({resp.status_code}): {detail}")

        data = resp.json()
        operation_name = data.get("name")
        if not operation_name:
            raise Veo3Error("Veo response missing operation name")

        logger.info("Veo image-to-video operation started: %s", operation_name)
        return await _await_veo_operation(
            client=http_client,
            settings=settings,
            region=region,
            project=project,
            model_id=model_id,
            operation_name=operation_name,
            out_path=out_path,
            log_label="image-to-video",
        )


async def generate_video_from_prompt(
    settings: Settings,
    prompt: str,
    *,
    duration_seconds: int = 8,
    aspect_ratio: str = "16:9",
) -> Path:
    """Generate a video from text prompt only (no source image) using Veo."""
    project = (settings.vertex_imagen_project_id or "").strip()
    if not project:
        raise Veo3Error("VERTEX_IMAGEN_PROJECT is not set")

    region = _veo3_region(settings)
    model_id = _veo_model(settings)
    token = await _get_token(settings)

    job_id = uuid.uuid4().hex[:12]
    storage_uri = _veo_storage_prefix(settings, job_id)
    output_dir = settings.artifact_root / f"veo3_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"video_{job_id}.mp4"

    duration = _veo_duration_seconds(duration_seconds)

    body: dict[str, Any] = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "aspectRatio": aspect_ratio,
            "sampleCount": 1,
            "durationSeconds": duration,
            "storageUri": storage_uri,
        },
    }

    timeout = httpx.Timeout(60.0, read=300.0)
    async with httpx.AsyncClient(timeout=timeout) as http_client:
        url = _predict_url(project, region, model_id)
        resp = await http_client.post(
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
            raise Veo3Error(f"Veo prediction failed ({resp.status_code}): {detail}")

        data = resp.json()
        operation_name = data.get("name")
        if not operation_name:
            raise Veo3Error("Veo response missing operation name")

        logger.info("Veo text-to-video operation started: %s", operation_name)
        return await _await_veo_operation(
            client=http_client,
            settings=settings,
            region=region,
            project=project,
            model_id=model_id,
            operation_name=operation_name,
            out_path=out_path,
            log_label="text-to-video",
        )
