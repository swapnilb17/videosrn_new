from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.config import Settings
from app.schemas import LanguageCode


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "C:\\Windows\\Fonts\\arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _lang_label(language: LanguageCode) -> str:
    return {"en": "English", "hi": "Hindi", "mr": "Marathi"}[language]


def _wrap_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    for w in words:
        trial = " ".join(current + [w])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(w)
        else:
            if current:
                lines.append(" ".join(current))
            current = [w]
    if current:
        lines.append(" ".join(current))
    return lines


def render_title_card(
    settings: Settings,
    topic: str,
    language: LanguageCode,
    out_png: Path,
) -> None:
    w, h = settings.video_width, settings.video_height
    img = Image.new("RGB", (w, h), color=(18, 18, 28))
    draw = ImageDraw.Draw(img)
    margin = int(min(w, h) * 0.08)
    max_text_w = w - 2 * margin

    title_font = _load_font(int(h * 0.055))
    sub_font = _load_font(int(h * 0.032))

    title_lines = _wrap_lines(topic.strip(), title_font, max_text_w, draw)
    subtitle = f"Educational short · {_lang_label(language)}"

    line_heights_title = []
    for line in title_lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        line_heights_title.append(bbox[3] - bbox[1])
    sub_bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    sub_h = sub_bbox[3] - sub_bbox[1]
    gap = int(h * 0.02)
    block_h = sum(line_heights_title) + gap * (len(title_lines) - 1) + gap + sub_h
    y = (h - block_h) // 2

    for line, lh in zip(title_lines, line_heights_title, strict=True):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        tw = bbox[2] - bbox[0]
        draw.text(((w - tw) // 2, y), line, fill=(245, 245, 250), font=title_font)
        y += lh + gap

    bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
    tw = bbox[2] - bbox[0]
    draw.text(((w - tw) // 2, y), subtitle, fill=(160, 160, 180), font=sub_font)

    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png, format="PNG")
