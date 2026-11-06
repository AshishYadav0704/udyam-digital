"""Indicative server-side latency (in-process, single worker, no network) for the main endpoints.
python scripts/perf_probe.py  -> prints p50 / p95 in ms. Not a load test."""
from __future__ import annotations

import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = Path(tempfile.mkdtemp(prefix="udyam-perf-"))
os.environ.update({"STORAGE_DIR": str(TMP), "DATABASE_URL": f"sqlite:///{TMP / 'p.db'}", "LLM_PROVIDER": "offline"})
sys.path.insert(0, str(ROOT / "backend"))
import logging  # noqa: E402
logging.disable(logging.INFO)
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def timed(fn, n):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    out.sort()
    return statistics.median(out), out[int(len(out) * 0.95) - 1]


with TestClient(app) as c:
    def turn():
        r = c.post("/api/advisor/sessions", json={"language": "en"}).json()
        c.post(f"/api/advisor/sessions/{r['session_id']}/messages", headers={"X-Session-Token": r["session_token"]},
               json={"text": "I run a CA firm in Delhi, 12 employees, one office, GST registered"})
    r = c.post("/api/advisor/sessions", json={"language": "en"}).json()
    H = {"X-Session-Token": r["session_token"]}
    t = c.post(f"/api/advisor/sessions/{r['session_id']}/messages", headers=H,
               json={"text": "I run a CA firm in Delhi, 12 employees, one office, GST registered"}).json()
    if t["state"] != "recommended":
        t = c.post(f"/api/advisor/sessions/{r['session_id']}/messages", headers=H, json={"action": "show_plan"}).json()
    items = [{"product_id": i["product_id"], "qty": i["qty"]} for i in t["recommendation"]["items"]]
    rows = [("advisor: new session + first message", timed(turn, 25)),
            ("quote preview", timed(lambda: c.post("/api/quotes/preview", headers=H, json={"session_id": r["session_id"], "items": items}), 50)),
            ("catalogue", timed(lambda: c.get("/api/catalogue/products"), 50))]
    o = c.post("/api/auth/otp/request", json={"mobile": "9811100099"}).json()
    A = {"Authorization": "Bearer " + c.post("/api/auth/otp/verify", json={"mobile": "9811100099", "otp": o["demo_otp"]}).json()["token"]}
    order = c.post("/api/checkout", headers={**H, **A}, json={"session_id": r["session_id"], "items": items, "contact_name": "Perf",
                   "install_address": "1 Perf Road, Delhi", "pincode": "110001", "accept_terms": True}).json()
    c.post("/api/consent", headers=A, json={"purposes": {"kyc_verification": True}})
    cid = c.post("/api/kyc/cases", headers=A, json={"order_id": order["order_id"], "declaration": {"business_name": "Perf", "signatory_name": "Perf"}}).json()["case_id"]
    rows.append(("KYC: load 4 documents (validate, OCR, encrypt)", timed(lambda: c.post(f"/api/kyc/cases/{cid}/specimen", headers=A, json={"applicant": "K03"}), 3)))
    rows.append(("KYC: evaluate case", timed(lambda: c.post(f"/api/kyc/cases/{cid}/evaluate", headers=A), 10)))
    for name, (p50, p95) in rows:
        print(f"{name:48s} p50 {p50:8.1f} ms   p95 {p95:8.1f} ms")
