"""Block 1 (hours 0-2): verify Qualcomm Cloud AI Playground end to end.

Usage:  .venv\\Scripts\\python scripts\\check_qualcomm.py [--runs 5]

Tests, with the real demo notes from the spec:
  1. key works, list of available models
  2. extraction via Imagine SDK + JSON prompt
  3. extraction via Imagine SDK + tool calling
  4. extraction via OpenAI SDK (OpenAI-compatible endpoint) + JSON prompt
  5. embeddings and reranker
  6. latency over N runs for the best combination
Writes docs/qualcomm-check.json. The API key is never printed or written.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from pydantic import ValidationError  # noqa: E402

from app.config import settings  # noqa: E402
from app.prompts import EXTRACTION_TOOL, extraction_messages  # noqa: E402
from app.qualcomm import Qualcomm, QualcommError  # noqa: E402
from app.schema import AIExtraction  # noqa: E402

DEMO_NOTES = (ROOT / "fixtures" / "demo_meeting_1.txt").read_text(encoding="utf-8").strip()


def parse_json(text: str) -> dict:
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[1] if "\n" in body else body
        body = body.rsplit("```", 1)[0]
    return json.loads(body)


def attempt(q: Qualcomm, client: str, mode: str) -> dict:
    out: dict = {"client": client, "mode": mode}
    msgs = extraction_messages(DEMO_NOTES, "2026-10-26", mode)
    try:
        r = q.chat(msgs, client=client, tool=EXTRACTION_TOOL if mode == "tool" else None)
    except QualcommError as e:
        out["error"] = f"{e.code}: {e.message}"
        return out
    out.update(latency_ms=r.latency_ms, finish_reason=r.finish_reason, model=r.model,
               prompt_tokens=r.prompt_tokens, completion_tokens=r.completion_tokens)
    try:
        data = r.tool_arguments if mode == "tool" else parse_json(r.text)
        if data is None:
            raise ValueError("model did not call the tool")
        ext = AIExtraction.model_validate(data)
        out["valid"] = True
        out["counts"] = {k: len(getattr(ext, k)) for k in ("decisions", "actions", "risks", "contradictions")}
        out["unknown_owners"] = sum(1 for a in ext.actions + ext.risks + ext.decisions if a.owner == "UNKNOWN")
        quotes = [a.evidence_quote for a in ext.actions + ext.risks + ext.decisions]
        out["quotes_found_in_notes"] = f"{sum(1 for x in quotes if x.rstrip('.') in DEMO_NOTES)}/{len(quotes)}"
        out["sample"] = ext.model_dump()
    except (ValueError, ValidationError) as e:
        out["valid"] = False
        out["parse_error"] = str(e)[:300]
        out["raw_head"] = (r.text or json.dumps(r.tool_arguments))[:400]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--apply", action="store_true", help="write the recommended settings into .env")
    args = ap.parse_args()
    s = settings()
    report: dict = {"endpoint": s.qualcomm_endpoint, "model": s.qualcomm_model}
    try:
        q = Qualcomm(s)
    except QualcommError as e:
        print(f"Cannot start: {e.message}\nCreate a key at https://aisuite.cirrascale.com/api-keys and put it in .env as QUALCOMM_API_KEY=...")
        return 2

    print("1. models ...")
    try:
        report["models"] = q.models()
        print("   ", json.dumps(report["models"])[:300])
    except QualcommError as e:
        report["models_error"] = f"{e.code}: {e.message}"
        print("   FAILED", report["models_error"])
        if e.code == "AUTH":
            return 1

    results = []
    for client, mode in (("imagine", "json"), ("imagine", "tool"), ("openai", "json"), ("openai", "tool")):
        print(f"2. extraction client={client} mode={mode} ...")
        r = attempt(q, client, mode)
        results.append(r)
        print("   ", {k: v for k, v in r.items() if k not in ("sample", "raw_head")})
    report["extraction"] = results

    print("3. embeddings + reranker ...")
    try:
        vecs = q.embed(["We agreed to deploy on AWS.", "Last week the team agreed to deploy on Azure."])
        report["embeddings"] = {"count": len(vecs), "dims": len(vecs[0])}
        ranked = q.rerank("Which cloud do we deploy on?", ["We agreed to deploy on AWS.", "Priya will test the API."], top_n=2)
        report["reranker"] = ranked
        print("   ", report["embeddings"], ranked)
    except QualcommError as e:
        report["embeddings_error"] = f"{e.code}: {e.message}"
        print("   FAILED", report["embeddings_error"])

    good = [r for r in results if r.get("valid")]
    if good:
        best = min(good, key=lambda r: r["latency_ms"])
        report["recommended"] = {"QUALCOMM_CLIENT": best["client"], "QUALCOMM_STRUCTURED_MODE": best["mode"]}
        print(f"4. latency x{args.runs} with {best['client']}/{best['mode']} ...")
        times, valid = [], 0
        for _ in range(args.runs):
            r = attempt(q, best["client"], best["mode"])
            if "latency_ms" in r:
                times.append(r["latency_ms"])
            valid += bool(r.get("valid"))
        if times:
            report["latency"] = {"runs": len(times), "valid": valid, "p50_ms": int(statistics.median(times)),
                                 "max_ms": max(times), "min_ms": min(times)}
            print("   ", report["latency"])

    text = json.dumps(report, indent=2, default=str)
    assert s.qualcomm_api_key not in text
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "qualcomm-check.json").write_text(text, encoding="utf-8")
    print("\nSaved docs/qualcomm-check.json")
    print("Recommended settings:", report.get("recommended", "none: no combination returned valid JSON"))
    if args.apply and report.get("recommended"):
        apply_env(report["recommended"])
        print("Applied to .env. Restart the backend to use them.")
    return 0 if good else 1


def apply_env(values: dict) -> None:
    env = ROOT / ".env"
    lines = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in values and not line.lstrip().startswith("#"):
            lines[i] = f"{key}={values[key]}"
            done.add(key)
    lines += [f"{k}={v}" for k, v in values.items() if k not in done]
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
