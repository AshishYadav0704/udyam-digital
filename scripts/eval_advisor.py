"""Evaluate the advisor's information extraction on the held-out set (backend/tests/advisor_eval_set.json).

    python scripts/eval_advisor.py                 # offline extractor only
    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=... python scripts/eval_advisor.py --provider

Scoring: each expected field is right or wrong (a list of accepted values counts if any matches; expected needs
must all be present). Extra fields the owner did not mention are reported as 'unasked fills'. Writes
analysis/outputs/advisor_eval.{md,json}.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.advisor.nlu import extract  # noqa: E402

FIELDS = ["business_type", "city", "employees", "sites", "has_gstin", "gstin_status", "needs"]


def offline(text: str) -> dict:
    return extract(text, None)


def with_provider(provider):
    from app.advisor import llm as llm_mod

    def run(text: str) -> dict:
        out = extract(text, None)
        try:
            upd = llm_mod.normalise_llm_extraction(provider.extract([], text))
        except Exception as e:  # noqa: BLE001
            print(f"  provider failed: {type(e).__name__}")
            return out
        for k, v in upd.items():
            if k in ("needs", "excluded_needs"):
                out[k] = list(dict.fromkeys([*out.get(k, []), *v]))
            elif k not in out or out.get(k) in (None, [], ""):
                out[k] = v
        return out
    return run


def ok(field, want, got) -> bool:
    if field == "needs":
        return set(want) <= set(got or [])
    if isinstance(want, list):
        return got in want
    return got == want


def evaluate(cases, fn):
    rows, per_field = [], defaultdict(lambda: [0, 0])
    unasked = 0
    t0 = time.perf_counter()
    for c in cases:
        got = fn(c["text"])
        wrong = []
        for f, want in c["expect"].items():
            right = ok(f, want, got.get(f))
            per_field[f][0] += right
            per_field[f][1] += 1
            if not right:
                wrong.append({"field": f, "expected": want, "got": got.get(f)})
        for f in FIELDS:
            if f not in c["expect"] and got.get(f) not in (None, [], "") and f != "needs":
                unasked += 1
        rows.append({"id": c["id"], "lang": c["lang"], "all_correct": not wrong, "wrong": wrong})
    ms = (time.perf_counter() - t0) * 1000 / max(1, len(cases))
    total_right = sum(v[0] for v in per_field.values())
    total = sum(v[1] for v in per_field.values())
    by_lang = defaultdict(lambda: [0, 0])
    for r in rows:
        by_lang[r["lang"]][0] += r["all_correct"]
        by_lang[r["lang"]][1] += 1
    return {"field_accuracy": total_right / total, "fields_scored": total,
            "case_accuracy": sum(r["all_correct"] for r in rows) / len(rows), "cases": len(rows),
            "per_field": {f: {"correct": a, "total": b, "accuracy": a / b} for f, (a, b) in per_field.items()},
            "by_language": {k: {"all_correct": a, "cases": b} for k, (a, b) in by_lang.items()},
            "unasked_fills": unasked, "ms_per_utterance": round(ms, 2), "rows": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", action="store_true", help="also evaluate the configured LLM provider (needs an API key)")
    args = ap.parse_args()
    data = json.loads((ROOT / "backend" / "tests" / "advisor_eval_set.json").read_text())
    results = {"offline": evaluate(data["cases"], offline)}
    if args.provider:
        from app.advisor.llm import get_provider
        prov = get_provider()
        if prov is None:
            print("No LLM provider configured; skipping provider evaluation.")
        else:
            results[f"offline+{prov.name}"] = evaluate(data["cases"], with_provider(prov))
    out = ROOT / "analysis" / "outputs"
    (out / "advisor_eval.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    lines = ["# Advisor extraction evaluation", "",
             f"Held-out set: {len(data['cases'])} first-message utterances (English, Hinglish, Hindi), "
             "`backend/tests/advisor_eval_set.json`. Field = one expected value; case = every expected value right.", ""]
    for name, r in results.items():
        lines += [f"## {name}", "",
                  f"- Field accuracy: **{r['field_accuracy']:.1%}** ({r['fields_scored']} fields)",
                  f"- Case accuracy (all fields right): **{r['case_accuracy']:.1%}** ({r['cases']} cases)",
                  f"- Unasked fills (a value set that the owner did not state): {r['unasked_fills']}",
                  f"- Latency: {r['ms_per_utterance']} ms per utterance", "",
                  "| Field | Correct | Total | Accuracy |", "|---|---:|---:|---:|"]
        for f, v in sorted(r["per_field"].items()):
            lines.append(f"| {f} | {v['correct']} | {v['total']} | {v['accuracy']:.0%} |")
        lines += ["", "| Language | Cases fully right |", "|---|---:|"]
        for k, v in r["by_language"].items():
            lines.append(f"| {k} | {v['all_correct']}/{v['cases']} |")
        misses = [x for x in r["rows"] if not x["all_correct"]]
        if misses:
            lines += ["", "Misses:", ""]
            for m in misses:
                lines.append(f"- `{m['id']}`: " + "; ".join(f"{w['field']} expected {w['expected']!r}, got {w['got']!r}" for w in m["wrong"]))
        lines.append("")
    lines += ["The advisor never relies on extraction alone: every slot it could not fill is asked as a question with tap-able "
              "answers, and the owner can correct the profile in a form before seeing prices.", ""]
    (out / "advisor_eval.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
