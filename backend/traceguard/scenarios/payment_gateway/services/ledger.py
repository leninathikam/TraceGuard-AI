"""Double-entry general ledger service recording balanced journal transactions."""
from __future__ import annotations

import time
import uuid
from typing import Optional
from gateway.models import Currency, Money, PaymentStatus, TransactionRecord


class LedgerEntry:
    def __init__(self, entry_id: str, account: str, debit_cents: int, credit_cents: int, currency: Currency):
        self.entry_id = entry_id
        self.account = account
        self.debit_cents = debit_cents
        self.credit_cents = credit_cents
        self.currency = currency


class LedgerService:
    def __init__(self):
        self._journal: list[LedgerEntry] = []
        self._transactions: dict[str, TransactionRecord] = {}
        self._idempotency_records: set[str] = set()

    def record_transaction(
        self,
        order_id: str,
        idempotency_key: str,
        gross_amount: Money,
        fee_amount: Money,
        status: PaymentStatus = PaymentStatus.CAPTURED,
    ) -> TransactionRecord:
        """Record double-entry transaction. Debits Cash, Credits Merchant and Processing Fees."""
        if not idempotency_key:
            raise ValueError("idempotency_key must be provided for financial ledger auditability")

        if idempotency_key in self._idempotency_records:
            # Replay protection: return existing record
            return self._transactions[idempotency_key]

        net_cents = gross_amount.amount_cents - fee_amount.amount_cents
        if net_cents < 0:
            raise ValueError("Fee cannot exceed gross transaction amount")

        tx_id = f"ldg_{uuid.uuid4().hex[:10]}"
        now = time.time()

        # Double-entry entries:
        # Debit: Cash Account (+gross)
        # Credit: Merchant Account (+net)
        # Credit: Platform Revenue (+fee)
        self._journal.append(LedgerEntry(f"{tx_id}_deb", "assets:cash", gross_amount.amount_cents, 0, gross_amount.currency))
        self._journal.append(LedgerEntry(f"{tx_id}_cr1", "liabilities:merchant_settlement", 0, net_cents, gross_amount.currency))
        self._journal.append(LedgerEntry(f"{tx_id}_cr2", "revenue:processing_fees", 0, fee_amount.amount_cents, gross_amount.currency))

        rec = TransactionRecord(
            id=tx_id,
            order_id=order_id,
            idempotency_key=idempotency_key,
            status=status,
            amount_cents=gross_amount.amount_cents,
            currency=gross_amount.currency,
            fee_cents=fee_amount.amount_cents,
            timestamp=now,
        )
        self._transactions[idempotency_key] = rec
        self._idempotency_records.add(idempotency_key)
        return rec

    def verify_ledger_balanced(self) -> bool:
        """Verify the accounting invariant: Total Debits == Total Credits."""
        debits = sum(e.debit_cents for e in self._journal)
        credits = sum(e.credit_cents for e in self._journal)
        return debits == credits
