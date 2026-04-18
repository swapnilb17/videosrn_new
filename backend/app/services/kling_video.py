"""Kling AI video generation (async task + poll).

Supports:
- Single API key with ``Authorization: Bearer`` (e.g. gateway at api.klingapi.com).
- Official-style AccessKey + SecretKey: HS256 JWT Bearer (api.klingai.com).

Create uses ``/v1/videos/text2video`` and ``/v1/videos/image2video``. For start+end frame,
the same image2video route sends an additional ``image_tail`` (base64, same encoding as
``image``). Gateways vary; if create fails, check provider docs for frames-specific paths.
Status polling tries several ``GET`` paths (and optional ``KLING_POLL_PATH``) because gateways differ.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


class KlingVideoError(Exception):
    pass


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _kling_jwt_token(access_key: str, secret_key: str, *, ttl_sec: int = 1800) -> str:
    header = _b64url(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8")
    )
    now = int(time.time())
    payload = _b64url(
        json.dumps(
            {"iss": access_key, "exp": now + ttl_sec, "nbf": now - 5},
            separators=(",", ":"),
        ).encode("utf-8")
    )
    msg = f"{header}.{payload}".encode("ascii")
    sig = _b64url(hmac.new(secret_key.encode("utf-8"), msg, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def _kling_bearer_token(settings: Settings) -> str:
    raw_key = (settings.kling_api_key or "").strip()
    if raw_key:
        return raw_key
    ak = (settings.kling_access_key or "").strip()
    sk = (settings.kling_secret_key or "").strip()
    if ak and sk:
        return _kling_jwt_token(ak, sk, ttl_sec=max(300, settings.kling_jwt_ttl_sec))
    raise KlingVideoError(
        "Kling is not configured. Set KLING_API_KEY or KLING_ACCESS_KEY + KLING_SECRET_KEY."
    )


def kling_duration_seconds(requested: int) -> int:
    """Many Kling tiers only allow 5s or 10s output."""
    r = max(4, min(10, int(requested)))
    return 10 if r > 6 else 5


def _kling_mode_for_api(raw: str) -> str:
    """Map env-friendly names to API values. Many Kling hosts expect ``pro`` / ``std``, not ``professional`` / ``standard``."""
    m = (raw or "pro").strip().lower()
    if m in ("std", "standard", "fast"):
        return "std"
    if m in ("pro", "professional", "professional_mode", "hq", "high"):
        return "pro"
    return "pro"


def _unwrap_payload(data: dict[str, Any]) -> dict[str, Any]:
    code = data.get("code")
    if code is not None and code != 0:
        msg = data.get("message") or data.get("msg") or json.dumps(data)[:400]
        raise KlingVideoError(f"Kling API error ({code}): {msg}")
    inner = data.get("data")
    if isinstance(inner, dict):
        return inner
    return data


def _extract_task_id(data: dict[str, Any]) -> str:
    d = _unwrap_payload(data)
    for k in ("task_id", "taskId", "id"):
        v = d.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    raise KlingVideoError(
        f"Kling create response missing task id (keys: {list(data.keys())[:12]})"
    )


def _extract_status_str(payload: dict[str, Any]) -> str:
    d = _unwrap_payload(payload)
    for k in ("status", "task_status", "state", "task_status_msg"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip().lower()
    # Nested task object (some gateways)
    task = d.get("task")
    if isinstance(task, dict):
        for k in ("status", "status_name", "state"):
            v = task.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip().lower()
            if isinstance(v, int):
                return f"numeric_{v}"
    return "unknown"


def _status_is_success(status: str) -> bool:
    s = status.lower()
    return s in (
        "completed",
        "complete",
        "success",
        "succeed",
        "done",
        "finished",
        "succeeded",
    )


def _status_is_failed(status: str) -> bool:
    s = status.lower()
    return s in ("failed", "fail", "error", "cancelled", "canceled")


def _find_video_url(obj: Any) -> str | None:
    if isinstance(obj, dict):
        for k in ("video_url", "url", "output_url", "videoUrl", "output", "result_url"):
            v = obj.get(k)
            if isinstance(v, str) and v.startswith(("http://", "https://")):
                return v
        vids = obj.get("videos")
        if isinstance(vids, list) and vids:
            u = _find_video_url(vids[0])
            if u:
                return u
        out = obj.get("output")
        if isinstance(out, dict):
            u = _find_video_url(out)
            if u:
                return u
        for v in obj.values():
            u = _find_video_url(v)
            if u:
                return u
    elif isinstance(obj, list):
        for x in obj:
            u = _find_video_url(x)
            if u:
                return u
    return None


def _extract_video_url(payload: dict[str, Any]) -> str | None:
    d = _unwrap_payload(payload)
    u = _find_video_url(d)
    if u:
        return u
    return _find_video_url(payload)


def _fail_reason(payload: dict[str, Any]) -> str:
    d = _unwrap_payload(payload)
    for k in ("error", "message", "fail_reason", "reason", "fail_msg"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "Kling generation failed"


async def _kling_create_task(
    client: httpx.AsyncClient,
    settings: Settings,
    path: str,
    body: dict[str, Any],
) -> str:
    base = settings.kling_effective_base_url().rstrip("/")
    url = f"{base}{path}"
    token = _kling_bearer_token(settings)
    resp = await client.post(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        json=body,
    )
    try:
        data = resp.json()
    except Exception as e:
        raise KlingVideoError(f"Kling create non-JSON ({resp.status_code}): {resp.text[:400]}") from e
    if resp.status_code >= 400:
        msg = data.get("message") or data.get("error") or data.get("msg") or resp.text[:400]
        raise KlingVideoError(f"Kling create failed ({resp.status_code}): {msg}")
    return _extract_task_id(data if isinstance(data, dict) else {})


def _kling_poll_candidate_urls(
    settings: Settings,
    task_id: str,
    task_kind: Literal["text_to_video", "image_to_video"],
) -> list[str]:
    """Ordered GET URLs to try until one stops returning 404."""
    base = settings.kling_effective_base_url().rstrip("/")
    tid = quote(str(task_id).strip(), safe="")
    kind_seg = "text2video" if task_kind == "text_to_video" else "image2video"
    paths: list[str] = []
    tmpl = (settings.kling_poll_path or "").strip()
    if tmpl:
        p = tmpl if tmpl.startswith("/") else f"/{tmpl}"
        try:
            paths.append(f"{base}{p.format(task_id=tid)}")
        except (KeyError, ValueError):
            paths.append(f"{base}{p.replace('{task_id}', tid)}")

    paths.extend(
        [
            f"{base}/v1/videos/{tid}",
            f"{base}/v1/videos/{kind_seg}/{tid}",
            f"{base}/api/v1/videos/{tid}",
            f"{base}/api/v1/videos/{kind_seg}/{tid}",
            f"{base}/kling/v1/videos/{kind_seg}/{tid}",
        ]
    )
    seen: set[str] = set()
    out: list[str] = []
    for u in paths:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _kling_poll_parse_response(
    data: dict[str, Any],
) -> str | None:
    """Return video URL if generation finished successfully; None if still in progress."""
    st = _extract_status_str(data)
    if _status_is_failed(st):
        raise KlingVideoError(_fail_reason(data))
    if _status_is_success(st):
        video_url = _extract_video_url(data)
        if video_url:
            return video_url
    task = _unwrap_payload(data).get("task")
    if isinstance(task, dict) and str(task.get("status_name", "")).lower() in (
        "succeed",
        "success",
    ):
        video_url = _extract_video_url(data)
        if video_url:
            return video_url
    return None


async def _kling_poll_task(
    client: httpx.AsyncClient,
    settings: Settings,
    task_id: str,
    task_kind: Literal["text_to_video", "image_to_video"],
) -> str:
    token = _kling_bearer_token(settings)
    interval = max(3.0, float(settings.kling_poll_interval_sec))
    attempts = max(1, int(settings.kling_max_poll_attempts))
    candidates = _kling_poll_candidate_urls(settings, task_id, task_kind)
    chosen_url: str | None = None
    consec_all_404 = 0

    for _ in range(attempts):
        await asyncio.sleep(interval)
        urls = candidates if chosen_url is None else [chosen_url]
        got_non404 = False

        for url in urls:
            resp = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
            )
            if resp.status_code == 404:
                logger.debug("Kling poll 404: %s", url)
                continue
            got_non404 = True
            if chosen_url is None:
                chosen_url = url
                logger.info("Kling poll status URL: %s", url)

            try:
                data = resp.json() if resp.content else {}
            except Exception:
                logger.warning("Kling poll non-JSON: %s", resp.text[:200])
                break
            if not isinstance(data, dict):
                break
            if resp.status_code >= 400:
                logger.warning("Kling poll HTTP %s: %s", resp.status_code, resp.text[:300])
                break

            try:
                done_url = _kling_poll_parse_response(data)
            except KlingVideoError:
                raise
            if done_url:
                return done_url
            break

        if not got_non404:
            if chosen_url is not None:
                logger.warning(
                    "Kling poll previous status URL returned 404; rediscovering (was %s)",
                    chosen_url,
                )
                chosen_url = None
            consec_all_404 += 1
            logger.warning(
                "Kling poll no non-404 status URL for task %s (streak=%s)",
                task_id,
                consec_all_404,
            )
            if consec_all_404 >= 4:
                raise KlingVideoError(
                    f"Kling task status not found (404) for id {task_id}. "
                    "Set KLING_POLL_PATH in .env (path only, with placeholder). Example for image-to-video: "
                    "KLING_POLL_PATH=/v1/videos/image2video/{task_id}"
                )
            continue

        consec_all_404 = 0

    raise KlingVideoError(
        f"Kling task {task_id} timed out after {attempts * interval:.0f}s (last poll)"
    )


async def _download_mp4(client: httpx.AsyncClient, url: str, out_path: Path) -> None:
    r = await client.get(url, follow_redirects=True, timeout=httpx.Timeout(60.0, read=600.0))
    if r.status_code >= 400:
        raise KlingVideoError(f"Kling video download failed ({r.status_code})")
    ct = (r.headers.get("content-type") or "").lower()
    if "text" in ct or "json" in ct:
        raise KlingVideoError("Kling video URL returned non-video content")
    out_path.write_bytes(r.content)


async def generate_kling_mp4(
    settings: Settings,
    *,
    task_kind: Literal["text_to_video", "image_to_video"],
    prompt: str,
    image_bytes: bytes | None,
    end_image_bytes: bytes | None = None,
    duration_seconds: int,
    aspect_ratio: str,
    artifact_job_id: str,
) -> Path:
    """Create a Kling task, poll until complete, download MP4 to the same layout as Veo jobs."""

    model = (settings.kling_model or "").strip() or "kling-v2-5-turbo"
    mode = _kling_mode_for_api(settings.kling_mode)
    if end_image_bytes and len(end_image_bytes) >= 100:
        # Many Kling tiers require pro mode when an end frame is supplied.
        mode = "pro"
    dur = kling_duration_seconds(duration_seconds)
    job_id = (artifact_job_id or "").strip().lower()
    if len(job_id) != 12 or any(c not in "0123456789abcdef" for c in job_id):
        raise KlingVideoError("Invalid artifact job id for Kling output path")

    out_dir = settings.artifact_root / f"veo3_{job_id}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"video_{job_id}.mp4"

    if task_kind == "image_to_video":
        if not image_bytes or len(image_bytes) < 100:
            raise KlingVideoError("Start image is required for Kling image-to-video")
        img_b64 = base64.b64encode(image_bytes).decode("ascii")
        body: dict[str, Any] = {
            "model": model,
            "prompt": (prompt or "Cinematic motion, photorealistic.").strip(),
            "image": img_b64,
            "duration": dur,
            "aspect_ratio": aspect_ratio,
            "mode": mode,
        }
        if end_image_bytes and len(end_image_bytes) >= 100:
            body["image_tail"] = base64.b64encode(end_image_bytes).decode("ascii")
            logger.info("Kling image2video: start + end frame (image_tail)")
        path = "/v1/videos/image2video"
    else:
        body = {
            "model": model,
            "prompt": prompt.strip(),
            "duration": dur,
            "aspect_ratio": aspect_ratio,
            "mode": mode,
        }
        path = "/v1/videos/text2video"

    timeout = httpx.Timeout(60.0, read=max(60.0, float(settings.kling_http_timeout)))
    async with httpx.AsyncClient(timeout=timeout) as client:
        task_id = await _kling_create_task(client, settings, path, body)
        logger.info("Kling task created: %s", task_id)
        video_url = await _kling_poll_task(client, settings, task_id, task_kind)
        if not video_url:
            raise KlingVideoError("Kling completed but no video URL was returned")
        await _download_mp4(client, video_url, out_path)

    return out_path
