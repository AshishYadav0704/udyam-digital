"""Encrypted document storage (Fernet: AES-128-CBC + HMAC-SHA256).

Files are written under storage/docs/<random key>.bin; the original filename is never used.
Production: replace with object storage + KMS-managed keys (envelope encryption) behind this interface.
"""
from __future__ import annotations

import logging
import os
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet

from app.config import settings

log = logging.getLogger("app.storage")


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    key = settings.doc_encryption_key
    if not key:
        kf = settings.storage_dir / ".dev_document_key"
        if not kf.exists():
            kf.write_bytes(Fernet.generate_key())
            os.chmod(kf, 0o600)
            log.warning("DOC_ENCRYPTION_KEY not set - generated a development key at %s (never use in production)", kf)
        key = kf.read_bytes().decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def _dir() -> Path:
    d = settings.storage_dir / "docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def put(data: bytes) -> str:
    key = secrets.token_hex(16)
    (_dir() / f"{key}.bin").write_bytes(_fernet().encrypt(data))
    return key


def get(key: str) -> bytes:
    if not key.isalnum():
        raise ValueError("bad key")
    return _fernet().decrypt((_dir() / f"{key}.bin").read_bytes())


def delete(key: str) -> None:
    if key.isalnum():
        p = _dir() / f"{key}.bin"
        if p.exists():
            p.unlink()


def encrypt_text(value: str) -> str:
    """Encrypt a short secret (e.g. a call-back mobile number) with the same managed key."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt_text(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
