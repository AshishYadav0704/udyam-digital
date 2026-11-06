import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DATA_DIR", str(ROOT / "data" / "raw"))
os.environ.setdefault("STORAGE_DIR", str(ROOT / "storage" / "test"))
os.environ.setdefault("DATABASE_URL", f"sqlite:///{ROOT / 'storage' / 'test' / 'test.db'}")
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-use-0123456789")
os.environ.setdefault("LLM_PROVIDER", "offline")
os.environ.setdefault("DOC_ENCRYPTION_KEY", "")
