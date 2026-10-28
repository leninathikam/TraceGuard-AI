"""Scenario C: a coding agent that writes solution.py and runs the visible test suite.

The code the agent produced is checked in as solution.py; it multiplies seconds by 60 and
silently accepts invalid input.
"""

import io
import time
import unittest

from _tracer import Tracer

TASK = ("Implement parse_duration(text) in solution.py. It returns total seconds for strings "
        "such as '1h30m', '45s', '2h' and '1h5m10s', and raises ValueError for invalid input.")


def run_tests(module):
    stream = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName(module)
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    failures = [{"name": t.id().split(".")[-1], "trace": tb[-800:]} for t, tb in result.failures + result.errors]
    return result.testsRun, failures, stream.getvalue()


def main():
    with open("solution.py", encoding="utf-8") as fh:
        code = fh.read()
    tracer = Tracer("coding-agent", "coding_agent", TASK, {
        "editable_files": ["solution.py"],
        "code_files": ["solution.py"],
        "agent_description": "Generates solution.py for the task, writes it, and runs test_visible.py.",
    })
    tracer.event("agent_start", "coding-agent", input={"task": TASK})
    tracer.event("agent_step", "generate_code", input={"task": TASK}, output={"file": "solution.py", "code": code})
    call = tracer.event("tool_call", "write_file", input={"path": "solution.py", "bytes": len(code)})
    tracer.event("tool_result", "write_file", parent_id=call, output={"written": True})

    t0 = time.perf_counter()
    try:
        total, failures, log = run_tests("test_visible")
        error = None
    except Exception as exc:  # import errors in solution.py surface here
        total, failures, log, error = 0, [{"name": "import", "trace": repr(exc)}], "", repr(exc)
    failed = len(failures)
    tracer.event("test_run", "test_visible", input={"command": "python -m unittest test_visible"},
                 output={"total": total, "failed": failed, "passed": total - failed,
                         "failures": failures, "log": log[-2000:]},
                 status="error" if failed or error else "ok", error=error,
                 duration_ms=(time.perf_counter() - t0) * 1000)
    status = "success" if not failed and not error else "failure"
    tracer.event("output", "final_answer",
                 output={"text": f"{total - failed}/{total} visible tests passing."})
    tracer.event("agent_end", "coding-agent", output={"status": status})
    tracer.finish(status)


if __name__ == "__main__":
    main()
