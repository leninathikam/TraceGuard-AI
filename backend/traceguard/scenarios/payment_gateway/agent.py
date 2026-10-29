"""Autonomous enterprise checkout agent."""
import json
import time
from _tracer import Tracer
from gateway.models import Money, Currency, CardDetails
from services.order_service import OrderService

TASK = "Process enterprise multi-currency checkout for Order ORD-9921 with financial compliance verification."


def main():
    tracer = Tracer(
        workflow="enterprise-checkout-service",
        scenario="payment_gateway",
        task=TASK,
        metadata={
            "agent_description": "Enterprise microservice coordinating payment authorization, cross-border fee computation, and double-entry general ledger accounting across a multi-file repository.",
            "tools": [
                {
                    "name": "process_checkout",
                    "description": "Execute atomic checkout with payment gateway and balance ledger entries.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string"},
                            "amount_cents": {"type": "integer"},
                            "currency": {"type": "string"},
                            "idempotency_key": {"type": "string"},
                        },
                        "required": ["order_id", "amount_cents", "currency", "idempotency_key"],
                    },
                }
            ],
            "editable_files": ["services/order_service.py"],
            "code_files": ["services/order_service.py"],
            "context_files": [
                "services/order_service.py",
                "gateway/models.py",
                "gateway/client.py",
                "services/ledger.py",
                "tests/test_compliance.py",
            ],
        },
    )

    tracer.event("agent_start", "enterprise-checkout-service", input={"task": TASK})

    card = CardDetails(
        token="tok_visa_audit_approved_4242",
        brand="VISA",
        last4="4242",
        exp_month=11,
        exp_year=2027,
    )
    amount = Money(amount_cents=10000, currency=Currency.USD)
    idempotency_key = "idemp_ord_9921_init"

    step = tracer.event("agent_step", "validate_order_parameters", input={"order_id": "ORD-9921", "amount_cents": 10000, "currency": "USD"})

    call = tracer.event(
        "tool_call",
        "process_checkout",
        parent_id=step,
        input={"order_id": "ORD-9921", "amount_cents": 10000, "currency": "USD", "idempotency_key": idempotency_key},
    )

    service = OrderService()
    error_msg = None
    receipt = None
    t0 = time.perf_counter()

    try:
        receipt = service.process_checkout(
            order_id="ORD-9921",
            customer_id="cust_enterprise_01",
            card=card,
            amount=amount,
            idempotency_key=idempotency_key,
            is_cross_border=False,
        )
        tracer.event(
            "tool_result",
            "process_checkout",
            parent_id=call,
            output={"transaction_id": receipt.transaction_id, "status": receipt.status.value, "ledger_balanced": receipt.ledger_balanced},
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        status = "success"
        final_text = f"Order ORD-9921 settled successfully: tx={receipt.transaction_id}"
    except Exception as exc:
        error_msg = str(exc)
        tracer.event(
            "tool_result",
            "process_checkout",
            parent_id=call,
            status="error",
            error=error_msg,
            duration_ms=(time.perf_counter() - t0) * 1000,
        )
        tracer.event(
            "test_run",
            "compliance_verification",
            parent_id=call,
            status="error",
            error=error_msg,
            output={
                "total": 6,
                "passed": 5,
                "failed": 1,
                "failures": [{"name": "test_compliance:test_ledger_idempotency_auditability", "message": error_msg}],
            },
        )
        status = "failure"
        final_text = f"Order ORD-9921 failed compliance: {error_msg}"

    tracer.event("output", "final_receipt", output={"text": final_text}, status="ok" if status == "success" else "error", error=error_msg)
    tracer.event("agent_end", "enterprise-checkout-service", output={"status": status})
    tracer.finish(status)

    with open("result.json", "w", encoding="utf-8") as fh:
        json.dump({"order_id": "ORD-9921", "status": status, "error": error_msg}, fh)


if __name__ == "__main__":
    main()
