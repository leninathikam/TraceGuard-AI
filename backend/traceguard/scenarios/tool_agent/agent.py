"""Scenario A: a tool-calling scheduling agent.

The agent parses a booking request into typed slots, then fills the tool arguments from
tool_policy.json. The shipped policy maps slots to the wrong argument names and formats.
"""

import json
import re
import time

from _tracer import Tracer

TASK = "Book a meeting room for 6 people on October 28, 2026 at 2:30 PM for 90 minutes."

BOOK_ROOM_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
        "start_time": {"type": "string", "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"},
        "duration_minutes": {"type": "integer", "minimum": 15, "maximum": 480},
        "attendees": {"type": "integer", "minimum": 1, "maximum": 50},
    },
    "required": ["date", "start_time", "duration_minutes", "attendees"],
    "additionalProperties": False,
}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], start=1)}


class ToolError(Exception):
    pass


def book_room(**args):
    errors = []
    allowed = set(BOOK_ROOM_SCHEMA["properties"])
    for key in args:
        if key not in allowed:
            errors.append(f"unexpected argument '{key}'")
    for key in BOOK_ROOM_SCHEMA["required"]:
        if key not in args:
            errors.append(f"missing argument '{key}'")
    if "date" in args and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(args["date"])):
        errors.append("'date' must be YYYY-MM-DD")
    if "start_time" in args and not re.fullmatch(r"\d{2}:\d{2}", str(args["start_time"])):
        errors.append("'start_time' must be 24-hour HH:MM")
    for key in ("duration_minutes", "attendees"):
        if key in args and not isinstance(args[key], int):
            errors.append(f"'{key}' must be an integer")
    if errors:
        raise ToolError("ValidationError: " + "; ".join(errors))
    room = "Orion" if args["attendees"] <= 8 else "Atlas"
    return {"confirmation": f"BK-{args['date'].replace('-', '')}-{args['start_time'].replace(':', '')}",
            "room": room, **args}


def parse_request(text):
    m = re.search(r"(\d+) people on (\w+) (\d{1,2}), (\d{4}) at (\d{1,2}):(\d{2}) (AM|PM) for (\d+) minutes", text)
    people, month, day, year, hour, minute, ampm, minutes = m.groups()
    h24 = int(hour) % 12 + (12 if ampm == "PM" else 0)
    month_num = MONTHS[month.lower()]
    return {
        "attendees": int(people),
        "date_iso": f"{year}-{month_num:02d}-{int(day):02d}",
        "date_us": f"{month_num:02d}/{int(day):02d}/{year}",
        "time_24h": f"{h24:02d}:{minute}",
        "time_12h": f"{int(hour)}:{minute} {ampm}",
        "duration_minutes": int(minutes),
        "duration_text": f"{minutes} minutes",
    }


def fill(template, slots):
    args = {}
    for key, spec in template.items():
        whole = re.fullmatch(r"\{(\w+)\}", spec)
        args[key] = slots[whole.group(1)] if whole else spec.format(**slots)
    return args


def main():
    with open("tool_policy.json", encoding="utf-8") as fh:
        policy = json.load(fh)
    tracer = Tracer("scheduling-assistant", "tool_agent", TASK, {
        "tools": [{"name": "book_room", "description": "Reserve a meeting room.",
                   "parameters": BOOK_ROOM_SCHEMA}],
        "editable_files": ["tool_policy.json"],
        "agent_description": "Parses the request into slots, then fills tool arguments using "
                             "the argument_template in tool_policy.json. Slots available: "
                             "attendees, date_iso, date_us, time_24h, time_12h, duration_minutes, duration_text.",
    })
    tracer.event("agent_start", "scheduling-assistant", input={"task": TASK})
    slots = parse_request(TASK)
    tracer.event("agent_step", "parse_request", input={"text": TASK}, output={"slots": slots})
    args = fill(policy["argument_template"], slots)
    tracer.event("agent_step", "fill_tool_arguments",
                 input={"template": policy["argument_template"]}, output={"arguments": args})

    result, last_error = None, None
    for attempt in range(1 + policy.get("max_retries", 0)):
        call = tracer.event("tool_call", "book_room", input=args,
                            attributes={"attempt": attempt + 1, "backoff_ms": 0})
        t0 = time.perf_counter()
        try:
            result = book_room(**args)
            tracer.event("tool_result", "book_room", parent_id=call, output=result,
                         duration_ms=(time.perf_counter() - t0) * 1000)
            break
        except ToolError as exc:
            last_error = str(exc)
            tracer.event("tool_result", "book_room", parent_id=call, status="error", error=last_error,
                         attributes={"http_status": 422, "retryable": False},
                         duration_ms=(time.perf_counter() - t0) * 1000)

    if result:
        answer = f"Booked {result['room']} on {result['date']} at {result['start_time']} ({result['confirmation']})."
        tracer.event("output", "final_answer", output={"text": answer})
        status = "success"
    else:
        answer = f"Sorry, I could not book the room: {last_error}"
        tracer.event("output", "final_answer", output={"text": answer}, status="error", error=last_error)
        status = "failure"
    tracer.event("agent_end", "scheduling-assistant", output={"status": status})
    tracer.finish(status)
    with open("result.json", "w", encoding="utf-8") as fh:
        json.dump({"booking": result, "answer": answer}, fh)


if __name__ == "__main__":
    main()
