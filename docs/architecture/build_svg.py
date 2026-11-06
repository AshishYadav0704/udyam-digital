"""Draws docs/architecture/architecture.svg (the layered view used in the deck and README).

The Mermaid file next to it describes the same components and connections for tools that render Mermaid.
Run: python docs/architecture/build_svg.py
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

INK, INK3, MUTED, LINE, MIST = "#1b2a4a", "#46597f", "#5b6475", "#dde2ea", "#f3f5f8"
MARIGOLD, AMBER, AMBER_SOFT, WHITE = "#e8a317", "#8a5a00", "#fff4d6", "#ffffff"
FONT = "Carlito, Calibri, 'Segoe UI', Arial, sans-serif"
W, H = 1600, 876

parts: list[str] = []


def text(x, y, s, size=15, weight=400, fill=INK, anchor="middle"):
    parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{fill}" '
                 f'text-anchor="{anchor}" font-family="{FONT}">{escape(s)}</text>')


def box(x, y, w, h, title, lines=(), fill=WHITE, stroke=INK, title_fill=INK, body_fill=INK3, dash=None, r=10, sw=1.6):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"{d}/>')
    n = 1 + len(lines)
    top = y + h / 2 - (n - 1) * 10.5 + 5
    text(x + w / 2, top, title, 16, 700, title_fill)
    for i, ln in enumerate(lines):
        text(x + w / 2, top + 21 * (i + 1), ln, 13.5, 400, body_fill)


def lane(y, h, label):
    parts.append(f'<rect x="20" y="{y}" width="{W - 40}" height="{h}" rx="14" fill="{MIST}" stroke="{LINE}"/>')
    text(40, y + 24, label, 14, 700, MUTED, "start")


def arrow(x1, y1, x2, y2, label=None, dash=None, color=INK3, lx=None, ly=None):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.8"{d} marker-end="url(#a)"/>')
    if label:
        tx, ty = (lx if lx is not None else (x1 + x2) / 2 + 6), (ly if ly is not None else (y1 + y2) / 2)
        parts.append(f'<text x="{tx}" y="{ty}" font-size="12.5" fill="{MUTED}" font-family="{FONT}" text-anchor="start" '
                     f'paint-order="stroke" stroke="{MIST}" stroke-width="4">{escape(label)}</text>')


# ------------------------------------------------------------------ lanes
lane(16, 112, "People")
box(170, 40, 300, 72, "Business owner", ["phone browser, Hindi or English"])
box(560, 40, 330, 72, "WhatsApp / partner QR link", ["carries source and partner code"])
box(1010, 40, 420, 72, "Sales, partner, KYC reviewer, admin", ["staff sign-in"])

lane(144, 112, "Web app")
box(170, 168, 720, 72, "Customer journey: 15 mobile-first screens (React + TypeScript)",
    ["advisor, plan, add-ons, quote, checkout, consent, upload, result, tracker, help"])
box(1010, 168, 420, 72, "Back office (loaded only for staff)",
    ["overview, leads, KYC queue, orders, partners, call-backs, audit"])
arrow(320, 112, 320, 166)
arrow(725, 112, 600, 166)
arrow(1220, 112, 1220, 166)

lane(272, 260, "API: one FastAPI service, separate modules")
box(60, 300, 1480, 56, "Security layer",
    ["OTP + JWT sessions, five roles, per-session secret for the advisor, rate limits, security headers, PII-scrubbed logs, audit trail"],
    fill=WHITE, stroke=INK)
arrow(530, 240, 530, 298, "HTTPS, JSON")
arrow(1220, 240, 1220, 298, "HTTPS, JSON")

# modules row (journey order, left to right)
mx, my, mw, mh, gap = 60, 392, 280, 126, 20
col = lambda i: mx + i * (mw + gap)          # noqa: E731
box(col(0), my, mw, mh, "Advisor", ["understands EN, Hinglish, Hindi;", "asks only what is missing;", "optional LLM: text only"])
box(col(1), my, mw, mh, "Deterministic engine",
    ["catalogue rules, eligibility,", "recommendation, one price per", "product, GST, install plan"], fill=INK, stroke=INK,
    title_fill=WHITE, body_fill="#d6dcea")
box(col(2), my, mw, mh, "Smart KYC",
    ["upload checks, deskew, blur,", "watermark removal, OCR ensemble,", "cross-checks, 3-way decision"], fill=INK, stroke=INK,
    title_fill=WHITE, body_fill="#d6dcea")
box(col(3), my, mw, mh, "Orders and privacy", ["re-prices the quote at checkout,", "payment retry, tracker, consent", "and withdrawal, call-backs"])
box(col(4), my, mw, mh, "Routing + lead score",
    ["calibrated logistic regression;", "self-serve, assisted, partner,", "field sales or KYC review"])
for i in range(5):
    arrow(col(i) + mw / 2, 356, col(i) + mw / 2, my - 2)
arrow(col(0) + mw, my + 63, col(1) - 2, my + 63)            # advisor -> engine (profile)
arrow(col(3) + mw, my + 63, col(4) - 2, my + 63)            # orders -> routing

# ------------------------------------------------------------------ storage lane
lane(540, 124, "Storage")
sy, sh = 566, 84
box(col(1), sy, mw, sh, "Catalogue rules", ["25 products, prices, tiers,", "dependencies (from the data pack)"])
box(col(2), sy, 168, sh, "Encrypted documents", ["Fernet now;", "KMS keys later"])
box(col(3), sy, mw, sh, "Database", ["sessions, quotes, orders, consent,", "audit; SQLite now, PostgreSQL later"])
box(col(4), sy, mw, sh, "Lead model", ["trained offline on history;", "re-validate on real data"])
arrow(col(1) + mw / 2, my + mh, col(1) + mw / 2, sy - 2)
arrow(col(2) + 84, my + mh, col(2) + 84, sy - 2)
arrow(col(3) + mw / 2, my + mh, col(3) + mw / 2, sy - 2)
arrow(col(4) + mw / 2, my + mh, col(4) + mw / 2, sy - 2)

# ------------------------------------------------------------------ outside services lane
lane(680, 150, "Outside services")
oy, oh = 712, 100
box(col(0), oy, mw, oh, "LLM provider API", ["only if a key is configured;", "never sees documents"], stroke=INK3, dash="6 5")
box(col(2), oy, mw, oh, "MOCK GST + Udyam registry", ["local, built from the synthetic", "CSVs. Not a government API."],
    fill=AMBER_SOFT, stroke=AMBER, dash="7 5")
box(col(3), oy, 2 * mw + gap, oh, "Production: swap the mock adapter for these (not called today)",
    ["GSP for GSTN, Udyam data source, DigiLocker / Entity Locker via API Setu,", "eSign service provider, SMS gateway, UPI AutoPay"],
    stroke=AMBER, dash="3 4", body_fill=MUTED)
arrow(col(0) + mw / 2, my + mh, col(0) + mw / 2, oy - 2, "text only, PII masked", dash="5 4")
arrow(col(2) + 230, my + mh, col(2) + 230, oy - 2)               # KYC -> registry (passes right of the document store)
arrow(col(2) + mw, oy + oh / 2, col(3) - 2, oy + oh / 2, None, dash="4 4")
text(col(1) + mw / 2, oy + 40, "Engine and KYC decide.", 15, 700, AMBER)
text(col(1) + mw / 2, oy + 62, "The model and the LLM only assist;", 13.5, 400, MUTED)
text(col(1) + mw / 2, oy + 80, "with no key the advisor runs offline.", 13.5, 400, MUTED)

legend_y = 858
parts.append(f'<rect x="60" y="{legend_y - 12}" width="16" height="12" fill="{INK}"/>')
text(84, legend_y - 2, "decides (deterministic rules)", 12.5, 400, MUTED, "start")
parts.append(f'<rect x="290" y="{legend_y - 12}" width="16" height="12" fill="{AMBER_SOFT}" stroke="{AMBER}" stroke-dasharray="4 3"/>')
text(314, legend_y - 2, "mock built from synthetic data", 12.5, 400, MUTED, "start")
parts.append(f'<rect x="530" y="{legend_y - 12}" width="16" height="12" fill="{WHITE}" stroke="{INK3}" stroke-dasharray="4 3"/>')
text(554, legend_y - 2, "optional, or production-only", 12.5, 400, MUTED, "start")

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
       f'aria-label="Udyam Digital architecture">'
       f'<title>Udyam Digital architecture</title>'
       f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
       f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{INK3}"/></marker></defs>'
       f'<rect width="{W}" height="{H}" fill="{WHITE}"/>' + "".join(parts) + "</svg>")
out = Path(__file__).with_name("architecture.svg")
out.write_text(svg)
print("wrote", out)
