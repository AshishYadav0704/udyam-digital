# OCR benchmark - 46 readable specimen documents

Ground truth: our manual transcription (`analysis/kyc_ground_truth.json`); K04's GST certificate is unreadable to a human
and K05 has no Udyam certificate, so both are excluded. Exact match after the same normalisation for every engine.

| Engine | Field accuracy | Identifier accuracy (GSTIN, Udyam, consumer no., ID no.) | Doc-type accuracy | Time / doc (2 vCPU) |
|---|---|---|---|---|
| pipeline | 98.7% (149 fields) | 97.8% | 100% | 1.24 s |
| ppocr_onnx_clean | 97.3% (149 fields) | 97.8% | 100% | 1.68 s |
| tesseract_raw | 96.6% (149 fields) | 93.5% | 100% | 0.37 s |
| tesseract_clean | 96.6% (149 fields) | 93.5% | 100% | 0.35 s |
| ppocr_onnx_raw | 69.1% (149 fields) | 28.3% | 100% | 2.12 s |

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
