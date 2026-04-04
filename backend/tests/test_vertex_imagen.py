import httpx

from app.config import Settings
from app.services.vertex_imagen import response_indicates_try_next_region


def test_try_next_region_on_429():
    r = httpx.Response(429, json={})
    assert response_indicates_try_next_region(r) is True


def test_try_next_region_on_resource_exhausted_body():
    r = httpx.Response(
        403,
        json={"error": {"status": "RESOURCE_EXHAUSTED", "message": "Quota exceeded"}},
    )
    assert response_indicates_try_next_region(r) is True


def test_no_failover_on_ok():
    r = httpx.Response(200, json={"predictions": []})
    assert response_indicates_try_next_region(r) is False


def test_no_failover_on_permission_denied_without_quota():
    r = httpx.Response(
        403,
        json={"error": {"status": "PERMISSION_DENIED", "message": "Permission denied"}},
    )
    assert response_indicates_try_next_region(r) is False


def test_imagen_model_effective_remaps_standard_to_fast():
    s = Settings(
        imagen_model="imagen-4.0-generate-001",
        imagen_allow_standard_generate=False,
    )
    assert s.imagen_model_effective() == "imagen-4.0-fast-generate-001"


def test_imagen_model_effective_keeps_standard_when_opt_in(monkeypatch):
    monkeypatch.setenv("IMAGEN_MODEL", "imagen-4.0-generate-001")
    monkeypatch.setenv("IMAGEN_ALLOW_STANDARD_GENERATE", "true")
    s = Settings()
    assert s.imagen_model_effective() == "imagen-4.0-generate-001"


def test_vertex_imagen_requires_key_file_not_tts_adc_only(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.setenv("GOOGLE_TTS_USE_ADC", "true")
    monkeypatch.setenv("IMAGEN_USE_VERTEX", "true")
    monkeypatch.setenv("VERTEX_IMAGEN_PROJECT", "test-project")
    monkeypatch.setenv("GOOGLE_TTS_CREDENTIALS_JSON", "/no/such/credentials.json")
    s = Settings()
    assert s.google_tts_is_configured()
    assert s.vertex_imagen_configured() is False
