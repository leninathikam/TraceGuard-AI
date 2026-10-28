import { useEffect, useState } from "react";
import { api, Evaluation, Health } from "../api";
import { Badge, Card, label, ms, pct, usd } from "../ui";

const MODE_NAMES: Record<string, string> = { rules: "A · Rules only", model: "B · Nemotron only", hybrid: "C · Hybrid" };

export default function EvaluationPage({ health }: { health: Health | null }) {
  const [ev, setEv] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.latestEvaluation().then(setEv).catch((e) => setError(e.message));
  }, []);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setEv(await api.runEvaluation(["rules", "model", "hybrid"]));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const modes = ev ? Object.keys(ev.diagnosis) : [];
  const caseIds = ev && modes.length ? ev.diagnosis[modes[0]].rows.map((r) => r.case) : [];

  return (
    <div className="stack">
      <div className="row between">
        <div>
          <h2>Evaluation</h2>
          <p className="dim">
            {caseIds.length || "26"} hand-labelled traces (structural, semantic, healthy and tricky) plus the three replayable
            scenarios. Model modes call {health?.model ?? "Nemotron"} live; nothing here is precomputed.
          </p>
        </div>
        <button onClick={run} disabled={busy}>{busy ? "Running (several minutes with model modes)…" : "Run evaluation"}</button>
      </div>
      {error && <div className="alert bad">{error}</div>}
      {!ev && <p className="dim">No evaluation yet.</p>}
      {ev && (
        <>
          <p className="dim small">Run {ev.id} · {new Date(ev.created_at).toLocaleString()} · model {ev.model}</p>
          {Object.entries(ev.skipped).map(([m, why]) => (
            <div key={m} className="alert warn small">{MODE_NAMES[m] ?? m}: skipped. {why}</div>
          ))}
          <div className="grid3">
            {modes.map((m) => {
              const s = ev.diagnosis[m];
              const r = ev.repairs[m];
              return (
                <Card key={m} title={MODE_NAMES[m] ?? m}>
                  <div className="metrics">
                    <Metric name="Root-cause accuracy" value={pct(s.root_cause_accuracy)} />
                    <Metric name="Detection precision" value={pct(s.failure_detection.precision)} />
                    <Metric name="Detection recall" value={pct(s.failure_detection.recall)} />
                    <Metric name="Median latency" value={ms(s.latency_ms_median)} />
                    {m !== "rules" && <Metric name="Cost / diagnosis" value={usd(s.cost_usd_per_diagnosis_mean)} />}
                    {m !== "rules" && <Metric name="Tokens / diagnosis" value={s.tokens_per_diagnosis_mean ? Math.round(s.tokens_per_diagnosis_mean).toLocaleString() : "n/a"} />}
                    {r && <Metric name="Valid repair proposals" value={pct(r.proposal_validity_rate)} />}
                    {r && <Metric name="Verified repairs" value={pct(r.verified_repair_rate)} />}
                    {r && <Metric name="Regression rate" value={pct(r.regression_rate)} />}
                    {s.invalid_or_failed_outputs > 0 && <Metric name="Invalid/failed outputs" value={String(s.invalid_or_failed_outputs)} />}
                  </div>
                  <div className="small dim">
                    By case type: {Object.entries(s.accuracy_by_kind).map(([k, v]) => `${k} ${pct(v)}`).join(" · ")}
                  </div>
                </Card>
              );
            })}
          </div>

          {Object.keys(ev.repairs).length > 0 && (
            <Card title="Verified Repair Loop on the three scenarios">
              <table>
                <thead><tr><th>Scenario</th>{Object.keys(ev.repairs).map((m) => <th key={m}>{MODE_NAMES[m] ?? m}</th>)}</tr></thead>
                <tbody>
                  {ev.repairs[Object.keys(ev.repairs)[0]].rows.map((row) => (
                    <tr key={row.scenario}>
                      <td className="mono">{row.scenario}</td>
                      {Object.keys(ev.repairs).map((m) => {
                        const cell = ev.repairs[m].rows.find((x) => x.scenario === row.scenario);
                        return (
                          <td key={m} title={cell?.reason ?? cell?.error}>
                            <Badge tone={cell?.status === "validated" ? "good" : cell?.status === "not_applicable" ? "muted" : "bad"}>
                              {label(cell?.status ?? "?")}
                            </Badge>
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          )}

          <Card title="Per-case root-cause predictions">
            <table>
              <thead>
                <tr><th>Case</th><th>Type</th><th>Expected</th>{modes.map((m) => <th key={m}>{MODE_NAMES[m] ?? m}</th>)}</tr>
              </thead>
              <tbody>
                {caseIds.map((cid) => {
                  const base = ev.diagnosis[modes[0]].rows.find((r) => r.case === cid)!;
                  return (
                    <tr key={cid}>
                      <td className="mono small">{cid}</td>
                      <td><Badge tone="muted">{base.kind}</Badge></td>
                      <td className="small">{label(base.expected)}</td>
                      {modes.map((m) => {
                        const r = ev.diagnosis[m].rows.find((x) => x.case === cid)!;
                        return (
                          <td key={m} className={`small ${r.correct ? "good-text" : "bad-text"}`} title={r.error ?? ""}>
                            {r.correct ? "✓ " : "✗ "}{label(r.predicted)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        </>
      )}
    </div>
  );
}

function Metric({ name, value }: { name: string; value: string }) {
  return (
    <div className="metric">
      <div className="metric-v">{value}</div>
      <div className="metric-n">{name}</div>
    </div>
  );
}
