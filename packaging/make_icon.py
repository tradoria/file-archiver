"""Generate a simple app icon (icon.ico) for the File Archiver build.

Draws a stylized "archive box with a document" glyph at multiple
resolutions and saves them as a single multi-size .ico file, since no
icon asset ships with the original project.
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT_PATH = Path(__file__).parent / "icon.ico"

BLUE = (37, 99, 235, 255)      # tailwind blue-600
DARK_BLUE = (30, 64, 175, 255)  # tailwind blue-800
WHITE = (255, 255, 255, 255)
LIGHT = (219, 234, 254, 255)   # tailwind blue-100


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    pad = round(size * 0.08)
    box_top = round(size * 0.30)

    # Archive box body
    d.rounded_rectangle(
        [pad, box_top, size - pad, size - pad],
        radius=round(size * 0.06),
        fill=BLUE,
    )

    # Box lid
    lid_h = round(size * 0.16)
    d.rounded_rectangle(
        [pad * 0.6, box_top - lid_h, size - pad * 0.6, box_top + round(size * 0.04)],
        radius=round(size * 0.05),
        fill=DARK_BLUE,
    )

    # Handle slot on the lid
    slot_w = round(size * 0.28)
    slot_h = round(size * 0.05)
    slot_x0 = (size - slot_w) // 2
    slot_y0 = box_top - lid_h // 2 - slot_h // 2
    d.rounded_rectangle(
        [slot_x0, slot_y0, slot_x0 + slot_w, slot_y0 + slot_h],
        radius=slot_h // 2,
        fill=LIGHT,
    )

    # Document peeking out of the box
    doc_w = round(size * 0.30)
    doc_h = round(size * 0.34)
    doc_x0 = size // 2 - doc_w // 2
    doc_y0 = box_top - round(size * 0.10)
    d.rectangle([doc_x0, doc_y0, doc_x0 + doc_w, doc_y0 + doc_h], fill=WHITE)
    for i in range(3):
        line_y = doc_y0 + round(doc_h * 0.28) + i * round(doc_h * 0.22)
        d.rectangle(
            [doc_x0 + round(doc_w * 0.15), line_y, doc_x0 + round(doc_w * 0.85), line_y + max(1, round(size * 0.02))],
            fill=LIGHT,
        )

    return img


def main() -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [draw_icon(s) for s in sizes]
    images[-1].save(OUT_PATH, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"Icon geschrieben: {OUT_PATH}")


if __name__ == "__main__":
    main()
