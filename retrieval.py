"""Shared retrieval over the Tier 1 index: keyword (FTS5), semantic
(fastembed vectors), and hybrid (reciprocal rank fusion of both).

Used by diagnose.py and app.py. Semantic search degrades gracefully: if the
page_vecs table is missing/empty or fastembed isn't installed, hybrid()
silently falls back to keyword-only.
"""

import re
import sqlite3
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "corpus" / "index.sqlite"
MODEL_NAME = "BAAI/bge-small-en-v1.5"

PAGE_KEYS = ("manual", "pdf_page", "printed_page", "paragraph",
             "paragraph_title", "text")
_SELECT = ("SELECT p.manual, p.pdf_page, p.printed_page, p.paragraph,"
           " p.paragraph_title, p.text, p.id")


def _db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def fts_query(terms: str, any_word: bool = False) -> str:
    words = re.findall(r"[A-Za-z0-9-]+", terms)
    joiner = " OR " if any_word else " "
    return joiner.join(f'"{w}"' for w in words)


def _rows_to_pages(rows) -> list[dict]:
    return [dict(zip(PAGE_KEYS, r[:6]), id=r[6]) for r in rows]


def _domain_clause(domains):
    if not domains:
        return "", []
    return (" AND p.domain IN (" + ",".join("?" * len(domains)) + ")",
            list(domains))


def keyword_search(question: str, k: int, domains=None) -> list[dict]:
    con = _db()
    dc, dparams = _domain_clause(domains)
    sql = (_SELECT + " FROM pages_fts f JOIN pages p ON p.id = f.rowid"
           " WHERE pages_fts MATCH ? AND p.kind = 'content'" + dc +
           " ORDER BY rank LIMIT ?")
    rows = con.execute(sql, (fts_query(question), *dparams, k)).fetchall()
    if len(rows) < k:
        seen = {r[6] for r in rows}
        extra = con.execute(sql, (fts_query(question, any_word=True),
                                  *dparams, k)).fetchall()
        rows += [r for r in extra if r[6] not in seen][: k - len(rows)]
    con.close()
    return _rows_to_pages(rows)


@lru_cache(maxsize=1)
def _vectors():
    """Load (ids, matrix) once per process; None if unavailable."""
    try:
        import numpy as np
        con = _db()
        rows = con.execute("SELECT id, vec FROM page_vecs").fetchall()
        con.close()
        if not rows:
            return None
        ids = [r[0] for r in rows]
        mat = np.frombuffer(b"".join(r[1] for r in rows), dtype=np.float32)
        mat = mat.reshape(len(ids), -1)
        mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
        return ids, mat
    except Exception:
        return None


@lru_cache(maxsize=1)
def _embedder():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL_NAME)


def semantic_search(question: str, k: int, domains=None) -> list[dict]:
    import numpy as np
    loaded = _vectors()
    if loaded is None:
        return []
    ids, mat = loaded
    q = np.asarray(next(iter(_embedder().embed([question]))), dtype=np.float32)
    q = q / (np.linalg.norm(q) + 1e-9)
    top = np.argsort(mat @ q)[::-1][:k]
    id_list = [ids[i] for i in top]
    con = _db()
    dc, dparams = _domain_clause(domains)
    rows = con.execute(
        _SELECT + f" FROM pages p WHERE p.id IN ({','.join('?' * len(id_list))})"
        + dc, id_list + dparams,
    ).fetchall()
    con.close()
    by_id = {r[6]: r for r in rows}
    return _rows_to_pages([by_id[i] for i in id_list if i in by_id])


def hybrid_search(question: str, k: int, domains=None) -> list[dict]:
    """Reciprocal rank fusion of keyword and semantic rankings."""
    kw = keyword_search(question, k, domains)
    try:
        sem = semantic_search(question, k * 2, domains)[:k]
    except Exception:
        sem = []
    scores: dict[int, float] = {}
    pages: dict[int, dict] = {}
    for ranking in (kw, sem):
        for rank, p in enumerate(ranking):
            scores[p["id"]] = scores.get(p["id"], 0.0) + 1.0 / (60 + rank)
            pages[p["id"]] = p
    ordered = sorted(scores, key=scores.get, reverse=True)[:k]
    return [pages[i] for i in ordered]
