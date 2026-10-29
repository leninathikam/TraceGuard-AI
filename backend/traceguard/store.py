"""SQLite persistence. Rows hold the full Pydantic JSON plus a few indexed columns."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from pathlib import Path
from typing import Any

from .schema import Diagnosis, Finding, ModelCallInfo, Trace, Verification, utcnow

SCHEMA = """
CREATE TABLE IF NOT EXISTS traces (
  id TEXT PRIMARY KEY, workflow TEXT, scenario TEXT, final_status TEXT, created_at TEXT,
  source TEXT, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS findings (
  trace_id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS diagnoses (
  id TEXT PRIMARY KEY, trace_id TEXT, mode TEXT, category TEXT, created_at TEXT, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS verifications (
  id TEXT PRIMARY KEY, diagnosis_id TEXT, trace_id TEXT, status TEXT, created_at TEXT, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS llm_calls (
  id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, purpose TEXT, trace_id TEXT, model TEXT,
  attempts INTEGER, prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL,
  latency_ms REAL, ok INTEGER, error TEXT);
CREATE TABLE IF NOT EXISTS evaluations (
  id TEXT PRIMARY KEY, created_at TEXT, body TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: str | Path | None = None):
        self.path = str(path or os.environ.get("TRACEGUARD_DB", "traceguard.db"))
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _rows(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # traces
    def add_trace(self, trace: Trace, source: str = "api") -> Trace:
        trace.id = trace.id or f"tr_{uuid.uuid4().hex[:10]}"
        self._exec(
            "INSERT OR REPLACE INTO traces VALUES (?,?,?,?,?,?,?)",
            (trace.id, trace.workflow, trace.scenario, trace.final_status, trace.created_at, source,
             trace.model_dump_json()),
        )
        return trace

    def get_trace(self, trace_id: str) -> Trace | None:
        rows = self._rows("SELECT body FROM traces WHERE id=?", (trace_id,))
        return Trace.model_validate_json(rows[0]["body"]) if rows else None

    def list_traces(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._rows(
            "SELECT t.id, t.workflow, t.scenario, t.final_status, t.created_at, t.source, f.body AS findings,"
            " (SELECT COUNT(*) FROM diagnoses d WHERE d.trace_id=t.id) AS diagnoses,"
            " (SELECT status FROM verifications v WHERE v.trace_id=t.id ORDER BY created_at DESC LIMIT 1) AS last_verification"
            " FROM traces t LEFT JOIN findings f ON f.trace_id=t.id ORDER BY t.created_at DESC LIMIT ?",
            (limit,),
        )
        out = []
        for r in rows:
            findings = json.loads(r["findings"]) if r["findings"] else []
            out.append({
                "id": r["id"], "workflow": r["workflow"], "scenario": r["scenario"],
                "final_status": r["final_status"], "created_at": r["created_at"], "source": r["source"],
                "finding_count": len(findings),
                "categories": sorted({f["category"] for f in findings}),
                "diagnoses": r["diagnoses"], "last_verification": r["last_verification"],
            })
        return out

    # findings
    def set_findings(self, trace_id: str, findings: list[Finding]) -> None:
        body = json.dumps([f.model_dump(mode="json") for f in findings])
        self._exec("INSERT OR REPLACE INTO findings VALUES (?,?)", (trace_id, body))

    def get_findings(self, trace_id: str) -> list[Finding]:
        rows = self._rows("SELECT body FROM findings WHERE trace_id=?", (trace_id,))
        return [Finding(**f) for f in json.loads(rows[0]["body"])] if rows else []

    # diagnoses
    def add_diagnosis(self, d: Diagnosis) -> Diagnosis:
        d.id = d.id or f"dx_{uuid.uuid4().hex[:10]}"
        self._exec(
            "INSERT OR REPLACE INTO diagnoses VALUES (?,?,?,?,?,?)",
            (d.id, d.trace_id, d.mode, d.category.value, d.created_at, d.model_dump_json()),
        )
        return d

    def get_diagnosis(self, diagnosis_id: str) -> Diagnosis | None:
        rows = self._rows("SELECT body FROM diagnoses WHERE id=?", (diagnosis_id,))
        return Diagnosis.model_validate_json(rows[0]["body"]) if rows else None

    def diagnoses_for(self, trace_id: str) -> list[Diagnosis]:
        rows = self._rows("SELECT body FROM diagnoses WHERE trace_id=? ORDER BY created_at DESC", (trace_id,))
        return [Diagnosis.model_validate_json(r["body"]) for r in rows]

    # verifications
    def add_verification(self, v: Verification) -> Verification:
        v.id = v.id or f"vf_{uuid.uuid4().hex[:10]}"
        self._exec(
            "INSERT OR REPLACE INTO verifications VALUES (?,?,?,?,?,?)",
            (v.id, v.diagnosis_id, v.trace_id, v.status, v.created_at, v.model_dump_json()),
        )
        return v

    def verifications_for(self, trace_id: str) -> list[Verification]:
        rows = self._rows("SELECT body FROM verifications WHERE trace_id=? ORDER BY created_at DESC", (trace_id,))
        return [Verification.model_validate_json(r["body"]) for r in rows]

    # usage
    def log_llm_call(self, purpose: str, trace_id: str | None, info: ModelCallInfo | None,
                     model: str, ok: bool, error: str | None = None) -> None:
        self._exec(
            "INSERT INTO llm_calls (created_at, purpose, trace_id, model, attempts, prompt_tokens,"
            " completion_tokens, cost_usd, latency_ms, ok, error) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (utcnow(), purpose, trace_id, model, info.attempts if info else 0,
             info.prompt_tokens if info else 0, info.completion_tokens if info else 0,
             info.cost_usd if info else 0.0, info.latency_ms if info else 0.0, int(ok), error),
        )

    def usage(self) -> dict[str, Any]:
        rows = self._rows(
            "SELECT model, COUNT(*) n, SUM(ok) ok, SUM(prompt_tokens) pt, SUM(completion_tokens) ct,"
            " SUM(cost_usd) cost, AVG(latency_ms) lat FROM llm_calls GROUP BY model"
        )
        recent = self._rows("SELECT * FROM llm_calls ORDER BY id DESC LIMIT 20")
        return {
            "by_model": [dict(r) for r in rows],
            "recent": [dict(r) for r in recent],
        }

    # evaluations
    def add_evaluation(self, body: dict[str, Any]) -> str:
        eid = f"ev_{uuid.uuid4().hex[:10]}"
        self._exec("INSERT INTO evaluations VALUES (?,?,?)", (eid, utcnow(), json.dumps(body)))
        return eid

    def latest_evaluation(self) -> dict[str, Any] | None:
        rows = self._rows("SELECT id, created_at, body FROM evaluations ORDER BY created_at DESC LIMIT 1")
        if not rows:
            base_dir = Path(__file__).resolve()
            candidates = [
                base_dir.parents[2] / "results" / "evaluation-2026-10-29-upgrade.json",
                base_dir.parents[1] / "results" / "evaluation-2026-10-29-upgrade.json",
                base_dir.parents[2] / "results" / "evaluation.json",
                base_dir.parents[1] / "results" / "evaluation.json",
            ]
            for candidate in candidates:
                if candidate.is_file():
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        return {"id": f"ev_{candidate.stem}", "created_at": data.get("created_at", utcnow()), **data}
                    except Exception:
                        pass
            return None
        return {"id": rows[0]["id"], "created_at": rows[0]["created_at"], **json.loads(rows[0]["body"])}
