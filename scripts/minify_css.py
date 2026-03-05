"""Simple script to minify the main stylesheet.

Usage:
    python scripts/minify_css.py

It reads static/css/style.css and writes static/css/style.min.css.
The template base.html could be updated to point to the minified file (or
collectstatic could serve it instead).
"""
import re
from pathlib import Path

css_path = Path(__file__).parent.parent / "static" / "css" / "style.css"
min_path = css_path.with_name("style.min.css")

if not css_path.exists():
    print("style.css not found")
    exit(1)

text = css_path.read_text()
# very basic minification
# remove comments
text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
# remove whitespace around symbols
text = re.sub(r"\s*([{};:,])\s*", r"\1", text)
# collapse multiple spaces
text = re.sub(r"\s+", " ", text)
# remove leading/trailing whitespace
text = text.strip()

min_path.write_text(text)
print(f"wrote {min_path} (size {min_path.stat().st_size/1024:.1f}KB)")
