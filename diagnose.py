"""Diagnostic reasoning over the Tier 1 index — the "brain" layer.

Pipeline per PROJECT_BRIEF.md section 3: retrieval pulls candidate TM pages,
Claude reasons ONLY over that material plus the as-built dossier, output is a
stop-and-report test card with page citations and A-D confidence labels, and
a validation pass checks every citation and numeric claim against the index
before display. The model is never the authority — the page image is.

Usage:
    python diagnose.py "slow air buildup, takes 8 min to reach 120 psi"
    python diagnose.py --intake latest          # diagnose newest sessions/*.json
    python diagnose.py --pages 12 "air dryer purges constantly"

Requires ANTHROPIC_API_KEY (or an `ant auth login` profile).
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

import anthropic

from retrieval import hybrid_search

REPO_ROOT = Path(__file__).resolve().parent
DB_PATH = REPO_ROOT / "corpus" / "index.sqlite"
AS_BUILT = REPO_ROOT / "AS_BUILT_CONFIGURATION.md"
SESSIONS_DIR = REPO_ROOT / "sessions"

from backends import get_config
MODEL = get_config()["claude_model"]

CITE_RE = re.compile(r"\[\[([A-Za-z0-9._-]+)\|(\d+)\]\]")
NUM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:psi|kpa|ft-?lbs?|lb-?ft|n·?m|inches|seconds|minutes|rpm)",
    re.I,
)

SYSTEM = """\
You are the diagnostic reasoning layer of an owner-technician service system \
for a 2003 M1083A1 FMTV truck. You operate under one governing rule, enforced \
by the surrounding pipeline:

THE TECHNICAL MANUAL AND ACTUAL MEASUREMENTS ARE AUTHORITATIVE. YOU ARE ADVISORY.

Rules:
1. Every specification, torque, pressure, procedure step, or safety step you \
state must come from the SOURCE pages provided in the user message. Cite the \
source page inline immediately after the claim using exactly this format: \
[[MANUAL|PDFPAGE]] e.g. [[TM-9-2320-366-20-2|1317]]. Never state a numeric \
spec without a citation. If the provided pages do not contain a needed spec, \
say so explicitly — never fill the gap from your general knowledge.
2. Account for the as-built configuration. This truck deviates from stock; \
any reasoning touching the affected systems must flag the deviation.
3. Output a STOP-AND-REPORT TEST CARD, not a lecture:
   - Working hypotheses, most likely first, each with a confidence label
   - THE ONE NEXT TEST to run: exact gauge/lead placement, test conditions, \
expected values with citations, and what each possible result means
   - What NOT to conclude yet
4. Confidence labels (append to each claim): [A] directly specified by the \
manual pages provided (owner must verify against the page image before \
wrenching); [B] supported by manual pages plus the reported measurements; \
[C] diagnostic inference requiring confirmation; [D] speculation/insufficient \
evidence.
5. Safety steps from the source pages (drain air, chock wheels, cage spring \
brakes) are repeated verbatim in the test card whenever applicable.
6. Every [[MANUAL|PAGE]] citation you write is rendered as a clickable link \
that opens the FULL PAGE IMAGE. For figures, diagrams, schematics, and \
fold-outs, the page image IS the deliverable: when the owner wants a diagram \
and retrieval surfaced its page (source text marked [OCR] means exactly \
this), confidently direct them to open that citation — e.g. "open \
[[TM-9-2320-366-24P-2|247]] — that is Figure 498, the air dryer hose \
routing." Never apologize for being unable to reproduce artwork in text.
Be concise and concrete. A technician reads this next to the truck."""

TIER2_ADDENDUM = """
6. TIER 2 (corroborating, NOT authoritative): you may use web search, \
restricted to military-vehicle forums, to find owners reporting similar \
symptoms. Tier 2 material may ONLY suggest candidate causes, known failure \
patterns, and field experience — never specs, torques, or procedures. Present \
it in a separate section titled "Field reports (Tier 2 — anecdotal)" with the \
thread URL for each item, labeled [T2]. A Tier 2 report can raise or lower a \
hypothesis's rank but can never raise its confidence label above [C]."""


def db() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def retrieve(question: str, k: int) -> list[dict]:
    """Top-k content pages: keyword + semantic, rank-fused (retrieval.py)."""
    return hybrid_search(question, k)


def build_context(pages: list[dict]) -> str:
    blocks = []
    for p in pages:
        head = (f"SOURCE [[{p['manual']}|{p['pdf_page']}]] "
                f"printed p.{p['printed_page'] or '?'}"
                + (f" para {p['paragraph']} {p['paragraph_title'] or ''}" if p['paragraph'] else ""))
        blocks.append(head + "\n" + p["text"].strip())
    return "\n\n=====\n\n".join(blocks)


def load_intake(spec: str) -> str:
    if spec == "latest":
        files = sorted(SESSIONS_DIR.glob("intake-*.json"))
        if not files:
            sys.exit("no intake sessions found in sessions/")
        spec = str(files[-1])
    rec = json.loads(Path(spec).read_text(encoding="utf-8"))
    fields = {k: v for k, v in rec["fields"].items() if v}
    lines = [f"- {k}: {v}" for k, v in fields.items()]
    return "Structured intake report:\n" + "\n".join(lines)


def validate(answer: str, pages: list[dict]) -> list[str]:
    """Citation-existence + number-grounding check (POC-level validation)."""
    problems = []
    provided = {(p["manual"], p["pdf_page"]): p["text"] for p in pages}
    cited_text = ""
    cites = CITE_RE.findall(answer)
    if not cites:
        problems.append("Answer contains no [[MANUAL|PAGE]] citations at all.")
    con = db()
    for manual, page in cites:
        key = (manual, int(page))
        if key in provided:
            cited_text += provided[key]
            continue
        row = con.execute(
            "SELECT text FROM pages WHERE manual = ? AND pdf_page = ?", key
        ).fetchone()
        if row:
            problems.append(f"Citation [[{manual}|{page}]] exists but was NOT "
                            "among the retrieved sources shown to the model.")
            cited_text += row[0]
        else:
            problems.append(f"FABRICATED CITATION: [[{manual}|{page}]] does not "
                            "exist in the index.")
    con.close()
    norm = re.sub(r"[,\s]", "", cited_text.lower())
    for num in set(NUM_RE.findall(answer)):
        if num not in cited_text and num not in norm:
            problems.append(f"Number '{num}' (with a unit) does not appear "
                            "verbatim in any cited page — verify against the "
                            "page image before trusting it.")
    return problems


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question", nargs="?", help="free-text diagnostic question")
    ap.add_argument("--intake", metavar="PATH|latest",
                    help="diagnose a filed intake session instead")
    ap.add_argument("--pages", type=int, default=10,
                    help="how many TM pages to retrieve (default 10)")
    ap.add_argument("--forums", action="store_true",
                    help="also live-search Steel Soldiers for similar cases "
                         "(Tier 2, anecdotal, clearly labeled)")
    args = ap.parse_args()

    if args.intake:
        problem = load_intake(args.intake)
        search_terms = problem
    elif args.question:
        problem = "Diagnostic question: " + args.question
        search_terms = args.question
    else:
        ap.error("give a question or --intake")

    pages = retrieve(search_terms, args.pages)
    if not pages:
        sys.exit("Retrieval found no relevant TM pages — refine the question.")
    print(f"[retrieved {len(pages)} pages: "
          + ", ".join(f"{p['manual'].split('-')[-2]}-{p['manual'].split('-')[-1]}"
                      f" p.{p['printed_page'] or p['pdf_page']}" for p in pages)
          + "]\n", file=sys.stderr)

    user_msg = (
        "AS-BUILT CONFIGURATION (canonical dossier — deviations from stock matter):\n"
        + (AS_BUILT.read_text(encoding="utf-8") if AS_BUILT.exists() else "(no as-built dossier recorded yet)")
        + "\n\n=====\n\nRETRIEVED TIER 1 SOURCE PAGES (your ONLY permitted "
        "source for specs and procedures):\n\n"
        + build_context(pages)
        + "\n\n=====\n\n" + problem
    )

    try:
        client = anthropic.Anthropic()
    except Exception as e:
        sys.exit(f"Anthropic client init failed: {e}")
    system_text = SYSTEM + (TIER2_ADDENDUM if args.forums else "")
    tools = []
    if args.forums:
        tools = [{
            "type": "web_search_20260209",
            "name": "web_search",
            "max_uses": 5,
            "allowed_domains": ["steelsoldiers.com"],
        }]
    messages = [{"role": "user", "content": user_msg}]
    try:
        for _ in range(4):  # pause_turn continuations for server-side search
            with client.messages.stream(
                model=MODEL,
                max_tokens=16000,
                thinking={"type": "adaptive"},
                system=[{"type": "text", "text": system_text,
                         "cache_control": {"type": "ephemeral"}}],
                tools=tools,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    print(text, end="", flush=True)
                response = stream.get_final_message()
            if response.stop_reason != "pause_turn":
                break
            messages = [{"role": "user", "content": user_msg},
                        {"role": "assistant", "content": response.content}]
    except (TypeError, anthropic.AuthenticationError) as e:
        sys.exit(
            "\nNo Anthropic API credentials found. Set the ANTHROPIC_API_KEY "
            "environment variable (get a key at platform.claude.com), then "
            f"re-run.\nDetail: {e}"
        )
    print()

    if response.stop_reason == "refusal":
        sys.exit("\n[model declined this request — no diagnostic produced]")

    answer = "".join(b.text for b in response.content if b.type == "text")
    problems = validate(answer, pages)
    print("\n--- VALIDATION ---")
    if problems:
        for p in problems:
            print(f"  ⚠ {p}")
    else:
        print("  all citations exist in the index and all unit-bearing numbers "
              "appear in cited pages")
    print("  Reminder: verify every [A] spec against the page image "
          "(python ingest/render_page.py MANUAL PDFPAGE) before wrenching.")


if __name__ == "__main__":
    main()
