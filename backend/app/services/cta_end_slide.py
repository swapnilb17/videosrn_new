"""Full-frame closing slide for user CTA art (buy URL, offer) — no overlap with product shots."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter


def render_dedicated_cta_slide_png(
    out_path: Path,
    width: int,
    height: int,
    cta_png_path: Path,
) -> None:
    """
    Build a WxH RGB slide: soft neutral backdrop with the CTA graphic scaled to fit
    (letterboxed), so it reads clearly without sitting on top of a generated scene.
    """
    w, h = max(64, int(width)), max(64, int(height))
    top = (248, 245, 240)
    bottom = (232, 228, 218)
    img = Image.new("RGB", (w, h), top)
    px = img.load()
    if px is not None:
        for y in range(h):
            t = y / max(h - 1, 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            for x in range(w):
                px[x, y] = (r, g, b)

    cta = Image.open(cta_png_path).convert("RGBA")
    max_w = int(w * 0.88)
    max_h = int(h * 0.78)
    cta.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    cw, ch = cta.size
    x0 = (w - cw) // 2
    y0 = (h - ch) // 2
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow.paste(cta, (0, 0), cta)
    alpha = cta.split()[3]
    shadow.putalpha(alpha.point(lambda p: min(255, int(p * 0.22)) if p else 0))
    blur = max(6, min(20, max(cw, ch) // 25))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    img_rgba = img.convert("RGBA")
    sx = max(0, min(w - cw, x0 + max(3, cw // 40)))
    sy = max(0, min(h - ch, y0 + max(4, ch // 35)))
    img_rgba.paste(shadow, (sx, sy), shadow)
    img_rgba.paste(cta, (x0, y0), cta)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img_rgba.convert("RGB").save(out_path, format="PNG")
