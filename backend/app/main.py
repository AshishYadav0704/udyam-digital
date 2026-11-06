"""Udyam Digital API - modular monolith (FastAPI)."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, settings
from app.routers import advisor, auth, backoffice, commerce, kyc, public
from app.security import configure_logging

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    configure_logging()
    from app.seed import init_db
    init_db()
    from app.db import SessionLocal
    from app.retention import purge_expired
    with SessionLocal() as db:
        n = purge_expired(db)
        if n:
            log.info("retention: deleted %d expired documents", n)
    if settings.jwt_secret_ephemeral:
        log.warning("JWT_SECRET not set - using a random per-process secret (development only)")
    from app.kyc.document_ai import ocr_engine_available
    if not ocr_engine_available():
        log.warning("Tesseract OCR not found - uploaded KYC documents will be kept and sent to human review")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Udyam Digital API", version="1.0.0", lifespan=lifespan,
                  description="Digital MSME acquisition & onboarding prototype (Airtel SYNC 2026, Track A). "
                              "Synthetic data only; registry adapters are mocks.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-Session-Token"])

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(self), geolocation=()")
        if request.url.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"detail": "Something went wrong on our side. Your progress is saved - please retry."}, status_code=500)

    for r in (public.router, auth.router, advisor.router, commerce.router, kyc.router, backoffice.router):
        app.include_router(r)

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            f = (dist / path).resolve()
            if path and f.is_file() and str(f).startswith(str(dist.resolve())):
                return FileResponse(f)
            return FileResponse(dist / "index.html")
    return app


app = create_app()
