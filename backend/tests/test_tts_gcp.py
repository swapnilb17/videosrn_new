from app.services.tts_gcp import _chunk_text, _utf8_byte_chunks, friendly_google_tts_voice_label


def test_friendly_voice_label_wavenet_neural_standard():
    assert friendly_google_tts_voice_label("en-IN-Wavenet-D") == "Voice D"
    assert friendly_google_tts_voice_label("hi-IN-Neural2-A") == "Voice A"
    assert friendly_google_tts_voice_label("mr-IN-Standard-B") == "Voice B"


def test_friendly_voice_label_chirp_uses_name():
    assert friendly_google_tts_voice_label("en-IN-Chirp3-HD-Algieba") == "Algieba"


def test_utf8_byte_chunks_respects_multibyte_boundary():
    s = "नमस्ते" * 800  # Hindi letters are multi-byte in UTF-8
    parts = _utf8_byte_chunks(s, 120)
    assert len(parts) >= 2
    assert "".join(parts) == s
    for p in parts:
        assert len(p.encode("utf-8")) <= 120


def test_chunk_text_single_short():
    assert _chunk_text("Hello world.", 1000) == ["Hello world."]


def test_chunk_text_splits_long_plain_text():
    text = ("x" * 300 + ". ") * 20
    chunks = _chunk_text(text, 400)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c.encode("utf-8")) <= 400
