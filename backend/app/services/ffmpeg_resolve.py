"""Find ffmpeg / ffprobe when PATH is minimal (e.g. GUI-launched uvicorn on macOS)."""

import shutil
import subprocess
from pathlib import Path

# Repository root (parent of app/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Local copies often live next to app/ or in bin/
_LOCAL_RELATIVE_CANDIDATES = (
    "ffmpeg",
    "ffmpeg.exe",
    "bin/ffmpeg",
    "bin/ffmpeg.exe",
    "ffmpeg-8.1/ffmpeg",
    "ffmpeg-8.1/ffmpeg.exe",
)


def _brew_ffmpeg(brew_exe: str) -> str | None:
    try:
        r = subprocess.run(
            [brew_exe, "--prefix"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0 or not (r.stdout or "").strip():
        return None
    p = Path(r.stdout.strip()) / "bin" / "ffmpeg"
    return str(p.resolve()) if p.is_file() else None


def resolve_ffmpeg(explicit: str | None = None) -> str | None:
    """explicit: optional path from FFMPEG_PATH; relative paths are under the project root."""
    if (explicit or "").strip():
        p = Path(explicit.strip()).expanduser()
        if not p.is_absolute():
            p = _PROJECT_ROOT / p
        p = p.resolve()
        if p.is_file():
            return str(p)

    found = shutil.which("ffmpeg")
    if found:
        return found

    for rel in _LOCAL_RELATIVE_CANDIDATES:
        candidate = (_PROJECT_ROOT / rel).resolve()
        if candidate.is_file():
            return str(candidate)

    for candidate in (
        Path("/opt/homebrew/bin/ffmpeg"),
        Path("/usr/local/bin/ffmpeg"),
    ):
        if candidate.is_file():
            return str(candidate)

    for brew in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew"):
        if Path(brew).is_file():
            ff = _brew_ffmpeg(brew)
            if ff:
                return ff

    return None


def resolve_ffprobe(ffmpeg_explicit: str = "") -> str | None:
    """ffprobe usually lives next to ffmpeg (Homebrew layout)."""
    ff = resolve_ffmpeg(explicit=ffmpeg_explicit or None)
    if ff:
        cand = Path(ff).parent / "ffprobe"
        if cand.is_file():
            return str(cand)
    return shutil.which("ffprobe")
