"""One-command corpus bootstrap for FMTV (MTV 6x6) owners.

Downloads the public-domain Army TM set (see SOURCES.md for provenance),
ingests it, and builds the semantic index. ~1.4 GB download, then roughly
30-60 minutes of local indexing depending on hardware.

Copyrighted factory documents (Cat, Allison, WABCO) are NOT downloaded here —
acquire your own copies (options in SOURCES.md), drop them in corpus/raw/,
and re-run this script or use the web app's Knowledge page.

Usage:  python bootstrap_fmtv.py [--skip-download]
"""

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
RAW = REPO_ROOT / "corpus" / "raw"

STORE = "https://store-yzfmq32nb8.mybigcommerce.com/content"
BASE = f"{STORE}/MTV%20%286x6%29"

# LMTV (4x4, M1078 series) — TM 9-2320-365 set from the same host
LMTV_SET = {
    "TM-9-2320-365-10.pdf": f"{STORE}/omlmtv.pdf",
    "TM-9-2320-365-20-1.pdf": f"{STORE}/umlmtv1.pdf",
    "TM-9-2320-365-20-2.pdf": f"{STORE}/umlmtv2.pdf",
    "TM-9-2320-365-20-3.pdf": f"{STORE}/umlmtv3.pdf",
    "TM-9-2320-365-20-4.pdf": f"{STORE}/umlmtv4.pdf",
    "TM-9-2320-365-20-5.pdf": f"{STORE}/umlmtv5.pdf",
    "TM-9-2320-365-24P.pdf": f"{STORE}/rpastllmtv.pdf",
    "TM-9-2320-365-34-1.pdf": f"{STORE}/gsmmlmtv.pdf",
    "TM-9-2320-365-34-2.pdf": f"{STORE}/gsmmlmtv2.pdf",
    "WTEC-II-Transmission-Codes.pdf": f"{BASE}/WTEC%20II%20Transmission%20Repair.pdf",
    "WTEC-3-4-Shift-Selector.pdf": f"{BASE}/fourthgenshift-selector-manual.pdf",
    "Allison-WTEC-2-Troubleshooting.pdf": f"{BASE}/Allison-WTEC-2-Troubleshooting-Manual.pdf",
}

# MTV (6x6, M1083 series) — TM 9-2320-366 set
TM_SET = {
    # operator
    "TM-9-2320-366-10-1.pdf": f"{BASE}/TM-9-2320-366-10-1.pdf",
    "TM-9-2320-366-10-2.pdf": f"{BASE}/TM-9-2320-366-10-2.pdf",
    # unit maintenance
    "TM-9-2320-366-20-1.pdf": f"{BASE}/TM-9-2320-366-20-1.pdf",
    "TM-9-2320-366-20-2.pdf": f"{BASE}/TM-9-2320-366-20-2.pdf",
    "TM-9-2320-366-20-3.pdf": f"{BASE}/TM-9-2320-366-20-3.pdf",
    "TM-9-2320-366-20-4.pdf": f"{BASE}/TM-9-2320-366-20-4.pdf",
    "TM-9-2320-366-20-5.pdf": f"{BASE}/TM-9-2320-366-20-5.pdf",
    # parts
    "TM-9-2320-366-24P-1.pdf": f"{BASE}/TM-9-2320-366-24P-1.pdf",
    "TM-9-2320-366-24P-2.pdf": f"{BASE}/TM-9-2320-366-24P-2.pdf",
    # direct/general support
    "TM-9-2320-366-34-1.pdf": f"{BASE}/TM%5F9-2320-366-34-1.pdf",
    "TM-9-2320-366-34-2.pdf": f"{BASE}/TM%5F9-2320-366-34-2.pdf",
    "TM-9-2320-366-34-3.pdf": f"{BASE}/TM%5F9-2320-366-34-3.pdf",
    "TM-9-2320-366-34-4.pdf": f"{BASE}/TM%5F9-2320-366-34-4.pdf",
    # extras hosted alongside
    "Electrical-Schematics.pdf": f"{BASE}/Electrical%20Schematics.pdf",
    "WTEC-II-Transmission-Codes.pdf": f"{BASE}/WTEC%20II%20Transmission%20Repair.pdf",
    "WTEC-3-4-Shift-Selector.pdf": f"{BASE}/fourthgenshift-selector-manual.pdf",
    "Allison-WTEC-2-Troubleshooting.pdf": f"{BASE}/Allison-WTEC-2-Troubleshooting-Manual.pdf",
}


def download(name: str, url: str) -> bool:
    dest = RAW / name
    if dest.exists() and dest.stat().st_size > 10_000:
        print(f"  {name}: already present")
        return True
    print(f"  {name}: downloading ...", flush=True)
    try:
        urllib.request.urlretrieve(url, dest)
        print(f"  {name}: {dest.stat().st_size // 1_000_000} MB")
        return True
    except Exception as e:
        print(f"  {name}: FAILED ({e}) — continuing")
        if dest.exists():
            dest.unlink()
        return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--skip-download", action="store_true",
                    help="index whatever is already in corpus/raw")
    ap.add_argument("--variant", choices=["mtv", "lmtv"], default="mtv",
                    help="mtv = 6x6 M1083 series (TM -366, default); "
                         "lmtv = 4x4 M1078 series (TM -365)")
    args = ap.parse_args()

    doc_set = LMTV_SET if args.variant == "lmtv" else TM_SET
    RAW.mkdir(parents=True, exist_ok=True)
    if not args.skip_download:
        print(f"Downloading {len(doc_set)} documents ({args.variant.upper()} "
              f"set) to {RAW}")
        ok = sum(download(n, u) for n, u in doc_set.items())
        print(f"{ok}/{len(doc_set)} downloads present\n")

    # index only this variant's document set (never other files that may be
    # in corpus/raw — irrelevant manuals pollute retrieval)
    pdfs = sorted(str(RAW / n) for n in doc_set if (RAW / n).exists())
    if not pdfs:
        sys.exit("none of the variant's PDFs are in corpus/raw — nothing to index")
    print(f"Ingesting {len(pdfs)} PDFs (text + metadata + keyword index) ...")
    subprocess.run([sys.executable, str(REPO_ROOT / "ingest" / "ingest_tm.py"),
                    *pdfs], check=True)
    print("\nBuilding semantic index (first run downloads a small local "
          "embedding model) ...")
    subprocess.run([sys.executable, str(REPO_ROOT / "ingest" / "embed_index.py")],
                   check=True)
    print("\nDone. Describe your truck in AS_BUILT_CONFIGURATION.md (or the "
          "web app's 'My truck' page), then:  python app.py")


if __name__ == "__main__":
    main()
