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
  const [activeStage, setActiveStage] = useState<number | null>(null);

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
      const r = id === 'live' ? await api.runLiveAgent() : await api.runScenario(id);
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

  const pipelineStages = [
    {
      num: 1,
      title: "Trace Ingestion",
      tech: "OTEL GenAI / JSON",
      metric: "Zero-overhead spans",
      detail: "Captures full agent execution events (LLM calls, tool inputs, outputs, errors, and environment states) into immutable traces with OpenTelemetry compliance."
    },
    {
      num: 2,
      title: "AST & Rules",
      tech: "15 Deterministic Detectors",
      metric: "0.1 ms Latency",
      detail: "Scans for structural failures (schema violations, syntax crashes, missing context, hallucinated tools, broken retries) with 100% precision before model invocation."
    },
    {
      num: 3,
      title: "Nebius Nemotron",
      tech: "Nemotron-3-Super-120B",
      metric: "$0.00093 / diagnosis",
      detail: "Performs deep causal failure reasoning on Nebius Token Factory. Synthesizes cross-file dependencies and generates concrete, minimal code edits."
    },
    {
      num: 4,
      title: "MicroVM Sandbox",
      tech: "Docker / Isolated Proc",
      metric: "Air-gapped replay",
      detail: "Executes agent replay in an isolated microVM with network disabled, read-only rootfs, and strict compute quotas. Fails closed on broken baselines."
    },
    {
      num: 5,
      title: "Causal Ablation",
      tech: "Counterfactual Matrix",
      metric: "Leave-One-Out Proof",
      detail: "Mathematically proves causal necessity by omitting proposed edits one-by-one. Re-runs acceptance checks to prove the failure is restored."
    },
    {
      num: 6,
      title: "Pytest Witness",
      tech: "Cryptographic SHA-256",
      metric: "CI/CD Regression Test",
      detail: "Generates standalone, executable pytest witnesses embedding SHA-256 artifact hashes, allowing GitHub Actions to lock in the repair without LLM re-sampling."
    }
  ];

  return (
    <div className="stack" style={{ gap: "28px" }}>
      {/* Hero Header */}
      <header className="hero">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <h1 style={{ fontSize: "28px", fontWeight: "800", letterSpacing: "-0.5px" }}>Agent Reliability, Verified.</h1>
            <p style={{ maxWidth: "800px", fontSize: "15px", lineHeight: "1.6" }}>
              TraceGuard transforms AI agent failure diagnosis from untrusted LLM guesses into scientifically verified, causally proven repairs. Powered by NVIDIA Nemotron-3-Super-120B on Nebius Token Factory with air-gapped microVM sandboxing.
            </p>
          </div>

          <div style={{ display: "flex", gap: "10px", flexWrap: "wrap" }}>
            <a href="#/codebase" className="btn" style={{ textDecoration: "none" }}>
              Codebase Explorer
            </a>
            <a href="#/causal-lab" className="btn" style={{ textDecoration: "none" }}>
              Causal Lab
            </a>
            <a href="#/analytics" className="btn" style={{ textDecoration: "none" }}>
              Token Analytics
            </a>
          </div>
        </div>
      </header>

      {error && <div className="alert bad">{error}</div>}

      {/* Interactive Architecture & Pipeline Topology Map */}
      <div style={{
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: "10px",
        padding: "20px"
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
          <h2 style={{ fontSize: "15px", fontWeight: "700", margin: 0, textTransform: "uppercase", letterSpacing: "0.5px", color: "var(--dim)" }}>
            TraceGuard Verification Pipeline Architecture (Click any stage to inspect)
          </h2>
          <span className="small dim">End-to-End Autonomous Reliability Engine</span>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
          gap: "10px"
        }}>
          {pipelineStages.map((stage) => {
            const isSelected = activeStage === stage.num;
            return (
              <div
                key={stage.num}
                onClick={() => setActiveStage(isSelected ? null : stage.num)}
                style={{
                  background: isSelected ? "rgba(118, 185, 0, 0.12)" : "var(--panel-2)",
                  border: isSelected ? "1px solid var(--accent)" : "1px solid var(--line)",
                  borderRadius: "8px",
                  padding: "12px",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  position: "relative"
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                  <span style={{ fontSize: "11px", fontWeight: "800", color: isSelected ? "var(--accent)" : "var(--dim)" }}>
                    STAGE 0{stage.num}
                  </span>
                  <span style={{ fontSize: "10px", padding: "1px 5px", borderRadius: "3px", background: "rgba(255,255,255,0.06)", color: "var(--dim)" }}>
                    {stage.metric}
                  </span>
                </div>
                <div style={{ fontWeight: "700", fontSize: "13px", color: "var(--text)" }}>{stage.title}</div>
                <div className="dim small" style={{ fontSize: "11px", marginTop: "2px" }}>{stage.tech}</div>
              </div>
            );
          })}
        </div>

        {activeStage !== null && (
          <div style={{
            marginTop: "16px",
            padding: "14px 18px",
            borderRadius: "6px",
            background: "rgba(118, 185, 0, 0.08)",
            border: "1px solid var(--accent)",
            fontSize: "13px",
            lineHeight: "1.5"
          }}>
            <strong style={{ color: "var(--accent)" }}>Stage 0{activeStage}: {pipelineStages[activeStage - 1].title}</strong> — {pipelineStages[activeStage - 1].detail}
          </div>
        )}
      </div>

      {/* Live Agent Card */}
      <Card
        title="Live Autonomous Coding Agent"
        actions={
          <button onClick={() => run('live')} disabled={busy !== null} className="primary" style={{ fontWeight: "600" }}>
            {busy === 'live' ? 'Generating & Testing on Nebius…' : 'Run Live Agent'}
          </button>
        }
      >
        <p style={{ margin: "0 0 10px 0" }}>
          Prompts NVIDIA Nemotron-3-Super-120B on Nebius Token Factory to generate a production duration parser. TraceGuard captures the invocation, runs it against visible and held-out test suites, and verifies acceptance.
        </p>
        <div style={{ display: "flex", gap: "10px", flexWrap: "wrap", alignItems: "center" }}>
          <span className="badge good" style={{ fontSize: "11px" }}>Frozen Replay Semantics</span>
          <span className="dim small">Replay evaluates the exact generated artifact in isolation; new model samples cannot masquerade as fixes.</span>
        </div>
      </Card>

      {/* Target Workspaces & Repositories Grid */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "14px" }}>
          <h2 style={{ fontSize: "18px", fontWeight: "700", margin: 0 }}>Target Workspaces & Codebases</h2>
          <a href="#/codebase" className="small" style={{ color: "var(--accent)", textDecoration: "none", fontWeight: "600" }}>
            Browse Codebases in Repository Explorer →
          </a>
        </div>

        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
          gap: "16px"
        }}>
          {scenarios.map((s) => {
            const isEnterprise = s.id === "payment_gateway";
            return (
              <div
                key={s.id}
                style={isEnterprise ? { border: "1px solid rgba(118, 185, 0, 0.4)", borderRadius: "8px", background: "linear-gradient(180deg, rgba(118, 185, 0, 0.05) 0%, transparent 100%)" } : {}}
              >
                <Card title={s.title}>
                  <div style={{ minHeight: "65px", marginBottom: "12px" }}>
                    <p className="dim small" style={{ margin: 0, lineHeight: "1.5" }}>{s.summary}</p>
                  </div>

                  <div style={{ display: "flex", flexDirection: "column", gap: "10px", borderTop: "1px solid var(--line)", paddingTop: "12px" }}>
                    <div className="row between" style={{ alignItems: "center" }}>
                      <span className="dim small mono" style={{ fontSize: "11px" }}>
                        Target: {s.editable_files.join(", ")}
                      </span>
                      {isEnterprise && (
                        <span style={{ fontSize: "10px", padding: "2px 6px", borderRadius: "3px", background: "rgba(118, 185, 0, 0.2)", color: "var(--accent)", fontWeight: "700" }}>
                          13 FILES · 850 LOC
                        </span>
                      )}
                    </div>

                    <div className="row between" style={{ alignItems: "center" }}>
                      <a href={`#/codebase`} className="small dim" style={{ textDecoration: "underline" }}>
                        View Source Files
                      </a>
                      <button onClick={() => run(s.id)} disabled={busy !== null} className="small primary" style={{ fontWeight: "600" }}>
                        {busy === s.id ? "Executing Sandbox…" : "Run & Diagnose"}
                      </button>
                    </div>
                  </div>
                </Card>
              </div>
            );
          })}
        </div>
      </div>

      {/* Traces Journal */}
      <Card
        title="Execution Traces & Diagnostic History"
        actions={
          <div style={{ display: "flex", gap: "8px" }}>
            <button className="ghost small" onClick={() => setShowImport(!showImport)}>Import Trace JSON</button>
            <button className="ghost small" onClick={refresh}>Refresh</button>
          </div>
        }
      >
        {showImport && (
          <div className="stack import" style={{ marginBottom: "16px" }}>
            <textarea
              placeholder='{"workflow": "my-agent", "task": "...", "metadata": {"tools": [...]}, "events": [...]}'
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
            />
            <div className="row">
              <button onClick={importTrace} disabled={!importText.trim()} className="primary">Ingest</button>
              <span className="dim small">OTLP GenAI JSON schema compatible.</span>
            </div>
          </div>
        )}

        {traces.length === 0 ? (
          <p className="dim" style={{ padding: "20px 0" }}>No traces recorded yet. Run a workflow above to capture your first execution trace.</p>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  <th>Trace ID</th><th>Workflow</th><th>Agent Reported</th><th>Findings</th><th>Diagnoses</th><th>Replay Verification</th><th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {traces.map((t) => (
                  <tr key={t.id} className="clickable" onClick={() => (window.location.hash = `#/trace/${t.id}`)}>
                    <td className="mono" style={{ color: "var(--accent)", fontWeight: "600" }}>{t.id}</td>
                    <td>{t.workflow} {t.source !== "scenario" && <Badge tone="muted">{t.source}</Badge>}</td>
                    <td><Status value={t.final_status} /></td>
                    <td>
                      {t.finding_count === 0 ? (
                        <Badge tone="good">Clean</Badge>
                      ) : (
                        t.categories.map((c) => <Badge key={c} tone="bad">{label(c)}</Badge>)
                      )}
                    </td>
                    <td>{t.diagnoses} diagnosis</td>
                    <td>
                      {t.last_verification ? (
                        <span style={{ fontSize: "11px", fontWeight: "700", color: t.last_verification === "validated" ? "#10b981" : "#f59e0b" }}>
                          {t.last_verification.toUpperCase()}
                        </span>
                      ) : (
                        <span className="dim small">unverified</span>
                      )}
                    </td>
                    <td className="dim small">{t.created_at.slice(11, 19)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
