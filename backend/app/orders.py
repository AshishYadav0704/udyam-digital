"""Order lifecycle and the customer-facing tracker."""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from app.i18n import t
from app.models import Order, OrderEvent

FLOW = ["order_placed", "payment_done", "kyc_submitted", "kyc_verified", "installation_scheduled", "installed",
        "end_user_kyc", "activated"]
STATUS_FOR_STAGE = {"order_placed": "payment_pending", "payment_done": "kyc_pending", "kyc_submitted": "kyc_submitted",
                    "kyc_verified": "scheduling", "installation_scheduled": "installation_scheduled",
                    "installed": "installed", "end_user_kyc": "end_user_kyc", "activated": "active"}
TERMINAL = {"activated"}


def new_order_no() -> str:
    return "AB" + datetime.now(timezone.utc).strftime("%y%m") + secrets.token_hex(3).upper()


def _customer_note(e: OrderEvent, lang: str) -> str | None:
    """KYC events store internal finding codes for staff; customers see a plain sentence instead."""
    if e.stage in ("kyc_review", "kyc_action_required"):
        codes = [c for c in (e.note or "").split(":")[-1].split(",") if c.strip()]
        return t(lang, f"tracker_note.{e.stage}", n=max(1, len(codes)))
    return e.note


def add_event(order: Order, stage: str, note: str | None = None, actor: str = "system"):
    order.events.append(OrderEvent(stage=stage, note=note, actor=actor))
    if stage in STATUS_FOR_STAGE:
        order.status = STATUS_FOR_STAGE[stage]
    elif stage == "kyc_action_required":
        order.status = "kyc_action_required"
    elif stage == "kyc_review":
        order.status = "kyc_review"
    elif stage == "payment_failed":
        order.payment_status = "failed"


def _has_lines(quote: dict) -> bool:
    return any(l["product_id"] in ("P07", "P08") for l in quote.get("lines", []))


def tracker(order: Order, quote: dict, lang: str) -> dict:
    done = {}
    for e in order.events:
        done.setdefault(e.stage, e.at)
    flow = [s for s in FLOW if s != "end_user_kyc" or _has_lines(quote)]
    start = order.created_at if order.created_at.tzinfo else order.created_at.replace(tzinfo=timezone.utc)
    kyc_at = done.get("kyc_verified") or start + timedelta(days=1)
    if kyc_at.tzinfo is None:
        kyc_at = kyc_at.replace(tzinfo=timezone.utc)
    act_days = int(quote.get("expected_activation_days", 5))
    expected = {"order_placed": start, "payment_done": start, "kyc_submitted": start, "kyc_verified": start + timedelta(days=1),
                "installation_scheduled": kyc_at + timedelta(days=1), "installed": kyc_at + timedelta(days=act_days),
                "end_user_kyc": kyc_at + timedelta(days=act_days), "activated": kyc_at + timedelta(days=act_days + 1)}
    steps, current_found = [], False
    for s in flow:
        if s in done:
            status = "done"
        elif not current_found:
            status, current_found = "current", True
        else:
            status = "upcoming"
        steps.append({"stage": s, "label": t(lang, f"tracker.{s}"), "status": status,
                      "at": done[s].isoformat() if s in done else None,
                      "expected": None if s in done else expected[s].date().isoformat()})
    blockers = [{"stage": e.stage, "label": t(lang, f"tracker.{e.stage}"), "note": _customer_note(e, lang), "at": e.at.isoformat()}
                for e in order.events if e.stage in ("kyc_action_required", "kyc_review", "payment_failed", "escalated")]
    installs = [{"product_id": l["product_id"], "name": l["name"], "qty": l["qty"],
                 "expected": (kyc_at + timedelta(days=l["install_done_day"])).date().isoformat()} for l in quote.get("lines", [])]
    return {"order_no": order.order_no, "status": order.status, "payment_status": order.payment_status, "steps": steps,
            "blockers": blockers, "installations": installs,
            "expected_activation": expected["activated"].date().isoformat() if "activated" not in done else None,
            "activated_at": done["activated"].isoformat() if "activated" in done else None}
