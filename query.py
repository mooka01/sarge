"""Search the Tier 1 TM index.

Every hit reports manual number, printed page, governing paragraph, and the
command to render the actual page image — the image, not this text, is the
authority for any numeric value (PROJECT_BRIEF.md governing rule).

Usage:
    python query.py "governor cutout pressure"
    python query.py --manual TM-9-2320-366-20-5 "air compressor"
    python query.py --all "warning summary"      # include non-content pages
    python query.py --show TM-9-2320-366-20-5:412   # dump one page's text
"""

import argparse
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "corpus" / "index.sqlite"


def fts_query(terms: str, any_word: bool = False) -> str:
    """Quote each word so FTS5 syntax characters can't break the query."""
    words = re.findall(r"[A-Za-z0-9-]+", terms)
    joiner = " OR " if any_word else " "
    return joiner.join(f'"{w}"' for w in words)


def search(args: argparse.Namespace) -> None:
    con = sqlite3.connect(DB_PATH)
    sql = """
        SELECT p.manual, p.pdf_page, p.printed_page, p.paragraph,
               p.paragraph_title, p.kind,
               snippet(pages_fts, 0, '>>', '<<', ' ... ', 24)
        FROM pages_fts f JOIN pages p ON p.id = f.rowid
        WHERE pages_fts MATCH ?
    """
    params: list = [fts_query(args.terms)]
    if not args.all:
        sql += " AND p.kind = 'content'"
    if args.manual:
        sql += " AND p.manual = ?"
        params.append(args.manual)
    sql += " ORDER BY rank LIMIT ?"
    params.append(args.limit)

    rows = con.execute(sql, params).fetchall()
    if not rows:
        # Fall back to any-word matching; BM25 rank still puts pages
        # containing most of the terms first.
        params[0] = fts_query(args.terms, any_word=True)
        rows = con.execute(sql, params).fetchall()
        if rows:
            print("(no page matched every term; showing best partial matches)\n")
    con.close()
    if not rows:
        print("No hits. (Non-content pages are excluded by default; try --all.)")
        return
    for manual, pdf_page, printed, para, title, kind, snip in rows:
        loc = f"{manual}  printed p.{printed or '?'}  (pdf page {pdf_page})"
        if para:
            loc += f"  para {para} {title or ''}"
        if kind != "content":
            loc += f"  [{kind}]"
        print(loc)
        print(f"  {' '.join(snip.split())}")
        print(f"  image: python ingest/render_page.py {manual} {pdf_page}")
        print()


def show(spec: str) -> None:
    manual, _, page = spec.rpartition(":")
    con = sqlite3.connect(DB_PATH)
    row = con.execute(
        "SELECT printed_page, paragraph, paragraph_title, text FROM pages"
        " WHERE manual = ? AND pdf_page = ?",
        (manual, int(page)),
    ).fetchone()
    con.close()
    if not row:
        sys.exit(f"no page {page} in {manual}")
    printed, para, title, text = row
    print(f"{manual}  printed p.{printed}  para {para} {title}\n")
    print(text)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("terms", nargs="?", help="search terms")
    ap.add_argument("--manual", help="restrict to one manual")
    ap.add_argument("--limit", type=int, default=8)
    ap.add_argument("--all", action="store_true",
                    help="include blank/TOC/front-matter pages")
    ap.add_argument("--show", metavar="MANUAL:PDFPAGE",
                    help="print full text of one page")
    args = ap.parse_args()
    if args.show:
        show(args.show)
    elif args.terms:
        search(args)
    else:
        ap.error("give search terms or --show")


if __name__ == "__main__":
    main()
