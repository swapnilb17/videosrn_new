"""CTA: dedicated slide path strips CTA from overlay; mux can still build with/without CTA layers."""

from dataclasses import replace
from pathlib import Path

from PIL import Image

from app.services.video_watermark import FrameOverlayAssets, write_watermark_overlay_png


def test_cta_overlay_differs_from_no_cta_version(tmp_path: Path) -> None:
    """Fallback overlay mode: last-segment watermark differs when CTA is included."""
    cta = tmp_path / "cta.png"
    Image.new("RGBA", (80, 40), (200, 40, 40, 230)).save(cta)
    assets = FrameOverlayAssets(cta_image_path=cta)
    w, h = 320, 180
    out_plain = tmp_path / "wm_plain.png"
    out_cta = tmp_path / "wm_cta.png"
    write_watermark_overlay_png(w, h, out_plain, assets=replace(assets, cta_image_path=None))
    write_watermark_overlay_png(w, h, out_cta, assets=assets)
    assert out_plain.stat().st_size != out_cta.stat().st_size
