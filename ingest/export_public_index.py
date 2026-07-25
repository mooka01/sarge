"""Export a redistributable index containing ONLY public-domain manuals.

US Army TMs are US-government works (public domain); Cat, Allison, WABCO and
other factory documents are copyrighted and are excluded from the export.
The result ships as a release asset so new users get working search without
re-ingesting — page images still require the PDFs (bootstrap_fmtv.py).

Usage:  python ingest/export_public_index.py
Output: dist/fmtv-tm-index.sqlite
"""

import argparse
import sqlite3
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# public-domain = US Army TM series only (covers -365 LMTV and -366 MTV)
#
# This prefix does double duty and both jobs must keep holding:
#   1. copyright — US Army TMs are US-government works; Cat/Allison/WABCO are not
#   2. distribution — every manual it admits is Distribution Statement A,
#      approved for public release, so redistribution is also export-clean
# It is a name whitelist, not a marking check. Before widening it (or before
# ingesting a TB/MWO that happens to be numbered in the -365/-366 family),
# confirm the cover page carries Distribution Statement A with no export
# warning. Restricted material must never reach a release asset.
PUBLIC_PREFIX = "TM-9-2320-36%"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=str(REPO_ROOT / "corpus" / "index.sqlite"))
    ap.add_argument("--out", default=str(REPO_ROOT / "dist" / "fmtv-tm-index.sqlite"))
    args = ap.parse_args()
    global SRC, DEST
    SRC, DEST = Path(args.db), Path(args.out)
    DEST.parent.mkdir(exist_ok=True)
    if DEST.exists():
        DEST.unlink()
    src = sqlite3.connect(SRC)
    dst = sqlite3.connect(DEST)
    dst.executescript(
        """
        CREATE TABLE pages (
            id INTEGER PRIMARY KEY, manual TEXT NOT NULL, pdf_path TEXT NOT NULL,
            pdf_page INTEGER NOT NULL, printed_page TEXT, paragraph TEXT,
            paragraph_title TEXT, kind TEXT NOT NULL DEFAULT 'content',
            tier INTEGER NOT NULL DEFAULT 1, text TEXT NOT NULL,
            UNIQUE (manual, pdf_page)
        );
        CREATE VIRTUAL TABLE pages_fts USING fts5(
            text, content=pages, content_rowid=id, tokenize='porter unicode61'
        );
        CREATE TRIGGER pages_ai AFTER INSERT ON pages BEGIN
            INSERT INTO pages_fts(rowid, text) VALUES (new.id, new.text);
        END;
        CREATE TRIGGER pages_ad AFTER DELETE ON pages BEGIN
            INSERT INTO pages_fts(pages_fts, rowid, text)
                VALUES ('delete', old.id, old.text);
        END;
        CREATE TABLE page_vecs (
            id INTEGER PRIMARY KEY REFERENCES pages(id), vec BLOB NOT NULL
        );
        """
    )
    rows = src.execute(
        "SELECT id, manual, pdf_path, pdf_page, printed_page, paragraph,"
        " paragraph_title, kind, tier, text FROM pages WHERE manual LIKE ?",
        (PUBLIC_PREFIX,),
    ).fetchall()
    dst.executemany(
        "INSERT INTO pages (id, manual, pdf_path, pdf_page, printed_page,"
        " paragraph, paragraph_title, kind, tier, text)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    ids = [r[0] for r in rows]
    for start in range(0, len(ids), 500):
        chunk = ids[start:start + 500]
        vec_rows = src.execute(
            f"SELECT id, vec FROM page_vecs WHERE id IN "
            f"({','.join('?' * len(chunk))})", chunk).fetchall()
        dst.executemany("INSERT INTO page_vecs (id, vec) VALUES (?, ?)",
                        vec_rows)
    dst.commit()
    n_pages = dst.execute("SELECT COUNT(*) FROM pages").fetchone()[0]
    n_vecs = dst.execute("SELECT COUNT(*) FROM page_vecs").fetchone()[0]
    manuals = [r[0] for r in dst.execute(
        "SELECT DISTINCT manual FROM pages ORDER BY manual")]
    dst.execute("VACUUM")
    dst.close()
    src.close()
    mb = DEST.stat().st_size / 1_000_000
    print(f"exported {n_pages} pages / {n_vecs} vectors from "
          f"{len(manuals)} public-domain manuals -> {DEST} ({mb:.0f} MB)")
    for m in manuals:
        print("  ", m)


if __name__ == "__main__":
    main()
