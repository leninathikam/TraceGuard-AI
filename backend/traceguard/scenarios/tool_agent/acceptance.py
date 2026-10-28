import json


def main():
    checks = []
    with open("result.json", encoding="utf-8") as fh:
        result = json.load(fh)
    with open("trace.json", encoding="utf-8") as fh:
        trace = json.load(fh)
    booking = result.get("booking") or {}
    checks.append(("booking_confirmed", bool(booking.get("confirmation")), result.get("answer", "")))
    expected = {"date": "2026-10-28", "start_time": "14:30", "duration_minutes": 90, "attendees": 6}
    wrong = {k: booking.get(k) for k, v in expected.items() if booking.get(k) != v}
    checks.append(("booking_matches_request", not wrong, f"mismatched: {wrong}" if wrong else "all fields match"))
    calls = [e for e in trace["events"] if e["kind"] == "tool_call"]
    checks.append(("at_most_one_tool_call", len(calls) <= 1, f"{len(calls)} tool call(s)"))
    errors = [e for e in trace["events"] if e["kind"] == "tool_result" and e["status"] == "error"]
    checks.append(("no_tool_errors", not errors, f"{len(errors)} tool error(s)"))
    print(json.dumps([{"name": n, "passed": p, "detail": d} for n, p, d in checks]))


if __name__ == "__main__":
    main()
