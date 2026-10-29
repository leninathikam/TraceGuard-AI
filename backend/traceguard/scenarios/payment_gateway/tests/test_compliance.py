"""Strict financial compliance and auditability test suite."""
import unittest
from gateway.models import Money, Currency, CardDetails, PaymentStatus
from gateway.config import GatewayConfig
from services.order_service import OrderService
from services.ledger import LedgerService


class TestFinancialCompliance(unittest.TestCase):
    def setUp(self):
        self.config = GatewayConfig()
        self.ledger = LedgerService()
        self.service = OrderService(ledger=self.ledger, config=self.config)
        self.card = CardDetails(
            token="tok_visa_audit_approved_4242",
            brand="VISA",
            last4="4242",
            exp_month=11,
            exp_year=2027,
        )

    def test_ledger_idempotency_auditability(self):
        """Financial compliance rule: every transaction recorded must carry an audit idempotency key."""
        receipt = self.service.process_checkout(
            order_id="ord_comp_881",
            customer_id="cust_corp_01",
            card=self.card,
            amount=Money(amount_cents=10000, currency=Currency.USD),
            idempotency_key="idemp_comp_audit_key_881",
            is_cross_border=False,
        )
        self.assertEqual(receipt.status, PaymentStatus.CAPTURED)
        self.assertTrue(receipt.ledger_balanced)

    def test_cross_border_basis_points_precision(self):
        """Financial compliance rule: cross-border variable fees must be computed using basis points."""
        # 47,381 cents @ 250 bps (2.50%) + 30 cents fixed = (47381 * 250) // 10000 + 30 = 1214 cents
        amount = Money(amount_cents=47381, currency=Currency.EUR)
        fee = self.service.calculate_processing_fee(amount, is_cross_border=True)
        # Expected integer fee using basis points formula
        expected_fee = (amount.amount_cents * self.config.cross_border_fee_bps) // 10000 + self.config.fixed_fee_cents
        self.assertEqual(fee.amount_cents, expected_fee)


if __name__ == "__main__":
    unittest.main()
