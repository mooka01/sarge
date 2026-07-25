"""Render a TM page image on demand from the source PDF.

The rendered image of the actual manual page is the display authority for
numeric specs (PROJECT_BRIEF.md section 3.2). Images are rasterized lazily
from the PDF and cached under corpus/pagecache/.

Usage:
    python ingest/render_page.py TM-9-2320-366-20-5 412        # by PDF page
    python ingest/render_page.py TM-9-2320-366-20-5 --printed 23-5
Prints the path of the rendered PNG.
"""

import argparse
import sqlite3
import sys
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = REPO_ROOT / "corpus" / "index.sqlite"
CACHE_DIR = REPO_ROOT / "corpus" / "pagecache"
DPI = 150


def render(manual: str, pdf_page: int) -> Path:
    out = CACHE_DIR / manual / f"p{pdf_page:04d}.png"
    if out.exists():
        return out
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT pdf_path FROM pages WHERE manual = ? AND pdf_page = ?",
        (manual, pdf_page),
    ).fetchone()
    con.close()
    if not row:
        sys.exit(f"No indexed page {pdf_page} in {manual}")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(REPO_ROOT / row[0])
    doc[pdf_page].get_pixmap(dpi=DPI).save(out)
    return out


def resolve_printed(manual: str, printed: str) -> int:
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT pdf_page FROM pages WHERE manual = ? AND printed_page = ?",
        (manual, printed),
    ).fetchall()
    con.close()
    if not rows:
        sys.exit(f"No page printed '{printed}' in {manual}")
    if len(rows) > 1:
        print(f"note: {len(rows)} pages carry label {printed}; using first",
              file=sys.stderr)
    return rows[0][0]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("manual")
    ap.add_argument("pdf_page", nargs="?", type=int)
    ap.add_argument("--printed", help="printed page label, e.g. 23-5")
    args = ap.parse_args()
    if args.printed is not None:
        page = resolve_printed(args.manual, args.printed)
    elif args.pdf_page is not None:
        page = args.pdf_page
    else:
        ap.error("give a PDF page number or --printed label")
    print(render(args.manual, page))


if __name__ == "__main__":
    main()
