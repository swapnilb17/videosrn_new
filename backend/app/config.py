import logging
import os
from pathlib import Path
from urllib.parse import urlparse

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load dotenv from repo root first, then backend/ (later files override). Cwd-independent.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent


def _env_file_tuple() -> tuple[Path, ...] | None:
    ordered = [_REPO_ROOT / ".env", _BACKEND_DIR / ".env"]
    found = [p for p in ordered if p.is_file()]
    return tuple(found) if found else None


_ENV_FILE = _BACKEND_DIR / ".env"
# Primary backend .env path for startup diagnostics / docs.
SETTINGS_DOTENV_PATH = _ENV_FILE
# Historically "project root" meant the backend package root (where data/ and .env live).
_PROJECT_ROOT = _BACKEND_DIR

logger = logging.getLogger(__name__)
_IMAGEN_STANDARD_REMAP_LOGGED = False


def normalize_s3_bucket_name(raw: str | None) -> str:
    """Boto3 expects a bucket name, not a console or object URL."""
    s = (raw or "").strip()
    if not s:
        return ""
    if not s.lower().startswith(("http://", "https://")):
        return s
    parsed = urlparse(s)
    host = (parsed.netloc or "").strip()
    hl = host.lower()
    if hl and ".s3." in hl and not hl.startswith("s3."):
        return host.split(".s3.", 1)[0]
    path_parts = [p for p in (parsed.path or "").split("/") if p]
    if path_parts:
        return path_parts[0]
    return s


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file_tuple(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-5", validation_alias="OPENAI_MODEL")
    openai_timeout: float = Field(default=120.0, validation_alias="OPENAI_TIMEOUT")

    elevenlabs_api_key: str = Field(default="", validation_alias="ELEVENLABS_API_KEY")
    elevenlabs_voice_id: str = Field(default="", validation_alias="ELEVENLABS_VOICE_ID")
    elevenlabs_voice_en: str = Field(default="", validation_alias="ELEVENLABS_VOICE_EN")
    elevenlabs_voice_hi: str = Field(default="", validation_alias="ELEVENLABS_VOICE_HI")
    elevenlabs_voice_mr: str = Field(default="", validation_alias="ELEVENLABS_VOICE_MR")
    elevenlabs_model_id: str = Field(
        default="eleven_multilingual_v2",
        validation_alias="ELEVENLABS_MODEL_ID",
    )
    elevenlabs_timeout: float = Field(default=120.0, validation_alias="ELEVENLABS_TIMEOUT")

    # Google Cloud Text-to-Speech (service account JSON). Uses GOOGLE_APPLICATION_CREDENTIALS if unset.
    google_tts_credentials_json_path: str = Field(
        default="",
        validation_alias=AliasChoices(
            "GOOGLE_TTS_CREDENTIALS_JSON",
            "GOOGLE_TTS_CREDENTIALS",
        ),
    )
    google_tts_voice_en: str = Field(default="", validation_alias="GOOGLE_TTS_VOICE_EN")
    google_tts_voice_hi: str = Field(default="", validation_alias="GOOGLE_TTS_VOICE_HI")
    google_tts_voice_mr: str = Field(default="", validation_alias="GOOGLE_TTS_VOICE_MR")
    google_tts_max_input_bytes: int = Field(
        default=4500,
        validation_alias="GOOGLE_TTS_MAX_INPUT_BYTES",
    )
    google_tts_speaking_rate: float = Field(
        default=1.0,
        validation_alias="GOOGLE_TTS_SPEAKING_RATE",
    )
    google_tts_pitch: float = Field(default=0.0, validation_alias="GOOGLE_TTS_PITCH")
    # When true, treat Google TTS as configured without a JSON path (use ADC: GCE/GKE workload identity,
    # or EC2/instance metadata when the VM has an attached service account with roles/cloudtexttospeech.user).
    google_tts_use_adc: bool = Field(default=False, validation_alias="GOOGLE_TTS_USE_ADC")

    # Full path to ffmpeg if not on PATH (e.g. /opt/homebrew/bin/ffmpeg)
    ffmpeg_path: str = Field(default="", validation_alias="FFMPEG_PATH")

    # Google AI Studio — same key as Gemini; used for Imagen slide generation
    gemini_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    )
    imagen_model: str = Field(
        default="imagen-4.0-fast-generate-001",
        validation_alias="IMAGEN_MODEL",
    )
    imagen_image_size: str = Field(default="1K", validation_alias="IMAGEN_IMAGE_SIZE")
    imagen_aspect_ratio: str = Field(default="9:16", validation_alias="IMAGEN_ASPECT_RATIO")
    imagen_person_generation: str = Field(
        default="allow_adult",
        validation_alias="IMAGEN_PERSON_GENERATION",
    )
    # Vertex/Gemini Imagen: block_medium_and_above (default API) | block_only_high | block_low_and_above | block_none
    imagen_safety_setting: str = Field(default="", validation_alias="IMAGEN_SAFETY_SETTING")
    gemini_timeout: float = Field(default=180.0, validation_alias="GEMINI_TIMEOUT")
    # Parallel image API calls. Higher values cut wall time but risk 429s from the provider.
    imagen_max_concurrent: int = Field(default=4, validation_alias="IMAGEN_MAX_CONCURRENT")
    # When true, IMAGEN_MODEL=imagen-4.0-generate-001 is kept (higher quality, slower). Default false maps it to fast.
    imagen_allow_standard_generate: bool = Field(
        default=False,
        validation_alias="IMAGEN_ALLOW_STANDARD_GENERATE",
    )

    # Vertex AI Imagen (GCP service account + project). When true, slide images use Vertex :predict instead of
    # Generative Language API. Also implied when Vertex Gemini 2.5 image failover is configured (same SA/project).
    imagen_use_vertex: bool = Field(default=True, validation_alias="IMAGEN_USE_VERTEX")
    vertex_imagen_project_id: str = Field(
        default="",
        validation_alias=AliasChoices("VERTEX_IMAGEN_PROJECT", "GOOGLE_CLOUD_PROJECT"),
    )
    vertex_imagen_regions: str = Field(
        default="us-central1",
        validation_alias="VERTEX_IMAGEN_REGIONS",
    )

    # Vertex Veo video (same SA + project as Imagen). Default: Veo 3.1 Lite (720p/1080p via API resolution).
    vertex_veo_model: str = Field(
        default="veo-3.1-lite-generate-001",
        validation_alias=AliasChoices("VERTEX_VEO_MODEL", "VEO_VERTEX_MODEL"),
    )
    # GCS prefix for Vertex Veo predictLongRunning output. Override in env for other projects.
    vertex_veo_storage_uri: str = Field(
        default="gs://veo_enablyai/",
        validation_alias=AliasChoices("VERTEX_VEO_STORAGE_URI", "VEO_STORAGE_URI"),
    )
    # Veo personGeneration: allow_all | allow_adult (default) | disallow — RAI docs + support codes (e.g. 17301594).
    vertex_veo_person_generation: str = Field(
        default="allow_adult",
        validation_alias="VERTEX_VEO_PERSON_GENERATION",
    )

    nano_banana_api_key: str = Field(default="", validation_alias="NANO_BANANA_API_KEY")
    nano_banana_base_url: str = Field(
        default="https://api.nanobananaimages.com",
        validation_alias="NANO_BANANA_BASE_URL",
    )
    nano_banana_style: str = Field(default="cinematic", validation_alias="NANO_BANANA_STYLE")
    nano_banana_steps: int = Field(default=25, validation_alias="NANO_BANANA_STEPS")
    nano_banana_guidance: float = Field(default=7.5, validation_alias="NANO_BANANA_GUIDANCE")
    nano_banana_timeout: float = Field(default=180.0, validation_alias="NANO_BANANA_TIMEOUT")
    nano_banana_max_concurrent: int = Field(default=2, validation_alias="NANO_BANANA_MAX_CONCURRENT")

    # Gemini native image (Nano Banana 2) — generateContent; tried before Imagen when GEMINI_API_KEY is set.
    gemini_native_image_first: bool = Field(
        default=True,
        validation_alias="GEMINI_NATIVE_IMAGE_FIRST",
    )
    gemini_native_image_model: str = Field(
        default="gemini-3.1-flash-image-preview",
        validation_alias="GEMINI_NATIVE_IMAGE_MODEL",
    )

    # After native Gemini image fails (quota, etc.): Vertex Gemini image (SA), then Imagen / Nano Banana.
    vertex_gemini_image_failover: bool = Field(
        default=True,
        validation_alias="VERTEX_GEMINI_IMAGE_FAILOVER",
    )
    vertex_gemini_image_model: str = Field(
        default="gemini-2.5-flash-image",
        validation_alias="VERTEX_GEMINI_IMAGE_MODEL",
    )
    # Comma-separated locations: global, us-central1, ... If empty, uses VERTEX_IMAGEN_REGIONS.
    vertex_gemini_image_regions: str = Field(
        default="",
        validation_alias="VERTEX_GEMINI_IMAGE_REGIONS",
    )

    artifact_root: Path = Field(
        default=_PROJECT_ROOT / "data" / "jobs",
        validation_alias="ARTIFACT_ROOT",
    )

    video_width: int = Field(default=1080, validation_alias="VIDEO_WIDTH")
    video_height: int = Field(default=1920, validation_alias="VIDEO_HEIGHT")

    coqui_model_en: str = Field(
        default="tts_models/en/ljspeech/tacotron2-DDC",
        validation_alias="COQUI_MODEL_EN",
    )
    coqui_model_hi: str = Field(
        default="tts_models/hi/cv/vits",
        validation_alias="COQUI_MODEL_HI",
    )
    coqui_model_mr: str = Field(
        default="tts_models/hi/cv/vits",
        validation_alias="COQUI_MODEL_MR",
    )

    # PostgreSQL (async): postgresql+asyncpg://user:pass@localhost:5432/dbname
    database_url: str = Field(default="", validation_alias="DATABASE_URL")
    # S3 — when set together with database_url, jobs are persisted and media is served via presigned URLs.
    s3_bucket: str = Field(default="", validation_alias="S3_BUCKET")
    s3_region: str = Field(default="", validation_alias="S3_REGION")
    s3_prefix: str = Field(default="jobs/", validation_alias="S3_PREFIX")
    s3_endpoint_url: str = Field(default="", validation_alias="S3_ENDPOINT_URL")
    media_presign_expires_seconds: int = Field(
        default=3600,
        validation_alias="MEDIA_PRESIGN_EXPIRES_SECONDS",
    )
    aws_profile: str = Field(default="", validation_alias="AWS_PROFILE")
    artifact_cleanup_after_s3: bool = Field(
        default=True,
        validation_alias="ARTIFACT_CLEANUP_AFTER_S3",
    )
    # When false, Image to Video / Image to Ad skip FFmpeg credit burn-in (fast on small CPUs; no overlay).
    veo_apply_credit_overlay: bool = Field(
        default=True,
        validation_alias="VEO_APPLY_CREDIT_OVERLAY",
    )

    # Google OAuth (browser sign-in). When all four are set, POST /generate requires a signed-in user.
    session_secret: str = Field(default="", validation_alias="SESSION_SECRET")
    google_oauth_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_CLIENT_ID"),
    )
    google_oauth_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_OAUTH_CLIENT_SECRET", "GOOGLE_CLIENT_SECRET"),
    )
    google_oauth_redirect_uri: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_OAUTH_REDIRECT_URI", "GOOGLE_REDIRECT_URI"),
    )
    session_cookie_https_only: bool = Field(
        default=True,
        validation_alias="SESSION_COOKIE_SECURE",
    )

    # Security / ops
    health_expose_internals: bool = Field(
        default=False,
        validation_alias="HEALTH_EXPOSE_INTERNALS",
    )
    openapi_enabled: bool = Field(
        default=True,
        validation_alias="OPENAPI_ENABLED",
    )
    # Required for /internal/* (Next.js proxy). Send X-Internal-Api-Key or Authorization: Bearer <value>.
    internal_api_secret: str = Field(default="", validation_alias="INTERNAL_API_SECRET")
    rate_limit_generate: str = Field(
        default="12/minute",
        validation_alias="RATE_LIMIT_GENERATE",
    )
    rate_limit_tts_preview: str = Field(
        default="30/minute",
        validation_alias="RATE_LIMIT_TTS_PREVIEW",
    )
    credits_enabled: bool = Field(default=True, validation_alias="CREDITS_ENABLED")

    def persistence_enabled(self) -> bool:
        return bool(
            (self.database_url or "").strip()
            and (self.s3_bucket or "").strip()
            and (self.s3_region or "").strip()
        )

    def credits_billing_enabled(self) -> bool:
        """Credits require a configured database URL (Postgres/SQLite)."""
        return bool(self.credits_enabled and (self.database_url or "").strip())

    def s3_key_prefix_for_job(self, job_id: str) -> str:
        p = (self.s3_prefix or "").strip()
        if not p:
            return f"{job_id}/"
        if not p.endswith("/"):
            p += "/"
        return f"{p}{job_id}/"

    def s3_key_for_veo3(self, job_dir: str, filename: str) -> str:
        """Object key for Veo standalone videos under the configured S3 prefix."""
        p = (self.s3_prefix or "").strip()
        base = f"veo3/{job_dir}/{filename}"
        if not p:
            return base
        if not p.endswith("/"):
            p += "/"
        return f"{p}{base}"

    def s3_object_storage_configured(self) -> bool:
        """Bucket + region set (used for uploads; does not require DATABASE_URL)."""
        return bool((self.s3_bucket or "").strip() and (self.s3_region or "").strip())

    def elevenlabs_voice_for_language(self, language: str) -> str:
        lang = language.lower()
        if lang == "en" and (self.elevenlabs_voice_en or "").strip():
            return (self.elevenlabs_voice_en or "").strip()
        if lang == "hi" and (self.elevenlabs_voice_hi or "").strip():
            return (self.elevenlabs_voice_hi or "").strip()
        if lang == "mr" and (self.elevenlabs_voice_mr or "").strip():
            return (self.elevenlabs_voice_mr or "").strip()
        return (self.elevenlabs_voice_id or "").strip()

    def elevenlabs_is_configured(self) -> bool:
        key = (self.elevenlabs_api_key or "").strip()
        if not key:
            return False
        return bool(self.elevenlabs_voice_for_language("en"))

    def google_tts_is_configured(self) -> bool:
        if self.google_tts_use_adc:
            return True
        p = (self.google_tts_credentials_json_path or "").strip()
        if p:
            try:
                return Path(p).expanduser().is_file()
            except OSError:
                return False
        adc = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        if adc:
            try:
                return Path(adc).expanduser().is_file()
            except OSError:
                return False
        return False

    def vertex_gcp_service_account_file_available(self) -> bool:
        """JSON key on disk for Vertex Imagen token refresh (ADC-only VMs need a file or GAC path)."""
        p = (self.google_tts_credentials_json_path or "").strip()
        if p:
            try:
                return Path(p).expanduser().is_file()
            except OSError:
                return False
        adc = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        if adc:
            try:
                return Path(adc).expanduser().is_file()
            except OSError:
                return False
        return False

    def vertex_imagen_configured(self) -> bool:
        """Vertex :predict when project+SA exist and (IMAGEN_USE_VERTEX or Vertex Gemini 2.5 image stack is on)."""
        if not (self.vertex_imagen_project_id or "").strip():
            return False
        if not self.vertex_gcp_service_account_file_available():
            return False
        if self.imagen_use_vertex:
            return True
        # Gemini 3.1 image uses API key; 2.5 image + Imagen belong on Vertex with the same service account.
        return self.vertex_gemini_image_configured()

    def imagen_model_effective(self) -> str:
        """Model id sent to Vertex / Generative Language predict (remaps legacy standard → fast)."""
        std = "imagen-4.0-generate-001"
        fast = "imagen-4.0-fast-generate-001"
        m = (self.imagen_model or "").strip()
        if m == std and not self.imagen_allow_standard_generate:
            return fast
        return m

    def gemini_imagen_configured(self) -> bool:
        if self.vertex_imagen_configured():
            return True
        return bool((self.gemini_api_key or "").strip())

    def nano_banana_configured(self) -> bool:
        return bool((self.nano_banana_api_key or "").strip())

    def gemini_native_image_configured(self) -> bool:
        if not self.gemini_native_image_first:
            return False
        if not (self.gemini_api_key or "").strip():
            return False
        return bool((self.gemini_native_image_model or "").strip())

    def vertex_gemini_image_locations(self) -> list[str]:
        raw = (self.vertex_gemini_image_regions or "").strip()
        if raw:
            return [x.strip() for x in raw.split(",") if x.strip()]
        return [x.strip() for x in (self.vertex_imagen_regions or "").split(",") if x.strip()]

    def vertex_gemini_image_configured(self) -> bool:
        if not self.vertex_gemini_image_failover:
            return False
        if not self.vertex_gcp_service_account_file_available():
            return False
        if not (self.vertex_imagen_project_id or "").strip():
            return False
        if not (self.vertex_gemini_image_model or "").strip():
            return False
        return bool(self.vertex_gemini_image_locations())

    def slide_visuals_configured(self) -> bool:
        return (
            self.gemini_native_image_configured()
            or self.vertex_gemini_image_configured()
            or self.gemini_imagen_configured()
            or self.nano_banana_configured()
        )

    def google_oauth_enabled(self) -> bool:
        return bool(
            (self.session_secret or "").strip()
            and (self.google_oauth_client_id or "").strip()
            and (self.google_oauth_client_secret or "").strip()
            and (self.google_oauth_redirect_uri or "").strip()
        )

    def rate_limit_generate_effective(self) -> str:
        """slowapi limit string; very high cap when rate limiting is turned off."""
        s = (self.rate_limit_generate or "").strip().lower()
        if s in ("", "off", "false", "none", "0"):
            return "10000/minute"
        return (self.rate_limit_generate or "").strip()

    def rate_limit_tts_preview_effective(self) -> str:
        s = (self.rate_limit_tts_preview or "").strip().lower()
        if s in ("", "off", "false", "none", "0"):
            return "10000/minute"
        return (self.rate_limit_tts_preview or "").strip()

    @field_validator("s3_bucket", mode="before")
    @classmethod
    def normalize_s3_bucket(cls, v: str | None) -> str:
        return normalize_s3_bucket_name(v)

    @field_validator("artifact_root", mode="before")
    @classmethod
    def resolve_artifact_root(cls, v: Path | str) -> Path:
        p = Path(v) if v is not None else _PROJECT_ROOT / "data" / "jobs"
        if not p.is_absolute():
            return (_PROJECT_ROOT / p).resolve()
        return p.resolve()

    @field_validator("imagen_model", mode="before")
    @classmethod
    def normalize_imagen_model_env(cls, v: object) -> str:
        if v is None:
            return ""
        s = str(v).strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in "'\"":
            s = s[1:-1].strip()
        return s

    @field_validator("imagen_allow_standard_generate", mode="before")
    @classmethod
    def normalize_allow_standard_generate(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return False
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return bool(v)

    @model_validator(mode="after")
    def use_fast_imagen_unless_standard_explicitly_allowed(self):
        """Stale .env often pins imagen-4.0-generate-001; remap to fast unless opted in."""
        global _IMAGEN_STANDARD_REMAP_LOGGED
        std = "imagen-4.0-generate-001"
        fast = "imagen-4.0-fast-generate-001"
        m = (self.imagen_model or "").strip()
        if m == std and not self.imagen_allow_standard_generate:
            if not _IMAGEN_STANDARD_REMAP_LOGGED:
                logger.warning(
                    "IMAGEN_MODEL was %s; using %s instead. "
                    "Set IMAGEN_ALLOW_STANDARD_GENERATE=true to keep the standard (slower) model.",
                    std,
                    fast,
                )
                _IMAGEN_STANDARD_REMAP_LOGGED = True
            return self.model_copy(update={"imagen_model": fast})
        return self


def get_settings() -> Settings:
    return Settings()
