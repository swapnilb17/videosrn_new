import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clear_persistence_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Avoid picking up DATABASE_URL / S3 from a developer .env unless a test sets them."""
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("S3_BUCKET", "")
    monkeypatch.setenv("S3_REGION", "")


@pytest.fixture(scope="session")
def tiny_mp3_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("audio") / "silence.mp3"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=r=44100:cl=mono",
                "-t",
                "0.4",
                "-c:a",
                "libmp3lame",
                str(out),
            ],
            check=True,
            capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        pytest.skip(f"ffmpeg required for audio fixture: {e}")
    return out
