import { useEffect, useState } from "react";
import { api, TraceSummary, TraceDetail, Verification } from "../api";

export default function CausalLab() {
  const [traces, setTraces] = useState<TraceSummary[]>([]);
  const [selectedTraceId, setSelectedTraceId] = useState<string>("");
  const [, setDetail] = useState<TraceDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [activeVerification, setActiveVerification] = useState<Verification | null>(null);

  useEffect(() => {
    api.traces().then((list) => {
      setTraces(list);
      if (list.length > 0) {
        // Choose trace with verification if available
        const withVerif = list.find((t) => t.last_verification === "validated") || list[0];
        setSelectedTraceId(withVerif.id);
      }
      setLoading(false);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedTraceId) return;
    setLoading(true);
    api.trace(selectedTraceId).then((d) => {
      setDetail(d);
      if (d.verifications && d.verifications.length > 0) {
        setActiveVerification(d.verifications[0]);
      } else {
        setActiveVerification(null);
      }
      setLoading(false);
    }).catch(console.error);
  }, [selectedTraceId]);

  return (
    <div className="page" style={{ maxWidth: "1400px", margin: "0 auto", padding: "24px 16px" }}>
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span style={{ fontSize: "24px" }}>🔬</span>
          <h1 style={{ fontSize: "22px", fontWeight: "700", margin: 0 }}>Causal Soundness Lab & Counterfactual Studio</h1>
        </div>
        <p className="dim" style={{ fontSize: "14px", marginTop: "6px", maxWidth: "900px" }}>
          In AI agent debugging, natural language explanations are merely hypotheses. TraceGuard transforms hypotheses into mathematically verified causal evidence through isolated sandbox replays, leave-one-out counterfactual ablation, and cryptographic SHA-256 evidence hashing.
        </p>
      </div>

      {/* Trace Selector Bar */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: "8px",
        padding: "12px 18px",
        marginBottom: "24px",
        flexWrap: "wrap",
        gap: "12px"
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <span className="dim small" style={{ fontWeight: "600" }}>Select Diagnostic Trace:</span>
          <select
            value={selectedTraceId}
            onChange={(e) => setSelectedTraceId(e.target.value)}
            style={{
              padding: "6px 12px",
              borderRadius: "6px",
              background: "var(--panel-2)",
              border: "1px solid var(--line)",
              color: "var(--text)",
              fontSize: "13px"
            }}
          >
            {traces.map((t) => (
              <option key={t.id} value={t.id}>
                {t.id} · {t.workflow} ({t.scenario || "synthetic"}) — {t.last_verification || "unverified"}
              </option>
            ))}
          </select>
        </div>

        {selectedTraceId && (
          <a
            href={`#/trace/${selectedTraceId}`}
            className="btn small"
            style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "6px" }}
          >
            Open in Trace Inspector ➔
          </a>
        )}
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "40px", color: "var(--dim)" }}>Loading causal evaluation models...</div>
      ) : activeVerification ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "24px" }}>
          {/* Causal Status Card */}
          <div style={{
            background: "linear-gradient(135deg, rgba(118, 185, 0, 0.08) 0%, rgba(20, 24, 30, 0.95) 100%)",
            border: "1px solid var(--accent)",
            borderRadius: "8px",
            padding: "20px"
          }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px", marginBottom: "12px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                <span style={{ fontSize: "18px", color: "var(--accent)" }}>🛡️</span>
                <span style={{ fontSize: "16px", fontWeight: "700" }}>Causal Verification Status:</span>
                <span className="badge good" style={{ textTransform: "uppercase" }}>{activeVerification.status}</span>
              </div>
              <span className="dim small" style={{ fontFamily: "ui-monospace, monospace" }}>Verification ID: {activeVerification.id}</span>
            </div>

            <div style={{ fontSize: "14px", lineHeight: "1.5", color: "#e2e8f0" }}>
              {activeVerification.reason}
            </div>

            {/* Fixed Checks Badges */}
            <div style={{ marginTop: "16px", display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
              <span className="dim small">Repaired Checks:</span>
              {activeVerification.fixed_checks.map((fc) => (
                <span key={fc} style={{ fontSize: "11px", padding: "3px 8px", borderRadius: "4px", background: "rgba(16, 185, 129, 0.15)", color: "#10b981", border: "1px solid #10b981" }}>
                  ✓ {fc}
                </span>
              ))}
              {activeVerification.regressions.length === 0 && (
                <span style={{ fontSize: "11px", padding: "3px 8px", borderRadius: "4px", background: "rgba(59, 130, 246, 0.1)", color: "#60a5fa" }}>
                  0 Regressions Introduced
                </span>
              )}
            </div>
          </div>

          {/* Section 1: Leave-One-Out Causal Ablation Matrix */}
          <div style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: "8px",
            padding: "20px"
          }}>
            <h2 style={{ fontSize: "16px", fontWeight: "700", margin: "0 0 8px 0" }}>
              1. Leave-One-Out Causal Intervention Matrix
            </h2>
            <p className="dim small" style={{ marginBottom: "16px" }}>
              To prove that each proposed edit is causally responsible for fixing the failure, TraceGuard generates counterfactual candidate workspaces omitting one edit at a time and re-runs the acceptance suite in the microVM sandbox.
            </p>

            {activeVerification.intervention_tests && activeVerification.intervention_tests.length > 0 ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                {activeVerification.intervention_tests.map((inv, idx) => (
                  <div
                    key={idx}
                    style={{
                      padding: "14px",
                      borderRadius: "6px",
                      background: "var(--panel-2)",
                      border: "1px solid var(--line)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      flexWrap: "wrap",
                      gap: "12px"
                    }}
                  >
                    <div>
                      <div style={{ fontWeight: "600", fontSize: "14px", display: "flex", alignItems: "center", gap: "8px" }}>
                        <span>Counterfactual Test #{inv.omitted_edit + 1}:</span>
                        <code style={{ color: "var(--accent)" }}>Omit edit to {inv.path || "target"}</code>
                      </div>
                      <div className="dim small" style={{ marginTop: "4px" }}>
                        Outcome: <strong style={{ color: inv.outcome === "failure_restored" ? "#10b981" : "#f59e0b" }}>{inv.outcome}</strong>
                        {inv.restored_failures && inv.restored_failures.length > 0 && (
                          <span> (restores baseline failure on {inv.restored_failures.join(", ")})</span>
                        )}
                      </div>
                    </div>

                    <span style={{
                      fontSize: "12px",
                      padding: "4px 10px",
                      borderRadius: "4px",
                      background: inv.outcome === "failure_restored" ? "rgba(16, 185, 129, 0.2)" : "rgba(245, 158, 11, 0.2)",
                      color: inv.outcome === "failure_restored" ? "#10b981" : "#f59e0b",
                      fontWeight: "700"
                    }}>
                      {inv.outcome === "failure_restored" ? "CAUSALLY NECESSARY ✓" : "INCONCLUSIVE"}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="dim small" style={{ padding: "14px", background: "var(--panel-2)", borderRadius: "6px" }}>
                Intervention tests are computed when verified repairs contain discrete patch edits.
              </div>
            )}
          </div>

          {/* Section 2: Cryptographic SHA-256 Provenance & Witness Hashes */}
          <div style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: "8px",
            padding: "20px"
          }}>
            <h2 style={{ fontSize: "16px", fontWeight: "700", margin: "0 0 8px 0" }}>
              2. Cryptographic SHA-256 Artifact Hashes
            </h2>
            <p className="dim small" style={{ marginBottom: "16px" }}>
              TraceGuard hashes every baseline file, modified source file, and harness script to prove zero test drift, zero hidden state, and reproducibility across CI/CD environments.
            </p>

            {activeVerification.evidence_hashes ? (
              <div style={{
                maxHeight: "300px",
                overflowY: "auto",
                background: "#0a0c10",
                padding: "12px",
                borderRadius: "6px",
                fontFamily: "ui-monospace, monospace",
                fontSize: "12px",
                display: "flex",
                flexDirection: "column",
                gap: "6px"
              }}>
                {Object.entries(activeVerification.evidence_hashes).map(([filename, hash]) => (
                  <div key={filename} style={{ display: "flex", justifyContent: "space-between", gap: "16px", padding: "4px 8px", borderBottom: "1px solid #1a202c" }}>
                    <span style={{ color: filename.startsWith("repaired:") ? "#10b981" : filename.startsWith("harness:") ? "#a78bfa" : "#94a3b8" }}>
                      {filename}
                    </span>
                    <span style={{ color: "#e2e8f0" }}>{hash}</span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="dim small">No artifact hashes recorded for this verification.</div>
            )}
          </div>

          {/* Section 3: Standalone Pytest Regression Generator */}
          <div style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: "8px",
            padding: "20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "16px"
          }}>
            <div>
              <h2 style={{ fontSize: "16px", fontWeight: "700", margin: "0 0 6px 0" }}>
                3. Standalone Pytest Witness Export
              </h2>
              <p className="dim small" style={{ margin: 0, maxWidth: "700px" }}>
                Export a self-contained, standalone Python test file (<code style={{ color: "var(--accent)" }}>test_traceguard_regression.py</code>) that locks in the verified fix and can run directly in GitHub Actions or any CI/CD runner.
              </p>
            </div>

            <a
              href={`/api/diagnoses/${activeVerification.diagnosis_id}/regression-test`}
              download="test_traceguard_regression.py"
              className="btn primary"
              style={{ textDecoration: "none", padding: "10px 18px", fontWeight: "600", display: "inline-flex", alignItems: "center", gap: "8px" }}
            >
              📥 Download Pytest Witness (.py)
            </a>
          </div>
        </div>
      ) : (
        <div style={{
          padding: "50px 20px",
          textAlign: "center",
          background: "var(--panel)",
          border: "1px solid var(--line)",
          borderRadius: "8px"
        }}>
          <span style={{ fontSize: "36px", display: "block", marginBottom: "12px" }}>🔍</span>
          <h3 style={{ fontSize: "18px", fontWeight: "600", margin: "0 0 8px 0" }}>No Verified Repair on this Trace Yet</h3>
          <p className="dim" style={{ maxWidth: "500px", margin: "0 auto 20px auto", fontSize: "14px" }}>
            To inspect causal ablation tests and cryptographic evidence hashes, generate a diagnosis with Nemotron 120B and click "Verify Repair in Sandbox".
          </p>
          <a href={`#/trace/${selectedTraceId}`} className="btn primary" style={{ textDecoration: "none" }}>
            Go to Trace & Verify Now
          </a>
        </div>
      )}
    </div>
  );
}
