import asyncio
import errno
import hmac
import logging
import os
import re
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from typing import Annotated, Literal

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.auth_deps import GoogleUserDep
from app.auth_google import router as google_auth_router
from app.config import SETTINGS_DOTENV_PATH, Settings, get_settings
from app.output_profile import build_visual_settings_from_forms
from app.db import (
    create_async_engine_from_settings,
    create_session_factory,
    create_tables_if_needed,
    get_db_session,
    ping_database,
)
from app.credit_deps import resolve_user_for_credits
from app.credit_holds import register_credit_hold, release_credit_hold
from app.credit_service import (
    IMAGE_CREDITS_PER_IMAGE,
    InsufficientCreditsError,
    add_credits,
    can_use_premium_models,
    check_credit_code,
    deduct_credits,
    get_or_create_user,
    redeem_code,
    standard_video_credit_cost,
    tts_credits_for_chars,
    veo_credits_for_seconds,
)
from app.job_store import (
    job_get_media_asset,
    job_insert_running,
    job_mark_failed,
    job_mark_succeeded,
    job_update_script,
)
from app.media_store import media_insert, media_list_by_owner
from app.models import User
from app.schemas import GenerateResponse, LanguageCode, RedeemBody
from app.services.branding_logo import save_branding_logo_from_upload
from app.services.user_assets import (
    normalize_address_form,
    save_optional_rgba_png,
    save_optional_thumbnail_jpeg,
)
from app.services.ffmpeg_resolve import resolve_ffprobe, resolve_ffmpeg
from app.services.gemini_native_image import GeminiNativeImageError, generate_gemini_native_slide_images
from app.services.google_imagen import GoogleImagenError, generate_imagen_slide_images
from app.services.vertex_gemini_image import VertexGeminiImageError, generate_vertex_gemini_slide_images
from app.services.image_prompts import script_visual_segments
from app.services.mux_mp4 import mux_still_image_and_audio, overlay_frame_watermark_on_mp4
from app.services.nano_banana import NanoBananaError, generate_slide_images
from app.services.s3_storage import (
    S3UploadError,
    safe_presign_get,
    upload_job_directory,
    upload_veo3_mp4,
)
from app.services.script_openai import generate_script
from app.services.slide_image_plan import visibility_by_slide_stem
from app.services.slide_product_composite import composite_user_product_onto_slide
from app.services.cta_end_slide import render_dedicated_cta_slide_png
from app.services.slideshow_video import (
    audio_duration_seconds,
    mux_slideshow_with_audio,
    slideshow_durations_with_cta_coda,
    trim_mp3_to_max_duration,
    word_weighted_durations,
)
from app.services.title_card import render_title_card
from app.services.video_thumbnail import attach_thumbnail_to_mp4
from app.services.video_watermark import FrameOverlayAssets
from app.services.tts_coqui import synthesize_coqui_sync
from app.services.tts_elevenlabs import ElevenLabsError, synthesize_elevenlabs
from app.services.tts_gcp import (
    GoogleTtsError,
    list_google_tts_voices_detail,
    synthesize_google_tts_conversational_sync,
    synthesize_google_tts_preview_sync,
    synthesize_google_tts_sync,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
# httpx logs full URLs at INFO (Generative Language embeds ?key=); avoid leaking API keys in logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Max length for user-authored prompts/topics/ad copy across Topic → Video, Veo flows, and Text → Image.
USER_PROMPT_MAX_CHARS = 1000


def _rate_limit_key(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    if request.client:
        return request.client.host
    return "unknown"


def _veo_preview_dimensions(aspect_ratio: str, *, is_1080p: bool) -> tuple[int, int]:
    """Approximate output size for API responses (matches Veo 720p/1080p tiers)."""
    ar = (aspect_ratio or "16:9").strip()
    if ar == "16:9":
        return (1920, 1080) if is_1080p else (1280, 720)
    if ar == "9:16":
        return (1080, 1920) if is_1080p else (720, 1280)
    return (1080, 1080) if is_1080p else (720, 720)


VEO_MODEL_FALLBACK = "veo-3.1-lite-generate-001"


_limiter_bootstrap = get_settings()
limiter = Limiter(key_func=_rate_limit_key)


def load_settings() -> Settings:
    """Hook for tests: patch `app.main.load_settings` instead of `get_settings`."""
    return get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Imagen: vertex=%s process_env_IMAGEN_MODEL=%r configured=%r effective_for_api=%r (dotenv %s)",
        settings.imagen_use_vertex,
        os.environ.get("IMAGEN_MODEL", "(unset)"),
        (settings.imagen_model or "").strip() or "(empty)",
        settings.imagen_model_effective(),
        SETTINGS_DOTENV_PATH,
    )
    if settings.google_tts_is_configured():
        logger.info(
            "Google Cloud TTS enabled (GOOGLE_TTS_USE_ADC=%s, GOOGLE_TTS_CREDENTIALS_JSON=%r)",
            settings.google_tts_use_adc,
            (settings.google_tts_credentials_json_path or "").strip() or None,
        )
    elif not settings.elevenlabs_is_configured():
        logger.warning(
            "Voice uses Coqui only (Google TTS and ElevenLabs not configured). "
            "Marathi/Hindi narration often logs missing Devanagari characters; enable Cloud Text-to-Speech: "
            "set GOOGLE_TTS_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS to a service account JSON "
            "(roles/cloudtexttospeech.user), or on GCP/EC2 with workload/instance identity set "
            "GOOGLE_TTS_USE_ADC=true."
        )
    if settings.persistence_enabled():
        engine = create_async_engine_from_settings(settings)
        if "sqlite" in (settings.database_url or "").lower():
            await create_tables_if_needed(engine)
        app.state.db_engine = engine
        app.state.session_factory = create_session_factory(engine)
    else:
        app.state.db_engine = None
        app.state.session_factory = None
    yield
    eng = getattr(app.state, "db_engine", None)
    if eng is not None:
        await eng.dispose()


app = FastAPI(
    title="Avatar Video Creator",
    lifespan=lifespan,
    docs_url="/docs" if _limiter_bootstrap.openapi_enabled else None,
    redoc_url="/redoc" if _limiter_bootstrap.openapi_enabled else None,
    openapi_url="/openapi.json" if _limiter_bootstrap.openapi_enabled else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_oauth_bootstrap = get_settings()
if _oauth_bootstrap.google_oauth_enabled():
    app.add_middleware(
        SessionMiddleware,
        secret_key=_oauth_bootstrap.session_secret.strip(),
        same_site="lax",
        https_only=_oauth_bootstrap.session_cookie_https_only,
    )

app.include_router(google_auth_router)

# In-memory tracker for async video jobs (status + result/error)
_job_results: dict[str, dict] = {}


async def _refund_veo_credits_on_failure(
    user_id: int | None,
    amount: int,
    *,
    meta: dict,
) -> None:
    if user_id is None or amount <= 0:
        return
    session_factory = getattr(app.state, "session_factory", None)
    if session_factory is None:
        logger.warning("veo refund skipped: no DB session factory (user=%s)", user_id)
        return
    session = session_factory()
    try:
        locked = (
            await session.execute(select(User).where(User.id == user_id).with_for_update())
        ).scalar_one()
        await add_credits(
            session,
            locked,
            amount,
            reason="refund_veo_failed",
            meta=meta,
        )
        await session.commit()
    except Exception:
        logger.warning("veo refund failed user=%s", user_id, exc_info=True)
    finally:
        await session.close()


async def _run_photo_to_video_job(
    *,
    job_id: str,
    veo_task: Literal["text_to_video", "image_to_video"],
    image_bytes: bytes | None,
    end_bytes: bytes | None,
    motion_text: str,
    duration: int,
    camera_movement: str,
    aspect_ratio: str,
    is_1080: bool,
    charged_user_id: int | None,
    veo_cost: int,
    user_email: str,
) -> None:
    """Background Veo pipeline for /api/photo-to-video (avoids proxy timeouts on long requests)."""
    from app.services.veo3_video import (
        _veo_duration_seconds,
        generate_video_from_image,
        generate_video_from_prompt,
        Veo3Error,
    )

    settings = get_settings()
    snap_d = _veo_duration_seconds(duration)
    veo_model = (settings.vertex_veo_model or "").strip() or VEO_MODEL_FALLBACK
    session_factory = getattr(app.state, "session_factory", None)

    async def _fail(msg: str) -> None:
        await _refund_veo_credits_on_failure(
            charged_user_id,
            veo_cost,
            meta={"stage": "photo-to-video", "job_id": job_id},
        )
        _job_results[job_id] = {"job_id": job_id, "status": "failed", "error": msg}

    try:
        if veo_task == "text_to_video":
            prompt = motion_text
            if "cinematic" not in prompt.lower():
                prompt += " Cinematic, photorealistic, smooth natural motion."
            video_path = await generate_video_from_prompt(
                settings,
                prompt,
                duration_seconds=duration,
                aspect_ratio=aspect_ratio,
                is_1080p=is_1080,
                veo_artifact_job_id=job_id,
            )
        else:
            assert image_bytes is not None
            if end_bytes is not None:
                base = motion_text or (
                    "Smooth, natural motion transitioning from the first frame to the last frame."
                )
                prompt = f"{base} Photorealistic, cinematic quality, coherent transition."
                video_path = await generate_video_from_image(
                    settings,
                    image_bytes,
                    prompt,
                    duration_seconds=duration,
                    aspect_ratio=aspect_ratio,
                    is_1080p=is_1080,
                    last_frame_bytes=end_bytes,
                    veo_artifact_job_id=job_id,
                )
            else:
                camera_desc = {
                    "pan_left": "smooth camera pan from right to left",
                    "pan_right": "smooth camera pan from left to right",
                    "zoom_in": "slow cinematic zoom in towards the subject",
                    "zoom_out": "slow cinematic zoom out revealing the full scene",
                    "orbit": "smooth orbital camera movement around the subject",
                    "dolly": "forward dolly movement towards the subject",
                    "static": "static camera with subtle ambient motion in the scene",
                }.get(camera_movement, "gentle camera movement")
                prompt = f"Bring this photo to life with {camera_desc}."
                if motion_text:
                    prompt += f" {motion_text}."
                prompt += " Photorealistic, cinematic quality, smooth natural motion."
                video_path = await generate_video_from_image(
                    settings,
                    image_bytes,
                    prompt,
                    duration_seconds=duration,
                    aspect_ratio=aspect_ratio,
                    is_1080p=is_1080,
                    veo_artifact_job_id=job_id,
                )
    except Veo3Error as e:
        await _fail(str(e))
        return
    except Exception as e:
        logger.exception("photo-to-video job=%s failed: %s", job_id, e)
        await _fail("Video generation failed")
        return

    ff = (settings.ffmpeg_path or "").strip()
    try:
        overlay_frame_watermark_on_mp4(video_path, ffmpeg_explicit=ff)
        await _persist_veo3_output_to_s3(settings, video_path)
    except Exception as e:
        logger.exception("photo-to-video job=%s postprocess failed: %s", job_id, e)
        await _fail("Video processing failed")
        return

    job_dir_name = video_path.parent.name
    video_url = f"/media/veo3/{job_dir_name}/{video_path.name}"
    pw, ph = _veo_preview_dimensions(aspect_ratio, is_1080p=is_1080)
    title_base = motion_text or (
        "Text to video" if veo_task == "text_to_video" else "Image to video"
    )
    ue = (user_email or "").strip()
    if ue and session_factory is not None:
        session = session_factory()
        try:
            await media_insert(
                session,
                owner_email=ue,
                media_type="video",
                title=title_base[:200],
                media_url=video_url,
                source_service="photo-to-video",
                extra={
                    "duration": snap_d,
                    "camera": camera_movement,
                    "model": veo_model,
                    "resolution": "1080p" if is_1080 else "720p",
                    "task": veo_task,
                    "end_frame": bool(end_bytes),
                },
            )
            await session.commit()
        except Exception:
            logger.warning("photo-to-video job=%s media_insert failed (non-fatal)", job_id, exc_info=True)
        finally:
            await session.close()

    _job_results[job_id] = {
        "job_id": job_id,
        "status": "done",
        "mp4_url": video_url,
        "video_url": video_url,
        "video_width": pw,
        "video_height": ph,
        "duration_seconds": snap_d,
        "model": veo_model,
    }


async def _run_image_to_ad_job(
    *,
    job_id: str,
    image_bytes: bytes,
    ad_copy_clean: str,
    cta_text: str,
    template: str,
    form_duration: int,
    aspect_ratio: str,
    is_1080: bool,
    charged_user_id: int | None,
    veo_cost: int,
    user_email: str,
) -> None:
    """Background Veo pipeline for /api/image-to-ad."""
    from app.services.veo3_video import (
        _veo_duration_seconds,
        generate_video_from_image,
        Veo3Error,
    )

    settings = get_settings()
    dur_req = min(int(form_duration), 15)
    snap_d = _veo_duration_seconds(dur_req)
    veo_model = (settings.vertex_veo_model or "").strip() or VEO_MODEL_FALLBACK
    session_factory = getattr(app.state, "session_factory", None)

    async def _fail(msg: str) -> None:
        await _refund_veo_credits_on_failure(
            charged_user_id,
            veo_cost,
            meta={"stage": "image-to-ad", "job_id": job_id},
        )
        _job_results[job_id] = {"job_id": job_id, "status": "failed", "error": msg}

    template_desc = {
        "product_showcase": "cinematic product showcase with dynamic camera angles revealing the product from multiple perspectives",
        "before_after": "transformation reveal showing the product's impact with a before and after transition",
        "feature_highlight": "focused feature highlight zooming into key product details one by one",
        "testimonial": "social proof style presentation with the product as the hero element",
        "sale_promo": "high-energy promotional video with urgency-driven motion and dynamic transitions",
    }.get(template, "cinematic product showcase")

    prompt = f"Create a {template_desc} for this product."
    if ad_copy_clean:
        prompt += f" The ad message: {ad_copy_clean}."
    if cta_text:
        prompt += f" End with a call to action: {cta_text.strip()[:50]}."
    prompt += " Professional advertising quality, smooth transitions, premium feel."

    try:
        video_path = await generate_video_from_image(
            settings,
            image_bytes,
            prompt,
            duration_seconds=dur_req,
            aspect_ratio=aspect_ratio,
            is_1080p=is_1080,
            veo_artifact_job_id=job_id,
        )
    except Veo3Error as e:
        await _fail(str(e))
        return
    except Exception as e:
        logger.exception("image-to-ad job=%s failed: %s", job_id, e)
        await _fail("Ad video generation failed")
        return

    ff = (settings.ffmpeg_path or "").strip()
    try:
        overlay_frame_watermark_on_mp4(video_path, ffmpeg_explicit=ff)
        await _persist_veo3_output_to_s3(settings, video_path)
    except Exception as e:
        logger.exception("image-to-ad job=%s postprocess failed: %s", job_id, e)
        await _fail("Ad video processing failed")
        return

    job_dir_name = video_path.parent.name
    ad_video_url = f"/media/veo3/{job_dir_name}/{video_path.name}"
    aw, ah = _veo_preview_dimensions(aspect_ratio, is_1080p=is_1080)
    ue = (user_email or "").strip()
    if ue and session_factory is not None:
        session = session_factory()
        try:
            await media_insert(
                session,
                owner_email=ue,
                media_type="video",
                title=(ad_copy_clean or "Image to Ad video")[:200],
                media_url=ad_video_url,
                source_service="image-to-ad",
                extra={
                    "template": template,
                    "duration": snap_d,
                    "model": veo_model,
                    "resolution": "1080p" if is_1080 else "720p",
                },
            )
            await session.commit()
        except Exception:
            logger.warning("image-to-ad job=%s media_insert failed (non-fatal)", job_id, exc_info=True)
        finally:
            await session.close()

    _job_results[job_id] = {
        "job_id": job_id,
        "status": "done",
        "mp4_url": ad_video_url,
        "video_url": ad_video_url,
        "video_width": aw,
        "video_height": ah,
        "duration_seconds": snap_d,
        "model": veo_model,
    }


_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _validate_persistence_config(settings: Settings) -> None:
    d = bool((settings.database_url or "").strip())
    s3 = bool((settings.s3_bucket or "").strip() and (settings.s3_region or "").strip())
    if d and not s3:
        raise HTTPException(
            status_code=500,
            detail="DATABASE_URL is set but S3_BUCKET and S3_REGION must also be set.",
        )
    if s3 and not d:
        raise HTTPException(
            status_code=500,
            detail="S3_BUCKET/S3_REGION are set but DATABASE_URL is missing.",
        )


def _cleanup_job_dir(path_str: str) -> None:
    p = Path(path_str)
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)


def _media_file(settings: Settings, job_id: str, filename: str) -> Path:
    allowed = frozenset({"voiceover.mp3", "output.mp4"})
    if filename not in allowed:
        raise HTTPException(status_code=404, detail="Unknown asset")
    if not job_id or "/" in job_id or job_id in (".", ".."):
        raise HTTPException(status_code=404, detail="Invalid job")
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid job") from None
    root = settings.artifact_root.resolve()
    job_dir = (root / job_id).resolve()
    try:
        job_dir.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid job") from None
    if not job_dir.is_dir():
        raise HTTPException(status_code=404, detail="Job not found")
    path = (job_dir / filename).resolve()
    try:
        path.relative_to(job_dir)
    except ValueError:
        raise HTTPException(status_code=404, detail="Invalid path") from None
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File not ready")
    return path


def _resolve_artifact_file_under_root(settings: Settings, *relative_segments: str) -> Path:
    """Resolve a file path under artifact_root; reject traversal outside the root."""
    root = settings.artifact_root.resolve()
    candidate = root.joinpath(*relative_segments).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Not found")
    return candidate


def _require_internal_api_key(request: Request, settings: Settings) -> None:
    secret = (settings.internal_api_secret or "").strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="INTERNAL_API_SECRET is not configured; /internal routes are disabled.",
        )
    hdr = (request.headers.get("x-internal-api-key") or "").strip()
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        hdr = auth[7:].strip() or hdr
    try:
        if not hmac.compare_digest(hdr, secret):
            raise HTTPException(status_code=401, detail="Invalid internal API credentials.")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid internal API credentials.") from None


def _resolve_google_sub_for_media(request: Request, settings: Settings) -> str | None:
    """OAuth subject for /media: browser session, or trusted Next.js proxy (internal key + X-User-Sub)."""
    secret = (settings.internal_api_secret or "").strip()
    hdr = (request.headers.get("x-internal-api-key") or "").strip()
    auth = (request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        hdr = auth[7:].strip() or hdr
    if secret and hdr:
        try:
            if not hmac.compare_digest(hdr, secret):
                raise HTTPException(status_code=401, detail="Invalid internal API credentials.")
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid internal API credentials.") from None
        sub = (request.headers.get("x-user-sub") or "").strip()
        if not sub:
            raise HTTPException(
                status_code=401,
                detail="Sign in required to access this media.",
            )
        return sub
    sess_user = request.session.get("user")
    sub = sess_user.get("sub") if isinstance(sess_user, dict) else None
    return sub if isinstance(sub, str) and sub.strip() else None


def _assert_local_topic_video_media_authorized(request: Request, settings: Settings, job_id: str) -> None:
    """When jobs are on local disk (no DB/S3), enforce OAuth + optional .owner_sub sidecar."""
    if not settings.google_oauth_enabled():
        return
    if not job_id or "/" in job_id or job_id in (".", ".."):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        uuid.UUID(job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    sub = _resolve_google_sub_for_media(request, settings)
    if not isinstance(sub, str) or not sub.strip():
        raise HTTPException(
            status_code=401,
            detail="Sign in required to access this media.",
        )
    root = settings.artifact_root.resolve()
    meta = (root / job_id / ".owner_sub").resolve()
    try:
        meta.relative_to(root / job_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None
    if not meta.is_file():
        return
    stored = meta.read_text(encoding="utf-8").strip()
    if stored and stored != sub:
        raise HTTPException(status_code=403, detail="Not allowed to access this media.")


def _validate_standalone_img_path(job_dir: str, filename: str) -> None:
    m = re.fullmatch(r"img_([0-9a-f]{12})", job_dir)
    if not m:
        raise HTTPException(status_code=404, detail="Image not found")
    h12 = m.group(1)
    if not re.fullmatch(rf"image_{h12}\.png", filename):
        raise HTTPException(status_code=404, detail="Image not found")


def _validate_standalone_veo3_path(job_dir: str, filename: str) -> None:
    m = re.fullmatch(r"veo3_([0-9a-f]{12})", job_dir)
    if not m:
        raise HTTPException(status_code=404, detail="Video not found")
    h12 = m.group(1)
    if not re.fullmatch(rf"video_{h12}\.mp4", filename):
        raise HTTPException(status_code=404, detail="Video not found")


def _validate_standalone_voice_path(job_id: str, filename: str) -> None:
    if not re.fullmatch(r"^[0-9a-f]{12}$", job_id):
        raise HTTPException(status_code=404, detail="Audio not found")
    if not re.fullmatch(rf"audio_{job_id}\.mp3", filename):
        raise HTTPException(status_code=404, detail="Audio not found")


async def _persist_veo3_output_to_s3(settings: Settings, video_path: Path) -> None:
    """Copy Veo MP4 to S3 when bucket/region are configured; optionally remove local copy."""
    if not settings.s3_object_storage_configured():
        return
    job_dir = video_path.parent.name
    try:
        await asyncio.to_thread(
            upload_veo3_mp4,
            settings,
            job_dir,
            video_path.name,
            video_path,
        )
    except S3UploadError as e:
        logger.warning("Veo video S3 upload failed (local file kept): %s", e)
        return
    if settings.artifact_cleanup_after_s3:

        def _rm_local() -> None:
            video_path.unlink(missing_ok=True)
            try:
                video_path.parent.rmdir()
            except OSError:
                pass

        await asyncio.to_thread(_rm_local)


@app.get("/")
async def index_page():
    index = _STATIC_DIR / "index.html"
    if not index.is_file():
        raise HTTPException(status_code=404, detail="UI not installed")
    return FileResponse(index, media_type="text/html")


def _download_name_for_media(job_id: str, filename: str) -> str:
    if filename == "output.mp4":
        return f"learncast-{job_id}.mp4"
    if filename == "voiceover.mp3":
        return f"learncast-{job_id}.mp3"
    return filename


@app.get("/media/{job_id}/{filename}")
async def serve_media(
    request: Request,
    job_id: str,
    filename: str,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    attachment: Annotated[bool, Query()] = False,
):
    settings = load_settings()
    download_as = _download_name_for_media(job_id, filename) if attachment else None
    if settings.persistence_enabled():
        if session is None:
            raise HTTPException(status_code=503, detail="Database session unavailable")
        allowed = frozenset({"voiceover.mp3", "output.mp4"})
        if filename not in allowed:
            raise HTTPException(status_code=404, detail="Unknown asset")
        try:
            job_uuid = uuid.UUID(job_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="Invalid job") from None
        s3_key, owner_sub = await job_get_media_asset(session, job_uuid, filename)
        if not s3_key:
            raise HTTPException(status_code=404, detail="File not ready")
        if settings.google_oauth_enabled():
            sub = _resolve_google_sub_for_media(request, settings)
            if not isinstance(sub, str) or not sub.strip():
                raise HTTPException(
                    status_code=401,
                    detail="Sign in required to access this media.",
                )
            if owner_sub and owner_sub != sub:
                raise HTTPException(status_code=403, detail="Not allowed to access this media.")
        try:
            url = await asyncio.to_thread(
                safe_presign_get,
                settings,
                s3_key,
                attachment=attachment,
                download_filename=download_as,
            )
        except S3UploadError as e:
            logger.warning("presign failed job=%s file=%s: %s", job_id, filename, e)
            raise HTTPException(status_code=503, detail="Could not sign media URL") from e
        return RedirectResponse(url=url, status_code=302)
    _assert_local_topic_video_media_authorized(request, settings, job_id)
    path = _media_file(settings, job_id, filename)
    media = "audio/mpeg" if filename.endswith(".mp3") else "video/mp4"
    if attachment and download_as:
        return FileResponse(
            path,
            media_type=media,
            filename=download_as,
            content_disposition_type="attachment",
        )
    return FileResponse(path, media_type=media, filename=filename)


@app.get("/health")
async def health(request: Request):
    settings = load_settings()
    body: dict = {
        "status": "ok",
        "openai_ready": bool((settings.openai_api_key or "").strip()),
        "elevenlabs_ready": settings.elevenlabs_is_configured(),
        "google_tts_ready": settings.google_tts_is_configured(),
        "ffmpeg_ready": bool(resolve_ffmpeg(explicit=settings.ffmpeg_path or None)),
        "ffprobe_ready": bool(resolve_ffprobe(settings.ffmpeg_path)),
        "gemini_imagen_ready": settings.gemini_imagen_configured(),
        "gemini_native_image_ready": settings.gemini_native_image_configured(),
        "vertex_gemini_image_ready": settings.vertex_gemini_image_configured(),
        "vertex_imagen_ready": settings.vertex_imagen_configured(),
        "nano_banana_ready": settings.nano_banana_configured(),
        "persistence_enabled": settings.persistence_enabled(),
        "google_oauth_enabled": settings.google_oauth_enabled(),
    }
    if settings.google_oauth_enabled():
        u = request.session.get("user")
        body["google_user_email"] = (
            u.get("email") if isinstance(u, dict) and isinstance(u.get("email"), str) else None
        )
    else:
        body["google_user_email"] = None
    if settings.persistence_enabled():
        db_ok = False
        db_err_type: str | None = None
        factory = getattr(request.app.state, "session_factory", None)
        if factory is not None:
            async with factory() as s:
                try:
                    await ping_database(s)
                    db_ok = True
                except Exception as e:
                    logger.exception("database ping failed")
                    cause = getattr(e, "__cause__", None)
                    db_err_type = (
                        f"{type(e).__name__}"
                        f" ({type(cause).__name__})"
                        if cause is not None
                        else type(e).__name__
                    )
        body["database_ready"] = db_ok
        if not db_ok and db_err_type is not None and settings.health_expose_internals:
            body["database_error_type"] = db_err_type
    return body


# ---------------------------------------------------------------------------
# Media library — internal endpoint called by the Next.js frontend proxy
# ---------------------------------------------------------------------------


@app.get("/internal/user-media")
async def internal_user_media(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    type: str | None = Query(None, alias="type"),
):
    """Return media items for the authenticated user.

    Trusted: only the frontend container should call this endpoint (via
    nginx routing).  The user's email is passed in X-User-Email by the
    Next.js API route after verifying the NextAuth session server-side.
    """
    _require_internal_api_key(request, load_settings())
    email = (request.headers.get("x-user-email") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="Missing user identity")
    if session is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    media_type = type if type in ("video", "image", "voice") else None
    items = await media_list_by_owner(session, email, media_type=media_type)
    return {"items": items}


@app.get("/internal/credits/me")
async def internal_credits_me(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
):
    """Trusted: Next.js API route passes X-User-Email (and optional X-User-Sub) after NextAuth."""
    _require_internal_api_key(request, load_settings())
    if session is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    email = (request.headers.get("x-user-email") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="Missing user identity")
    settings = load_settings()
    if not settings.credits_billing_enabled():
        return {
            "credits_enabled": False,
            "balance": 0,
            "plan": "free",
        }
    sub = (request.headers.get("x-user-sub") or "").strip() or None
    u = await get_or_create_user(session, email=email, google_sub=sub)
    await session.commit()
    return {
        "credits_enabled": True,
        "balance": int(u.credit_balance),
        "plan": u.plan,
        "starter_redeem_available": not u.starter_redeem_completed,
    }


@app.post("/internal/credits/redeem")
async def internal_credits_redeem(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    body: RedeemBody,
):
    _require_internal_api_key(request, load_settings())
    if session is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    email = (request.headers.get("x-user-email") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="Missing user identity")
    sub = (request.headers.get("x-user-sub") or "").strip() or None
    u = await get_or_create_user(session, email=email, google_sub=sub)
    try:
        await redeem_code(session, u, body.code)
        await session.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await session.refresh(u)
    return {
        "ok": True,
        "plan": u.plan,
        "balance": u.credit_balance,
    }


@app.post("/internal/credits/check-code")
async def internal_credits_check_code(
    request: Request,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    body: RedeemBody,
):
    """Validate a redeem / promo code without applying it (trusted internal route)."""
    _require_internal_api_key(request, load_settings())
    if session is None:
        raise HTTPException(status_code=503, detail="Database not configured")
    email = (request.headers.get("x-user-email") or "").strip()
    if not email:
        raise HTTPException(status_code=401, detail="Missing user identity")
    sub = (request.headers.get("x-user-sub") or "").strip() or None
    u = await get_or_create_user(session, email=email, google_sub=sub)
    result = await check_credit_code(session, u, body.code)
    await session.commit()
    return result


# ---------------------------------------------------------------------------
# Job status polling (async video pipeline)
# ---------------------------------------------------------------------------


@app.get("/api/jobs/{job_id}/status")
async def job_status(job_id: str):
    """Poll for the result of an async job (topic video, photo-to-video, image-to-ad)."""
    entry = _job_results.get(job_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return entry


def _parse_language_form(raw: str) -> LanguageCode:
    v = (raw or "en").strip().lower()
    if v not in ("en", "hi", "mr"):
        raise HTTPException(status_code=400, detail="language must be en, hi, or mr")
    return v  # type: ignore[return-value]


@app.get("/api/tts/voices")
@limiter.limit("60/minute")
async def api_tts_voices(
    request: Request,
    _google_user: GoogleUserDep,
    language: str = Query(..., min_length=2, max_length=8),
):
    settings = load_settings()
    if not settings.google_tts_is_configured():
        return {
            "available": False,
            "language": (language or "en").strip().lower()[:8],
            "locale": None,
            "voices": [],
            "counts": {"male": 0, "female": 0, "neutral": 0, "unspecified": 0},
        }
    lang = _parse_language_form(language)
    data = await asyncio.to_thread(list_google_tts_voices_detail, settings, lang)
    data["available"] = True
    return data


@app.get("/api/tts/preview.mp3")
@limiter.limit(_limiter_bootstrap.rate_limit_tts_preview_effective())
async def api_tts_preview_mp3(
    request: Request,
    _google_user: GoogleUserDep,
    voice: str = Query(..., min_length=4, max_length=120),
    language: str = Query(..., min_length=2, max_length=8),
):
    settings = load_settings()
    if not settings.google_tts_is_configured():
        raise HTTPException(status_code=503, detail="Voice preview is not available on this server.")
    lang = _parse_language_form(language)
    v = (voice or "").strip()

    def _synth_preview() -> bytes:
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            p = Path(tmp.name)
        try:
            synthesize_google_tts_preview_sync(settings, lang, v, p)
            return p.read_bytes()
        finally:
            p.unlink(missing_ok=True)

    try:
        blob = await asyncio.to_thread(_synth_preview)
    except GoogleTtsError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    return Response(
        content=blob,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=300"},
    )


ALLOWED_TARGET_DURATION_SECONDS: frozenset[int] = frozenset(
    {30, 59, 90, 120, 180, 240, 300}
)


def _parse_target_duration_form(raw: str | None) -> int:
    s = (raw or "").strip()
    if not s:
        return 59
    try:
        v = int(s, 10)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="target_duration_seconds must be an integer",
        ) from None
    if v not in ALLOWED_TARGET_DURATION_SECONDS:
        raise HTTPException(
            status_code=400,
            detail=(
                "target_duration_seconds must be one of: "
                "30, 59, 90, 120, 180, 240, 300"
            ),
        )
    return v


def _parse_enhance_motion_form(raw: str | None) -> bool:
    """Optional subtle Ken Burns zoom on slides; independent of target duration."""
    if raw is None:
        return False
    s = str(raw).strip().lower()
    return s in ("1", "true", "yes", "on")


@app.post("/generate", status_code=202)
@limiter.limit(_limiter_bootstrap.rate_limit_generate_effective())
async def generate(
    request: Request,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    _google_user: GoogleUserDep,
    topic: Annotated[str, Form(min_length=1, max_length=USER_PROMPT_MAX_CHARS)],
    language: Annotated[str, Form()] = "en",
    target_duration_seconds: Annotated[str, Form()] = "59",
    enhance_motion: Annotated[str, Form()] = "",
    google_tts_voice: Annotated[str, Form()] = "",
    logo: UploadFile | None = File(None),
    product_image: UploadFile | None = File(None),
    cta_image: UploadFile | None = File(None),
    thumbnail_image: UploadFile | None = File(None),
    address: Annotated[str, Form()] = "",
    content_format: Annotated[str, Form()] = "",
    output_quality: Annotated[str, Form()] = "",
    user_email: Annotated[str, Form()] = "",
    user_sub: Annotated[str, Form()] = "",
):
    settings = load_settings()
    _validate_persistence_config(settings)
    try:
        visual_settings, applied_content_format, applied_output_quality = build_visual_settings_from_forms(
            settings,
            content_format,
            output_quality,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    job_id = str(uuid.uuid4())
    job_uuid = uuid.UUID(job_id)
    job_dir = settings.artifact_root / job_id

    owner_sub: str | None = None
    if _google_user and isinstance(_google_user.get("sub"), str):
        t = _google_user["sub"].strip()
        if t:
            owner_sub = t

    lang = _parse_language_form(language)
    target_sec = _parse_target_duration_form(target_duration_seconds)
    enhance_kb = _parse_enhance_motion_form(enhance_motion)
    gcp_voice_choice = (google_tts_voice or "").strip() or None

    if enhance_kb and not settings.google_tts_is_configured():
        shutil.rmtree(job_dir, ignore_errors=True)
        raise HTTPException(
            status_code=503,
            detail=(
                "Enhance mode uses a two-voice dialogue and needs multi-voice narration enabled on "
                "this server. Turn off Enhance for a single narrator, or ask your administrator "
                "to enable it."
            ),
        )

    try:
        job_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        if e.errno == errno.ENOSPC:
            logger.error("job=%s artifact_root full: %s", job_id, job_dir)
            raise HTTPException(
                status_code=503,
                detail=(
                    "Server disk is full (cannot write under ARTIFACT_ROOT). "
                    "Free space or enlarge the EBS volume, then retry."
                ),
            ) from e
        raise

    try:
        (job_dir / ".owner_sub").write_text((owner_sub or "").strip(), encoding="utf-8")
    except OSError:
        logger.warning("job=%s could not write .owner_sub", job_id)

    branding_file = job_dir / "branding_logo.png"
    branding_applied = await save_branding_logo_from_upload(logo, branding_file)
    address_norm = normalize_address_form(address)
    if address_norm:
        (job_dir / "user_address.txt").write_text(address_norm, encoding="utf-8")

    product_file = job_dir / "user_product.png"
    product_applied = await save_optional_rgba_png(
        product_image,
        product_file,
        label="Product image",
    )
    cta_file = job_dir / "user_cta.png"
    cta_applied = await save_optional_rgba_png(cta_image, cta_file, label="CTA image")
    thumb_file = job_dir / "user_thumbnail.jpg"
    thumbnail_applied = await save_optional_thumbnail_jpeg(thumbnail_image, thumb_file)

    overlay_assets = FrameOverlayAssets(
        branding_logo_path=branding_file if branding_applied else None,
        product_image_path=product_file if product_applied else None,
        cta_image_path=cta_file if cta_applied else None,
        address_text=address_norm,
    )

    persist = settings.persistence_enabled() and session is not None
    credit_cost = standard_video_credit_cost(target_sec, enhance_motion=enhance_kb)
    if settings.credits_billing_enabled() and session is not None:
        cu = await resolve_user_for_credits(
            session,
            google_user=_google_user,
            user_email=user_email,
            user_sub=user_sub,
        )
        if cu is None:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(
                status_code=401,
                detail="Sign in and pass your account email (user_email) to use credits.",
            )
        locked = (
            await session.execute(select(User).where(User.id == cu.id).with_for_update())
        ).scalar_one()
        try:
            await deduct_credits(
                session,
                locked,
                credit_cost,
                reason="standard_video",
                meta={
                    "target_sec": target_sec,
                    "job_id": job_id,
                    "enhance_motion": enhance_kb,
                },
            )
        except InsufficientCreditsError as e:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits: need {credit_cost}, balance {e.balance}.",
            ) from e
        if not persist:
            await session.commit()
        register_credit_hold(job_id, locked.id, credit_cost)

    logger.info(
        "job=%s topic=%s language=%s target_sec=%s enhance_motion=%s branding=%s persist=%s "
        "video=%sx%s content_format=%s output_quality=%s",
        job_id,
        topic[:80],
        lang,
        target_sec,
        enhance_kb,
        branding_applied,
        persist,
        visual_settings.video_width,
        visual_settings.video_height,
        applied_content_format or "-",
        applied_output_quality or "-",
    )

    if persist:
        await job_insert_running(
            session,
            job_uuid,
            topic=topic,
            language=lang,
            branding_logo_applied=branding_applied,
            owner_sub=owner_sub,
        )

    _job_results[job_id] = {"job_id": job_id, "status": "running", "owner_sub": owner_sub}

    asyncio.create_task(
        _run_video_pipeline(
            job_id=job_id,
            job_uuid=job_uuid,
            job_dir=job_dir,
            settings=settings,
            topic=topic,
            lang=lang,
            target_sec=target_sec,
            enhance_kb=enhance_kb,
            gcp_voice_choice=gcp_voice_choice,
            visual_settings=visual_settings,
            applied_content_format=applied_content_format,
            applied_output_quality=applied_output_quality,
            overlay_assets=overlay_assets,
            branding_applied=branding_applied,
            product_applied=product_applied,
            cta_applied=cta_applied,
            thumb_file=thumb_file,
            thumbnail_applied=thumbnail_applied,
            address_norm=address_norm,
            user_email=user_email,
            owner_sub=owner_sub,
        )
    )

    return {"job_id": job_id, "status": "running"}


async def _run_video_pipeline(
    *,
    job_id: str,
    job_uuid: uuid.UUID,
    job_dir: Path,
    settings: Settings,
    topic: str,
    lang: str,
    target_sec: int,
    enhance_kb: bool,
    gcp_voice_choice: str | None,
    visual_settings,
    applied_content_format: str | None,
    applied_output_quality: str | None,
    overlay_assets: FrameOverlayAssets,
    branding_applied: bool,
    product_applied: bool,
    cta_applied: bool,
    thumb_file: Path,
    thumbnail_applied: bool,
    address_norm: str,
    user_email: str,
    owner_sub: str | None,
) -> None:
    """Run the full video pipeline in the background; update _job_results on completion."""
    session_factory = getattr(app.state, "session_factory", None)
    session: AsyncSession | None = None
    persist = settings.persistence_enabled() and session_factory is not None

    if persist and session_factory is not None:
        session = session_factory()

    try:
        await _do_video_pipeline(
            job_id=job_id,
            job_uuid=job_uuid,
            job_dir=job_dir,
            settings=settings,
            topic=topic,
            lang=lang,
            target_sec=target_sec,
            enhance_kb=enhance_kb,
            gcp_voice_choice=gcp_voice_choice,
            visual_settings=visual_settings,
            applied_content_format=applied_content_format,
            applied_output_quality=applied_output_quality,
            overlay_assets=overlay_assets,
            branding_applied=branding_applied,
            product_applied=product_applied,
            cta_applied=cta_applied,
            thumb_file=thumb_file,
            thumbnail_applied=thumbnail_applied,
            address_norm=address_norm,
            user_email=user_email,
            owner_sub=owner_sub,
            session=session,
            persist=persist,
        )
    except Exception as exc:
        logger.exception("job=%s pipeline failed: %s", job_id, exc)
        _job_results[job_id] = {
            "job_id": job_id,
            "status": "failed",
            "error": str(exc),
            "owner_sub": owner_sub,
        }
        if persist and session is not None:
            try:
                await job_mark_failed(session, job_uuid, str(exc)[:4000])
            except Exception:
                logger.warning("job=%s mark_failed after crash also failed", job_id, exc_info=True)
    finally:
        entry = _job_results.get(job_id)
        ok = isinstance(entry, dict) and entry.get("status") == "done"
        await release_credit_hold(session_factory, job_id, success=ok)
        if session is not None:
            await session.close()


async def _do_video_pipeline(
    *,
    job_id: str,
    job_uuid: uuid.UUID,
    job_dir: Path,
    settings: Settings,
    topic: str,
    lang: str,
    target_sec: int,
    enhance_kb: bool,
    gcp_voice_choice: str | None,
    visual_settings,
    applied_content_format: str | None,
    applied_output_quality: str | None,
    overlay_assets: FrameOverlayAssets,
    branding_applied: bool,
    product_applied: bool,
    cta_applied: bool,
    thumb_file: Path,
    thumbnail_applied: bool,
    address_norm: str,
    user_email: str,
    owner_sub: str | None,
    session: AsyncSession | None,
    persist: bool,
) -> None:
    """Inner pipeline logic (extracted so _run_video_pipeline can catch all errors)."""
    t_pipeline_start = time.perf_counter()
    stage_times: dict[str, float] = {}

    async def _fail(msg: str) -> None:
        if persist and session is not None:
            await job_mark_failed(session, job_uuid, msg)
        _job_results[job_id] = {
            "job_id": job_id,
            "status": "failed",
            "error": msg,
            "owner_sub": owner_sub,
        }

    t0 = time.perf_counter()
    try:
        script = await generate_script(
            settings,
            topic,
            lang,
            target_duration_seconds=target_sec,
            conversational=enhance_kb,
        )
    except (ValueError, RuntimeError) as e:
        await _fail(str(e))
        return
    stage_times["script_generation"] = time.perf_counter() - t0
    logger.info("job=%s TIMING script_generation=%.1fs", job_id, stage_times["script_generation"])

    if persist and session is not None:
        await job_update_script(session, job_uuid, script.model_dump())

    script_path = job_dir / "script.json"
    script_path.write_text(script.model_dump_json(indent=2), encoding="utf-8")

    mp3_path = job_dir / "voiceover.mp3"
    tts_provider: Literal["google", "elevenlabs", "coqui"] = "coqui"
    t0 = time.perf_counter()

    async def _tts_coqui_fallback(
        primary_err: Exception,
        primary_label: str,
        fix_hint: str,
    ) -> None:
        nonlocal tts_provider
        try:
            await asyncio.to_thread(
                synthesize_coqui_sync,
                settings,
                script.full_script_plain,
                lang,
                mp3_path,
            )
            tts_provider = "coqui"
        except Exception as ce:
            logger.exception(
                "job=%s Coqui fallback failed %s=%s Coqui=%s",
                job_id,
                primary_label,
                primary_err,
                ce,
            )
            detail = (
                f"Voice generation failed. {primary_label}: {primary_err}. "
                f"Fallback (Coqui): {ce}. {fix_hint}"
            )
            await _fail(detail)
            hint = str(ce).strip()
            if len(hint) > 600:
                hint = hint[:597] + "..."
            raise HTTPException(
                status_code=503,
                detail=hint or "Voice generation failed. Check server logs.",
            ) from ce

    if settings.google_tts_is_configured():
        try:
            if enhance_kb and script.conversational_turns:
                await asyncio.to_thread(
                    synthesize_google_tts_conversational_sync,
                    settings,
                    script.conversational_turns,
                    lang,
                    mp3_path,
                    user_voice=gcp_voice_choice,
                )
            else:
                await asyncio.to_thread(
                    synthesize_google_tts_sync,
                    settings,
                    script.full_script_plain,
                    lang,
                    mp3_path,
                    voice_name=gcp_voice_choice,
                )
            tts_provider = "google"
        except GoogleTtsError as e:
            logger.warning("job=%s Google Cloud TTS failed, trying Coqui: %s", job_id, e)
            await _tts_coqui_fallback(
                e,
                "Primary voice service",
                "Fix: check server voice configuration and logs. "
                "Or install local TTS: pip install -e '.[coqui]'",
            )
    elif settings.elevenlabs_is_configured():
        try:
            await synthesize_elevenlabs(
                settings,
                script.full_script_plain,
                lang,
                mp3_path,
            )
            tts_provider = "elevenlabs"
        except ElevenLabsError as e:
            logger.warning("job=%s ElevenLabs failed, trying Coqui: %s", job_id, e)
            await _tts_coqui_fallback(
                e,
                "ElevenLabs",
                "Fix: set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env (see .env.example), "
                "restart the server, or install local TTS with: pip install -e '.[coqui]'",
            )
    else:
        try:
            await asyncio.to_thread(
                synthesize_coqui_sync,
                settings,
                script.full_script_plain,
                lang,
                mp3_path,
            )
            tts_provider = "coqui"
        except Exception as ce:
            logger.exception("job=%s Coqui TTS failed: %s", job_id, ce)
            detail = (
                f"Voice generation failed (Coqui): {ce}. "
                "Configure cloud voice, ElevenLabs, or install local TTS with: pip install -e '.[coqui]'"
            )
            await _fail(detail)
            hint = str(ce).strip()
            if len(hint) > 600:
                hint = hint[:597] + "..."
            raise HTTPException(
                status_code=503,
                detail=hint or "Voice generation failed. Check server logs.",
            ) from ce

    stage_times["tts"] = time.perf_counter() - t0
    logger.info("job=%s TIMING tts=%.1fs provider=%s", job_id, stage_times["tts"], tts_provider)

    t0 = time.perf_counter()
    mp3_path = await asyncio.to_thread(
        trim_mp3_to_max_duration,
        mp3_path,
        float(target_sec),
        ffmpeg_explicit=settings.ffmpeg_path,
    )
    stage_times["audio_trim"] = time.perf_counter() - t0

    mp4_path = job_dir / "output.mp4"
    visual_mode: Literal[
        "gemini_native_image_slideshow",
        "vertex_gemini_image_slideshow",
        "google_imagen_slideshow",
        "nano_banana_slideshow",
        "title_card",
    ] = "title_card"
    visual_detail: str | None = None

    if not settings.slide_visuals_configured():
        visual_detail = (
            "No slide API configured. Add GEMINI_API_KEY for Gemini 3.1 native image, set VERTEX_IMAGEN_PROJECT "
            "and a service account for Vertex Imagen / Gemini 2.5 image, or set NANO_BANANA_API_KEY."
        )

    t0 = time.perf_counter()
    image_paths: list[Path] | None = None
    slides_dir = job_dir / "slides"
    product_ref_path = product_file if product_applied and product_file.is_file() else None
    used_multimodal_product_ref = False

    if settings.gemini_native_image_configured():
        try:
            image_paths = await generate_gemini_native_slide_images(
                visual_settings,
                topic,
                script,
                lang,
                slides_dir,
                reserve_product_hero_zone=product_applied and product_ref_path is None,
                product_reference_path=product_ref_path,
            )
            visual_mode = "gemini_native_image_slideshow"
        except (GeminiNativeImageError, RuntimeError, ValueError) as e:
            logger.warning("job=%s Gemini native image (Nano Banana 2) slides failed: %s", job_id, e)
            visual_detail = f"Gemini native image: {e}"[:600]
        else:
            used_multimodal_product_ref = bool(product_ref_path)

    if image_paths is None and settings.vertex_gemini_image_configured():
        try:
            image_paths = await generate_vertex_gemini_slide_images(
                visual_settings,
                topic,
                script,
                lang,
                slides_dir,
                reserve_product_hero_zone=product_applied and product_ref_path is None,
                product_reference_path=product_ref_path,
            )
            visual_mode = "vertex_gemini_image_slideshow"
        except (VertexGeminiImageError, RuntimeError, ValueError) as e:
            logger.warning("job=%s Vertex Gemini image slides failed: %s", job_id, e)
            extra = f"Vertex Gemini image: {e}"[:600]
            visual_detail = f"{visual_detail} · {extra}" if visual_detail else extra
        else:
            used_multimodal_product_ref = bool(product_ref_path)

    if image_paths is None and settings.gemini_imagen_configured():
        try:
            image_paths = await generate_imagen_slide_images(
                visual_settings,
                topic,
                script,
                lang,
                slides_dir,
                reserve_product_hero_zone=product_applied,
            )
            visual_mode = "google_imagen_slideshow"
        except (GoogleImagenError, RuntimeError, ValueError) as e:
            logger.warning("job=%s Google Imagen slides failed: %s", job_id, e)
            extra = f"Imagen: {e}"[:600]
            visual_detail = f"{visual_detail} · {extra}" if visual_detail else extra
        else:
            used_multimodal_product_ref = False

    if image_paths is None and settings.nano_banana_configured():
        try:
            image_paths = await generate_slide_images(
                visual_settings,
                topic,
                script,
                lang,
                slides_dir,
                reserve_product_hero_zone=product_applied,
            )
            visual_mode = "nano_banana_slideshow"
        except (NanoBananaError, RuntimeError, ValueError) as e:
            logger.warning("job=%s Nano Banana slides failed: %s", job_id, e)
            extra = f"Nano Banana: {e}"[:600]
            visual_detail = f"{visual_detail} · {extra}" if visual_detail else extra
        else:
            used_multimodal_product_ref = False

    stage_times["slide_image_gen"] = time.perf_counter() - t0
    logger.info(
        "job=%s TIMING slide_image_gen=%.1fs slides=%s mode=%s",
        job_id, stage_times["slide_image_gen"],
        len(image_paths) if image_paths else 0, visual_mode,
    )

    if image_paths is not None:
        slideshow_overlay = overlay_assets
        if product_applied and product_file.is_file():
            if not used_multimodal_product_ref:
                t0 = time.perf_counter()
                stem_vis = visibility_by_slide_stem(
                    topic,
                    script_visual_segments(script),
                    script.visual_segments_en,
                )
                composite_tasks = [
                    asyncio.to_thread(composite_user_product_onto_slide, sp, product_file)
                    for sp in image_paths
                    if stem_vis.get(sp.stem, False)
                ]
                if composite_tasks:
                    await asyncio.gather(*composite_tasks)
                stage_times["product_composite"] = time.perf_counter() - t0
                logger.info(
                    "job=%s TIMING product_composite=%.1fs composites=%d",
                    job_id, stage_times["product_composite"], len(composite_tasks),
                )
            slideshow_overlay = replace(overlay_assets, product_image_path=None)
        try:
            ffprobe = resolve_ffprobe(settings.ffmpeg_path)
            if not ffprobe:
                raise RuntimeError(
                    "ffprobe not found (usually installed with ffmpeg). "
                    "Install ffmpeg fully or fix FFMPEG_PATH."
                )
            total_audio = audio_duration_seconds(ffprobe, mp3_path)
            segment_texts = [t for _, t in script_visual_segments(script)]
            paths_mux = list(image_paths)
            dedicated_cta = False
            if cta_applied and cta_file.is_file():
                durs_script, cta_dur = slideshow_durations_with_cta_coda(
                    segment_texts, total_audio
                )
                if cta_dur >= 0.5:
                    cta_slide_path = job_dir / "slide_cta_dedicated.png"
                    await asyncio.to_thread(
                        render_dedicated_cta_slide_png,
                        cta_slide_path,
                        visual_settings.video_width,
                        visual_settings.video_height,
                        cta_file,
                    )
                    paths_mux.append(cta_slide_path)
                    durs = [*durs_script, cta_dur]
                    dedicated_cta = True
                    slideshow_overlay = replace(slideshow_overlay, cta_image_path=None)
                else:
                    durs = word_weighted_durations(segment_texts, total_audio)
            else:
                durs = word_weighted_durations(segment_texts, total_audio)
            t0 = time.perf_counter()
            mux_slideshow_with_audio(
                paths_mux,
                durs,
                mp3_path,
                mp4_path,
                visual_settings.video_width,
                visual_settings.video_height,
                ffmpeg_explicit=settings.ffmpeg_path,
                overlay_assets=slideshow_overlay,
                ken_burns=enhance_kb,
                final_slide_is_dedicated_cta=dedicated_cta,
            )
            stage_times["slideshow_mux"] = time.perf_counter() - t0
            logger.info(
                "job=%s TIMING slideshow_mux=%.1fs slides=%d",
                job_id, stage_times["slideshow_mux"], len(paths_mux),
            )
        except (RuntimeError, ValueError) as e:
            logger.warning(
                "job=%s slideshow mux failed, using title card: %s",
                job_id,
                e,
            )
            image_paths = None
            visual_mode = "title_card"
            visual_detail = f"Slide video assembly: {e}"[:600]

    if image_paths is None:
        png_path = job_dir / "title.png"
        render_title_card(visual_settings, topic, lang, png_path)
        try:
            mux_still_image_and_audio(
                png_path,
                mp3_path,
                mp4_path,
                ffmpeg_explicit=settings.ffmpeg_path,
                video_width=visual_settings.video_width,
                video_height=visual_settings.video_height,
                overlay_assets=overlay_assets,
            )
        except RuntimeError as e:
            await _fail(str(e))
            raise HTTPException(status_code=500, detail=str(e)) from e

    thumbnail_attached = False
    if thumbnail_applied and thumb_file.is_file():
        try:
            await asyncio.to_thread(
                attach_thumbnail_to_mp4,
                mp4_path,
                thumb_file,
                ffmpeg_explicit=settings.ffmpeg_path,
            )
            thumbnail_attached = True
        except Exception as e:
            logger.warning("job=%s embed thumbnail failed: %s", job_id, e)

    if visual_mode != "title_card":
        visual_detail = None

    if persist and session is not None:
        t0 = time.perf_counter()
        try:
            s3_keys = await asyncio.to_thread(upload_job_directory, settings, job_dir, job_id)
            await job_mark_succeeded(
                session,
                job_uuid,
                tts_provider=tts_provider,
                visual_mode=visual_mode,
                visual_detail=visual_detail,
                branding_logo_applied=branding_applied,
                s3_keys=s3_keys,
            )
        except S3UploadError as e:
            logger.exception("job=%s S3 upload failed: %s", job_id, e)
            await _fail(str(e))
            raise HTTPException(
                status_code=503,
                detail="Video storage failed. Try again later.",
            ) from e
        stage_times["s3_upload"] = time.perf_counter() - t0
        logger.info("job=%s TIMING s3_upload=%.1fs", job_id, stage_times["s3_upload"])
        if settings.artifact_cleanup_after_s3:
            await asyncio.to_thread(_cleanup_job_dir, str(job_dir.resolve()))

    ue = (user_email or "").strip()
    if ue and persist and session is not None:
        try:
            await media_insert(
                session,
                owner_email=ue,
                media_type="video",
                title=topic[:200],
                media_url=f"/media/{job_id}/output.mp4",
                source_service="topic-to-video",
                thumbnail_url=None,
                extra={"job_id": job_id, "visual_mode": visual_mode, "tts_provider": tts_provider},
            )
        except Exception:
            logger.warning("job=%s media_insert failed (non-fatal)", job_id, exc_info=True)

    total_elapsed = time.perf_counter() - t_pipeline_start
    stage_summary = " ".join(f"{k}={v:.1f}s" for k, v in stage_times.items())
    logger.info(
        "job=%s TIMING TOTAL=%.1fs visual_mode=%s tts=%s slides=%d | %s",
        job_id, total_elapsed, visual_mode, tts_provider,
        len(image_paths) if image_paths is not None else 0,
        stage_summary,
    )

    _job_results[job_id] = {
        "job_id": job_id,
        "status": "done",
        "mp3_url": f"/media/{job_id}/voiceover.mp3",
        "mp4_url": f"/media/{job_id}/output.mp4",
        "video_width": visual_settings.video_width,
        "video_height": visual_settings.video_height,
        "tts_provider": tts_provider,
        "visual_mode": visual_mode,
        "owner_sub": owner_sub,
    }


# ---------------------------------------------------------------------------
# Media routes for standalone image / Veo3 video / voice generation
# ---------------------------------------------------------------------------


@app.get("/media/img/{job_dir}/{filename}")
async def serve_generated_image(job_dir: str, filename: str):
    """Serve standalone generated images."""
    settings = get_settings()
    _validate_standalone_img_path(job_dir, filename)
    file_path = _resolve_artifact_file_under_root(settings, job_dir, filename)
    return FileResponse(file_path, media_type="image/png")


@app.get("/media/veo3/{job_dir}/{filename}")
async def serve_veo3_video(job_dir: str, filename: str):
    """Serve Veo-generated videos from local disk, or redirect to S3 presigned URL when applicable."""
    settings = get_settings()
    _validate_standalone_veo3_path(job_dir, filename)
    file_path = settings.artifact_root.resolve() / job_dir / filename
    root = settings.artifact_root.resolve()
    try:
        file_path = file_path.resolve()
        file_path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="Video not found") from None
    if file_path.is_file():
        return FileResponse(file_path, media_type="video/mp4")
    if settings.s3_object_storage_configured():
        key = settings.s3_key_for_veo3(job_dir, filename)
        try:
            url = await asyncio.to_thread(safe_presign_get, settings, key)
            return RedirectResponse(url=url, status_code=302)
        except S3UploadError as e:
            logger.warning("veo3 presign failed job_dir=%s file=%s: %s", job_dir, filename, e)
            raise HTTPException(status_code=503, detail="Could not sign media URL") from e
    raise HTTPException(status_code=404, detail="Video not found")


@app.get("/media/voice/{job_id}/{filename}")
async def serve_generated_voice(job_id: str, filename: str):
    """Serve standalone generated voice audio."""
    settings = get_settings()
    _validate_standalone_voice_path(job_id, filename)
    voice_dir = f"voice_{job_id}"
    file_path = _resolve_artifact_file_under_root(settings, voice_dir, filename)
    return FileResponse(file_path, media_type="audio/mpeg")


# ---------------------------------------------------------------------------
# Standalone generation endpoints
# ---------------------------------------------------------------------------


@app.get("/api/portrait-templates")
async def list_portrait_templates():
    """Return available portrait style templates for the frontend grid."""
    templates = [
        {"id": k, "label": k.replace("_", " ").title()}
        for k in _PORTRAIT_STYLE_PREFIX
    ]
    return {"templates": templates}


_TEXT_STYLE_PREFIX = {
    "photorealistic": "Photorealistic cinematic photograph, shot on professional cinema camera, shallow depth of field, natural lighting. ",
    "cinematic": "Cinematic film still, dramatic lighting, anamorphic lens flare, color graded. ",
    "illustration": "Digital illustration, clean lines, vibrant colors, detailed artwork. ",
    "3d_render": "3D rendered scene, realistic materials, global illumination, octane render quality. ",
    "anime": "Anime-style illustration, vibrant colors, expressive, detailed character art. ",
    "watercolor": "Watercolor painting, soft washes, visible brush strokes, artistic and dreamy. ",
}

_PORTRAIT_IDENTITY_SUFFIX = (
    " Preserve the exact facial features, face shape, bone structure, eyes, and expression of this person."
    " The result must be unmistakably this person."
    " No text, captions, watermarks, or logos in the image."
)

# Stronger than generic "no logos" — some image models paint model-id strings in a corner.
_STANDALONE_IMAGE_NO_LABEL_SUFFIX = (
    " Do not render any visible model names, API labels, version strings "
    "(such as gemini, flash, preview, imagen, or vertex), corner captions, or technology watermarks."
)

_PORTRAIT_STYLE_PREFIX = {
    "ink_sketch": "Transform this person into a dramatic black and white ink sketch portrait. Crosshatching technique, half-face close-up composition, textured paper background, ink splatter accents, bold contrast, celebrity magazine cover quality.",
    "bold_text": "Transform this person into a dramatic black and white ink sketch portrait, half-face close-up composition with bold large title text overlaid on the empty side. Crosshatching and ink splatter details, textured paper, magazine poster design.",
    "street_art": "Transform this person into a street art graffiti style portrait. Black and white base photo with colorful spray paint scribbles, marker doodles, paint brush strokes overlaid. Urban concrete wall texture background, indie zine aesthetic, raw and edgy.",
    "sticky_notes": "Transform this person into a creative portrait covered with sticky notes and post-it notes on their face and around them. Each note has handwritten text with life goals and ideas. Clean studio background, content creator aesthetic, motivational mood board style.",
    "polaroid": "Transform this person into a cinematic portrait holding a polaroid photo of themselves. Multiple floating polaroid photos scattered in the background showing different expressions. Warm moody library or studio setting, shallow depth of field, nostalgic film quality.",
    "monochrome": "Transform this person into a high contrast black and white studio portrait. Professional fashion photography, dramatic single-source lighting, sharp details, editorial magazine quality.",
    "color_block": "Transform this person into a bold pop art portrait with flat color blocks, graphic design aesthetic, vivid saturated colors, modern poster style.",
    "runway": "Transform this person into a high fashion editorial portrait, dramatic runway lighting, shallow depth of field, Vogue magazine cover quality.",
    "risograph": "Transform this person into a risograph print style portrait, halftone dots, limited two-tone color palette, vintage print texture, indie art zine aesthetic.",
    "technicolor": "Transform this person into a vibrant technicolor portrait, retro Hollywood golden age glamour, rich saturated warm colors, classic film star quality.",
    "gothic_clay": "Transform this person into a dark gothic clay sculpture portrait, dramatic chiaroscuro shadows, museum quality, Renaissance master painting aesthetic.",
    "dynamite": "Transform this person into an explosive cinematic action portrait with dramatic fire and sparks, intense energy, blockbuster movie poster composition.",
    "steampunk": "Transform this person into a steampunk portrait with Victorian industrial aesthetic, brass goggles, mechanical gears, warm sepia tones, adventure explorer look.",
    "sunrise": "Transform this person into a golden hour backlit portrait, warm sunrise tones, ethereal soft glow, dreamy atmosphere, silhouette rim lighting.",
    "satou": "Transform this person into a minimalist Japanese aesthetic portrait, clean lines, muted earth tones, wabi-sabi beauty, serene composition.",
    "cinematic_portrait": "Transform this person into a cinematic film still portrait, dramatic side lighting, shallow depth of field, film grain, moody color grading, Hollywood movie star quality.",
}


@app.post("/api/generate-image")
async def api_generate_image(
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    prompt: Annotated[str, Form()],
    style: Annotated[str, Form()] = "photorealistic",
    aspect_ratio: Annotated[str, Form()] = "1:1",
    count: Annotated[int, Form()] = 1,
    image: UploadFile | None = File(None),
    user_email: Annotated[str, Form()] = "",
    user_sub: Annotated[str, Form()] = "",
):
    """Standalone image generation (Gemini native, then Vertex Gemini, then Vertex Imagen).

    When an *image* file is uploaded the model receives it as a reference photo
    for face-preserving portrait stylisation.
    """
    from app.services.standalone_image_gen import generate_standalone_image, ImageGenResult

    settings = get_settings()
    prompt_clean = (prompt or "").strip()
    if not prompt_clean:
        raise HTTPException(status_code=422, detail="prompt is required")
    if len(prompt_clean) > USER_PROMPT_MAX_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"prompt too long (max {USER_PROMPT_MAX_CHARS} characters)",
        )

    count = max(1, min(count, 4))
    logger.info(
        "generate-image: count=%s style=%s aspect=%s has_upload=%s",
        count,
        style,
        aspect_ratio,
        image is not None and bool(image.filename),
    )

    reference_bytes: bytes | None = None
    if image is not None and image.filename:
        reference_bytes = await image.read()
        if len(reference_bytes) < 100:
            reference_bytes = None

    if reference_bytes:
        portrait_prefix = _PORTRAIT_STYLE_PREFIX.get(style, "")
        if portrait_prefix:
            full_prompt = f"{portrait_prefix}{_PORTRAIT_IDENTITY_SUFFIX}"
        else:
            full_prompt = f"{prompt_clean}.{_PORTRAIT_IDENTITY_SUFFIX}"
    else:
        style_prefix = _TEXT_STYLE_PREFIX.get(style, "")
        full_prompt = f"{style_prefix}{prompt_clean}. No text, captions, watermarks, or logos in the image."

    full_prompt = f"{full_prompt}{_STANDALONE_IMAGE_NO_LABEL_SUFFIX}"

    images = []
    errors = []
    for i in range(count):
        try:
            result = await generate_standalone_image(
                settings, full_prompt, aspect_ratio=aspect_ratio,
                reference_image=reference_bytes,
            )
            images.append({
                "url": f"/media/img/{result.path.parent.name}/{result.path.name}",
                "width": result.width,
                "height": result.height,
                "model": "",
            })
        except Exception as e:
            logger.exception("generate-image failed (image %s): %s", i + 1, e)
            errors.append(str(e))

    if not images:
        raise HTTPException(
            status_code=503,
            detail=f"All image generation attempts failed: {'; '.join(errors)}",
        )

    settings_credits = get_settings()
    img_cost = len(images) * IMAGE_CREDITS_PER_IMAGE
    if settings_credits.credits_billing_enabled() and session is not None:
        cu = await resolve_user_for_credits(
            session,
            google_user=None,
            user_email=user_email,
            user_sub=user_sub,
        )
        if cu is None:
            raise HTTPException(
                status_code=401,
                detail="Sign in and pass user_email to use credits for image generation.",
            )
        locked = (
            await session.execute(select(User).where(User.id == cu.id).with_for_update())
        ).scalar_one()
        try:
            await deduct_credits(
                session,
                locked,
                img_cost,
                reason="generate_image",
                meta={"count": len(images)},
            )
        except InsufficientCreditsError as e:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits: need {img_cost}, balance {e.balance}.",
            ) from e
        await session.commit()

    img_job_id = uuid.uuid4().hex[:12]
    ue = (user_email or "").strip()
    if ue and session is not None and images:
        try:
            await media_insert(
                session,
                owner_email=ue,
                media_type="image",
                title=prompt_clean[:200],
                media_url=images[0]["url"],
                source_service="text-to-image",
                extra={"style": style, "count": len(images), "images": images},
            )
        except Exception:
            logger.warning("generate-image media_insert failed (non-fatal)", exc_info=True)

    return {
        "job_id": img_job_id,
        "images": images,
        "prompt_used": full_prompt[:300],
    }


@app.post("/api/photo-to-video")
async def api_photo_to_video(
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    task: Annotated[str, Form()] = "image_to_video",
    photo: Annotated[UploadFile | None, File()] = None,
    end_photo: Annotated[UploadFile | None, File()] = None,
    motion_prompt: Annotated[str, Form()] = "",
    duration: Annotated[int, Form()] = 8,
    camera_movement: Annotated[str, Form()] = "zoom_in",
    aspect_ratio: Annotated[str, Form()] = "16:9",
    user_email: Annotated[str, Form()] = "",
    user_sub: Annotated[str, Form()] = "",
    video_tier: Annotated[str, Form()] = "1080",
):
    """Veo 3.1 Lite: text-to-video, image-to-video, or first+last-frame video (async job + poll)."""
    from app.services.veo3_video import _veo_duration_seconds

    settings = get_settings()
    raw_task = (task or "image_to_video").strip().lower().replace("-", "_")
    if raw_task in ("text", "text_to_video"):
        veo_task = "text_to_video"
    elif raw_task in ("image", "image_to_video", "photo", "photo_to_video"):
        veo_task = "image_to_video"
    else:
        raise HTTPException(
            status_code=422,
            detail="task must be text_to_video or image_to_video",
        )

    motion_text = (motion_prompt or "").strip()
    if len(motion_text) > USER_PROMPT_MAX_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Prompt too long (max {USER_PROMPT_MAX_CHARS} characters)",
        )
    if veo_task == "text_to_video" and len(motion_text) < 3:
        raise HTTPException(status_code=422, detail="Enter a prompt for text-to-video")

    image_bytes: bytes | None = None
    end_bytes: bytes | None = None
    if veo_task == "image_to_video":
        if photo is None:
            raise HTTPException(status_code=422, detail="Start frame image is required")
        image_bytes = await photo.read()
        if len(image_bytes) < 100:
            raise HTTPException(status_code=422, detail="Start frame file is empty or too small")
        if end_photo is not None:
            end_raw = await end_photo.read()
            if len(end_raw) >= 100:
                end_bytes = end_raw

    snap_d = _veo_duration_seconds(duration)
    is_1080 = (video_tier or "1080").strip().lower() != "720"
    veo_cost = veo_credits_for_seconds(snap_d, is_1080p=is_1080)
    charged_user: User | None = None
    if settings.credits_billing_enabled() and session is not None:
        cu = await resolve_user_for_credits(
            session,
            google_user=None,
            user_email=user_email,
            user_sub=user_sub,
        )
        if cu is None:
            raise HTTPException(
                status_code=401,
                detail="Sign in and pass user_email to use credits for Veo video.",
            )
        if not can_use_premium_models(cu):
            raise HTTPException(
                status_code=403,
                detail="Veo requires Starter. Redeem an invite or promo code in Settings.",
            )
        locked = (
            await session.execute(select(User).where(User.id == cu.id).with_for_update())
        ).scalar_one()
        debit_reason = (
            "veo_text_to_video"
            if veo_task == "text_to_video"
            else "veo_frame_to_video"
            if end_bytes
            else "veo_photo_to_video"
        )
        try:
            await deduct_credits(
                session,
                locked,
                veo_cost,
                reason=debit_reason,
                meta={
                    "duration_sec": snap_d,
                    "tier": "1080" if is_1080 else "720",
                    "task": veo_task,
                    "end_frame": bool(end_bytes),
                },
            )
        except InsufficientCreditsError as e:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits: need {veo_cost}, balance {e.balance}.",
            ) from e
        await session.commit()
        charged_user = locked

    job_id = uuid.uuid4().hex[:12]
    _job_results[job_id] = {"job_id": job_id, "status": "running"}
    asyncio.create_task(
        _run_photo_to_video_job(
            job_id=job_id,
            veo_task=veo_task,
            image_bytes=image_bytes,
            end_bytes=end_bytes,
            motion_text=motion_text,
            duration=duration,
            camera_movement=camera_movement,
            aspect_ratio=aspect_ratio,
            is_1080=is_1080,
            charged_user_id=charged_user.id if charged_user is not None else None,
            veo_cost=veo_cost,
            user_email=(user_email or "").strip(),
        )
    )
    return JSONResponse(
        content={"job_id": job_id, "status": "running"},
        status_code=202,
    )


@app.post("/api/image-to-ad")
async def api_image_to_ad(
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    product_image: Annotated[UploadFile, File()],
    ad_copy: Annotated[str, Form()] = "",
    cta_text: Annotated[str, Form()] = "",
    template: Annotated[str, Form()] = "product_showcase",
    duration: Annotated[int, Form()] = 30,
    aspect_ratio: Annotated[str, Form()] = "9:16",
    brand_color: Annotated[str, Form()] = "#8b5cf6",
    logo: Annotated[UploadFile | None, File()] = None,
    user_email: Annotated[str, Form()] = "",
    user_sub: Annotated[str, Form()] = "",
    video_tier: Annotated[str, Form()] = "1080",
):
    """Generate an ad video from a product image using Vertex Veo (async job + poll)."""
    from app.services.veo3_video import _veo_duration_seconds

    settings = get_settings()
    ad_copy_clean = (ad_copy or "").strip()
    if len(ad_copy_clean) > USER_PROMPT_MAX_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Ad copy too long (max {USER_PROMPT_MAX_CHARS} characters)",
        )

    image_bytes = await product_image.read()
    if len(image_bytes) < 100:
        raise HTTPException(status_code=422, detail="Product image is empty or too small")

    dur_req = min(int(duration), 15)
    snap_d = _veo_duration_seconds(dur_req)
    is_1080 = (video_tier or "1080").strip().lower() != "720"
    veo_cost = veo_credits_for_seconds(snap_d, is_1080p=is_1080)
    charged_user: User | None = None
    if settings.credits_billing_enabled() and session is not None:
        cu = await resolve_user_for_credits(
            session,
            google_user=None,
            user_email=user_email,
            user_sub=user_sub,
        )
        if cu is None:
            raise HTTPException(
                status_code=401,
                detail="Sign in and pass user_email to use credits for Veo video.",
            )
        if not can_use_premium_models(cu):
            raise HTTPException(
                status_code=403,
                detail="Veo requires Starter. Redeem an invite or promo code in Settings.",
            )
        locked = (
            await session.execute(select(User).where(User.id == cu.id).with_for_update())
        ).scalar_one()
        try:
            await deduct_credits(
                session,
                locked,
                veo_cost,
                reason="veo_image_to_ad",
                meta={"duration_sec": snap_d, "tier": "1080" if is_1080 else "720"},
            )
        except InsufficientCreditsError as e:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits: need {veo_cost}, balance {e.balance}.",
            ) from e
        await session.commit()
        charged_user = locked

    job_id = uuid.uuid4().hex[:12]
    _job_results[job_id] = {"job_id": job_id, "status": "running"}
    asyncio.create_task(
        _run_image_to_ad_job(
            job_id=job_id,
            image_bytes=image_bytes,
            ad_copy_clean=ad_copy_clean,
            cta_text=(cta_text or "").strip(),
            template=template,
            form_duration=duration,
            aspect_ratio=aspect_ratio,
            is_1080=is_1080,
            charged_user_id=charged_user.id if charged_user is not None else None,
            veo_cost=veo_cost,
            user_email=(user_email or "").strip(),
        )
    )
    return JSONResponse(
        content={"job_id": job_id, "status": "running"},
        status_code=202,
    )


@app.post("/api/generate-voice")
async def api_generate_voice(
    session: Annotated[AsyncSession | None, Depends(get_db_session)],
    text: Annotated[str, Form()],
    language: Annotated[str, Form()] = "en",
    voice: Annotated[str, Form()] = "",
    speed: Annotated[float, Form()] = 1.0,
    user_email: Annotated[str, Form()] = "",
    user_sub: Annotated[str, Form()] = "",
):
    """Generate speech audio from text using Google TTS / ElevenLabs."""
    settings = get_settings()
    text_clean = (text or "").strip()
    if not text_clean:
        raise HTTPException(status_code=422, detail="text is required")
    if len(text_clean) > 5000:
        raise HTTPException(status_code=422, detail="text too long (max 5000 chars)")

    job_id = uuid.uuid4().hex[:12]
    output_dir = settings.artifact_root / f"voice_{job_id}"
    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / f"audio_{job_id}.mp3"

    tts_provider = "none"
    lang = _parse_language_form(language)

    if settings.google_tts_is_configured():
        try:
            patched_settings = settings.model_copy(update={
                "google_tts_speaking_rate": speed,
            })
            await asyncio.to_thread(
                synthesize_google_tts_sync,
                patched_settings,
                text_clean,
                lang,
                audio_path,
                voice_name=voice if voice else None,
            )
            if audio_path.is_file() and audio_path.stat().st_size > 100:
                tts_provider = "google"
        except Exception as e:
            logger.warning("generate-voice Google TTS failed: %s", e)

    if tts_provider == "none" and settings.elevenlabs_is_configured():
        try:
            await synthesize_elevenlabs(settings, text_clean, lang, audio_path)
            if audio_path.is_file() and audio_path.stat().st_size > 100:
                tts_provider = "elevenlabs"
        except Exception as e:
            logger.warning("generate-voice ElevenLabs failed: %s", e)

    if tts_provider == "none":
        raise HTTPException(status_code=503, detail="No TTS provider available")

    voice_cost = tts_credits_for_chars(len(text_clean))
    if settings.credits_billing_enabled() and session is not None:
        cu = await resolve_user_for_credits(
            session,
            google_user=None,
            user_email=user_email,
            user_sub=user_sub,
        )
        if cu is None:
            raise HTTPException(
                status_code=401,
                detail="Sign in and pass user_email to use credits for voice generation.",
            )
        locked = (
            await session.execute(select(User).where(User.id == cu.id).with_for_update())
        ).scalar_one()
        try:
            await deduct_credits(
                session,
                locked,
                voice_cost,
                reason="tts_generate",
                meta={"chars": len(text_clean)},
            )
        except InsufficientCreditsError as e:
            raise HTTPException(
                status_code=402,
                detail=f"Insufficient credits: need {voice_cost}, balance {e.balance}.",
            ) from e
        await session.commit()

    duration = 0.0
    try:
        ffprobe = resolve_ffprobe(settings.ffmpeg_path)
        if ffprobe:
            duration = await asyncio.to_thread(audio_duration_seconds, ffprobe, audio_path)
    except Exception:
        pass

    audio_url = f"/media/voice/{job_id}/{audio_path.name}"

    ue = (user_email or "").strip()
    if ue and session is not None:
        try:
            await media_insert(
                session,
                owner_email=ue,
                media_type="voice",
                title=text_clean[:200],
                media_url=audio_url,
                source_service="text-to-voice",
                extra={"duration": round(duration, 1), "tts_provider": tts_provider, "voice": voice or "auto"},
            )
        except Exception:
            logger.warning("generate-voice media_insert failed (non-fatal)", exc_info=True)

    return {
        "job_id": job_id,
        "audio_url": audio_url,
        "duration_seconds": round(duration, 1),
        "tts_provider": tts_provider,
        "voice_used": voice or "auto",
    }
