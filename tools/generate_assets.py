"""
generate_assets.py — DME Innovation branding pipeline
=====================================================

Renders every logo asset used by the AutoTuner Backup Tool straight from the
vector master (`assets/logo-source/DME-Innovation.ai`, an Illustrator file with
a PDF-compatible stream) and rewrites the base64 blobs that are embedded in
`autotuner_tool.py`, so the GUI stays a single self-contained script.

Usage:
    pip install pymupdf pillow
    python tools/generate_assets.py            # write assets/ + patch the .py
    python tools/generate_assets.py --check     # verify the .py is up to date

Only needed when the logo changes — the generated files are committed.
"""

from __future__ import annotations

import argparse
import base64
import io
import re
import sys
import textwrap
from pathlib import Path

try:
    import pymupdf  # PyMuPDF renders the .ai/PDF vector master
except ImportError:  # pragma: no cover - older PyMuPDF exposes `fitz` only
    import fitz as pymupdf

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
LOGO_SRC = ROOT / "assets" / "logo-source" / "DME-Innovation.ai"
ASSETS = ROOT / "assets"
BRAND_PY = ROOT / "dme_brand.py"

# Brand / UI colours (must match dme_ui.SURFACE / dme_ui.ACCENT)
AMBER = (255, 170, 0)
BLACK = (10, 10, 10)
HEADER_BG = (11, 13, 17)      # dme_ui.SURFACE / dme_brand.HEADER_BG
OFF_WHITE = (233, 236, 241)   # dme_ui.TEXT

# Icon sizes baked into the multi-resolution .ico
ICO_SIZES = [16, 24, 32, 48, 64, 128, 256]

# Header wordmark, rendered at the exact heights the app uses at 100 %, 150 %
# and 200 % display scaling. Tk can only scale bitmaps by whole factors, so the
# app picks a ready-made size instead of resampling anything.
HEADER_HEIGHTS = (40, 60, 80)


def render_master(dpi: int = 600) -> Image.Image:
    """Render the vector master to a trimmed RGBA image (black on transparent)."""
    doc = pymupdf.open(LOGO_SRC)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi, alpha=True)
    img = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
    bbox = img.split()[3].getbbox()
    if bbox is None:
        raise SystemExit("Logo source contains no visible ink.")
    return img.crop(bbox)


def split_wordmark(img: Image.Image) -> tuple[Image.Image, Image.Image]:
    """Split the master into the 'DME' block and the 'INNOVATION' baseline."""
    alpha = img.split()[3]
    width, height = img.size
    row_has_ink = [
        any(alpha.getpixel((x, y)) > 20 for x in range(0, width, 3))
        for y in range(height)
    ]
    # Largest empty horizontal band = the gap between 'DME' and 'INNOVATION'
    best: tuple[int, int] | None = None
    run: int | None = None
    for y, ink in enumerate(row_has_ink + [True]):
        if not ink:
            run = y if run is None else run
        elif run is not None:
            if best is None or (y - run) > (best[1] - best[0]):
                best = (run, y)
            run = None
    if best is None:
        return img, img
    dme = img.crop((0, 0, width, best[0]))
    dme = dme.crop(dme.split()[3].getbbox())
    tagline = img.crop((0, best[1], width, height))
    tagline = tagline.crop(tagline.split()[3].getbbox())
    return dme, tagline


def recolour(img: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
    """Keep the alpha channel, replace the ink colour."""
    solid = Image.new("RGBA", img.size, rgb + (255,))
    solid.putalpha(img.split()[3])
    return solid


def fit(img: Image.Image, box: tuple[int, int]) -> Image.Image:
    """Scale (preserving aspect) so the image fits inside box."""
    bw, bh = box
    scale = min(bw / img.width, bh / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    return img.resize(size, Image.LANCZOS)


def scale_to_height(img: Image.Image, height: int) -> Image.Image:
    width = max(1, round(img.width * height / img.height))
    return img.resize((width, height), Image.LANCZOS)


def make_icon(dme: Image.Image, size: int) -> Image.Image:
    """Amber tile with the black DME mark — the application icon."""
    tile = Image.new("RGBA", (size, size), AMBER + (255,))
    # Tighter margins on tiny sizes so the mark stays readable
    margin = 0.06 if size <= 24 else 0.11
    inner = (round(size * (1 - 2 * margin)), round(size * (1 - 2 * margin)))
    mark = fit(recolour(dme, BLACK), inner)
    tile.alpha_composite(mark, ((size - mark.width) // 2, (size - mark.height) // 2))
    return tile


def png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def b64_block(data: bytes, indent: str = "    ") -> str:
    """Format bytes as an indented, wrapped Python string-concatenation block."""
    encoded = base64.b64encode(data).decode("ascii")
    lines = textwrap.wrap(encoded, 76)
    return "\n".join(f'{indent}"{line}"' for line in lines)


def patch_source(blobs: dict[str, bytes], check_only: bool = False) -> bool:
    """Replace the NAME = ( ... ) base64 literals inside dme_brand.py."""
    source = BRAND_PY.read_text(encoding="utf-8")
    updated = source
    for name, data in blobs.items():
        pattern = re.compile(rf"^{name} = \(\n.*?^\)$", re.DOTALL | re.MULTILINE)
        if not pattern.search(updated):
            raise SystemExit(f"Could not find the {name} block in {BRAND_PY.name}")
        replacement = f"{name} = (\n{b64_block(data)}\n)"
        updated = pattern.sub(lambda _m, r=replacement: r, updated, count=1)
    if updated == source:
        print("dme_brand.py already up to date.")
        return False
    if check_only:
        print("OUT OF DATE: dme_brand.py does not match assets/ — re-run without --check")
        return True
    BRAND_PY.write_text(updated, encoding="utf-8")
    print(f"Patched {BRAND_PY.relative_to(ROOT)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="only report whether autotuner_tool.py is up to date")
    args = parser.parse_args()

    if not LOGO_SRC.exists():
        raise SystemExit(f"Missing logo master: {LOGO_SRC}")

    ASSETS.mkdir(parents=True, exist_ok=True)
    master = render_master()
    dme, _tagline = split_wordmark(master)

    # ── Flat asset files (for docs, installers, websites) ───────────────────
    wordmark_black = recolour(scale_to_height(master, 512), BLACK)
    wordmark_white = recolour(scale_to_height(master, 512), (255, 255, 255))
    icon_png = make_icon(dme, 256)

    (ASSETS / "dme-logo-black.png").write_bytes(png_bytes(wordmark_black))
    (ASSETS / "dme-logo-white.png").write_bytes(png_bytes(wordmark_white))
    (ASSETS / "dme-icon.png").write_bytes(png_bytes(icon_png))

    icons = [make_icon(dme, s) for s in ICO_SIZES]
    ico_buf = io.BytesIO()
    icons[-1].save(ico_buf, format="ICO", sizes=[(s, s) for s in ICO_SIZES],
                   append_images=icons[:-1])
    ico_data = ico_buf.getvalue()
    (ASSETS / "dme-icon.ico").write_bytes(ico_data)

    # ── Embedded blobs (keep autotuner_tool.py self-contained) ──────────────
    blobs = {
        "ICON_ICO_B64": ico_data,
        "ICON_PNG_B64": png_bytes(make_icon(dme, 64)),
        "LOGO_WHITE_B64": png_bytes(recolour(scale_to_height(master, 128), OFF_WHITE)),
    }
    header_sizes = []
    for height in HEADER_HEIGHTS:
        wordmark = recolour(scale_to_height(master, height), OFF_WHITE)
        plate = Image.new("RGBA", wordmark.size, HEADER_BG + (255,))
        plate.alpha_composite(wordmark)
        blobs[f"LOGO_HEADER_{height}_B64"] = png_bytes(plate.convert("RGB"))
        header_sizes.append(f"{plate.width}x{plate.height}")

    for path in sorted(ASSETS.glob("dme-*")):
        print(f"  {path.relative_to(ROOT)}  ({path.stat().st_size:,} bytes)")
    print(f"  header wordmark: {', '.join(header_sizes)} px")

    if BRAND_PY.exists():
        changed = patch_source(blobs, check_only=args.check)
        if args.check and changed:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
