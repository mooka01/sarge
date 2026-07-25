"""A/B compare backends on the same diagnostic question.

Identical retrieval, identical grounding prompt, identical validation —
only the model differs. Prints both answers with timing and validation
results so quality can be judged fairly.

Usage:
    python compare.py "slow air buildup, 8 minutes to 120 psi"
    python compare.py --pages 8 --ollama-model llama3.1:8b "governor cut-out spec"
"""

import argparse
import sys

import backends
import diagnose as dx


def run(backend: str, system: str, user_msg: str, pages, model=None):
    print(f"\n{'=' * 70}\n### {backend.upper()}\n{'=' * 70}", flush=True)
    try:
        text, meta = backends.chat(
            backend, system, [{"role": "user", "content": user_msg}],
            on_text=lambda t: print(t, end="", flush=True), model=model)
    except Exception as e:
        print(f"[{backend} failed: {e}]")
        return None
    print()
    problems = dx.validate(text, pages)
    print(f"\n--- validation ({meta['backend']}, {meta['seconds']}s, "
          f"{meta['output_tokens']} tokens) ---")
    if problems:
        for p in problems:
            print(f"  X {p}")
    else:
        print("  ok: citations exist, numbers grounded")
    return {"meta": meta, "problems": problems, "chars": len(text)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("question")
    ap.add_argument("--pages", type=int, default=8)
    ap.add_argument("--ollama-model", default=None)
    args = ap.parse_args()

    pages = dx.retrieve(args.question, args.pages)
    if not pages:
        sys.exit("no pages retrieved")
    print(f"[retrieved {len(pages)} pages — identical context for both models]")

    user_msg = (
        "AS-BUILT CONFIGURATION (canonical dossier):\n"
        + dx.AS_BUILT.read_text(encoding="utf-8")
        + "\n\n=====\n\nRETRIEVED TIER 1 SOURCE PAGES (your ONLY permitted "
        "source for specs and procedures):\n\n" + dx.build_context(pages)
        + "\n\n=====\n\nDiagnostic question: " + args.question
    )

    results = {}
    results["claude"] = run("claude", dx.SYSTEM, user_msg, pages)
    results["ollama"] = run("ollama", dx.SYSTEM, user_msg, pages,
                            model=args.ollama_model)

    print(f"\n{'=' * 70}\n### SCORECARD\n{'=' * 70}")
    print(f"{'':14} {'time':>8} {'tokens':>8} {'validation issues':>18} {'length':>8}")
    for name, r in results.items():
        if r is None:
            print(f"{name:14} {'failed':>8}")
            continue
        print(f"{name:14} {r['meta']['seconds']:>7}s {r['meta']['output_tokens']:>8} "
              f"{len(r['problems']):>18} {r['chars']:>8}")
    print("\nJudge for yourself: correctness of the cited pages, honesty about "
          "missing specs, and as-built awareness matter more than speed.")


if __name__ == "__main__":
    main()
