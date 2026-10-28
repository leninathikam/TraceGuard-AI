import { useCallback, useEffect, useState } from "react";
import { api, Scenario, TraceSummary } from "../api";
import { Badge, Card, Status, label } from "../ui";

export default function Overview() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importText, setImportText] = useState("");
  const [showImport, setShowImport] = useState(false);

  const refresh = useCallback(() => {
    api.traces().then(setTraces).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    api.scenarios().then(setScenarios).catch((e) => setError(e.message));
    refresh();
  }, [refresh]);

  async function run(id: string) {
    setBusy(id);
    setError(null);
    try {
      const r = await api.runScenario(id);
      window.location.hash = `#/trace/${r.trace_id}`;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function importTrace() {
    setError(null);
    try {
      const r = await api.ingest(importText);
      window.location.hash = `#/trace/${r.trace_id}`;
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="stack">
      <header className="hero">
        <h1>Agent reliability, verified.</h1>
        <p>
          TraceGuard ingests agent execution traces, pinpoints the root cause with deterministic detectors and
          NVIDIA Nemotron on Nebius Token Factory, then proves a repair works by replaying the agent in a sandbox.
        </p>
      </header>

      {error && <div className="alert bad">{error}</div>}

      <div className="grid3">
        {scenarios.map((s) => (
          <Card key={s.id} title={s.title}>
            <p className="dim small">{s.summary}</p>
            <div className="row between">
              <span className="dim small mono">edits: {s.editable_files.join(", ")}</span>
              <button onClick={() => run(s.id)} disabled={busy !== null}>
                {busy === s.id ? "Running…" : "Run workflow"}
              </button>
            </div>
          </Card>
        ))}
      </div>

      <Card
        title="Traces"
        actions={
          <>
            <button className="ghost" onClick={() => setShowImport(!showImport)}>Import trace JSON</button>
            <button className="ghost" onClick={refresh}>Refresh</button>
          </>
        }
      >
        {showImport && (
          <div className="stack import">
            <textarea
              placeholder='{"workflow": "my-agent", "task": "...", "metadata": {"tools": [...]}, "events": [...]}'
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
            />
            <div className="row">
              <button onClick={importTrace} disabled={!importText.trim()}>Ingest</button>
              <span className="dim small">TraceGuard schema; OTLP GenAI spans go to POST /api/traces/otlp.</span>
            </div>
          </div>
        )}
        {traces.length === 0 ? (
          <p className="dim">No traces yet. Run a workflow above.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Trace</th><th>Workflow</th><th>Agent reported</th><th>Findings</th><th>Diagnoses</th><th>Repair</th><th>Created</th>
              </tr>
            </thead>
            <tbody>
              {traces.map((t) => (
                <tr key={t.id} className="clickable" onClick={() => (window.location.hash = `#/trace/${t.id}`)}>
                  <td className="mono">{t.id}</td>
                  <td>{t.workflow} {t.source !== "scenario" && <Badge tone="muted">{t.source}</Badge>}</td>
                  <td><Status value={t.final_status} /></td>
                  <td>
                    {t.finding_count === 0 ? <Badge tone="good">clean</Badge>
                      : t.categories.map((c) => <Badge key={c} tone="bad">{label(c)}</Badge>)}
                  </td>
                  <td>{t.diagnoses}</td>
                  <td><Status value={t.last_verification} /></td>
                  <td className="dim small">{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
