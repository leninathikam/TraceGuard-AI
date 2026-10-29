"""Order Service orchestrator coordinating payment capture, currency fees, and ledger accounting."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from gateway.client import PaymentGatewayClient
from gateway.config import GatewayConfig
from gateway.models import CardDetails, Currency, Money, PaymentRequest, PaymentResponse, PaymentStatus
from services.ledger import LedgerService


class OrderReceipt:
    def __init__(
        self,
        order_id: str,
        status: PaymentStatus,
        charged_amount: Money,
        fee_amount: Money,
        transaction_id: str,
        ledger_balanced: bool,
    ):
        self.order_id = order_id
        self.status = status
        self.charged_amount = charged_amount
        self.fee_amount = fee_amount
        self.transaction_id = transaction_id
        self.ledger_balanced = ledger_balanced


class OrderService:
    def __init__(self, client: Optional[PaymentGatewayClient] = None, ledger: Optional[LedgerService] = None, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self.client = client or PaymentGatewayClient(self.config)
        self.ledger = ledger or LedgerService()

    def calculate_processing_fee(self, amount: Money, is_cross_border: bool = False) -> Money:
        """Calculate processing fee in exact integer minor units (cents)."""
        # BUG: Floating-point division and omission of basis points formula causes precision loss
        if is_cross_border:
            fee_pct = 2.5
            variable_fee = int(amount.amount_cents * (fee_pct / 100.0))
        else:
            variable_fee = 0
        total_fee_cents = variable_fee + self.config.fixed_fee_cents
        return Money(amount_cents=total_fee_cents, currency=amount.currency)

    def process_checkout(
        self,
        order_id: str,
        customer_id: str,
        card: CardDetails,
        amount: Money,
        idempotency_key: str,
        is_cross_border: bool = False,
    ) -> OrderReceipt:
        """Execute atomic checkout with payment gateway and balance ledger entries."""
        req = PaymentRequest(
            idempotency_key=idempotency_key,
            order_id=order_id,
            customer_id=customer_id,
            money=amount,
            card=card,
        )

        resp = self.client.authorize(req)
        if resp.status != PaymentStatus.AUTHORIZED:
            return OrderReceipt(
                order_id=order_id,
                status=resp.status,
                charged_amount=amount,
                fee_amount=Money(amount_cents=0, currency=amount.currency),
                transaction_id=resp.transaction_id,
                ledger_balanced=True,
            )

        fee = self.calculate_processing_fee(amount, is_cross_border=is_cross_border)

        # BUG: Fails to pass the idempotency_key to the ledger service (passes empty string)
        self.ledger.record_transaction(
            order_id=order_id,
            idempotency_key="",
            gross_amount=amount,
            fee_amount=fee,
            status=PaymentStatus.CAPTURED,
        )

        return OrderReceipt(
            order_id=order_id,
            status=PaymentStatus.CAPTURED,
            charged_amount=amount,
            fee_amount=fee,
            transaction_id=resp.transaction_id,
            ledger_balanced=self.ledger.verify_ledger_balanced(),
        )
