import VoiceOperator from "./VoiceOperator";
import { useEffect, useState } from "react";
import { api, Health, SandboxStatus } from "./api";
import Overview from "./pages/Overview";
import TraceView from "./pages/TraceView";
import EvaluationPage from "./pages/Evaluation";

function useHashRoute() {
  const [hash, setHash] = useState(window.location.hash || "#/");
  useEffect(() => {
    const on = () => setHash(window.location.hash || "#/");
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return hash.slice(1);
}

export default function App() {
  const route = useHashRoute();
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [sandbox, setSandbox] = useState<SandboxStatus | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch((e) => setHealthError(String(e.message ?? e)));
    api.sandboxStatus().then(setSandbox).catch(() => {});
  }, []);

  async function handleSandboxChange(mode: "subprocess" | "docker") {
    try {
      const res = await api.setSandboxMode(mode);
      setSandbox(res);
      api.health().then(setHealth).catch(() => {});
    } catch (e: any) {
      alert(e.message);
    }
  }

  const traceMatch = route.match(/^\/trace\/(.+)$/);
  let page = <Overview />;
  if (traceMatch) page = <TraceView id={traceMatch[1]} health={health} />;
  else if (route.startsWith("/evaluation")) page = <EvaluationPage health={health} />;

  return (
    <div className="app">
      <nav className="topbar">
        <a href="#/" className="brand">
          <span className="logo">◆</span> TraceGuard <span className="dim">AI</span>
        </a>
        <a href="#/" className={!traceMatch && !route.startsWith("/evaluation") ? "active" : ""}>Workflows</a>
        <a href="#/evaluation" className={route.startsWith("/evaluation") ? "active" : ""}>Evaluation</a>
        <VoiceOperator />
        <div className="spacer" />
        {sandbox && (
          <div className="row" style={{ alignItems: "center", gap: "6px" }}>
            <span className="small dim">Sandbox:</span>
            <select
              value={sandbox.current_mode}
              onChange={(e) => handleSandboxChange(e.target.value as any)}
              style={{
                padding: "2px 8px",
                fontSize: "12px",
                background: sandbox.current_mode === "docker" ? "rgba(118, 185, 0, 0.15)" : "var(--panel-2)",
                borderColor: sandbox.current_mode === "docker" ? "var(--accent)" : "var(--line)",
                color: sandbox.current_mode === "docker" ? "var(--accent)" : "var(--dim)",
              }}
              title={sandbox.docker_available ? `Docker engine active: ${sandbox.docker_detail}` : `Docker: ${sandbox.docker_detail}`}
            >
              <option value="subprocess">Subprocess (-E -s)</option>
              <option value="docker">Docker {sandbox.docker_available ? "MicroVM (Online)" : "MicroVM"}</option>
            </select>
          </div>
        )}
        {healthError && <span className="badge bad">backend unreachable</span>}
        {health && (
          <span className={`badge ${health.nebius_configured ? "good" : "warn"}`}
            title={health.nebius_configured ? "NEBIUS_API_KEY is set" : "Set NEBIUS_API_KEY to enable Nemotron diagnosis"}>
            {health.nebius_configured ? "Nebius Token Factory" : "Nebius key missing"} · {health.model}
          </span>
        )}
      </nav>
      <main>{page}</main>
    </div>
  );
}
