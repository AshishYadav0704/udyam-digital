"""Runtime configuration. Every secret comes from the environment (see .env.example)."""
from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"          # relative paths in the environment are resolved from here, whatever the CWD


def parse_dotenv(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; '#' after whitespace starts a comment in unquoted values; quotes are removed."""
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, raw = line.split("=", 1)
        value = raw.strip()
        if value[:1] in {'"', "'"}:
            end = value.find(value[0], 1)
            value = value[1:end] if end != -1 else value[1:]
        else:
            value = re.sub(r"\s+#.*$", "", raw).strip()
        out[key.strip()] = value
    return out


def _load_dotenv() -> None:
    env = ROOT / ".env"
    if env.exists():
        for k, v in parse_dotenv(env).items():
            os.environ.setdefault(k, v)   # a real environment variable always wins over the file


_load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: Path) -> Path:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    p = Path(value).expanduser()
    return p if p.is_absolute() else (BACKEND / p).resolve()


def resolve_sqlite_url(url: str) -> str:
    """sqlite:///relative/path is relative to the backend directory, not to wherever the process was started."""
    prefix = "sqlite:///"
    if url.startswith(prefix):
        p = url[len(prefix):]
        if p and not p.startswith("/") and not p.startswith(":memory:"):
            return prefix + str((BACKEND / p).resolve())
    return url


def _optional_date(name: str, default: str) -> date | None:
    value = os.getenv(name, default).strip()
    return date.fromisoformat(value) if value else None      # empty means "use today's date"


@dataclass
class Settings:
    env: str = os.getenv("APP_ENV", "development").strip() or "development"
    data_dir: Path = _path("DATA_DIR", ROOT / "data" / "raw")
    storage_dir: Path = _path("STORAGE_DIR", ROOT / "storage")
    database_url: str = resolve_sqlite_url(os.getenv("DATABASE_URL", "").strip()
                                           or f"sqlite:///{ROOT / 'storage' / 'udyam.db'}")
    model_path: Path = _path("PROPENSITY_MODEL_PATH", ROOT / "ml" / "artifacts" / "propensity_model.joblib")

    # Security
    jwt_secret: str = os.getenv("JWT_SECRET", "")
    jwt_ttl_minutes: int = int(os.getenv("JWT_TTL_MINUTES", "120"))
    doc_encryption_key: str = os.getenv("DOC_ENCRYPTION_KEY", "")
    pii_pepper: str = os.getenv("PII_PEPPER", "")             # HMAC key for mobile-number lookups (separate from JWT)
    demo_otp: str = os.getenv("DEMO_OTP", "123456")          # prototype only: no SMS gateway is wired
    demo_staff_password: str = os.getenv("DEMO_STAFF_PASSWORD", "demo1234")
    max_upload_mb: float = float(os.getenv("MAX_UPLOAD_MB", "5"))
    cors_origins: list[str] = field(default_factory=lambda: os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","))

    # Commercial policy
    price_policy: str = os.getenv("PRICE_POLICY", "").strip() or "midpoint"   # midpoint | floor | ceiling
    gst_rate: float = float(os.getenv("GST_RATE", "0.18"))       # tax estimate shown on the quote
    quote_validity_days: int = int(os.getenv("QUOTE_VALIDITY_DAYS", "15"))

    # KYC policy
    kyc_reference_date: date | None = _optional_date("KYC_REFERENCE_DATE", "2026-07-15")   # None -> today
    address_proof_max_age_days: int = int(os.getenv("ADDRESS_PROOF_MAX_AGE_DAYS", "90"))
    synthetic_identifier_mode: bool = _bool("SYNTHETIC_IDENTIFIER_MODE", True)  # accept PAN 4th char X and district 00
    ocr_min_field_confidence: float = float(os.getenv("OCR_MIN_FIELD_CONFIDENCE", "0.80"))
    doc_retention_days_after_activation: int = int(os.getenv("DOC_RETENTION_DAYS", "180"))

    # GenAI
    llm_provider: str = os.getenv("LLM_PROVIDER", "").strip().lower() or "auto"  # auto | anthropic | openai | gemini | offline
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "").strip() or "claude-haiku-5-5"
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "").strip() or "gpt-5-mini"
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "").strip() or "gemini-2.5-flash"
    llm_timeout_s: float = float(os.getenv("LLM_TIMEOUT_S", "12"))

    def __post_init__(self):
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        if self.is_production:
            missing = [n for n, v in (("JWT_SECRET", self.jwt_secret), ("DOC_ENCRYPTION_KEY", self.doc_encryption_key),
                                      ("PII_PEPPER", self.pii_pepper)) if not v]
            if missing:   # fail closed: never run production on generated development keys
                raise RuntimeError("missing required secrets for production: " + ", ".join(missing))
            if self.synthetic_identifier_mode:
                raise RuntimeError("SYNTHETIC_IDENTIFIER_MODE must be false in production")
        if not self.pii_pepper:
            # Development: persist a local pepper so customer lookups survive restarts (never used in production).
            kf = self.storage_dir / ".dev_pii_pepper"
            if not kf.exists():
                kf.write_text(secrets.token_hex(32))
                os.chmod(kf, 0o600)
            self.pii_pepper = kf.read_text().strip()
        if not self.jwt_secret:
            # Development fallback: a per-process random secret (tokens die on restart).
            self.jwt_secret = secrets.token_urlsafe(48)
            self.jwt_secret_ephemeral = True
        else:
            self.jwt_secret_ephemeral = False

    @property
    def is_production(self) -> bool:
        return self.env == "production"


settings = Settings()
