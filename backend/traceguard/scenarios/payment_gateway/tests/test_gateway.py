"""Unit and integration test suite for payment gateway client and models."""
import unittest
from gateway.models import Money, Currency, CardDetails, PaymentRequest, PaymentStatus
from gateway.client import PaymentGatewayClient, GatewayAPIError
from gateway.config import GatewayConfig


class TestPaymentGateway(unittest.TestCase):
    def setUp(self):
        self.config = GatewayConfig()
        self.client = PaymentGatewayClient(self.config)
        self.valid_card = CardDetails(
            token="tok_visa_4242_standard_vault",
            brand="VISA",
            last4="4242",
            exp_month=12,
            exp_year=2028,
        )

    def test_money_addition_and_subtraction(self):
        m1 = Money(amount_cents=1500, currency=Currency.USD)
        m2 = Money(amount_cents=550, currency=Currency.USD)
        total = m1.add(m2)
        self.assertEqual(total.amount_cents, 2050)
        diff = m1.subtract(m2)
        self.assertEqual(diff.amount_cents, 950)

    def test_money_currency_mismatch_raises(self):
        m1 = Money(amount_cents=1000, currency=Currency.USD)
        m2 = Money(amount_cents=1000, currency=Currency.EUR)
        with self.assertRaises(ValueError):
            m1.add(m2)

    def test_payment_authorization_success(self):
        req = PaymentRequest(
            idempotency_key="idemp_unit_test_901",
            order_id="ord_test_01",
            customer_id="cust_999",
            money=Money(amount_cents=4999, currency=Currency.USD),
            card=self.valid_card,
        )
        resp = self.client.authorize(req)
        self.assertEqual(resp.status, PaymentStatus.AUTHORIZED)
        self.assertEqual(resp.authorized_amount.amount_cents, 4999)

    def test_idempotent_authorization_replay(self):
        req = PaymentRequest(
            idempotency_key="idemp_repeat_key_111",
            order_id="ord_test_02",
            customer_id="cust_999",
            money=Money(amount_cents=1200, currency=Currency.USD),
            card=self.valid_card,
        )
        resp1 = self.client.authorize(req)
        resp2 = self.client.authorize(req)
        self.assertEqual(resp1.transaction_id, resp2.transaction_id)


if __name__ == "__main__":
    unittest.main()
