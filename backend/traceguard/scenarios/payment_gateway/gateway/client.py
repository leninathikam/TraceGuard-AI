"""Resilient Payment Gateway API Client with HMAC Signing and Idempotency Tracking."""
from __future__ import annotations

import hashlib
import hmac
import time
import uuid
from typing import Any, Optional

from .config import GatewayConfig
from .models import CardDetails, Currency, Money, PaymentRequest, PaymentResponse, PaymentStatus


class GatewayAPIError(Exception):
    def __init__(self, message: str, code: str, http_status: int = 400):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


class PaymentGatewayClient:
    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self._processed_keys: dict[str, PaymentResponse] = {}
        self._circuit_failures = 0

    def _sign_payload(self, idempotency_key: str, amount_cents: int, currency: str) -> str:
        msg = f"{idempotency_key}:{amount_cents}:{currency}".encode("utf-8")
        return hmac.new(self.config.hmac_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    def authorize(self, request: PaymentRequest) -> PaymentResponse:
        """Simulate secure authorization endpoint with idempotency and token validation."""
        if self._circuit_failures >= self.config.circuit_breaker_threshold:
            raise GatewayAPIError("Circuit breaker tripped: gateway downstream unavailable", "CIRCUIT_OPEN", 503)

        # Idempotency check: if key seen, return cached immutable response
        if request.idempotency_key in self._processed_keys:
            return self._processed_keys[request.idempotency_key]

        # PCI-DSS token validation
        if not request.card.token.startswith("tok_"):
            raise GatewayAPIError("Invalid card token: token must be a vaulted token", "INVALID_TOKEN", 422)

        # Simulating test decline cards
        if request.card.last4 == "0002":
            resp = PaymentResponse(
                transaction_id=f"txn_{uuid.uuid4().hex[:12]}",
                idempotency_key=request.idempotency_key,
                status=PaymentStatus.DECLINED,
                authorized_amount=request.money,
                created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                error_code="CARD_DECLINED",
                error_message="Do not honor: insufficient funds on issuer",
            )
            self._processed_keys[request.idempotency_key] = resp
            return resp

        # Success path
        resp = PaymentResponse(
            transaction_id=f"txn_{uuid.uuid4().hex[:12]}",
            idempotency_key=request.idempotency_key,
            status=PaymentStatus.AUTHORIZED,
            authorized_amount=request.money,
            captured_amount=request.money,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
        self._processed_keys[request.idempotency_key] = resp
        return resp

    def refund(self, transaction_id: str, amount: Money, reason: str = "customer_request") -> PaymentResponse:
        """Process partial or full refund for settled transaction."""
        return PaymentResponse(
            transaction_id=f"ref_{uuid.uuid4().hex[:12]}",
            idempotency_key=f"idemp_{uuid.uuid4().hex[:8]}",
            status=PaymentStatus.REFUNDED,
            authorized_amount=amount,
            captured_amount=amount,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        )
