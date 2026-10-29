import { useEffect, useState } from "react";
import { api, CodebaseFile, Scenario } from "../api";

export default function CodebaseExplorer() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [selectedScenario, setSelectedScenario] = useState<string>("payment_gateway");
  const [files, setFiles] = useState<CodebaseFile[]>([]);
  const [selectedFile, setSelectedFile] = useState<CodebaseFile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    api.scenarios().then((list) => {
      setScenarios(list);
      // Default to enterprise codebase if available
      const hasD = list.some((s) => s.id === "payment_gateway");
      if (hasD) setSelectedScenario("payment_gateway");
      else if (list.length > 0) setSelectedScenario(list[0].id);
    }).catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedScenario) return;
    setLoading(true);
    api.scenarioFiles(selectedScenario)
      .then((data) => {
        setFiles(data);
        if (data.length > 0) {
          // Default to the first editable target file or main file
          const target = data.find((f) => f.is_editable) || data[0];
          setSelectedFile(target);
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setLoading(false);
      });
  }, [selectedScenario]);

  async function handleRunScenario() {
    if (!selectedScenario) return;
    setRunning(true);
    try {
      const res = await api.runScenario(selectedScenario);
      window.location.hash = `#/trace/${res.trace_id}`;
    } catch (e: any) {
      alert(e.message);
    } finally {
      setRunning(false);
    }
  }

  function handleCopy() {
    if (!selectedFile) return;
    navigator.clipboard.writeText(selectedFile.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  const totalLines = files.reduce((acc, f) => acc + f.line_count, 0);
  const totalBytes = files.reduce((acc, f) => acc + f.size_bytes, 0);

  return (
    <div className="page" style={{ maxWidth: "1400px", margin: "0 auto", padding: "24px 16px" }}>
      {/* Top Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "20px", flexWrap: "wrap", gap: "16px" }}>
        <div>
          <div>
            <h1 style={{ fontSize: "22px", fontWeight: "700", margin: 0 }}>Codebase & Repository Explorer</h1>
          </div>
          <p className="dim" style={{ fontSize: "14px", marginTop: "6px", maxWidth: "800px" }}>
            Explore the multi-file software repositories and enterprise microservices where AI coding agents operate. TraceGuard analyzes cross-file dependencies, reproduces failures in air-gapped sandboxes, and verifies repairs.
          </p>
        </div>

        {/* Scenario Switcher & Run Action */}
        <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
          <div>
            <label className="dim small" style={{ display: "block", marginBottom: "4px" }}>Select Target Repository:</label>
            <select
              value={selectedScenario}
              onChange={(e) => setSelectedScenario(e.target.value)}
              style={{
                padding: "8px 12px",
                fontSize: "13px",
                borderRadius: "6px",
                background: "var(--panel)",
                border: "1px solid var(--line)",
                color: "var(--text)",
                minWidth: "280px",
              }}
            >
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </div>

          <button
            onClick={handleRunScenario}
            disabled={running}
            className="btn primary"
            style={{ marginTop: "18px", padding: "8px 16px", display: "flex", alignItems: "center", gap: "8px", fontWeight: "600" }}
          >
            {running ? "Executing Sandbox..." : "Run Workflow Replay"}
          </button>
        </div>
      </div>

      {/* Codebase Metrics Banner */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
        gap: "12px",
        marginBottom: "20px",
        background: "var(--panel)",
        border: "1px solid var(--line)",
        borderRadius: "8px",
        padding: "14px 20px"
      }}>
        <div>
          <div className="dim small">Repository Files</div>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "var(--accent)" }}>{files.length} Files</div>
        </div>
        <div>
          <div className="dim small">Total Lines of Code</div>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "var(--text)" }}>{totalLines.toLocaleString()} LOC</div>
        </div>
        <div>
          <div className="dim small">Codebase Size</div>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "var(--text)" }}>{(totalBytes / 1024).toFixed(1)} KB</div>
        </div>
        <div>
          <div className="dim small">Editable Targets</div>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "#10b981" }}>
            {files.filter(f => f.is_editable).length} Target File(s)
          </div>
        </div>
        <div>
          <div className="dim small">Test Suites</div>
          <div style={{ fontSize: "20px", fontWeight: "700", color: "#8b5cf6" }}>
            {files.filter(f => f.is_test).length} Test Module(s)
          </div>
        </div>
      </div>

      {/* Main File Browser Split Pane */}
      {loading ? (
        <div style={{ padding: "40px", textAlign: "center", color: "var(--dim)" }}>Loading codebase files...</div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "320px 1fr",
          gap: "16px",
          minHeight: "650px",
          alignItems: "stretch"
        }}>
          {/* File Tree Sidebar */}
          <div style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: "8px",
            padding: "14px 10px",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
            maxHeight: "750px"
          }}>
            <div style={{ fontSize: "12px", fontWeight: "600", textTransform: "uppercase", color: "var(--dim)", padding: "0 10px 10px", borderBottom: "1px solid var(--line)" }}>
              Repository Explorer
            </div>

            <div style={{ marginTop: "10px", display: "flex", flexDirection: "column", gap: "4px" }}>
              {files.map((file) => {
                const isSelected = selectedFile?.path === file.path;
                let badge = null;
                if (file.is_editable) {
                  badge = <span style={{ fontSize: "9px", padding: "2px 6px", borderRadius: "4px", background: "rgba(16, 185, 129, 0.2)", color: "#10b981", fontWeight: "700" }}>TARGET</span>;
                } else if (file.is_test) {
                  badge = <span style={{ fontSize: "9px", padding: "2px 6px", borderRadius: "4px", background: "rgba(139, 92, 246, 0.2)", color: "#a78bfa", fontWeight: "600" }}>TEST</span>;
                } else if (file.is_context) {
                  badge = <span style={{ fontSize: "9px", padding: "2px 6px", borderRadius: "4px", background: "rgba(59, 130, 246, 0.2)", color: "#60a5fa", fontWeight: "600" }}>CONTEXT</span>;
                }

                return (
                  <button
                    key={file.path}
                    onClick={() => setSelectedFile(file)}
                    style={{
                      textAlign: "left",
                      padding: "8px 10px",
                      borderRadius: "6px",
                      background: isSelected ? "rgba(118, 185, 0, 0.15)" : "transparent",
                      border: isSelected ? "1px solid var(--accent)" : "1px solid transparent",
                      color: isSelected ? "var(--text)" : "var(--dim)",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      fontSize: "13px",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {file.path}
                    </span>
                    {badge}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Code Viewer */}
          <div style={{
            background: "var(--panel)",
            border: "1px solid var(--line)",
            borderRadius: "8px",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden"
          }}>
            {selectedFile ? (
              <>
                {/* File Header Bar */}
                <div style={{
                  padding: "12px 18px",
                  background: "var(--panel-2)",
                  borderBottom: "1px solid var(--line)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center"
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                    <span style={{ fontFamily: "ui-monospace, monospace", fontWeight: "600", fontSize: "14px" }}>
                      {selectedFile.path}
                    </span>
                    <span className="dim small">· {selectedFile.line_count} lines · {(selectedFile.size_bytes / 1024).toFixed(1)} KB</span>
                    {selectedFile.is_editable && (
                      <span style={{ fontSize: "11px", padding: "2px 8px", borderRadius: "4px", background: "rgba(16, 185, 129, 0.15)", color: "#10b981", border: "1px solid #10b981" }}>
                        Editable Repair Target
                      </span>
                    )}
                  </div>

                  <button
                    onClick={handleCopy}
                    style={{
                      padding: "4px 10px",
                      fontSize: "12px",
                      borderRadius: "4px",
                      background: "var(--panel)",
                      border: "1px solid var(--line)",
                      color: "var(--text)",
                      cursor: "pointer"
                    }}
                  >
                    {copied ? "Copied" : "Copy Code"}
                  </button>
                </div>

                {/* Source Code Content with Line Numbers */}
                <div style={{
                  flex: 1,
                  overflowY: "auto",
                  padding: "16px",
                  background: "#0a0c10",
                  fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace",
                  fontSize: "12.5px",
                  lineHeight: "1.6",
                }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <tbody>
                      {selectedFile.content.split("\n").map((line, idx) => (
                        <tr key={idx} style={{ hover: { background: "rgba(255,255,255,0.03)" } } as any}>
                          <td style={{
                            width: "45px",
                            userSelect: "none",
                            color: "#4a5568",
                            textAlign: "right",
                            paddingRight: "16px",
                            verticalAlign: "top"
                          }}>
                            {idx + 1}
                          </td>
                          <td style={{ color: "#e2e8f0", whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                            {line || " "}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : (
              <div style={{ padding: "40px", textAlign: "center", color: "var(--dim)" }}>Select a file from the explorer</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
