"""Make search-invisible pages findable (scans, fold-outs, RPSTL plates).

Finds pages whose extracted text is near-empty but which carry imagery,
renders them, and writes recognized/described text back into the index
prefixed with [OCR] — retrieval bait only; the page IMAGE stays the
authority. Re-run embed_index.py afterwards (old vectors are dropped here).

Engines:
  rapidocr       local ONNX OCR — raw text scrape, fast, free (default)
  vision-ollama  a vision model via Ollama (e.g. qwen2.5-vl on a DGX Spark;
                 set OLLAMA_URL / VISION_MODEL) — transcribes AND describes
                 the figure, much better retrieval quality
  vision-claude  Claude vision via API — highest quality, costs per page

Usage:
  python ingest/ocr_pages.py --limit 20                      # rapidocr
  OLLAMA_URL=http://spark:11434 VISION_MODEL=qwen2.5vl:32b \\
    python ingest/ocr_pages.py --engine vision-ollama
  python ingest/ocr_pages.py --engine vision-claude --manual Electrical-Schematics
"""

import argparse
import base64
import time
import json
import os
import sqlite3
import urllib.request
from pathlib import Path

import fitz

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SERVICE_BAY_DB") or
               REPO_ROOT / "corpus" / "index.sqlite")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen2.5vl:7b")

VISION_PROMPT = (
    "This is a page from a military truck technical manual (FMTV). "
    "Produce text that makes this page findable by search:\n"
    "1. Transcribe ALL visible text: figure number and title, part callouts, "
    "wire/hose labels, table contents, notes.\n"
    "2. Then one short paragraph describing what the figure shows "
    "(component, view type, what connects to what).\n"
    "Output plain text only, no markdown, no commentary."
)


def page_has_imagery(page: fitz.Page) -> bool:
    if page.get_images():
        return True
    return len(page.get_drawings()) > 20


def recognize_rapidocr(ocr, png: bytes) -> str:
    result, _ = ocr(png)
    return " ".join(item[1] for item in result) if result else ""


def recognize_vision_ollama(png: bytes) -> str:
    payload = {
        "model": VISION_MODEL,
        "messages": [{"role": "user", "content": VISION_PROMPT,
                      "images": [base64.b64encode(png).decode()]}],
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read())["message"]["content"]


def recognize_vision_claude(client, png: bytes) -> str:
    r = client.messages.create(
        model="claude-opus-4-8", max_tokens=2000,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
             "media_type": "image/png",
             "data": base64.b64encode(png).decode()}},
            {"type": "text", "text": VISION_PROMPT},
        ]}])
    if r.stop_reason == "refusal":
        return ""
    return "".join(b.text for b in r.content if b.type == "text")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0, help="stop after N pages")
    ap.add_argument("--manual", help="restrict to one manual")
    ap.add_argument("--engine", default="rapidocr",
                    choices=["rapidocr", "vision-ollama", "vision-claude"])
    args = ap.parse_args()

    ocr = claude_client = None
    if args.engine == "rapidocr":
        from rapidocr_onnxruntime import RapidOCR
        ocr = RapidOCR()
    elif args.engine == "vision-claude":
        import anthropic
        claude_client = anthropic.Anthropic()

    con = sqlite3.connect(DB_PATH, timeout=60)
    con.execute("PRAGMA journal_mode=WAL")
    q = ("SELECT id, manual, pdf_path, pdf_page FROM pages"
         " WHERE LENGTH(text) < 50 AND text NOT LIKE '[OCR]%'")
    params = []
    if args.manual:
        q += " AND manual = ?"
        params.append(args.manual)
    rows = con.execute(q + " ORDER BY manual, pdf_page", params).fetchall()
    print(f"{len(rows)} candidate pages")

    docs: dict[str, fitz.Document] = {}
    done = skipped = failed = 0
    for pid, manual, path, pg in rows:
        if args.limit and done >= args.limit:
            break
        if path not in docs:
            docs[path] = fitz.open(REPO_ROOT / path)
        page = docs[path][pg]
        if not page_has_imagery(page):
            skipped += 1
            continue
        # cap long edge (vision models max out ~2500px; API rejects >8000)
        long_edge = max(page.rect.width, page.rect.height)
        zoom = min(200 / 72, 2400 / long_edge)
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        png = pix.tobytes("png")
        text = None
        for attempt in range(6):
            try:
                if args.engine == "vision-ollama":
                    text = recognize_vision_ollama(png)
                elif args.engine == "vision-claude":
                    text = recognize_vision_claude(claude_client, png)
                else:
                    text = recognize_rapidocr(ocr, png)
                break
            except Exception as e:
                wait = min(120, 5 * 2 ** attempt)
                print(f"  RETRY {manual} p.{pg} in {wait}s "
                      f"(attempt {attempt + 1}): {str(e)[:100]}", flush=True)
                time.sleep(wait)
        if text is None:
            failed += 1
            print(f"  GIVING UP on {manual} p.{pg} after 6 attempts", flush=True)
            continue
        if len(text.strip()) < 20:
            skipped += 1
            continue
        new_text = "[OCR] " + text.strip()
        old = con.execute("SELECT text FROM pages WHERE id = ?", (pid,)).fetchone()[0]
        con.execute("INSERT INTO pages_fts(pages_fts, rowid, text)"
                    " VALUES ('delete', ?, ?)", (pid, old))
        con.execute("UPDATE pages SET text = ?, kind = 'content' WHERE id = ?",
                    (new_text, pid))
        con.execute("INSERT INTO pages_fts(rowid, text) VALUES (?, ?)",
                    (pid, new_text))
        con.execute("DELETE FROM page_vecs WHERE id = ?", (pid,))
        done += 1
        if done % 25 == 0:
            con.commit()
            print(f"  {done} OCR'd (last: {manual} pdf p.{pg})", flush=True)
    con.commit()
    con.close()
    print(f"done: {done} pages OCR'd, {skipped} skipped, {failed} failed")
    print("run  python ingest/embed_index.py  to add them to semantic search")


if __name__ == "__main__":
    main()
