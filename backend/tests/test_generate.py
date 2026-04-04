import io
import shutil
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import app
from app.schemas import ScriptPayload
from app.services.tts_elevenlabs import ElevenLabsError

REPO_ROOT = Path(__file__).resolve().parents[1]


def _artifact_root_for_test() -> Path:
    """Sandbox allows writes under the repo; system tmp often does not."""
    root = REPO_ROOT / ".pytest_artifacts" / uuid.uuid4().hex
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sample_script() -> ScriptPayload:
    return ScriptPayload(
        hook="Did you know plants make food from light?",
        facts=[
            "Chlorophyll absorbs sunlight.",
            "Water and CO2 become sugar and oxygen.",
            "This process is called photosynthesis.",
        ],
        ending="Follow for more science bites!",
        full_script_plain=(
            "Did you know plants make food from light?\n\n"
            "Chlorophyll absorbs sunlight.\n\n"
            "Water and CO2 become sugar and oxygen.\n\n"
            "This process is called photosynthesis.\n\n"
            "Follow for more science bites!"
        ),
        visual_segments_en=[
            "Curious student in sunlight looking at green leaves outdoors.",
            "Close-up of leaf cells and sunlight beams hitting chlorophyll.",
            "Diagram-like scene: water droplets and carbon dioxide merging into sugar and oxygen.",
            "Wide shot of a thriving plant in a field, energy from sun.",
            "Friendly educator waving, science classroom vibe.",
        ],
    )


@patch("app.main.mux_still_image_and_audio")
@patch("app.main.synthesize_google_tts_sync")
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_uses_google_tts_when_configured(
    mock_generate_script: AsyncMock,
    mock_gcp_tts: object,
    mock_mux: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    cred = tmp_path / "gcp-sa.json"
    cred.write_text('{"type": "service_account"}', encoding="utf-8")
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_CREDENTIALS_JSON", str(cred))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")
    mock_generate_script.return_value = _sample_script()

    def _gcp(settings, text, language, out_mp3: Path, *, voice_name=None) -> None:
        out_mp3.write_bytes(b"fake-mp3-bytes")

    mock_gcp_tts.side_effect = _gcp

    def _fake_mux(_png: Path, _mp3: Path, out_mp4: Path, **_kw: object) -> None:
        out_mp4.write_bytes(b"fake-mp4")

    mock_mux.side_effect = _fake_mux

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={"topic": "Photosynthesis", "language": "en"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tts_provider"] == "google"
    assert body["target_duration_seconds"] == 59
    assert body["video_width"] == 320
    assert body["video_height"] == 180
    assert body.get("content_format_applied") is None
    assert body.get("output_quality_applied") is None
    mock_gcp_tts.assert_called_once()


def test_generate_rejects_invalid_target_duration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_CREDENTIALS_JSON", str(tmp_path / "missing.json"))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={"topic": "x", "language": "en", "target_duration_seconds": "10"},
        )
    assert r.status_code == 400
    assert "target_duration_seconds" in r.json().get("detail", "")


def test_generate_invalid_output_quality(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_CREDENTIALS_JSON", str(tmp_path / "missing.json"))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={
                "topic": "x",
                "language": "en",
                "output_quality": "ultra_hd",
            },
        )
    assert r.status_code == 400
    assert "output_quality" in r.json().get("detail", "")


@patch("app.main.mux_still_image_and_audio")
@patch("app.main.synthesize_google_tts_sync")
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_applies_format_and_quality_to_mux(
    mock_generate_script: AsyncMock,
    mock_gcp_tts: object,
    mock_mux: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    cred = tmp_path / "gcp-sa.json"
    cred.write_text('{"type": "service_account"}', encoding="utf-8")
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_CREDENTIALS_JSON", str(cred))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")
    mock_generate_script.return_value = _sample_script()

    def _gcp(settings, text, language, out_mp3: Path, *, voice_name=None) -> None:
        out_mp3.write_bytes(b"fake-mp3-bytes")

    mock_gcp_tts.side_effect = _gcp

    def _fake_mux(_png: Path, _mp3: Path, out_mp4: Path, **_kw: object) -> None:
        out_mp4.write_bytes(b"fake-mp4")

    mock_mux.side_effect = _fake_mux

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={
                "topic": "Photosynthesis",
                "language": "en",
                "content_format": "youtube_landscape",
                "output_quality": "1080p",
            },
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["video_width"] == 1920
    assert body["video_height"] == 1080
    assert body["content_format_applied"] == "youtube_landscape"
    assert body["output_quality_applied"] == "1080p"
    mock_mux.assert_called_once()
    assert mock_mux.call_args.kwargs["video_width"] == 1920
    assert mock_mux.call_args.kwargs["video_height"] == 1080


def test_health():
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "openai_ready" in body
    assert "elevenlabs_ready" in body
    assert "google_tts_ready" in body
    assert "ffmpeg_ready" in body
    assert "ffprobe_ready" in body
    assert "gemini_imagen_ready" in body
    assert "gemini_native_image_ready" in body
    assert "vertex_gemini_image_ready" in body
    assert "vertex_imagen_ready" in body
    assert "nano_banana_ready" in body
    assert body.get("persistence_enabled") is False
    assert body.get("google_oauth_enabled") is False
    assert body.get("google_user_email") is None


def test_health_google_tts_ready_with_use_adc(monkeypatch):
    monkeypatch.setenv("GOOGLE_TTS_USE_ADC", "true")
    with TestClient(app) as client:
        r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("google_tts_ready") is True


@pytest.mark.integration
def test_mux_still_image_and_audio(tiny_mp3_path: Path):
    pytest.importorskip("PIL")
    from app.config import Settings
    from app.services.mux_mp4 import mux_still_image_and_audio
    from app.services.title_card import render_title_card

    work = _artifact_root_for_test()
    settings = Settings(
        artifact_root=work,
        video_width=320,
        video_height=180,
    )
    png = work / "c.png"
    mp3 = work / "a.mp3"
    shutil.copy(tiny_mp3_path, mp3)
    render_title_card(settings, "Test Topic", "en", png)
    out = work / "out.mp4"
    mux_still_image_and_audio(
        png,
        mp3,
        out,
        video_width=settings.video_width,
        video_height=settings.video_height,
    )
    assert out.exists() and out.stat().st_size > 0


@patch("app.main.mux_still_image_and_audio")
@patch("app.main.synthesize_elevenlabs", new_callable=AsyncMock)
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_end_to_end(
    mock_generate_script: AsyncMock,
    mock_eleven: AsyncMock,
    mock_mux: object,
    monkeypatch: pytest.MonkeyPatch,
):
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id-1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")
    mock_generate_script.return_value = _sample_script()

    async def _write_mp3(_s, _t, _l, out_mp3: Path) -> None:
        out_mp3.write_bytes(b"fake-mp3-bytes")

    mock_eleven.side_effect = _write_mp3

    def _fake_mux(_png: Path, _mp3: Path, out_mp4: Path, **_kw: object) -> None:
        out_mp4.write_bytes(b"fake-mp4")

    mock_mux.side_effect = _fake_mux

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={"topic": "Photosynthesis", "language": "en"},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tts_provider"] == "elevenlabs"
    assert body["visual_mode"] == "title_card"
    assert body.get("visual_detail")
    assert body.get("branding_logo_applied") is False
    job_id = body["job_id"]
    assert uuid.UUID(job_id)
    job_dir = root / job_id
    assert (job_dir / "voiceover.mp3").exists()
    assert (job_dir / "output.mp4").exists()
    assert (job_dir / "script.json").exists()


@patch("app.main.mux_still_image_and_audio")
@patch("app.main.synthesize_coqui_sync")
@patch("app.main.synthesize_elevenlabs", new_callable=AsyncMock)
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_falls_back_to_coqui(
    mock_generate_script: AsyncMock,
    mock_eleven: AsyncMock,
    mock_coqui: object,
    mock_mux: object,
    monkeypatch: pytest.MonkeyPatch,
):
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id-1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")
    mock_generate_script.return_value = _sample_script()
    mock_eleven.side_effect = ElevenLabsError("upstream down")

    def _coqui(settings, text, language, out_mp3: Path) -> None:
        out_mp3.write_bytes(b"coqui-mp3")

    mock_coqui.side_effect = _coqui

    def _fake_mux(_png: Path, _mp3: Path, out_mp4: Path, **_kw: object) -> None:
        out_mp4.write_bytes(b"fake-mp4")

    mock_mux.side_effect = _fake_mux

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={"topic": "Gravity", "language": "en"},
        )

    assert r.status_code == 200, r.text
    assert r.json()["tts_provider"] == "coqui"
    body_fb = r.json()
    assert body_fb["visual_mode"] == "title_card"
    assert body_fb.get("visual_detail")
    mock_coqui.assert_called_once()


@patch("app.main.mux_still_image_and_audio")
@patch("app.main.synthesize_elevenlabs", new_callable=AsyncMock)
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_with_branding_logo(
    mock_generate_script: AsyncMock,
    mock_eleven: AsyncMock,
    mock_mux: object,
    monkeypatch: pytest.MonkeyPatch,
):
    pytest.importorskip("PIL")
    from PIL import Image

    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id-1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")
    mock_generate_script.return_value = _sample_script()

    async def _write_mp3(_s, _t, _l, out_mp3: Path) -> None:
        out_mp3.write_bytes(b"fake-mp3-bytes")

    mock_eleven.side_effect = _write_mp3

    def _fake_mux(_png: Path, _mp3: Path, out_mp4: Path, **_kw: object) -> None:
        out_mp4.write_bytes(b"fake-mp4")

    mock_mux.side_effect = _fake_mux

    buf = io.BytesIO()
    Image.new("RGBA", (100, 50), (30, 144, 200, 255)).save(buf, format="PNG")
    logo_bytes = buf.getvalue()

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={"topic": "Photosynthesis", "language": "en"},
            files={"logo": ("co.png", logo_bytes, "image/png")},
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["branding_logo_applied"] is True
    job_dir = root / body["job_id"]
    assert (job_dir / "branding_logo.png").is_file()
    mock_mux.assert_called_once()
    call_kw = mock_mux.call_args.kwargs
    oa = call_kw.get("overlay_assets")
    assert oa is not None
    assert oa.branding_logo_path == job_dir / "branding_logo.png"


@patch("app.main.mux_still_image_and_audio")
@patch("app.main.synthesize_elevenlabs", new_callable=AsyncMock)
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_persistence_s3_upload_and_media_presigned_redirect(
    mock_generate_script: AsyncMock,
    mock_eleven: AsyncMock,
    mock_mux: object,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    pytest.importorskip("moto")
    import boto3
    from moto import mock_aws

    db_path = (tmp_path / "persist.db").resolve()
    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    root = _artifact_root_for_test()
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("ARTIFACT_CLEANUP_AFTER_S3", "false")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id-1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")
    mock_generate_script.return_value = _sample_script()

    async def _write_mp3(_s, _t, _l, out_mp3: Path) -> None:
        out_mp3.write_bytes(b"fake-mp3-bytes")

    mock_eleven.side_effect = _write_mp3

    def _fake_mux(_png: Path, _mp3: Path, out_mp4: Path, **_kw: object) -> None:
        out_mp4.write_bytes(b"fake-mp4")

    mock_mux.side_effect = _fake_mux

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        with TestClient(app) as client:
            h = client.get("/health")
            assert h.status_code == 200
            assert h.json().get("persistence_enabled") is True
            assert h.json().get("database_ready") is True
            r = client.post(
                "/generate",
                data={"topic": "Photosynthesis", "language": "en"},
            )
            assert r.status_code == 200, r.text
            job_id = r.json()["job_id"]
            listed = s3.list_objects_v2(Bucket="test-bucket", Prefix=f"jobs/{job_id}/")
            names = {o["Key"] for o in listed.get("Contents", [])}
            assert any(k.endswith("voiceover.mp3") for k in names)
            assert any(k.endswith("output.mp4") for k in names)
            redir = client.get(f"/media/{job_id}/voiceover.mp3", follow_redirects=False)
            redir_dl = client.get(
                f"/media/{job_id}/output.mp4?attachment=1",
                follow_redirects=False,
            )
    assert redir.status_code == 302
    assert "voiceover.mp3" in (redir.headers.get("location") or "").lower()
    assert redir_dl.status_code == 302
    loc_dl = redir_dl.headers.get("location") or ""
    assert "response-content-disposition" in loc_dl.lower()
    assert "attachment" in loc_dl.lower()
