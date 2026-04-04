#!/usr/bin/env python3
"""Create square template thumbnails from reference images.

Crops to center-square, resizes to 400x400, applies EnablyAI.com watermark,
and saves as JPEG in public/templates/.
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


def load_font(size: int):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def center_crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    return img.crop((left, top, left + side, top + side))


def add_watermark(img: Image.Image) -> Image.Image:
    canvas = img.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    wm_text = "EnablyAI.com"
    font_size = max(11, canvas.width // 30)
    font = load_font(font_size)

    bbox = draw.textbbox((0, 0), wm_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    margin = max(8, canvas.width // 40)
    pad_x, pad_y = 5, 3
    x = margin + pad_x
    y = canvas.height - margin - th - pad_y

    draw.rounded_rectangle(
        [margin, y - pad_y, x + tw + pad_x, y + th + pad_y],
        radius=4, fill=(0, 0, 0, 140),
    )
    draw.text((x, y), wm_text, fill=(255, 255, 255, 200), font=font)

    result = Image.alpha_composite(canvas, overlay)
    return result.convert("RGB")


def process(src_path: str, out_name: str):
    img = Image.open(src_path)
    img = center_crop_square(img)
    img = img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    img = add_watermark(img)
    out = OUT_DIR / f"{out_name}.jpg"
    img.save(out, "JPEG", quality=90)
    print(f"  {out_name}.jpg  ({src_path})")


ASSETS = Path("/Users/swapnilbhairavkar/.cursor/projects/Users-swapnilbhairavkar-Documents-Website-EnablyAI-New/assets")

MAPPING = {
    "ink_sketch": "image_8715d86e98a2.png-f50b99fa-c658-4a31-98e9-1272523705fc.png",
    "bold_text": "ChatGPT_Image_Apr_4__2026__01_25_55_AM-749a16a3-79e1-4f16-9f95-82f309c13f4a.png",
    "street_art": "Stay_cool_in_street_art_style-843c1d2d-4fe6-4b8b-96ff-70b86ee0fb47.png",
    "sticky_notes": "A0F45386-4061-461E-AAEB-C36C22C43142_4_5005_c-ff725df7-85ac-45e3-8578-ee2e3a2e263f.png",
    "polaroid": "Polaroids_and_portrait_in_motion-a3e03cc2-22e1-41fd-8a7e-3582ae9b4b74.png",
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Creating thumbnails in {OUT_DIR}")
    for name, filename in MAPPING.items():
        src = ASSETS / filename
        if src.is_file():
            process(str(src), name)
        else:
            print(f"  SKIP {name} — {src} not found")
    print("Done!")


if __name__ == "__main__":
    main()
