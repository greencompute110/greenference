from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from time import time
from typing import Protocol

from pydantic import BaseModel, Field


class SignedRequest(BaseModel):
    actor_id: str
    nonce: str = Field(default_factory=lambda: secrets.token_hex(8))
    timestamp: int = Field(default_factory=lambda: int(time()))
    signature: str


class ReplayStore(Protocol):
    def mark_seen(self, actor_id: str, nonce: str, timestamp: int) -> bool: ...


class MemoryReplayStore:
    def __init__(self) -> None:
        self._seen: set[tuple[str, str, int]] = set()

    def mark_seen(self, actor_id: str, nonce: str, timestamp: int) -> bool:
        key = (actor_id, nonce, timestamp)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True


@dataclass(frozen=True)
class VerificationResult:
    valid: bool
    reason: str | None = None


def _canonical(actor_id: str, nonce: str, timestamp: int, body: bytes) -> bytes:
    digest = hashlib.sha256(body).hexdigest()
    return f"{actor_id}:{nonce}:{timestamp}:{digest}".encode()


def sign_payload(secret: str, actor_id: str, body: bytes, nonce: str | None = None) -> SignedRequest:
    request = SignedRequest(
        actor_id=actor_id,
        nonce=nonce or secrets.token_hex(8),
        signature="",
    )
    signature = hmac.new(
        secret.encode(),
        _canonical(request.actor_id, request.nonce, request.timestamp, body),
        hashlib.sha256,
    ).hexdigest()
    return request.model_copy(update={"signature": signature})


def verify_payload(
    secret: str,
    signed: SignedRequest,
    body: bytes,
    replay_store: ReplayStore,
    now: int | None = None,
    window_seconds: int = 60,
) -> VerificationResult:
    current_time = now or int(time())
    if abs(current_time - signed.timestamp) > window_seconds:
        return VerificationResult(valid=False, reason="signature expired")
    if not replay_store.mark_seen(signed.actor_id, signed.nonce, signed.timestamp):
        return VerificationResult(valid=False, reason="replay detected")
    expected = hmac.new(
        secret.encode(),
        _canonical(signed.actor_id, signed.nonce, signed.timestamp, body),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected, signed.signature):
        return VerificationResult(valid=False, reason="signature mismatch")
    return VerificationResult(valid=True)

