"""Video overlay: optional logo, product, CTA, address; Enably credit bottom-center (PIL + FFmpeg)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

WATERMARK_TEXT = "Powered by EnablyAI.com"

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


@dataclass(frozen=True)
class FrameOverlayAssets:
    """Optional paths / text composited on every frame (same WxH as video).

    For slideshow videos, the CTA file normally becomes its own full-frame closing
    slide (see ``render_dedicated_cta_slide_png`` / ``mux_slideshow_with_audio``).
    If the narration is too short to carve out a coda, the CTA may fall back to a
    corner overlay on the last script slide only. Title-card / single-image output
    still shows the CTA for the full duration when provided.
    """

    branding_logo_path: Path | None = None
    product_image_path: Path | None = None
    cta_image_path: Path | None = None
    address_text: str | None = None


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for raw in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(raw, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _paste_logo_blended(canvas: Image.Image, logo: Image.Image, lx: int, ty: int) -> None:
    lw, lh = logo.size
    if lw < 1 or lh < 1:
        return

    blur = int(max(4, min(14, max(lw, lh) // 14)))
    ox = max(1, blur // 4)
    oy = max(2, blur // 3)

    alpha = logo.getchannel("A")
    shadow = Image.new("RGBA", (lw, lh), (18, 22, 32, 0))
    shadow.putalpha(alpha.point(lambda p: min(255, int(p * 0.38)) if p else 0))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    canvas.paste(shadow, (lx + ox, ty + oy), shadow)
    canvas.paste(logo, (lx, ty), logo)


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, draw: ImageDraw.ImageDraw, max_width: int) -> list[str]:
    words = (text or "").split()
    if not words:
        return []
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        test = " ".join(cur + [w])
        bbox = draw.textbbox((0, 0), test, font=font)
        tw = bbox[2] - bbox[0]
        if tw <= max_width:
            cur.append(w)
        else:
            if cur:
                lines.append(" ".join(cur))
            cur = [w]
    if cur:
        lines.append(" ".join(cur))
    return lines


def write_watermark_overlay_png(
    width: int,
    height: int,
    dest: Path,
    *,
    assets: FrameOverlayAssets | None = None,
) -> None:
    """
    Full-frame RGBA PNG (transparent) for FFmpeg overlay.
    Stack (bottom → top): optional CTA image, optional address, Powered by plate,
    optional product (BR), optional logo (TL). Slideshows normally use a generated
    CTA slide instead of this CTA layer; see ``cta_end_slide`` and ``mux_slideshow_with_audio``.
    """
    a = assets or FrameOverlayAssets()
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    ref = min(width, height)
    margin_x = max(14, ref // 48)
    margin_y = max(14, ref // 48)
    gap = max(8, height // 120)
    pad = max(6, height // 160)

    fs_credit = max(16, height // 48)
    font_credit = _load_font(fs_credit)
    text = WATERMARK_TEXT
    bbox_cr = draw.textbbox((0, 0), text, font=font_credit)
    tw, th = bbox_cr[2] - bbox_cr[0], bbox_cr[3] - bbox_cr[1]
    x_text = (width - tw) // 2
    y_text = height - margin_y - th

    fs_addr = max(13, height // 52)
    font_addr = _load_font(fs_addr)
    addr_max_w = int(width * 0.84)
    address_lines = _wrap_lines(a.address_text or "", font_addr, draw, addr_max_w)[:5]
    line_h = fs_addr + max(3, fs_addr // 5)

    cta_im: Image.Image | None = None
    if a.cta_image_path is not None and a.cta_image_path.is_file():
        try:
            cta_im = Image.open(a.cta_image_path).convert("RGBA")
            max_cta_w = int(width * 0.62)
            max_cta_h = int(height * 0.18)
            cta_im.thumbnail((max_cta_w, max_cta_h), Image.Resampling.LANCZOS)
        except OSError:
            cta_im = None

    # Vertical stack above the credit line (going upward from y_text - pad)
    cursor_bottom = y_text - pad - gap

    if cta_im is not None:
        cw, ch = cta_im.size
        cx = (width - cw) // 2
        cy = cursor_bottom - ch
        _paste_logo_blended(img, cta_im, cx, cy)
        cursor_bottom = cy - gap

    if address_lines:
        total_txt_h = len(address_lines) * line_h
        addr_pad_y = max(4, pad // 2)
        block_h = total_txt_h + addr_pad_y * 2
        y_block_top = cursor_bottom - block_h
        inner_w = min(addr_max_w + 2 * pad, width - 2 * margin_x)
        x0 = (width - inner_w) // 2
        y0 = y_block_top
        x1 = x0 + inner_w
        y1 = cursor_bottom
        draw.rounded_rectangle([x0, y0, x1, y1], radius=8, fill=(0, 0, 0, 120))
        y_line = y0 + addr_pad_y
        for line in address_lines:
            bbox_ln = draw.textbbox((0, 0), line, font=font_addr)
            lw_ln = bbox_ln[2] - bbox_ln[0]
            draw.text((x0 + (inner_w - lw_ln) // 2, y_line), line, fill=(255, 255, 255, 235), font=font_addr)
            y_line += line_h
        cursor_bottom = y_block_top - gap

    draw.rounded_rectangle(
        [x_text - pad, y_text - pad, x_text + tw + pad, y_text + th + pad],
        radius=6,
        fill=(0, 0, 0, 130),
    )
    draw.text((x_text, y_text), text, fill=(255, 255, 255, 240), font=font_credit)

    if a.product_image_path is not None and a.product_image_path.is_file():
        try:
            pim = Image.open(a.product_image_path).convert("RGBA")
        except OSError:
            pim = None
        if pim is not None:
            max_side = max(40, int(ref * 0.19))
            pim.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            pw, ph = pim.size
            lx = width - margin_x - pw
            ty = height - margin_y - ph
            _paste_logo_blended(img, pim, lx, ty)

    if a.branding_logo_path is not None and a.branding_logo_path.is_file():
        try:
            logo_im = Image.open(a.branding_logo_path).convert("RGBA")
        except OSError:
            logo_im = None
        if logo_im is not None:
            max_side = max(40, int(ref * 0.132))
            logo_im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            lw, lh = logo_im.size
            lx = margin_x
            logo_top = margin_y
            _paste_logo_blended(img, logo_im, lx, logo_top)

    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="PNG")


def ffmpeg_filter_scale_pad_then_overlay_wm(width: int, height: int) -> str:
    """filter_complex: scale+pad video [0], overlay full-frame wm [1]."""
    scale_pad = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,format=yuv420p[bg];"
        f"[bg][1:v]overlay=0:0:format=auto[outv]"
    )
    return scale_pad
