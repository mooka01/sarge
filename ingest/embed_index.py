"""Embed all content pages for semantic retrieval.

Uses fastembed (BAAI/bge-small-en-v1.5, 384-dim, ONNX on CPU — no GPU/torch).
Vectors are stored as float32 blobs in a page_vecs table keyed to pages.id;
query-time search is brute-force cosine over ~16k vectors (milliseconds).

Usage:  python ingest/embed_index.py        # embeds pages missing a vector
"""

import os
import sqlite3
from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SERVICE_BAY_DB") or
               REPO_ROOT / "corpus" / "index.sqlite")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
BATCH = 64


def page_repr(manual, para, title, text) -> str:
    head = f"{manual}" + (f" para {para} {title}" if para else "")
    return head + "\n" + text[:2000]


def main() -> None:
    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute(
        "CREATE TABLE IF NOT EXISTS page_vecs ("
        " id INTEGER PRIMARY KEY REFERENCES pages(id), vec BLOB NOT NULL)"
    )
    rows = con.execute(
        "SELECT p.id, p.manual, p.paragraph, p.paragraph_title, p.text"
        " FROM pages p LEFT JOIN page_vecs v ON v.id = p.id"
        " WHERE p.kind = 'content' AND v.id IS NULL"
    ).fetchall()
    if not rows:
        print("nothing to embed — up to date")
        return
    print(f"embedding {len(rows)} pages with {MODEL_NAME} ...")
    model = TextEmbedding(MODEL_NAME)
    for start in range(0, len(rows), BATCH):
        chunk = rows[start:start + BATCH]
        texts = [page_repr(m, p, t, x) for _, m, p, t, x in chunk]
        vecs = list(model.embed(texts))
        con.executemany(
            "INSERT OR REPLACE INTO page_vecs (id, vec) VALUES (?, ?)",
            [(row[0], np.asarray(v, dtype=np.float32).tobytes())
             for row, v in zip(chunk, vecs)],
        )
        con.commit()
        if (start // BATCH) % 20 == 0:
            print(f"  {start + len(chunk)}/{len(rows)}", flush=True)
    print(f"done: {len(rows)} pages embedded")
    con.close()


if __name__ == "__main__":
    main()
