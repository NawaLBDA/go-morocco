"""Small utility to batch-compress and/or convert tour and hero images.

Run from the project root with the virtualenv activated:

    python scripts/compress_images.py

It will walk the static/img directory, resize any images wider than 1200px,
convert PNG to JPEG or WebP, and write optimized versions (overwriting by
default). Adjust `MAX_WIDTH` and `QUALITY` as needed.

This is a simple way to cut down the ~2-6MB hero images that are currently
blowing up the LCP metric.
"""

import os
from pathlib import Path
from PIL import Image

BASE = Path(__file__).parent.parent / "static" / "img"
MAX_WIDTH = 1200
QUALITY = 75

if not BASE.exists():
    print("static/img directory not found")
    exit(1)

print("Compressing images under", BASE)

from itertools import chain

for path in chain(BASE.rglob("*.jpg"), BASE.rglob("*.png")):
    try:
        with Image.open(path) as im:
            original_size = path.stat().st_size
            # resize if too wide
            if im.width > MAX_WIDTH:
                ratio = MAX_WIDTH / im.width
                new_size = (MAX_WIDTH, int(im.height * ratio))
                im = im.resize(new_size, Image.LANCZOS)
            # convert png to jpeg or webp
            if path.suffix.lower() == ".png":
                if im.mode in ("RGBA", "LA"):
                    # preserve alpha via webp
                    output_path = path.with_suffix(".webp")
                    im.save(output_path, format="WEBP", quality=QUALITY, optimize=True)
                else:
                    output_path = path.with_suffix(".jpg")
                    im.save(output_path, format="JPEG", quality=QUALITY, optimize=True)
            else:
                output_path = path
                im.save(output_path, format="JPEG", quality=QUALITY, optimize=True)
            new_size = output_path.stat().st_size
            savings = (original_size - new_size) / 1024
            print(f"{path.name}: {original_size/1024:.1f}KB -> {new_size/1024:.1f}KB (\u2212{int(savings)}KB)")
            if output_path != path:
                try:
                    path.unlink()
                except Exception:
                    pass
    except Exception as e:
        print(path, "error", e)

print("Done")
