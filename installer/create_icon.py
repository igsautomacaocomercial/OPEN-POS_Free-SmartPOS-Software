import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).with_name("openpos.ico")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = []
    for size in sizes:
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        radius = max(4, size // 5)
        d.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=(234, 88, 12, 255))
        try:
            font = ImageFont.truetype("arialbd.ttf", max(10, size // 3))
        except Exception:
            font = ImageFont.load_default()
        text = "POS"
        box = d.textbbox((0, 0), text, font=font)
        x = (size - (box[2] - box[0])) / 2
        y = (size - (box[3] - box[1])) / 2 - size * 0.03
        d.text((x, y), text, font=font, fill=(255, 247, 237, 255))
        images.append(img)
    out.parent.mkdir(parents=True, exist_ok=True)
    images[-1].save(out, sizes=[(s, s) for s in sizes], append_images=images[:-1])


if __name__ == "__main__":
    main()
