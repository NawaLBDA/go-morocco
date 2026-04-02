from __future__ import annotations

from pathlib import Path

from PIL import Image


# (input_path, output_path, max_width, quality)
TARGETS: list[tuple[str, str, int, int]] = [
    ("static/img/hero-ma.jpg", "static/img/hero-ma.webp", 1920, 75),
    ("static/img/hero2-ir.jpg", "static/img/hero2-ir.webp", 1920, 75),
    ("static/img/hero4-ir.jpg", "static/img/hero4-ir.webp", 1920, 75),
    ("static/img/hero1-ir.png", "static/img/hero1-ir.webp", 1920, 75),
    ("static/img/hero3-ir.png", "static/img/hero3-ir.webp", 1920, 75),
    ("static/img/hero2.jpg", "static/img/hero2.webp", 1920, 75),
    ("static/img/hero3.jpg", "static/img/hero3.webp", 1920, 75),
    ("static/img/hero4.jpg", "static/img/hero4.webp", 1920, 75),
    ("static/img/reservation.jpg", "static/img/reservation.webp", 1600, 75),
    ("static/img/reservation-ir.jpg", "static/img/reservation-ir.webp", 1600, 75),
]


def _convert(in_path: str, out_path: str, max_width: int, quality: int) -> None:
    src = Path(in_path)
    dst = Path(out_path)

    if not src.exists():
        print(f"SKIP missing: {src}")
        return

    with Image.open(src) as img:
        img.load()

        if img.mode in ("RGBA", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        if w > max_width:
            new_h = int(h * (max_width / w))
            img = img.resize((max_width, new_h), Image.LANCZOS)

        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "WEBP", quality=quality, method=6)

    print(f"OK: {src} -> {dst}")


def main() -> None:
    for inp, outp, mw, q in TARGETS:
        _convert(inp, outp, mw, q)

    print("\nOutput sizes:")
    for _, outp, _, _ in TARGETS:
        p = Path(outp)
        if p.exists():
            print(f"{outp}: {p.stat().st_size} bytes")


if __name__ == "__main__":
    main()
