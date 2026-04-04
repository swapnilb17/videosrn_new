import logging
import subprocess
import tempfile
from pathlib import Path

from app.config import Settings
from app.schemas import LanguageCode
from app.services.ffmpeg_resolve import resolve_ffmpeg

logger = logging.getLogger(__name__)


def _model_for_language(settings: Settings, language: LanguageCode) -> str:
    if language == "en":
        return settings.coqui_model_en
    if language == "hi":
        return settings.coqui_model_hi
    return settings.coqui_model_mr


def synthesize_coqui_sync(
    settings: Settings,
    text: str,
    language: LanguageCode,
    out_mp3: Path,
) -> None:
    try:
        from TTS.api import TTS
    except ImportError as e:
        raise RuntimeError(
            "Coqui TTS is not installed. From the app repo with the app venv active: "
            'pip install -e ".[coqui]"'
        ) from e

    primary = _model_for_language(settings, language)
    candidates: list[str] = [primary]
    if language in ("hi", "mr"):
        en = (settings.coqui_model_en or "").strip()
        if en and en not in candidates:
            candidates.append(en)

    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = Path(tmp.name)

    try:
        last_exc: BaseException | None = None
        used_model: str | None = None
        for model_name in candidates:
            try:
                tts = TTS(model_name=model_name, progress_bar=False, gpu=False)
                tts.tts_to_file(text=text, file_path=str(wav_path))
                used_model = model_name
                if model_name != primary:
                    logger.warning(
                        "Coqui TTS used English fallback model %s for language=%s "
                        "(primary %s failed; narration may sound wrong)",
                        model_name,
                        language,
                        primary,
                    )
                break
            except Exception as e:
                last_exc = e
                logger.warning("Coqui TTS failed (model=%s): %s", model_name, e)
        if used_model is None:
            logger.exception("Coqui TTS failed (all candidates) primary=%s", primary)
            if last_exc:
                msg = str(last_exc).strip() or type(last_exc).__name__
            else:
                msg = "unknown"
            raise RuntimeError(
                f"Coqui TTS failed ({type(last_exc).__name__ if last_exc else 'Error'}): {msg}. "
                "First run downloads the model (slow); ensure enough RAM/disk and "
                "check server logs for the full traceback."
            ) from last_exc

        ffmpeg_bin = resolve_ffmpeg(explicit=settings.ffmpeg_path or None)
        if not ffmpeg_bin:
            raise RuntimeError(
                "ffmpeg is not installed or not on PATH (needed for MP3 encoding). "
                "macOS: brew install ffmpeg"
            )

        cmd = [
            ffmpeg_bin,
            "-y",
            "-i",
            str(wav_path),
            "-codec:a",
            "libmp3lame",
            "-qscale:a",
            "2",
            str(out_mp3),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.error("ffmpeg wav->mp3 failed: %s", proc.stderr)
            raise RuntimeError(
                "Failed to encode MP3 from Coqui output (ffmpeg needs libmp3lame). "
                f"stderr: {(proc.stderr or '').strip()[:400]}"
            )
    finally:
        if wav_path.exists():
            wav_path.unlink(missing_ok=True)
