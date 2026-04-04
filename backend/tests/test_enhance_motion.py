"""Enhance: Ken Burns + (when on) conversational script path and Google TTS requirement."""

import shutil
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.main import app
from app.schemas import DialogueTurn, ScriptPayload
from tests.test_generate import _artifact_root_for_test, _sample_script


def _sample_conversational_script() -> ScriptPayload:
    """Six alternating lines + six slide hints (matches Enhance conversational pipeline)."""
    turns = [
        DialogueTurn(speaker="male", text="What is photosynthesis in one line?"),
        DialogueTurn(
            speaker="female",
            text="Plants capturing sunlight to make sugar from water and air.",
        ),
        DialogueTurn(speaker="male", text="Why does that matter for us?"),
        DialogueTurn(
            speaker="female",
            text="It releases the oxygen we breathe and anchors the food web.",
        ),
        DialogueTurn(speaker="male", text="So it's solar-powered cooking for Earth?"),
        DialogueTurn(
            speaker="female",
            text="Exactly—nature's cleantech, billions of years old.",
        ),
    ]
    visual = [
        "Curious student in a bright classroom asking about plants.",
        "Sunlight beams hitting green leaves, botanical illustration style.",
        "Planet Earth diagram with oxygen arrows and people outdoors.",
        "Lush ecosystem food chain at a pond without readable labels.",
        "Friendly metaphor of sunlight as warmth over green leaves.",
        "Warm sunset over a field with crop silhouettes, cinematic.",
    ]
    full = "\n\n".join(t.text for t in turns)
    return ScriptPayload(
        hook=turns[0].text,
        facts=[turns[1].text, turns[2].text, turns[3].text, turns[4].text],
        ending=turns[-1].text,
        full_script_plain=full,
        visual_segments_en=visual,
        conversational_turns=turns,
    )


def test_enhance_requires_google_cloud_tts(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_CREDENTIALS_JSON", str(tmp_path / "nonexistent-sa.json"))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id-1")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={
                "topic": "Photosynthesis",
                "language": "en",
                "enhance_motion": "true",
            },
        )
    assert r.status_code == 503
    assert "Enhance mode" in (r.json().get("detail") or "")
    assert "multi-voice" in (r.json().get("detail") or "")


@patch("app.main.audio_duration_seconds")
@patch("app.main.mux_slideshow_with_audio")
@patch("app.main.generate_gemini_native_slide_images", new_callable=AsyncMock)
@patch("app.main.synthesize_google_tts_conversational_sync")
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_enhance_motion_passes_ken_burns_to_mux(
    mock_generate_script: AsyncMock,
    mock_conv_tts: MagicMock,
    mock_gemini_imgs: AsyncMock,
    mock_mux: MagicMock,
    mock_audio_duration: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tiny_mp3_path: Path,
    tmp_path: Path,
):
    root = _artifact_root_for_test()
    cred = tmp_path / "gcp-sa.json"
    cred.write_text('{"type": "service_account"}', encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_TTS_CREDENTIALS_JSON", str(cred))
    monkeypatch.setenv("ELEVENLABS_API_KEY", "")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")

    mock_generate_script.return_value = _sample_conversational_script()
    mock_audio_duration.return_value = 2.0

    def _conv_tts(_settings, turns, _lang, out_mp3: Path, **_kw: object) -> None:
        assert len(turns) == 6
        shutil.copy(tiny_mp3_path, out_mp3)

    mock_conv_tts.side_effect = _conv_tts

    async def _fake_slides(
        _settings, _topic, _script, _lang, slides_dir: Path, **_kw: object
    ) -> list[Path]:
        slides_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i in range(6):
            p = slides_dir / f"s{i}.png"
            Image.new("RGB", (64, 64), (40 + i * 10, 80, 120)).save(p)
            paths.append(p)
        return paths

    mock_gemini_imgs.side_effect = _fake_slides

    def _mux_side_effect(
        _imgs: object,
        _durs: object,
        _audio: object,
        out_mp4: Path,
        *_a: object,
        **kw: object,
    ) -> None:
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        out_mp4.write_bytes(b"fake-slideshow-mp4")
        assert kw.get("ken_burns") is True

    mock_mux.side_effect = _mux_side_effect

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={
                "topic": "Photosynthesis",
                "language": "en",
                "target_duration_seconds": "30",
                "enhance_motion": "true",
            },
        )

    assert r.status_code == 200, r.text
    assert r.json()["target_duration_seconds"] == 30
    mock_mux.assert_called_once()
    mock_conv_tts.assert_called_once()
    mock_generate_script.assert_awaited_once()
    call_kw = mock_generate_script.await_args.kwargs
    assert call_kw.get("conversational") is True


@patch("app.main.audio_duration_seconds")
@patch("app.main.mux_slideshow_with_audio")
@patch("app.main.generate_gemini_native_slide_images", new_callable=AsyncMock)
@patch("app.main.synthesize_elevenlabs", new_callable=AsyncMock)
@patch("app.main.generate_script", new_callable=AsyncMock)
def test_generate_enhance_motion_off_disables_ken_burns(
    mock_generate_script: AsyncMock,
    mock_eleven: AsyncMock,
    mock_gemini_imgs: AsyncMock,
    mock_mux: MagicMock,
    mock_audio_duration: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    tiny_mp3_path: Path,
):
    root = _artifact_root_for_test()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice-id-1")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "")
    monkeypatch.setenv("NANO_BANANA_API_KEY", "")
    monkeypatch.setenv("ARTIFACT_ROOT", str(root))
    monkeypatch.setenv("VIDEO_WIDTH", "320")
    monkeypatch.setenv("VIDEO_HEIGHT", "180")

    mock_generate_script.return_value = _sample_script()
    mock_audio_duration.return_value = 2.0

    async def _write_mp3(_s, _t, _l, out_mp3: Path) -> None:
        shutil.copy(tiny_mp3_path, out_mp3)

    mock_eleven.side_effect = _write_mp3

    async def _fake_slides(
        _settings, _topic, _script, _lang, slides_dir: Path, **_kw: object
    ) -> list[Path]:
        slides_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for i in range(5):
            p = slides_dir / f"s{i}.png"
            Image.new("RGB", (64, 64), (40 + i * 10, 80, 120)).save(p)
            paths.append(p)
        return paths

    mock_gemini_imgs.side_effect = _fake_slides

    def _mux_side_effect(
        _imgs: object,
        _durs: object,
        _audio: object,
        out_mp4: Path,
        *_a: object,
        **kw: object,
    ) -> None:
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        out_mp4.write_bytes(b"fake-slideshow-mp4")
        assert kw.get("ken_burns") is False

    mock_mux.side_effect = _mux_side_effect

    with TestClient(app) as client:
        r = client.post(
            "/generate",
            data={
                "topic": "Photosynthesis",
                "language": "en",
                "enhance_motion": "false",
            },
        )

    assert r.status_code == 200, r.text
    mock_mux.assert_called_once()
    call_kw = mock_generate_script.await_args.kwargs
    assert call_kw.get("conversational") is False


@pytest.mark.integration
def test_mux_slideshow_ken_burns_writes_mp4(tiny_mp3_path: Path):
    from app.services.slideshow_video import mux_slideshow_with_audio

    work = _artifact_root_for_test()
    png_a = work / "a.png"
    png_b = work / "b.png"
    Image.new("RGB", (400, 300), (90, 120, 200)).save(png_a)
    Image.new("RGB", (400, 300), (200, 90, 60)).save(png_b)
    mp3 = work / "n.mp3"
    shutil.copy(tiny_mp3_path, mp3)
    out = work / f"out_{uuid.uuid4().hex}.mp4"
    mux_slideshow_with_audio(
        [png_a, png_b],
        [0.2, 0.2],
        mp3,
        out,
        320,
        180,
        ken_burns=True,
    )
    assert out.is_file() and out.stat().st_size > 100


def test_script_visual_segments_uses_conversational_turns():
    from app.services.image_prompts import script_visual_segments

    script = _sample_conversational_script()
    segs = script_visual_segments(script)
    assert len(segs) == 6
    assert segs[0][0] == "turn_0"
    assert "photosynthesis" in segs[0][1].lower()


def test_script_payload_rejects_non_alternating_conversational():
    from pydantic import ValidationError

    turns = [
        DialogueTurn(speaker="male", text="One"),
        DialogueTurn(speaker="female", text="Two"),
        DialogueTurn(speaker="male", text="Three"),
        DialogueTurn(speaker="male", text="Four breaks alternate"),
        DialogueTurn(speaker="female", text="Five"),
        DialogueTurn(speaker="male", text="Six"),
    ]
    with pytest.raises(ValidationError):
        ScriptPayload(
            hook="One",
            facts=["Two", "Three"],
            ending="Six",
            full_script_plain="x",
            visual_segments_en=["v"] * 6,
            conversational_turns=turns,
        )
