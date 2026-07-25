"""Cloud vs local vision accuracy eval — measured, not vibes.

Takes pages that HAVE clean digital text layers (ground truth), renders them
to images, runs each vision engine on the image, and scores recognized text
against the truth. Reports overall token recall and — more important for a
spec-critical system — numeric-token recall. Run before committing to a
batch engine; accuracy beats cost.

Usage:
  python ingest/ocr_eval.py --engines vision-claude vision-ollama:qwen3-vl:32b
  OLLAMA_URL=http://spark:11434 python ingest/ocr_eval.py \
      --engines vision-ollama:qwen3-vl:32b vision-ollama:qwen3-vl:8b-instruct
"""

import argparse
import os
import re
import sqlite3
import time
from pathlib import Path

import fitz

import ocr_pages  # engine functions + prompt

REPO_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("SERVICE_BAY_DB") or
               REPO_ROOT / "corpus" / "index.sqlite")

# deterministic, diverse sample: (manual, pdf_page) picked for dense text,
# tables of numbers, and procedure steps
SAMPLE = [
    ("TM-9-2320-366-20-1", 97),      # air system w/ governor pressures
    ("TM-9-2320-366-20-2", 1317),    # troubleshooting tree w/ psi values
    ("TM-9-2320-366-20-4", 601),     # wheel bearing/CTIS seal procedure
    ("Cat-RENR1367-3126-Troubleshooting", 118),  # flash-code page
    ("WABCO-ABS-ESC-MM0112", 40),    # ABS component page
]

TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9./-]{2,}")
NUM_RE = re.compile(r"\d")


def tokens(text: str) -> set[str]:
    return {t.upper() for t in TOKEN_RE.findall(text)}


def score(truth: str, recognized: str) -> tuple[float, float, int]:
    t, r = tokens(truth), tokens(recognized)
    if not t:
        return 0.0, 0.0, 0
    nums = {x for x in t if NUM_RE.search(x)}
    recall = len(t & r) / len(t)
    num_recall = len(nums & r) / len(nums) if nums else 1.0
    return recall, num_recall, len(t)


def run_engine(engine: str, png: bytes, claude_client) -> str:
    if engine == "vision-claude":
        return ocr_pages.recognize_vision_claude(claude_client, png)
    if engine.startswith("vision-ollama:"):
        ocr_pages.VISION_MODEL = engine.split(":", 1)[1]
        return ocr_pages.recognize_vision_ollama(png)
    if engine == "rapidocr":
        from rapidocr_onnxruntime import RapidOCR
        if not hasattr(run_engine, "_ocr"):
            run_engine._ocr = RapidOCR()
        return ocr_pages.recognize_rapidocr(run_engine._ocr, png)
    raise ValueError(engine)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--engines", nargs="+", required=True,
                    help="vision-claude | rapidocr | vision-ollama:<model>")
    args = ap.parse_args()

    claude_client = None
    if "vision-claude" in args.engines:
        import anthropic
        claude_client = anthropic.Anthropic()

    con = sqlite3.connect(DB_PATH)
    pages = []
    for manual, pg in SAMPLE:
        row = con.execute(
            "SELECT pdf_path, text FROM pages WHERE manual = ? AND pdf_page = ?",
            (manual, pg)).fetchone()
        if row:
            pages.append((manual, pg, row[0], row[1]))
    con.close()
    print(f"{len(pages)} ground-truth pages\n")

    results: dict[str, list] = {e: [] for e in args.engines}
    for manual, pg, pdf_path, truth in pages:
        doc = fitz.open(REPO_ROOT / pdf_path)
        page = doc[pg]
        long_edge = max(page.rect.width, page.rect.height)
        zoom = min(200 / 72, 2400 / long_edge)
        png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
        print(f"--- {manual} pdf p.{pg}")
        for eng in args.engines:
            t0 = time.monotonic()
            try:
                out = run_engine(eng, png, claude_client)
                rec, num_rec, n = score(truth, out)
                dt = time.monotonic() - t0
                results[eng].append((rec, num_rec, dt))
                print(f"    {eng:38} recall {rec:5.0%}  numbers {num_rec:5.0%}"
                      f"  ({dt:5.1f}s, {n} truth tokens)")
            except Exception as e:
                results[eng].append(None)
                print(f"    {eng:38} FAILED: {str(e)[:80]}")

    print(f"\n{'=' * 72}\nAVERAGES")
    for eng, rs in results.items():
        ok = [r for r in rs if r]
        if not ok:
            print(f"  {eng:38} all failed")
            continue
        rec = sum(r[0] for r in ok) / len(ok)
        num = sum(r[1] for r in ok) / len(ok)
        dt = sum(r[2] for r in ok) / len(ok)
        print(f"  {eng:38} recall {rec:5.0%}  numbers {num:5.0%}  avg {dt:.0f}s"
              f"  ({len(ok)}/{len(rs)} pages)")
    print("\nNumbers-recall is the safety-relevant column: it is how reliably "
          "spec values on image pages would become findable.")


if __name__ == "__main__":
    main()
