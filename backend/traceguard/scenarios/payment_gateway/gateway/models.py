"""Domain entities and financial data models for the payment gateway."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class Currency(str, Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    JPY = "JPY"
    CAD = "CAD"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    SETTLED = "SETTLED"
    DECLINED = "DECLINED"
    REFUNDED = "REFUNDED"


class Money(BaseModel):
    """Immutable monetary representation in integer minor units (cents)."""
    amount_cents: int = Field(..., ge=0, description="Amount in minor units (e.g. cents, pence, yen)")
    currency: Currency = Currency.USD

    @classmethod
    def from_major(cls, major_amount: float, currency: Currency = Currency.USD) -> Money:
        # Strict integer rounding to avoid float drift
        cents = int(round(major_amount * 100))
        return cls(amount_cents=cents, currency=currency)

    def to_major(self) -> float:
        return self.amount_cents / 100.0

    def add(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Cannot add mismatched currencies: {self.currency} vs {other.currency}")
        return Money(amount_cents=self.amount_cents + other.amount_cents, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        if self.currency != other.currency:
            raise ValueError(f"Cannot subtract mismatched currencies: {self.currency} vs {other.currency}")
        if self.amount_cents < other.amount_cents:
            raise ValueError(f"Insufficient funds: {self.amount_cents} < {other.amount_cents}")
        return Money(amount_cents=self.amount_cents - other.amount_cents, currency=self.currency)


class CardDetails(BaseModel):
    token: str = Field(..., min_length=16, description="PCI-DSS compliant vaulted token (tok_*)")
    brand: str = "VISA"
    last4: str = "4242"
    exp_month: int = Field(..., ge=1, le=12)
    exp_year: int = Field(..., ge=2026)


class PaymentRequest(BaseModel):
    idempotency_key: str = Field(..., min_length=8)
    order_id: str
    customer_id: str
    money: Money
    card: CardDetails
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaymentResponse(BaseModel):
    transaction_id: str
    idempotency_key: str
    status: PaymentStatus
    authorized_amount: Money
    captured_amount: Optional[Money] = None
    fee_amount: Optional[Money] = None
    created_at: str
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class TransactionRecord(BaseModel):
    id: str
    order_id: str
    idempotency_key: str
    status: PaymentStatus
    amount_cents: int
    currency: Currency
    fee_cents: int
    timestamp: float
