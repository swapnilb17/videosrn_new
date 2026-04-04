from pathlib import Path

from PIL import Image

from app.services.cta_end_slide import render_dedicated_cta_slide_png
from app.services.slideshow_video import slideshow_durations_with_cta_coda


def test_slideshow_durations_with_cta_coda_matches_total() -> None:
    texts = ["one two", "three four five", "six", "seven eight"]
    total = 48.0
    durs, coda = slideshow_durations_with_cta_coda(texts, total)
    if coda >= 0.5:
        assert len(durs) == len(texts)
        assert abs(sum(durs) + coda - total) < 0.05
    else:
        assert abs(sum(durs) - total) < 0.05


def test_render_dedicated_cta_slide_png_writes_file(tmp_path: Path) -> None:
    cta = tmp_path / "in.png"
    Image.new("RGBA", (120, 80), (255, 200, 50, 255)).save(cta)
    out = tmp_path / "out.png"
    render_dedicated_cta_slide_png(out, 640, 360, cta)
    assert out.is_file() and out.stat().st_size > 500
