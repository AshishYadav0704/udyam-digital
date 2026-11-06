"""Step 4 - OCR engine comparison on the 47 specimens, scored against our manual ground truth.

Usage:  python -I analysis/04_ocr_benchmark.py [data_dir]
Writes: analysis/outputs/ocr_benchmark.json, analysis/outputs/ocr_benchmark.md

Engines compared (all run locally, no document leaves the machine):
  tesseract_raw     Tesseract 5 LSTM, greyscale page, single pass
  tesseract_clean   + specimen-watermark suppression (red-channel threshold), single pass
  pipeline          our production path: quality gate, deskew, 3-variant ensemble, identifier-aware voting
  ppocr_onnx_raw    PaddleOCR PP-OCR detection+recognition models on ONNX Runtime (RapidOCR), colour page
  ppocr_onnx_clean  the same on the watermark-suppressed page
                    (the PaddlePaddle runtime and its model server were not reachable from this sandbox)
EasyOCR was not benchmarked: it needs PyTorch, whose CPU wheels are served from a host this sandbox
cannot reach. That gap is stated in the report rather than filled with published numbers.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402

from app.kyc import document_ai as da  # noqa: E402

D = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "data" / "raw"
K = D / "kyc_documents"
OUT = ROOT / "analysis" / "outputs"
GT = json.loads((ROOT / "analysis" / "kyc_ground_truth.json").read_text())


def tesseract_lines(img):
    return da._ocr_lines(img)


def eng_tesseract_raw(img):
    return tesseract_lines(cv2.cvtColor(da._std_width(img), cv2.COLOR_BGR2GRAY))


def eng_tesseract_clean(img):
    return tesseract_lines(da._suppress_watermark(da._std_width(img)))


_rapid = None


def eng_rapidocr_raw(img):
    return _rapid_lines(da._std_width(img))


def eng_rapidocr_clean(img):
    return _rapid_lines(cv2.cvtColor(da._suppress_watermark(da._std_width(img)), cv2.COLOR_GRAY2BGR))


def _rapid_lines(im):
    global _rapid
    if _rapid is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid = RapidOCR()
    res, _ = _rapid(im)
    if not res:
        return []
    boxes = []
    for box, text, score in res:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), text, float(score)))
    boxes.sort()
    med_h = float(np.median([b[1] for b in boxes])) or 10.0
    lines, cur = [], [boxes[0]]
    for b in boxes[1:]:
        if abs(b[0] - cur[-1][0]) < 0.5 * med_h:
            cur.append(b)
        else:
            lines.append(cur)
            cur = [b]
    lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda b: b[2])
        words, confs = [], []
        for b in ln:
            for w in b[3].split():
                words.append(w)
                confs.append(b[4])
        out.append((" ".join(words), confs))
    return out


def single_pass_fields(lines, slot):
    doc_type, _ = da.classify("\n".join(t for t, _ in lines))
    parsed = da.parse_fields(doc_type or slot, lines) if (doc_type or slot) in da.LABELS else {}
    return {k: da.normalise_field(k, v)[0] for k, (v, c) in parsed.items()}, doc_type


def norm_gt(field, value):
    if value is None:
        return None
    return da.normalise_field(field, value)[0] if field not in ("gstin",) else value


engines = {"tesseract_raw": eng_tesseract_raw, "tesseract_clean": eng_tesseract_clean,
           "ppocr_onnx_raw": eng_rapidocr_raw, "ppocr_onnx_clean": eng_rapidocr_clean}
scores = {e: {"correct": 0, "total": 0, "by_field": {}, "seconds": 0.0, "docs": 0, "classified": 0} for e in [*engines, "pipeline"]}
details = {}
for app_id in sorted(GT):
    if app_id.startswith("_"):
        continue
    for slot, truth in GT[app_id].items():
        f = K / f"{app_id}_{slot}.png"
        if not isinstance(truth, dict) or not f.exists():
            continue
        data = f.read_bytes()
        img = da.decode(data)
        outputs = {}
        for name, fn in engines.items():
            t = time.time()
            vals, dt = single_pass_fields(fn(img), slot)
            scores[name]["seconds"] += time.time() - t
            scores[name]["classified"] += dt == slot
            outputs[name] = vals
        t = time.time()
        ex = da.extract(data, slot)
        scores["pipeline"]["seconds"] += time.time() - t
        scores["pipeline"]["classified"] += ex.doc_type == slot
        outputs["pipeline"] = {k: v.value for k, v in ex.fields.items()}
        for name, vals in outputs.items():
            scores[name]["docs"] += 1
            for field, tv in truth.items():
                exp = norm_gt(field, tv)
                got = vals.get(field)
                ok = (got or None) == exp
                s = scores[name]
                s["total"] += 1
                s["correct"] += ok
                bf = s["by_field"].setdefault(field, [0, 0])
                bf[0] += ok
                bf[1] += 1
                if not ok:
                    details.setdefault(name, []).append({"doc": f"{app_id}_{slot}", "field": field, "expected": exp, "got": got})
        print(f"{app_id}_{slot} done")

summary = {}
for name, s in scores.items():
    summary[name] = {"field_accuracy": s["correct"] / s["total"], "fields_scored": s["total"],
                     "type_classification_accuracy": s["classified"] / s["docs"],
                     "seconds_per_doc": s["seconds"] / s["docs"],
                     "identifier_accuracy": (sum(s["by_field"].get(k, [0, 0])[0] for k in ("gstin", "udyam_number", "consumer_no", "id_no")) /
                                             max(1, sum(s["by_field"].get(k, [0, 0])[1] for k in ("gstin", "udyam_number", "consumer_no", "id_no")))),
                     "by_field": {k: f"{v[0]}/{v[1]}" for k, v in s["by_field"].items()}}
(OUT / "ocr_benchmark.json").write_text(json.dumps({"summary": summary, "errors": details}, indent=1))
rows = "\n".join(f"| {n} | {v['field_accuracy']:.1%} ({v['fields_scored']} fields) | {v['identifier_accuracy']:.1%} | "
                 f"{v['type_classification_accuracy']:.0%} | {v['seconds_per_doc']:.2f} s |" for n, v in
                 sorted(summary.items(), key=lambda kv: -kv[1]["field_accuracy"]))
md = f"""# OCR benchmark - 46 readable specimen documents

Ground truth: our manual transcription (`analysis/kyc_ground_truth.json`); K04's GST certificate is unreadable to a human
and K05 has no Udyam certificate, so both are excluded. Exact match after the same normalisation for every engine.

| Engine | Field accuracy | Identifier accuracy (GSTIN, Udyam, consumer no., ID no.) | Doc-type accuracy | Time / doc (2 vCPU) |
|---|---|---|---|---|
{rows}

Per-field results: see `ocr_benchmark.json`. Every error is listed there with expected vs extracted value.

Interpretation
- The diagonal specimen watermark hurts PP-OCR's text detector badly (values under the watermark are not detected) and
  barely affects Tesseract; suppressing it (red-channel threshold) is cheap and is applied in the pipeline.
- The production pipeline adds deskew (K02 is photographed at ~7 degrees) and validator-aware voting across three
  renderings, trading ~3x the CPU time for accuracy. A blurred page (K04) is rejected by the quality gate before OCR.
- No engine is perfect; every extracted field carries a confidence and anything that does not match the registry or the
  declaration is routed to a person, not auto-approved.
- EasyOCR was not run (PyTorch could not be installed from this sandbox). PaddleOCR was evaluated through its PP-OCR
  models on ONNX Runtime (RapidOCR), not through the PaddlePaddle runtime.
"""
(OUT / "ocr_benchmark.md").write_text(md)
print(md)
