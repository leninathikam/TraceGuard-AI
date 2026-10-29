import { speak } from "../VoiceOperator";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, Diagnosis, Health, TraceDetail, TraceEvent, Verification } from "../api";
import { Badge, Card, Diff, Json, Status, label, ms, usd } from "../ui";

const MODES = [
  { id: "hybrid", name: "Hybrid", hint: "Rule evidence + Nemotron reasoning" },
  { id: "model", name: "Nemotron only", hint: "Model sees the raw trace only" },
  { id: "rules", name: "Rules only", hint: "Deterministic detectors, no model" },
];

export default function TraceView({ id, health }: { id: string; health: Health | null }) {
  const [data, setData] = useState<TraceDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState("hybrid");
  const [busy, setBusy] = useState<"diagnose" | "verify" | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<string[]>([]);

  const load = useCallback(() => {
    api.trace(id).then(setData).catch((e) => setError(e.message));
  }, [id]);
  useEffect(load, [load]);

  const flagged = useMemo(() => {
    const m = new Map<string, string>();
    data?.findings.forEach((f) => f.event_ids.forEach((e) => m.has(e) || m.set(e, f.severity)));
    return m;
  }, [data]);

  if (error) return <div className="alert bad">{error}</div>;
  if (!data) return <p className="dim">Loading…</p>;

  const { trace, findings, diagnoses, verifications } = data;
  const diagnosis = diagnoses[0];
  const verification = diagnosis ? verifications.find((v) => v.diagnosis_id === diagnosis.id) : undefined;
  const root = findings.find((f) => !f.is_symptom_of);
  const silent = trace.final_status === "success" && findings.length > 0;

  async function runDiagnosis() {
    setBusy("diagnose");
    setError(null);
    try {
      await api.diagnose(id, mode);
      load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function runVerify(d: Diagnosis) {
    setBusy("verify");
    try {
      await api.verify(d.id);
      load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="stack">
      <div className="row between">
        <div>
          <a href="#/" className="dim small">← Workflows</a>
          <h2>{trace.workflow} <span className="mono dim small">{trace.id}</span></h2>
          <p className="dim">{trace.task}</p>
          <a className="small" href={`/api/traces/${id}/evidence`} download>Download evidence JSON</a>
          {trace.metadata.agent_origin === 'live_nebius_generation' &&
            <p className="small dim">Live Nebius generation captured. Verification replays the frozen code artifact.</p>}
        </div>
      </div>

      <section className={`summary ${findings.length ? "bad" : "good"}`}>
        <div>
          <div className="eyebrow">Agent reported</div>
          <Status value={trace.final_status} />
        </div>
        <div className="grow">
          <div className="eyebrow">{findings.length ? "What failed" : "Result"}</div>
          {root ? (
            <strong>{root.title}</strong>
          ) : (
            <strong>No deterministic findings{diagnosis?.category && diagnosis.category !== "none" ? "; see AI diagnosis" : ""}</strong>
          )}
          {silent && <div className="small warn-text">Silent failure: the agent believed it succeeded.</div>}
        </div>
        <div>
          <div className="eyebrow">Why (current diagnosis)</div>
          {diagnosis ? <span>{label(diagnosis.category)} · <Status value={diagnosis.hypothesis_status} /></span> : <span className="dim">not diagnosed</span>}
        </div>
        <div>
          <div className="eyebrow">Repair</div>
          <Status value={verification?.status ?? null} />
        </div>
      </section>

      <div className="split">
        <Card title={`Trace timeline · ${trace.events.length} events`}>
          <ol className="timeline">
            {trace.events.map((e) => (
              <TimelineItem
                key={e.id}
                event={e}
                severity={flagged.get(e.id)}
                highlighted={highlight.includes(e.id)}
                open={selected === e.id}
                onClick={() => setSelected(selected === e.id ? null : e.id)}
              />
            ))}
          </ol>
        </Card>

        <div className="stack">
          <Card title={`Failure inspector · ${findings.length}`}>
            {findings.length === 0 && <p className="dim">No structural failures detected. Semantic issues need the model.</p>}
            {findings.map((f, i) => (
              <div key={i} className="finding" onMouseEnter={() => setHighlight(f.event_ids)} onMouseLeave={() => setHighlight([])}>
                <div className="row between">
                  <strong>{f.title}</strong>
                  <Status value={f.severity} />
                </div>
                <div className="small">{f.detail}</div>
                <div className="row small dim">
                  <span className="mono">{label(f.category)}</span>
                  <span>events {f.event_ids.join(", ")}</span>
                  {f.is_symptom_of && <Badge tone="muted">symptom of {label(f.is_symptom_of)}</Badge>}
                </div>
              </div>
            ))}
          </Card>

          <Card
            title="AI diagnosis"
            actions={
              <>
                <select value={mode} onChange={(e) => setMode(e.target.value)} title={MODES.find((m) => m.id === mode)?.hint}>
                  {MODES.map((m) => <option key={m.id} value={m.id}>{m.name}</option>)}
                </select>
                <button onClick={runDiagnosis} disabled={busy !== null}>
                  {busy === "diagnose" ? "Diagnosing…" : "Diagnose"}
                </button>
              </>
            }
          >
            {mode !== "rules" && health && !health.nebius_configured && (
              <div className="alert warn small">NEBIUS_API_KEY is not set on the server; Nemotron modes will fail or fall back to rules.</div>
            )}
            {busy === "diagnose" && mode !== "rules" && <p className="dim small">Calling {health?.model} on Nebius Token Factory…</p>}
            {diagnosis ? (
              <DiagnosisView d={diagnosis} onHover={setHighlight} />
            ) : (
              <p className="dim">Run a diagnosis to get a root-cause hypothesis and repair proposal.</p>
            )}
          </Card>

          {diagnosis && (
            <Card
              title="Repair proposal"
              actions={
                diagnosis.repair.edits.length > 0 && data.scenario ? (
                  <button onClick={() => runVerify(diagnosis)} disabled={busy !== null}>
                    {busy === "verify" ? "Replaying in sandbox…" : "Verify in sandbox"}
                  </button>
                ) : null
              }
            >
              <p>{diagnosis.repair.summary}</p>
              {diagnosis.repair.edits.length === 0 && (
                <p className="dim small">No concrete edits proposed, so this repair cannot be replay-verified.</p>
              )}
              {diagnosis.repair.edits.length > 0 && !data.scenario && (
                <p className="dim small">Imported trace: no workspace to replay against. Review the edits manually.</p>
              )}
              {verification?.diff ? <Diff text={verification.diff} /> : diagnosis.repair.edits.map((e, i) => (
                <div key={i} className="small">
                  <div className="mono dim">{e.path}</div>
                  <Diff text={(e.find ? e.find.split("\n").map((l) => "-" + l) : ["-(entire file)"]).concat(e.replace.split("\n").map((l) => "+" + l)).join("\n")} />
                </div>
              ))}
              <ol className="small dim">
                {diagnosis.verification_procedure.map((s, i) => <li key={i}>{s}</li>)}
              </ol>
            </Card>
          )}

          {verification && <VerificationView v={verification} />}
        </div>
      </div>
    </div>
  );
}

function TimelineItem({ event: e, severity, highlighted, open, onClick }: {
  event: TraceEvent; severity?: string; highlighted: boolean; open: boolean; onClick: () => void;
}) {
  const summary = e.error ?? summarize(e);
  return (
    <li className={`tl ${e.status} ${severity ? "flag-" + severity : ""} ${highlighted ? "hl" : ""}`}>
      <button className="tl-head" onClick={onClick}>
        <span className="mono dim">{e.id}</span>
        <span className={`kind k-${e.kind}`}>{label(e.kind)}</span>
        <strong>{e.name}</strong>
        {e.parent_id && <span className="dim small">← {e.parent_id}</span>}
        <span className="spacer" />
        {e.tokens_in + e.tokens_out > 0 && <span className="dim small">{(e.tokens_in + e.tokens_out).toLocaleString()} tok</span>}
        {e.duration_ms > 0 && <span className="dim small">{ms(e.duration_ms)}</span>}
      </button>
      {summary && <div className={`tl-sum small ${e.status === "error" ? "bad-text" : "dim"}`}>{summary}</div>}
      {open && (
        <div className="tl-body">
          {Object.keys(e.input).length > 0 && <><div className="eyebrow">input</div><Json value={e.input} /></>}
          {e.output && <><div className="eyebrow">output</div><Json value={e.output} /></>}
          {Object.keys(e.attributes).length > 0 && <><div className="eyebrow">attributes</div><Json value={e.attributes} /></>}
        </div>
      )}
    </li>
  );
}

function summarize(e: TraceEvent): string {
  const o = e.output ?? {};
  if (typeof o.text === "string") return o.text.slice(0, 160);
  if (e.kind === "tool_call") return JSON.stringify(e.input).slice(0, 160);
  if (e.kind === "test_run") return `${o.passed}/${o.total} passed`;
  if (e.kind === "retrieval") return `${(o.documents as unknown[] | undefined)?.length ?? 0} documents`;
  return "";
}

function DiagnosisView({ d, onHover }: { d: Diagnosis; onHover: (ids: string[]) => void }) {
  return (
    <div className="stack tight">
      <div className="row">
        <Badge tone="accent">{d.mode === "model" ? "Nemotron only" : d.mode === "hybrid" ? "Hybrid" : "Rules only"}</Badge>
        <Badge tone="bad">{label(d.category)}</Badge>
        <Status value={d.hypothesis_status} />
        <Badge tone="muted">confidence: {d.confidence}</Badge>
      </div>
      {d.fallback_reason && <div className="alert warn small">{d.fallback_reason}</div>}
      <div className="row" style={{ alignItems: "center", gap: "8px" }}>
        <p className="hypothesis" style={{ margin: 0, flex: 1 }}>{d.root_cause_hypothesis}</p>
        <button
          className="ghost small"
          onClick={() => speak(`Root cause hypothesis: ${d.root_cause_hypothesis}. Confidence is ${d.confidence}.`)}
          style={{ padding: "2px 8px", fontSize: "11px", whiteSpace: "nowrap" }}
          title="Audio readback of hypothesis"
        >
          Read Aloud
        </button>
      </div>
      <div className="small" onMouseEnter={() => onHover(d.supporting_event_ids)} onMouseLeave={() => onHover([])}>
        <span className="dim">Evidence: </span>
        {d.supporting_event_ids.map((i) => <span key={i} className="mono chip">{i}</span>)}
      </div>
      <div className="small"><span className="dim">Confidence rationale: </span>{d.confidence_rationale}</div>
      <div className="small"><span className="dim">Limitations: </span>{d.limitations}</div>
      {d.hypothesis_status === "hypothesis" && (
        <div className="small dim">This is a hypothesis until a repair based on it passes sandbox replay.</div>
      )}
      {d.model_call && (
        <div className="meta-row small">
          <span className="mono">{d.model_call.model}</span>
          <span>{(d.model_call.prompt_tokens + d.model_call.completion_tokens).toLocaleString()} tokens</span>
          <span>{usd(d.model_call.cost_usd)}</span>
          <span>{ms(d.model_call.latency_ms)}</span>
          <span>{d.model_call.attempts} attempt{d.model_call.attempts > 1 ? "s" : ""}</span>
          {d.model_call.validation_errors.length > 0 && (
            <span title={d.model_call.validation_errors.join("\n")} className="warn-text">
              {d.model_call.validation_errors.length} validation error(s) corrected
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function VerificationView({ v }: { v: Verification }) {
  const names = Array.from(new Set([...(v.baseline?.checks ?? []), ...(v.repaired?.checks ?? [])].map((c) => c.name)));
  const get = (run: typeof v.baseline, n: string) => run?.checks.find((c) => c.name === n);
  return (
    <Card title={<>Replay results <Status value={v.status} /></>}>
      <p>{v.reason}</p>
      {v.causal_scope && <p className="dim small">{v.causal_scope}</p>}
      {!!v.intervention_tests?.length && <div className="stack tight">
        <strong>Controlled interventions</strong>
        {v.intervention_tests.map((test) => <p className="small" key={test.omitted_edit}>
          Omit edit {test.omitted_edit + 1}{test.path ? ` (${test.path})` : ''}: <strong>{label(test.outcome)}</strong>
          {test.restored_failures?.length ? ` — ${test.restored_failures.join(', ')}` : ''}
          {test.error ? ` — ${test.error}` : ''}
        </p>)}
      </div>}
      {v.status === 'validated' && <p><a href={`/api/diagnoses/${v.diagnosis_id}/regression-test`} download>
        Download executable regression test</a></p>}
      {v.evidence_hashes && <details><summary className="small">Workspace and oracle SHA-256 hashes</summary>
        <Json value={v.evidence_hashes} /></details>}
      {names.length > 0 && (
        <table className="checks">
          <thead><tr><th>Acceptance check</th><th>Baseline</th><th>Repaired</th><th></th></tr></thead>
          <tbody>
            {names.map((n) => {
              const b = get(v.baseline, n), r = get(v.repaired, n);
              return (
                <tr key={n}>
                  <td className="mono small">{n}</td>
                  <td>{b ? <Badge tone={b.passed ? "good" : "bad"}>{b.passed ? "PASS" : "FAIL"}</Badge> : <span className="dim">—</span>}</td>
                  <td title={r?.detail}>{r ? <Badge tone={r.passed ? "good" : "bad"}>{r.passed ? "PASS" : "FAIL"}</Badge> : <span className="dim">—</span>}</td>
                  <td className="small">
                    {v.fixed_checks.includes(n) && <Badge tone="good">fixed</Badge>}
                    {v.regressions.includes(n) && <Badge tone="bad">regression</Badge>}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div className="meta-row small">
        {v.repaired && <span>sandbox: {v.repaired.sandbox}</span>}
        {v.repaired && <span>replay {ms(v.repaired.duration_ms)}</span>}
        {v.repaired_trace_id && <a href={`#/trace/${v.repaired_trace_id}`}>View replayed trace →</a>}
      </div>
    </Card>
  );
}
