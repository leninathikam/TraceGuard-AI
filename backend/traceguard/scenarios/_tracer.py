"""Stdlib-only tracer copied into each sandbox so agents can emit TraceGuard traces."""

import json
import time


class Tracer:
    def __init__(self, workflow, scenario, task, metadata=None):
        self.trace = {
            "workflow": workflow,
            "scenario": scenario,
            "task": task,
            "metadata": metadata or {},
            "events": [],
            "final_status": "unknown",
        }
        self._seq = 0

    def event(self, kind, name, input=None, output=None, status="ok", error=None,
              parent_id=None, tokens_in=0, tokens_out=0, attributes=None, duration_ms=0.0):
        self._seq += 1
        eid = f"e{self._seq:03d}"
        self.trace["events"].append({
            "id": eid, "seq": self._seq, "kind": kind, "name": name, "parent_id": parent_id,
            "input": input or {}, "output": output, "status": status, "error": error,
            "duration_ms": round(duration_ms, 3), "tokens_in": tokens_in, "tokens_out": tokens_out,
            "attributes": attributes or {},
        })
        return eid

    def timed(self):
        return time.perf_counter()

    def finish(self, status, path="trace.json"):
        self.trace["final_status"] = status
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.trace, fh, indent=2)
