"""Google Cloud Text-to-Speech (Neural2 preferred, then Wavenet)."""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from google.api_core import exceptions as google_exceptions

from app.config import Settings
from app.schemas import DialogueTurn, LanguageCode
from app.services.ffmpeg_resolve import resolve_ffmpeg

logger = logging.getLogger(__name__)


class GoogleTtsError(Exception):
    pass


_LOCALE: dict[LanguageCode, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "mr": "mr-IN",
}

# If list_voices fails, try these names in order (Neural2-heavy then Wavenet).
_FALLBACK_VOICE_CHAINS: dict[str, list[str]] = {
    "en-IN": [
        "en-IN-Neural2-C",
        "en-IN-Neural2-D",
        "en-IN-Neural2-A",
        "en-IN-Neural2-B",
        "en-IN-Wavenet-C",
        "en-IN-Wavenet-D",
        "en-IN-Wavenet-A",
        "en-IN-Wavenet-B",
    ],
    "hi-IN": [
        "hi-IN-Neural2-A",
        "hi-IN-Neural2-C",
        "hi-IN-Neural2-D",
        "hi-IN-Wavenet-A",
        "hi-IN-Wavenet-B",
        "hi-IN-Wavenet-C",
    ],
    "mr-IN": [
        "mr-IN-Neural2-A",
        "mr-IN-Wavenet-A",
        "mr-IN-Wavenet-B",
        "mr-IN-Standard-A",
    ],
}

# Short lines for voice preview (keep under TTS byte limits).
_PREVIEW_TEXT: dict[LanguageCode, str] = {
    "en": "This is a short sample of this voice.",
    "hi": "यह आवाज़ का एक छोटा नमूना है।",
    "mr": "ही आवाज ऐकंदा छोटा नमुना आहे.",
}


def _voice_tier(name: str) -> int:
    # Chirp HD voices handle multilingual / code-mixed text better (e.g. Hinglish on hi-IN).
    if "-Chirp3-HD-" in name or "-Chirp-HD-" in name:
        return -1
    if "-Neural2-" in name:
        return 0
    if "-Wavenet-" in name:
        return 1
    return 2


def _ordered_voices_for_locale(client: object, locale: str) -> list[str]:
    try:
        resp = client.list_voices(language_code=locale)
    except Exception as e:
        logger.warning("Google TTS list_voices failed for %s: %s", locale, e)
        return list(_FALLBACK_VOICE_CHAINS.get(locale, []))

    names: list[tuple[int, str]] = []
    for v in resp.voices:
        n = (v.name or "").strip()
        if not n:
            continue
        codes = [c for c in v.language_codes if c]
        if locale not in codes:
            continue
        names.append((_voice_tier(n), n))
    names.sort(key=lambda x: (x[0], x[1]))
    out: list[str] = []
    seen: set[str] = set()
    for _, n in names:
        if n not in seen:
            seen.add(n)
            out.append(n)
    if out:
        return out
    return list(_FALLBACK_VOICE_CHAINS.get(locale, []))


def _voice_override(settings: Settings, language: LanguageCode) -> str | None:
    if language == "en":
        v = (settings.google_tts_voice_en or "").strip()
    elif language == "hi":
        v = (settings.google_tts_voice_hi or "").strip()
    else:
        v = (settings.google_tts_voice_mr or "").strip()
    return v or None


_VOICE_NAME_RE = re.compile(r"^[a-z]{2}-[A-Z]{2,3}-[A-Za-z0-9_-]+$")
_LOCALE_PREFIX_RE = re.compile(r"^[a-z]{2}-[A-Z]{2,3}-")
_TIER_VOICE_RE = re.compile(r"(?i)^(Neural2|Wavenet|Standard|Studio)-([A-Z])$")


def friendly_google_tts_voice_label(technical_name: str) -> str:
    """Short UI label without locale or engine jargon (Neural2, Wavenet, Standard, etc.)."""
    n = (technical_name or "").strip()
    if not n:
        return ""
    rest = _LOCALE_PREFIX_RE.sub("", n)
    if not rest:
        return n

    if "Chirp" in rest or "-HD-" in rest:
        parts = [p for p in rest.split("-") if p]
        if parts:
            last = parts[-1]
            if last.isalpha():
                if len(last) > 1:
                    return last.replace("_", " ").title()
                return f"Voice {last.upper()}"

    m = _TIER_VOICE_RE.match(rest)
    if m:
        return f"Voice {m.group(2).upper()}"

    tail = rest.split("-")[-1]
    if len(tail) == 1 and tail.isalpha():
        return f"Voice {tail.upper()}"

    cleaned = re.sub(
        r"(?i)\b(Neural2|Wavenet|Standard|Studio|Chirp3|Chirp|HD)\b",
        "",
        rest,
    )
    cleaned = re.sub(r"-+", " ", cleaned).strip()
    if cleaned:
        return " ".join(w for w in cleaned.split() if w).title()
    return n


def _voice_name_allowed(client: object, locale: str, name: str) -> bool:
    n = (name or "").strip()
    if not n or not _VOICE_NAME_RE.match(n):
        return False
    try:
        resp = client.list_voices(language_code=locale)
    except Exception:
        return n in _FALLBACK_VOICE_CHAINS.get(locale, [])
    for v in resp.voices:
        vn = (v.name or "").strip()
        if vn != n:
            continue
        codes = [c for c in (v.language_codes or []) if c]
        return locale in codes
    return False


def _ssml_gender_label(voice_obj: object) -> str:
    try:
        from google.cloud.texttospeech_v1 import SsmlVoiceGender

        g = int(getattr(voice_obj, "ssml_gender", 0))
        if g == SsmlVoiceGender.MALE:
            return "MALE"
        if g == SsmlVoiceGender.FEMALE:
            return "FEMALE"
        if g == SsmlVoiceGender.NEUTRAL:
            return "NEUTRAL"
    except Exception:
        pass
    return "UNSPECIFIED"


def list_google_tts_voices_detail(settings: Settings, language: LanguageCode) -> dict[str, Any]:
    """Return locale, voice entries (name + gender), and gender counts for the UI."""
    locale = _LOCALE[language]
    client = _build_client(settings)
    voices_out: list[dict[str, str]] = []
    try:
        resp = client.list_voices(language_code=locale)
    except Exception as e:
        logger.warning("list_voices failed for UI %s: %s", locale, e)
        for n in _FALLBACK_VOICE_CHAINS.get(locale, []):
            voices_out.append(
                {
                    "name": n,
                    "label": friendly_google_tts_voice_label(n),
                    "gender": "UNSPECIFIED",
                }
            )
    else:
        for v in resp.voices:
            n = (v.name or "").strip()
            if not n:
                continue
            codes = [c for c in (v.language_codes or []) if c]
            if locale not in codes:
                continue
            voices_out.append(
                {
                    "name": n,
                    "label": friendly_google_tts_voice_label(n),
                    "gender": _ssml_gender_label(v),
                }
            )
        voices_out.sort(key=lambda x: x["name"])

    counts = {"male": 0, "female": 0, "neutral": 0, "unspecified": 0}
    for row in voices_out:
        g = row["gender"].upper()
        if g == "MALE":
            counts["male"] += 1
        elif g == "FEMALE":
            counts["female"] += 1
        elif g == "NEUTRAL":
            counts["neutral"] += 1
        else:
            counts["unspecified"] += 1

    return {
        "locale": locale,
        "language": language,
        "voices": voices_out,
        "counts": counts,
    }


def synthesize_google_tts_preview_sync(
    settings: Settings,
    language: LanguageCode,
    voice_name: str,
    out_mp3: Path,
) -> None:
    try:
        from google.cloud import texttospeech_v1  # noqa: F401
    except ImportError as e:
        raise GoogleTtsError(
            "google-cloud-texttospeech is not installed. Install with: pip install google-cloud-texttospeech"
        ) from e

    locale = _LOCALE[language]
    client = _build_client(settings)
    vn = (voice_name or "").strip()
    if not _voice_name_allowed(client, locale, vn):
        raise GoogleTtsError(f"Voice {vn!r} is not available for {locale}")

    text = _PREVIEW_TEXT[language]
    audio = _synthesize_chunk_with_retries(
        client,
        text,
        vn,
        locale,
        settings.google_tts_speaking_rate,
        settings.google_tts_pitch,
    )
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    out_mp3.write_bytes(audio)


def _resolve_voice_names(
    settings: Settings,
    language: LanguageCode,
    client: object,
    *,
    user_voice: str | None = None,
) -> list[str]:
    locale = _LOCALE[language]
    uv = (user_voice or "").strip()
    if uv:
        if not _voice_name_allowed(client, locale, uv):
            raise GoogleTtsError(f"Voice {uv!r} is not available for {locale}")
        return [uv]
    override = _voice_override(settings, language)
    if override:
        return [override]
    return _ordered_voices_for_locale(client, locale)


def _utf8_byte_chunks(s: str, max_bytes: int) -> list[str]:
    """Split a string into UTF-8-safe segments each under max_bytes (last chunk may exceed if one char is larger)."""
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return [s]
    out: list[str] = []
    i = 0
    while i < len(b):
        end = min(i + max_bytes, len(b))
        while end > i:
            try:
                b[i:end].decode("utf-8")
                break
            except UnicodeDecodeError:
                end -= 1
        if end == i:
            end = i + 1
            while end <= len(b):
                try:
                    b[i:end].decode("utf-8")
                    break
                except UnicodeDecodeError:
                    end += 1
            else:
                raise ValueError("invalid UTF-8 in text") from None
        out.append(b[i:end].decode("utf-8"))
        i = end
    return out


def _split_sentences(text: str) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"(?<=[.!?।॥\n])\s+", t)
    return [p.strip() for p in parts if p.strip()]


def _chunk_text(text: str, max_bytes: int) -> list[str]:
    """Split into chunks under max_bytes (UTF-8), preferring sentence boundaries."""
    text = (text or "").strip()
    if not text:
        return []
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    sentences = _split_sentences(text)
    if not sentences:
        return _utf8_byte_chunks(text, max_bytes)

    chunks: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current.strip():
            chunks.append(current.strip())
        current = ""

    for s in sentences:
        candidate = f"{current} {s}".strip() if current else s
        if len(candidate.encode("utf-8")) <= max_bytes:
            current = candidate
            continue
        if current.strip():
            flush()
        if len(s.encode("utf-8")) <= max_bytes:
            current = s
            continue
        for piece in _utf8_byte_chunks(s, max_bytes):
            t = piece.strip()
            if t:
                chunks.append(t)
        current = ""

    if current.strip():
        chunks.append(current.strip())
    return chunks


def _build_client(settings: Settings):
    from google.cloud import texttospeech_v1 as texttospeech

    path = (settings.google_tts_credentials_json_path or "").strip()
    if path:
        expanded = Path(path).expanduser()
        if expanded.is_file():
            return texttospeech.TextToSpeechClient.from_service_account_file(str(expanded))
        logger.warning(
            "Google TTS GOOGLE_TTS_CREDENTIALS_JSON path is not a file (%s); "
            "falling back to Application Default Credentials",
            expanded,
        )
    return texttospeech.TextToSpeechClient()


def _synthesize_chunk(
    client: object,
    text: str,
    voice_name: str,
    locale: str,
    speaking_rate: float,
    pitch: float,
) -> bytes:
    from google.cloud import texttospeech_v1 as texttospeech

    inp = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=locale,
        name=voice_name,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3,
        speaking_rate=speaking_rate,
        pitch=pitch,
    )
    resp = client.synthesize_speech(
        input=inp,
        voice=voice,
        audio_config=audio_config,
    )
    return resp.audio_content


def _synthesize_chunk_with_retries(
    client: object,
    text: str,
    voice_name: str,
    locale: str,
    speaking_rate: float,
    pitch: float,
    *,
    max_attempts: int = 4,
) -> bytes:
    """Retry transient Cloud TTS failures (503 UNAVAILABLE, 429, timeouts)."""
    last_exc: BaseException | None = None
    for attempt in range(max_attempts):
        if attempt:
            delay = min(8.0, 2.0 ** (attempt - 1))
            time.sleep(delay)
        try:
            return _synthesize_chunk(
                client, text, voice_name, locale, speaking_rate, pitch
            )
        except google_exceptions.ServiceUnavailable as e:
            last_exc = e
            logger.warning(
                "Google TTS ServiceUnavailable attempt %s/%s voice=%s: %s",
                attempt + 1,
                max_attempts,
                voice_name,
                e,
            )
        except google_exceptions.ResourceExhausted as e:
            last_exc = e
            logger.warning(
                "Google TTS ResourceExhausted attempt %s/%s voice=%s: %s",
                attempt + 1,
                max_attempts,
                voice_name,
                e,
            )
        except google_exceptions.DeadlineExceeded as e:
            last_exc = e
            logger.warning(
                "Google TTS DeadlineExceeded attempt %s/%s voice=%s: %s",
                attempt + 1,
                max_attempts,
                voice_name,
                e,
            )
        except google_exceptions.InternalServerError as e:
            last_exc = e
            logger.warning(
                "Google TTS InternalServerError attempt %s/%s voice=%s: %s",
                attempt + 1,
                max_attempts,
                voice_name,
                e,
            )
        except google_exceptions.Aborted as e:
            last_exc = e
            logger.warning(
                "Google TTS Aborted attempt %s/%s voice=%s: %s",
                attempt + 1,
                max_attempts,
                voice_name,
                e,
            )
    assert last_exc is not None
    raise last_exc


def _concat_mp3s(ffmpeg_bin: str, chunk_paths: list[Path], out_mp3: Path) -> None:
    if not chunk_paths:
        raise GoogleTtsError("No audio chunks to concatenate")
    if len(chunk_paths) == 1:
        out_mp3.parent.mkdir(parents=True, exist_ok=True)
        out_mp3.write_bytes(chunk_paths[0].read_bytes())
        return

    n = len(chunk_paths)
    args = [ffmpeg_bin, "-y"]
    for p in chunk_paths:
        args.extend(["-i", str(p)])
    labels = "".join(f"[{i}:a]" for i in range(n))
    filt = f"{labels}concat=n={n}:v=0:a=1[aout]"
    args.extend(["-filter_complex", filt, "-map", "[aout]", "-c:a", "libmp3lame", "-q:a", "2", str(out_mp3)])
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        logger.error("ffmpeg concat mp3 failed: %s", proc.stderr)
        raise GoogleTtsError(
            "Failed to concatenate TTS segments (ffmpeg). "
            f"stderr: {(proc.stderr or '').strip()[:400]}"
        )


def pick_conversation_voices_google(
    settings: Settings,
    language: LanguageCode,
    *,
    user_voice: str | None = None,
) -> tuple[str, str]:
    """Return (male_voice_name, female_voice_name) for alternating dialogue TTS."""
    try:
        from google.cloud import texttospeech_v1  # noqa: F401
    except ImportError as e:
        raise GoogleTtsError(
            "google-cloud-texttospeech is not installed. Install with: pip install google-cloud-texttospeech"
        ) from e

    locale = _LOCALE[language]
    client = _build_client(settings)
    try:
        resp = client.list_voices(language_code=locale)
    except Exception as e:
        raise GoogleTtsError(f"Google TTS list_voices failed for {locale}: {e}") from e

    males: list[tuple[int, str]] = []
    females: list[tuple[int, str]] = []
    gender_by_name: dict[str, str] = {}
    for v in resp.voices:
        n = (v.name or "").strip()
        if not n:
            continue
        codes = [c for c in (v.language_codes or []) if c]
        if locale not in codes:
            continue
        g = _ssml_gender_label(v)
        gender_by_name[n] = g
        tier = _voice_tier(n)
        if g == "MALE":
            males.append((tier, n))
        elif g == "FEMALE":
            females.append((tier, n))
    males.sort(key=lambda x: (x[0], x[1]))
    females.sort(key=lambda x: (x[0], x[1]))
    m_names = [x[1] for x in males]
    f_names = [x[1] for x in females]
    if not m_names or not f_names:
        raise GoogleTtsError(
            f"Conversational mode needs at least one male and one female Neural/Wavenet-class voice "
            f"for {locale}. Try another language or check Cloud TTS voice inventory."
        )

    uv = (user_voice or "").strip()
    if uv and _voice_name_allowed(client, locale, uv):
        ug = gender_by_name.get(uv, "UNSPECIFIED")
        if ug == "MALE":
            return (uv, f_names[0])
        if ug == "FEMALE":
            return (m_names[0], uv)

    return (m_names[0], f_names[0])


def _make_silence_mp3(ffmpeg_bin: str, duration: float, out_path: Path) -> None:
    if duration <= 0:
        raise GoogleTtsError("silence duration must be positive")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        ffmpeg_bin,
        "-y",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=mono",
        "-t",
        f"{duration:.3f}",
        "-c:a",
        "libmp3lame",
        "-q:a",
        "9",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        logger.error("ffmpeg silence mp3 failed: %s", proc.stderr)
        raise GoogleTtsError("Failed to generate pause between dialogue lines (ffmpeg).")


def synthesize_google_tts_conversational_sync(
    settings: Settings,
    turns: list[DialogueTurn],
    language: LanguageCode,
    out_mp3: Path,
    *,
    user_voice: str | None = None,
    pause_sec: float = 0.22,
) -> None:
    """Synthesize each line with male or female Google voice; concatenate with short pauses."""
    if not turns:
        raise GoogleTtsError("No dialogue lines for TTS")

    try:
        from google.cloud import texttospeech_v1  # noqa: F401
    except ImportError as e:
        raise GoogleTtsError(
            "google-cloud-texttospeech is not installed. Install with: pip install google-cloud-texttospeech"
        ) from e

    locale = _LOCALE[language]
    max_bytes = max(512, settings.google_tts_max_input_bytes)
    client = _build_client(settings)
    male_v, female_v = pick_conversation_voices_google(
        settings, language, user_voice=user_voice
    )

    ffmpeg_bin = resolve_ffmpeg(explicit=settings.ffmpeg_path or None)
    if not ffmpeg_bin:
        raise GoogleTtsError(
            "ffmpeg is required for conversational TTS (concatenation). Install ffmpeg and/or set FFMPEG_PATH."
        )

    speaking_rate = settings.google_tts_speaking_rate
    pitch = settings.google_tts_pitch

    with tempfile.TemporaryDirectory(prefix="gcp_tts_conv_") as tmp:
        tmp_path = Path(tmp)
        seg_paths: list[Path] = []
        silence_path = tmp_path / "pause.mp3"
        _make_silence_mp3(ffmpeg_bin, pause_sec, silence_path)

        for i, turn in enumerate(turns):
            text = (turn.text or "").strip()
            if not text:
                raise GoogleTtsError(f"Empty dialogue text at line {i + 1}")
            vn = male_v if turn.speaker == "male" else female_v
            chunks = _chunk_text(text, max_bytes)
            if not chunks:
                continue
            line_paths: list[Path] = []
            for j, chunk in enumerate(chunks):
                audio = _synthesize_chunk_with_retries(
                    client, chunk, vn, locale, speaking_rate, pitch
                )
                p = tmp_path / f"line_{i:03d}_part_{j:02d}.mp3"
                p.write_bytes(audio)
                line_paths.append(p)
            if len(line_paths) > 1:
                merged = tmp_path / f"line_{i:03d}_merged.mp3"
                _concat_mp3s(ffmpeg_bin, line_paths, merged)
                seg_paths.append(merged)
            else:
                seg_paths.append(line_paths[0])
            if i < len(turns) - 1:
                seg_paths.append(silence_path)

        _concat_mp3s(ffmpeg_bin, seg_paths, out_mp3)

    logger.info(
        "Google TTS conversational ok locale=%s lines=%s male=%s female=%s",
        locale,
        len(turns),
        male_v,
        female_v,
    )


def synthesize_google_tts_sync(
    settings: Settings,
    text: str,
    language: LanguageCode,
    out_mp3: Path,
    *,
    voice_name: str | None = None,
) -> None:
    try:
        from google.cloud import texttospeech_v1  # noqa: F401
    except ImportError as e:
        raise GoogleTtsError(
            "google-cloud-texttospeech is not installed. Install with: pip install google-cloud-texttospeech"
        ) from e

    locale = _LOCALE[language]
    max_bytes = max(512, settings.google_tts_max_input_bytes)
    chunks = _chunk_text(text, max_bytes)
    if not chunks:
        raise GoogleTtsError("Empty script text for TTS")

    client = _build_client(settings)
    voice_names = _resolve_voice_names(settings, language, client, user_voice=voice_name)
    if not voice_names:
        raise GoogleTtsError(f"No Google TTS voices available for {locale}")

    speaking_rate = settings.google_tts_speaking_rate
    pitch = settings.google_tts_pitch

    chosen_voice: str | None = None
    first_audio: bytes | None = None
    last_err: Exception | None = None

    for voice_name in voice_names:
        try:
            first_audio = _synthesize_chunk_with_retries(
                client,
                chunks[0],
                voice_name,
                locale,
                speaking_rate,
                pitch,
            )
            chosen_voice = voice_name
            break
        except google_exceptions.InvalidArgument as e:
            last_err = e
            logger.info("Google TTS voice not usable, trying next: %s — %s", voice_name, e)
            continue
        except google_exceptions.GoogleAPICallError as e:
            raise GoogleTtsError(f"Google TTS failed for {locale}: {e}") from e

    if chosen_voice is None or first_audio is None:
        msg = str(last_err).strip() if last_err else "no voice matched"
        raise GoogleTtsError(f"Google TTS could not synthesize with any voice for {locale}: {msg}") from last_err

    ffmpeg_bin: str | None = None
    if len(chunks) > 1:
        ffmpeg_bin = resolve_ffmpeg(explicit=settings.ffmpeg_path or None)
        if not ffmpeg_bin:
            raise GoogleTtsError(
                "ffmpeg is not installed or not on PATH (needed to join long TTS segments). "
                "macOS: brew install ffmpeg"
            )

    out_mp3.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="gcp_tts_") as tmp:
        tmp_path = Path(tmp)
        paths: list[Path] = []
        seg0 = tmp_path / "seg_0000.mp3"
        seg0.write_bytes(first_audio)
        paths.append(seg0)
        for i, chunk in enumerate(chunks[1:], start=1):
            try:
                audio = _synthesize_chunk_with_retries(
                    client,
                    chunk,
                    chosen_voice,
                    locale,
                    speaking_rate,
                    pitch,
                )
            except google_exceptions.GoogleAPICallError as e:
                raise GoogleTtsError(f"Google TTS synthesis failed on segment {i + 1}/{len(chunks)}: {e}") from e
            seg = tmp_path / f"seg_{i:04d}.mp3"
            seg.write_bytes(audio)
            paths.append(seg)

        if len(paths) == 1:
            out_mp3.write_bytes(paths[0].read_bytes())
        else:
            assert ffmpeg_bin is not None
            _concat_mp3s(ffmpeg_bin, paths, out_mp3)

    logger.info(
        "Google TTS ok voice=%s locale=%s segments=%s",
        chosen_voice,
        locale,
        len(chunks),
    )
