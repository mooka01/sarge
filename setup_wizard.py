"""SARGE first-run wizard — plain questions, no software knowledge needed.

Run via setup.bat (Windows) or  python setup_wizard.py  directly.
"""

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RELEASE = "https://github.com/mooka01/sarge/releases/download/v0.1"
INDEXES = {"mtv": "fmtv-tm-index.sqlite", "lmtv": "lmtv-tm-index.sqlite"}


def ask(prompt, choices=None, default=None):
    while True:
        raw = input(prompt + " ").strip()
        if not raw and default is not None:
            return default
        if choices is None and raw:
            return raw
        if choices and raw.lower() in choices:
            return raw.lower()
        print("  (please answer: " + "/".join(choices or []) + ")")


def download(url, dest, label):
    print(f"  downloading {label} ...", flush=True)
    tmp = dest.with_suffix(".part")

    def hook(n, size, total):
        if total > 0 and n % 50 == 0:
            print(f"\r  {n * size * 100 // total}%", end="", flush=True)
    urllib.request.urlretrieve(url, tmp, reporthook=hook)
    print("\r  done          ")
    tmp.replace(dest)


def main():
    print()
    print("=" * 60)
    print("  SARGE setup — Search-Augmented Retrieval, Grounded Evidence")
    print("=" * 60)
    print()

    # 1. variant
    print("Which truck do you have?")
    print("  1) MTV  — 6x6, 5-ton  (M1083/M1084/M1085... series)")
    print("  2) LMTV — 4x4, 2.5-ton (M1078/M1079... series)")
    v = ask("Enter 1 or 2 [1]:", choices=["1", "2"], default="1")
    variant = "mtv" if v == "1" else "lmtv"

    # 2. instant search index (small download)
    idx = ROOT / "corpus" / "index.sqlite"
    idx.parent.mkdir(parents=True, exist_ok=True)
    if idx.exists():
        print("\nAn index already exists — keeping it.")
    else:
        print("\nGetting the prebuilt manual search index (about 60 MB)...")
        try:
            download(f"{RELEASE}/{INDEXES[variant]}", idx, "search index")
            print("Search is ready.")
        except Exception as e:
            print(f"  couldn't download the prebuilt index ({e}).")
            print("  Search will be empty until you run: python bootstrap_fmtv.py")

    # 3. page images (the big TM download) — offer, don't force
    print("\nSARGE shows the actual manual page image for every answer.")
    print("That needs the TM PDFs (~1.3 GB download, can run while you try SARGE).")
    if ask("Download them now? (y/n) [y]:", choices=["y", "n"], default="y") == "y":
        args = [sys.executable, str(ROOT / "bootstrap_fmtv.py")]
        if variant == "lmtv":
            args += ["--variant", "lmtv"]
        print("  (this runs in this window; go get coffee)")
        subprocess.run(args)
    else:
        print("  Skipped. Run bootstrap_fmtv.py later — page-image links will "
              "explain what's missing until then.")

    # 4. AI key
    print("\nFor AI diagnosis you need a Claude API key (platform.claude.com,")
    print("a few cents per diagnosis). Search works fine without one.")
    key = ask("Paste your key (or press Enter to skip):", default="")
    if key.startswith("sk-ant-"):
        subprocess.run(["setx", "ANTHROPIC_API_KEY", key],
                       capture_output=True)
        os.environ["ANTHROPIC_API_KEY"] = key
        print("  saved.")
    elif key:
        print("  that doesn't look like a key (should start sk-ant-) — skipped.")

    # 5. done
    print()
    print("=" * 60)
    print("  Setup complete.")
    print("  Start SARGE any time by double-clicking  run.bat")
    print("  Then describe YOUR truck on the 'My truck' page —")
    print("  the AI can only account for modifications you record.")
    print("=" * 60)
    if ask("\nStart SARGE now? (y/n) [y]:", choices=["y", "n"], default="y") == "y":
        subprocess.Popen([sys.executable, str(ROOT / "app.py")])
        import webbrowser
        import time
        time.sleep(3)
        webbrowser.open("http://127.0.0.1:8383")
        print("SARGE is running — keep the new window open. Enjoy.")


if __name__ == "__main__":
    main()
