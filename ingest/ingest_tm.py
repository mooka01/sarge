"""Ingest a TM PDF into the Tier 1 index.

Extracts per-page text and metadata (manual number, PDF page, printed page
number, governing paragraph heading) into SQLite with an FTS5 keyword index.
Page images are NOT pre-rendered; render_page.py rasterizes on demand from
the source PDF, which stays the numeric authority per PROJECT_BRIEF.md.

Usage:
    python ingest/ingest_tm.py corpus/raw/TM-9-2320-366-20-5.pdf
    python ingest/ingest_tm.py corpus/raw/*.pdf
"""

import re
import os
import sqlite3
import sys
from pathlib import Path

import fitz  # PyMuPDF

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SERVICE_BAY_DB") or
               REPO_ROOT / "corpus" / "index.sqlite")

# Paragraph headings look like "23-4.  AIR GOVERNOR REPLACEMENT" at the
# start of a line. This TM uses chapter-paragraph numbering, not WP numbers.
PARA_RE = re.compile(r"^\s*(\d{1,2}-\d+(?:\.\d+)?)\.\s+([A-Z][A-Z0-9 /,()&.'-]{3,})\s*$", re.M)

# Dotted leader lines ("Air System . . . . . . 1-44") mark TOC/index pages.
LEADER_RE = re.compile(r"(?:\.\s?){6,}")

# Printed page numbers appear in the footer: "2-1976", "23-5", "A-7", "ix",
# optionally with a change notice like "Change 1  2-1976".
PRINTED_PAGE_RE = re.compile(
    r"^(?:Change\s+\d+\s+)?((?:[A-Z]|\d{1,2})-\d+(?:\.\d+)?|[ivxlc]+)(?:\s+Change\s+\d+)?$",
    re.I,
)


def printed_page_of(page: fitz.Page) -> str | None:
    """Find the printed page label from text near the bottom of the page."""
    bottom = page.rect.height * 0.90
    candidates = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if y0 < bottom:
            continue
        for line in text.splitlines():
            m = PRINTED_PAGE_RE.match(line.strip())
            if m:
                candidates.append((y0, m.group(1)))
    if candidates:
        return max(candidates)[1]  # lowest block on the page wins
    return None


def classify(text: str) -> str:
    """Tag non-substantive pages so search can rank real content first.

    Nothing is removed — the page image always shows the full page including
    warnings. This only keeps front matter from burying procedure/spec pages.
    """
    stripped = text.strip()
    if len(stripped) < 40 or "INTENTIONALLY LEFT BLANK" in stripped:
        return "blank"
    head = stripped[:400]
    if "WARNING SUMMARY" in head:
        return "warning-summary"
    if re.search(r"(?i)change sheet|LIST OF EFFECTIVE PAGES", head):
        return "front-matter"
    lines = stripped.splitlines()
    leader_lines = sum(1 for l in lines if LEADER_RE.search(l))
    if lines and leader_lines / len(lines) > 0.35:
        return "toc-index"
    return "content"


def ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS pages (
            id INTEGER PRIMARY KEY,
            manual TEXT NOT NULL,          -- e.g. TM-9-2320-366-20-5
            pdf_path TEXT NOT NULL,        -- source PDF, repo-relative
            pdf_page INTEGER NOT NULL,     -- 0-based page index in the PDF
            printed_page TEXT,             -- page label as printed, e.g. 23-5
            paragraph TEXT,                -- governing paragraph, e.g. 23-4
            paragraph_title TEXT,          -- e.g. AIR GOVERNOR REPLACEMENT
            kind TEXT NOT NULL DEFAULT 'content',  -- content | blank | toc-index | warning-summary | front-matter
            domain TEXT NOT NULL DEFAULT 'chassis',  -- chassis | habitat | shared
            tier INTEGER NOT NULL DEFAULT 1,
            text TEXT NOT NULL,
            UNIQUE (manual, pdf_page)
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS pages_fts USING fts5(
            text, content=pages, content_rowid=id, tokenize='porter unicode61'
        );
        CREATE TRIGGER IF NOT EXISTS pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, text) VALUES (new.id, new.text);
        END;
        CREATE TRIGGER IF NOT EXISTS pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, text)
                VALUES ('delete', old.id, old.text);
        END;
        """
    )


def ingest(pdf_path: Path, con: sqlite3.Connection, domain: str = "chassis") -> int:
    manual = pdf_path.stem
    rel = pdf_path.resolve().relative_to(REPO_ROOT).as_posix()
    doc = fitz.open(pdf_path)

    con.execute("DELETE FROM pages WHERE manual = ?", (manual,))

    para, para_title = None, None
    n = 0
    for i, page in enumerate(doc):
        text = page.get_text()
        # Track the governing paragraph: last heading seen on or before this
        # page. A page with multiple headings is governed by its last one for
        # carry-forward, first-heading pages still match via full text search.
        headings = PARA_RE.findall(text)
        if headings:
            para, para_title = headings[-1][0], headings[-1][1].strip()
        con.execute(
            "INSERT INTO pages (manual, pdf_path, pdf_page, printed_page,"
            " paragraph, paragraph_title, kind, domain, tier, text)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (manual, rel, i, printed_page_of(page), para, para_title,
             classify(text), domain, text),
        )
        n += 1
        if i % 250 == 0:
            print(f"  {manual}: page {i}/{doc.page_count}", flush=True)
    return n


def main() -> None:
    args = [a for a in sys.argv[1:]]
    domain = "chassis"
    if "--domain" in args:
        i = args.index("--domain")
        domain = args[i + 1]
        del args[i:i + 2]
    if not args:
        sys.exit(__doc__)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    ensure_schema(con)
    for arg in args:
        pdf = Path(arg)
        print(f"Ingesting {pdf.name} ({domain}) ...", flush=True)
        n = ingest(pdf, con, domain)
        con.commit()
        print(f"  done: {n} pages")
    con.close()


if __name__ == "__main__":
    main()
