"""Measure accuracy on the 10-note gold set with live Qualcomm, and save it for the scoreboard.

    .venv\\Scripts\\python scripts\\eval_gold.py            # writes fixtures/gold/results.json
    .venv\\Scripts\\python scripts\\eval_gold.py --only g01 # one note, printed only

About 20-30 Qualcomm calls (one extraction, sometimes a retry, and one Verifier call per note).
Needs QUALCOMM_API_KEY in .env. Replay mode is refused: the numbers must come from the real model.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ai import build_ai  # noqa: E402
from app.config import settings  # noqa: E402
from app.gold import LAYERS, RESULTS_FILE, evaluate, load_gold  # noqa: E402


def pct(v: float | None) -> str:
    return "  -  " if v is None else f"{v * 100:5.1f}%"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run a single note id, e.g. g01 (results are not saved)")
    args = ap.parse_args()

    s = settings()
    ai = build_ai(s)
    if getattr(ai, "mode", "") != "live":
        sys.exit("No QUALCOMM_API_KEY (or QUALCOMM_REPLAY is set). Add the key to .env: the scoreboard only shows real model output.")
    gold = load_gold()
    if args.only:
        gold = [g for g in gold if g["id"] == args.only]
        if not gold:
            sys.exit(f"No note {args.only}.")

    started = time.perf_counter()
    res = evaluate(ai, gold, s.structured_mode, progress=lambda g: print(f"  {g['id']} {g['title']}...", flush=True))
    took = time.perf_counter() - started

    print(f"\nModel {res['model']} · {res['notes']} notes · {res['gold_items']} gold items · {took:.0f} s")
    if res["failed_notes"]:
        print(f"Failed (counted as nothing extracted): {', '.join(res['failed_notes'])}")
    print(f"\n{'':28}{'Precision':>10}{'Recall':>9}{'Halluc.':>9}{'Rate':>8}")
    for k in LAYERS:
        L = res["layers"][k]
        print(f"{L['label']:28}{pct(L['precision']):>10}{pct(L['recall']):>9}{L['hallucinations']:>9}{pct(L['hallucination_rate']):>8}")
    print("\nCaught by the checks:")
    for n in res["per_note"]:
        for m in n.get("caught", []):
            print(f"  {n['id']}: {m['type']}: {m['text']} ({m['why']})")
    lost = [(n["id"], m) for n in res["per_note"] for m in n.get("lost", [])]
    if lost:
        print("\nRight answers the Verifier removed:")
        for nid, m in lost:
            print(f"  {nid}: {m['text']} ({m['why']})")
    left = [(n["id"], m) for n in res["per_note"] for m in n.get("remaining", [])]
    if left:
        print("\nStill wrong after all checks:")
        for nid, m in left:
            print(f"  {nid}: {m['type']}: {m['text']} ({m['why']})")

    if args.only:
        print("\n(--only: results not saved)")
        return
    RESULTS_FILE.write_text(json.dumps(res, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nSaved {RESULTS_FILE.relative_to(ROOT)}. Commit it so the scoreboard shows these numbers after a redeploy.")


if __name__ == "__main__":
    main()
