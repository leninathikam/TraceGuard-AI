import { useEffect, useRef, useState } from "react";
import { api } from "./api";

// Web Speech API interface declarations for TypeScript
interface IWindow extends Window {
  webkitSpeechRecognition?: any;
  SpeechRecognition?: any;
}

export function speak(text: string) {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.rate = 1.05;
  utterance.pitch = 1.0;
  window.speechSynthesis.speak(utterance);
}

export default function VoiceOperator() {
  const [active, setActive] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const recognitionRef = useRef<any>(null);

  useEffect(() => {
    const win = window as unknown as IWindow;
    const SpeechRec = win.SpeechRecognition || win.webkitSpeechRecognition;
    if (!SpeechRec) {
      setSupported(false);
      return;
    }
    const rec = new SpeechRec();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";

    rec.onresult = async (event: any) => {
      let current = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        current += event.results[i][0].transcript;
      }
      setTranscript(current);

      const phrase = current.toLowerCase().trim();
      if (phrase.includes("live") && phrase.includes("agent")) {
        setStatus("Running live Nemotron agent…");
        speak("Running live Nemotron coding agent on Nebius Token Factory.");
        try {
          const r = await api.runLiveAgent();
          window.location.hash = `#/trace/${r.trace_id}`;
        } catch (e: any) {
          setStatus(`Error: ${e.message}`);
        }
      } else if (phrase.includes("tool") && (phrase.includes("agent") || phrase.includes("run"))) {
        setStatus("Running tool-calling agent…");
        speak("Running tool-calling agent scenario.");
        try {
          const r = await api.runScenario("tool_agent");
          window.location.hash = `#/trace/${r.trace_id}`;
        } catch (e: any) {
          setStatus(`Error: ${e.message}`);
        }
      } else if (phrase.includes("research") && (phrase.includes("agent") || phrase.includes("run"))) {
        setStatus("Running research agent…");
        speak("Running research agent scenario.");
        try {
          const r = await api.runScenario("research_agent");
          window.location.hash = `#/trace/${r.trace_id}`;
        } catch (e: any) {
          setStatus(`Error: ${e.message}`);
        }
      } else if (phrase.includes("coding") && (phrase.includes("agent") || phrase.includes("run"))) {
        setStatus("Running coding agent scenario…");
        speak("Running deterministic coding agent scenario.");
        try {
          const r = await api.runScenario("coding_agent");
          window.location.hash = `#/trace/${r.trace_id}`;
        } catch (e: any) {
          setStatus(`Error: ${e.message}`);
        }
      } else if (phrase.includes("evaluation") || phrase.includes("benchmark")) {
        setStatus("Navigating to evaluation…");
        speak("Navigating to benchmark evaluation.");
        window.location.hash = "#/evaluation";
      } else if (phrase.includes("overview") || phrase.includes("workflows") || phrase.includes("home")) {
        setStatus("Navigating to workflows overview…");
        speak("Navigating to workflows.");
        window.location.hash = "#/";
      }
    };

    rec.onerror = (err: any) => {
      if (err.error !== "no-speech") {
        setStatus(`Voice error: ${err.error}`);
      }
    };

    rec.onend = () => {
      if (active) {
        try {
          rec.start();
        } catch {}
      }
    };

    recognitionRef.current = rec;
  }, [active]);

  function toggle() {
    if (!supported) {
      alert("Web Speech API is not supported in this browser. Please use Chrome or Edge.");
      return;
    }
    if (active) {
      recognitionRef.current?.stop();
      setActive(false);
      setStatus(null);
      setTranscript("");
      speak("Voice operator deactivated.");
    } else {
      try {
        recognitionRef.current?.start();
        setActive(true);
        setStatus("Listening for commands: 'run live agent', 'run tool agent', 'open evaluation'…");
        speak("TraceGuard Voice Operator online. Listening for commands.");
      } catch (err: any) {
        setStatus(`Could not start microphone: ${err.message}`);
      }
    }
  }

  return (
    <div className="voice-operator row" style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
      <button
        onClick={toggle}
        className={active ? "" : "ghost"}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "6px",
          padding: "4px 10px",
          fontSize: "12px",
          borderColor: active ? "var(--accent)" : "var(--line)",
          background: active ? "var(--accent)" : "var(--panel-2)",
          color: active ? "#0b0f14" : "var(--dim)",
        }}
        title="Voice Operator: control TraceGuard with spoken commands"
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
          <span style={{
            width: "6px",
            height: "6px",
            borderRadius: "50%",
            background: active ? "#0b0f14" : "var(--accent)",
            display: "inline-block",
          }} />
          {active ? "Voice Listening" : "Voice Control"}
        </span>
      </button>
      {active && (
        <span className="small dim" style={{ maxWidth: "340px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {status} {transcript && <strong style={{ color: "var(--accent)" }}>"{transcript}"</strong>}
        </span>
      )}
    </div>
  );
}
