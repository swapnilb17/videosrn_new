import logging
import subprocess
from dataclasses import replace
from pathlib import Path

from app.services.ffmpeg_resolve import resolve_ffmpeg, resolve_ffprobe
from app.services.video_watermark import (
    FrameOverlayAssets,
    ffmpeg_filter_scale_pad_then_overlay_wm,
    write_watermark_overlay_png,
)

logger = logging.getLogger(__name__)

# Zoom range (scale multiplier from 1 .. 1+delta). Slightly stronger reads more "decisive" on screen.
_KB_ZOOM_DELTA = 0.11


def _filter_complex_static_slide(width: int, height: int) -> str:
    return ffmpeg_filter_scale_pad_then_overlay_wm(width, height)


def _ken_burns_scale_multiplier(zoom_in: bool, denom: int) -> str:
    """Per-frame scale factor using smoothstep(n/denom). Scale filter uses ``n`` (not zoompan's ``on``)."""
    d = max(denom, 1)
    # t = n/d; smoothstep = t*t*(3-2*t). No min()/max() — commas break filter_complex.
    sm = f"(n/{d})*(n/{d})*(3-2*(n/{d}))"
    if zoom_in:
        return f"(1+{_KB_ZOOM_DELTA}*({sm}))"
    return f"({1.0 + _KB_ZOOM_DELTA}-{_KB_ZOOM_DELTA}*({sm}))"


def _filter_complex_ken_burns_slide(
    width: int,
    height: int,
    *,
    zoom_in: bool,
    num_frames: int,
) -> str:
    """Ken Burns via scale+eval=frame + center crop (interpolated resize; avoids zoompan crop jitter)."""
    denom = max(num_frames - 1, 1)
    zm = _ken_burns_scale_multiplier(zoom_in, denom)
    # Cover output frame first so every pixel is filled, then zoom inside that raster.
    cover = f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase[fill]"
    anim = (
        f"[fill]scale=w='iw*{zm}':h='ih*{zm}':eval=frame:"
        f"flags=lanczos+accurate_rnd+full_chroma_inp[sc]"
    )
    # Default crop centers each frame when iw/ih change (see crop filter x/y defaults).
    crop = f"[sc]crop={width}:{height}[cr]"
    fmt = "[cr]format=yuv420p[bg]"
    ov = "[bg][1:v]overlay=0:0:format=auto[outv]"
    return f"{cover};{anim};{crop};{fmt};{ov}"


def audio_duration_seconds(ffprobe: str, audio: Path) -> float:
    r = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {r.stderr or r.stdout}")
    return float((r.stdout or "0").strip())


def trim_mp3_to_max_duration(
    src_mp3: Path,
    max_seconds: float,
    *,
    ffmpeg_explicit: str = "",
) -> Path:
    """Return ``src_mp3`` if narration is within the cap; otherwise a trimmed MP3 path.

    Ensures the user's chosen target duration is respected even when TTS or the model
    produces a longer track. If ffprobe/ffmpeg is missing or trim fails, returns ``src_mp3``.
    """
    if max_seconds <= 0:
        return src_mp3
    ffprobe = resolve_ffprobe(ffmpeg_explicit)
    ffmpeg = resolve_ffmpeg(explicit=ffmpeg_explicit or None)
    if not ffprobe or not ffmpeg:
        return src_mp3
    try:
        dur = audio_duration_seconds(ffprobe, src_mp3)
    except (RuntimeError, ValueError):
        return src_mp3
    if dur <= max_seconds + 0.15:
        return src_mp3
    out = src_mp3.parent / f"{src_mp3.stem}_max{int(max_seconds)}s{src_mp3.suffix}"
    base = [
        ffmpeg,
        "-y",
        "-i",
        str(src_mp3),
        "-t",
        str(max_seconds),
        "-vn",
    ]
    codec_variants: list[list[str]] = [
        ["-c:a", "libmp3lame", "-b:a", "192k"],
        ["-c:a", "copy"],
    ]
    last_err = ""
    for codec_args in codec_variants:
        cmd = [*base, *codec_args, str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        last_err = (proc.stderr or proc.stdout or "").strip()
        if proc.returncode == 0 and out.is_file() and out.stat().st_size > 0:
            return out
    logger.warning(
        "Could not cap MP3 to %.2fs (using full narration): %s",
        max_seconds,
        last_err[:500],
    )
    try:
        out.unlink(missing_ok=True)
    except OSError:
        pass
    return src_mp3


def word_weighted_durations(segments: list[str], total_seconds: float, floor: float = 0.75) -> list[float]:
    """Split total audio time across segments by word count (aligned with narration density)."""
    weights = [max(len((s or "").split()), 1) for s in segments]
    s = sum(weights)
    raw = [(w / s) * total_seconds for w in weights]
    # Enforce a small floor then renormalize to match total
    adj = [max(floor, d) for d in raw]
    scale = total_seconds / sum(adj)
    out = [d * scale for d in adj]
    drift = total_seconds - sum(out)
    if out:
        out[-1] = max(floor, out[-1] + drift)
    return out


def slideshow_durations_with_cta_coda(
    segment_texts: list[str],
    total_seconds: float,
    *,
    floor: float = 0.75,
) -> tuple[list[float], float]:
    """
    Split total audio so script slides use ``rest`` and a final CTA coda gets ``coda``,
    with ``sum(durs) + coda == total_seconds`` (voiceover continues over the CTA slide).

    Returns ``coda == 0`` when the track is too short to carve out a dedicated CTA beat;
    callers should skip appending a CTA slide in that case.
    """
    n = len(segment_texts)
    if n < 1:
        return [], 0.0
    max_coda = max(0.0, total_seconds - n * floor)
    if max_coda < 0.5:
        return word_weighted_durations(segment_texts, total_seconds, floor=floor), 0.0
    target_coda = max(2.0, min(5.0, total_seconds * 0.125))
    coda = min(target_coda, max_coda)
    if coda < 1.25:
        coda = min(max(0.6, max_coda), max_coda)
    coda = max(0.5, coda)
    rest = total_seconds - coda
    if rest <= 0:
        return word_weighted_durations(segment_texts, total_seconds, floor=floor), 0.0
    durs = word_weighted_durations(segment_texts, rest, floor=floor)
    return durs, coda


def mux_slideshow_with_audio(
    image_paths: list[Path],
    segment_seconds: list[float],
    audio: Path,
    out_mp4: Path,
    width: int,
    height: int,
    *,
    ffmpeg_explicit: str = "",
    overlay_assets: FrameOverlayAssets | None = None,
    ken_burns: bool = False,
    final_slide_is_dedicated_cta: bool = False,
) -> None:
    if len(image_paths) != len(segment_seconds):
        raise ValueError("images and durations length mismatch")
    if not image_paths:
        raise ValueError("no images")

    ffmpeg = resolve_ffmpeg(explicit=ffmpeg_explicit or None)
    if not ffmpeg:
        raise RuntimeError("ffmpeg not found")

    work = out_mp4.parent / f".slideshow_{out_mp4.stem}"
    work.mkdir(parents=True, exist_ok=True)
    assets = overlay_assets or FrameOverlayAssets()
    wm_main = work / "watermark_overlay_main.png"
    wm_with_cta = work / "watermark_overlay_with_cta.png"
    wm_cta_final = work / "watermark_overlay_cta_final.png"
    last_idx = len(image_paths) - 1
    has_cta_overlay = (
        not final_slide_is_dedicated_cta
        and assets.cta_image_path is not None
        and assets.cta_image_path.is_file()
    )
    if has_cta_overlay:
        write_watermark_overlay_png(
            width, height, wm_main, assets=replace(assets, cta_image_path=None)
        )
        write_watermark_overlay_png(width, height, wm_with_cta, assets=assets)
    elif final_slide_is_dedicated_cta:
        write_watermark_overlay_png(width, height, wm_main, assets=assets)
        write_watermark_overlay_png(
            width,
            height,
            wm_cta_final,
            assets=replace(assets, product_image_path=None),
        )
    else:
        write_watermark_overlay_png(width, height, wm_main, assets=assets)

    seg_files: list[Path] = []
    list_path = work / "concat.txt"
    merged = work / "video_noaudio.mp4"
    try:
        for i, (img, dur) in enumerate(zip(image_paths, segment_seconds, strict=True)):
            dur = max(0.5, float(dur))
            seg = work / f"part_{i:03d}.mp4"
            is_cta_end = final_slide_is_dedicated_cta and i == last_idx
            if is_cta_end:
                wm_png = wm_cta_final
            elif has_cta_overlay and i == last_idx:
                wm_png = wm_with_cta
            else:
                wm_png = wm_main
            use_ken = ken_burns and not is_cta_end
            if use_ken:
                # More frames per second of slide = smaller zoom steps (less visible stepping).
                num_frames = max(24, int(round(dur * 30)))
                fc = _filter_complex_ken_burns_slide(
                    width,
                    height,
                    zoom_in=(i % 2 == 0),
                    num_frames=num_frames,
                )
                cmd = [
                    ffmpeg,
                    "-y",
                    "-framerate",
                    "30",
                    "-loop",
                    "1",
                    "-t",
                    f"{dur:.3f}",
                    "-i",
                    str(img),
                    "-i",
                    str(wm_png),
                    "-filter_complex",
                    fc,
                    "-map",
                    "[outv]",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "30",
                    "-preset",
                    "veryfast",
                    "-tune",
                    "stillimage",
                    str(seg),
                ]
            else:
                fc = _filter_complex_static_slide(width, height)
                cmd = [
                    ffmpeg,
                    "-y",
                    "-loop",
                    "1",
                    "-t",
                    f"{dur:.3f}",
                    "-i",
                    str(img),
                    "-i",
                    str(wm_png),
                    "-filter_complex",
                    fc,
                    "-map",
                    "[outv]",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    "-r",
                    "30",
                    str(seg),
                ]
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if proc.returncode != 0:
                logger.error("ffmpeg segment %s failed: %s", i, proc.stderr)
                raise RuntimeError(f"Failed to encode slide {i}")
            seg_files.append(seg)

        lines: list[str] = []
        for seg in seg_files:
            p = seg.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{p}'")
        list_path.write_text("\n".join(lines), encoding="utf-8")

        cmd_cat = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(merged),
        ]
        proc = subprocess.run(cmd_cat, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.error("ffmpeg concat failed: %s", proc.stderr)
            raise RuntimeError("Failed to concatenate slides")

        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        cmd_final = [
            ffmpeg,
            "-y",
            "-i",
            str(merged),
            "-i",
            str(audio),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            str(out_mp4),
        ]
        proc = subprocess.run(cmd_final, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            logger.error("ffmpeg final mux failed: %s", proc.stderr)
            raise RuntimeError("Failed to mux audio with slideshow")
    finally:
        for seg in seg_files:
            seg.unlink(missing_ok=True)
        list_path.unlink(missing_ok=True)
        merged.unlink(missing_ok=True)
        wm_main.unlink(missing_ok=True)
        if has_cta_overlay:
            wm_with_cta.unlink(missing_ok=True)
        if final_slide_is_dedicated_cta:
            wm_cta_final.unlink(missing_ok=True)
        try:
            work.rmdir()
        except OSError:
            pass
