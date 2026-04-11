#!/usr/bin/env python3
"""Generate placeholder template thumbnails for portrait style templates.

Each thumbnail is a 400x400 image with a styled gradient and the template name.

Usage:
    python scripts/generate_template_thumbnails.py
"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZE = 400
OUT_DIR = Path(__file__).resolve().parent.parent / "public" / "templates"

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
]

def load_font(size: int, candidates=None):
    for f in (candidates or FONT_CANDIDATES):
        try:
            return ImageFont.truetype(f, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


TEMPLATES = {
    "ink_sketch": {
        "label": "Ink Sketch",
        "gradient": [(245, 240, 230), (30, 30, 30)],
        "text_color": (20, 20, 20),
    },
    "bold_text": {
        "label": "Bold Text",
        "gradient": [(255, 215, 0), (180, 0, 120)],
        "text_color": (255, 255, 255),
    },
    "street_art": {
        "label": "Street Art",
        "gradient": [(80, 200, 255), (255, 80, 160)],
        "text_color": (20, 20, 30),
    },
    "sticky_notes": {
        "label": "Sticky Notes",
        "gradient": [(255, 245, 120), (255, 200, 80)],
        "text_color": (60, 50, 20),
    },
    "polaroid": {
        "label": "Polaroid",
        "gradient": [(250, 248, 240), (200, 190, 175)],
        "text_color": (40, 35, 30),
    },
    "monochrome": {
        "label": "Monochrome",
        "gradient": [(60, 60, 60), (10, 10, 10)],
        "text_color": (220, 220, 220),
    },
    "color_block": {
        "label": "Color Block",
        "gradient": [(255, 90, 120), (60, 20, 200)],
        "text_color": (255, 255, 255),
    },
    "runway": {
        "label": "Runway",
        "gradient": [(180, 140, 100), (40, 30, 20)],
        "text_color": (255, 230, 200),
    },
    "risograph": {
        "label": "Risograph",
        "gradient": [(230, 100, 80), (60, 140, 160)],
        "text_color": (255, 255, 240),
    },
    "technicolor": {
        "label": "Technicolor",
        "gradient": [(255, 180, 50), (200, 50, 120)],
        "text_color": (255, 255, 255),
    },
    "gothic_clay": {
        "label": "Gothic Clay",
        "gradient": [(80, 50, 40), (20, 15, 12)],
        "text_color": (200, 170, 140),
    },
    "dynamite": {
        "label": "Dynamite",
        "gradient": [(255, 120, 30), (180, 20, 20)],
        "text_color": (255, 255, 220),
    },
    "steampunk": {
        "label": "Steampunk",
        "gradient": [(160, 120, 60), (60, 40, 20)],
        "text_color": (230, 200, 140),
    },
    "sunrise": {
        "label": "Sunrise",
        "gradient": [(255, 200, 100), (200, 80, 60)],
        "text_color": (255, 255, 255),
    },
    "satou": {
        "label": "Satou",
        "gradient": [(200, 190, 170), (100, 95, 80)],
        "text_color": (50, 45, 40),
    },
    "cinematic_portrait": {
        "label": "Cinematic",
        "gradient": [(40, 60, 80), (10, 15, 25)],
        "text_color": (200, 210, 230),
    },
}


def make_gradient(size: int, c1: tuple, c2: tuple) -> Image.Image:
    img = Image.new("RGB", (size, size))
    for y in range(size):
        t = y / (size - 1)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        for x in range(size):
            img.putpixel((x, y), (r, g, b))
    return img


def generate_thumbnail(key: str, info: dict):
    c1, c2 = info["gradient"]
    img = make_gradient(SIZE, c1, c2).convert("RGBA")
    draw = ImageDraw.Draw(img)

    label_font = load_font(SIZE // 10)
    bbox = draw.textbbox((0, 0), info["label"], font=label_font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (SIZE - tw) // 2
    y = (SIZE - th) // 2
    r, g, b = info["text_color"]
    shadow_offset = max(1, SIZE // 200)
    draw.text((x + shadow_offset, y + shadow_offset), info["label"],
              fill=(0, 0, 0, 100), font=label_font)
    draw.text((x, y), info["label"], fill=(r, g, b, 255), font=label_font)

    out_path = OUT_DIR / f"{key}.jpg"
    img.convert("RGB").save(out_path, "JPEG", quality=88)
    print(f"  -> {out_path.name}")


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Generating {len(TEMPLATES)} template thumbnails in {OUT_DIR}")
    for key, info in TEMPLATES.items():
        generate_thumbnail(key, info)
    print("Done!")


if __name__ == "__main__":
    main()
