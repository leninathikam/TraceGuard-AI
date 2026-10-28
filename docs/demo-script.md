# Demo video script (target 2:45, hard limit 3:00)

Before recording: set `NEBIUS_API_KEY`, start the app, clear `data/traceguard.db`, and run the
evaluation once so the Evaluation page has live numbers. Record at 1440p, browser zoom 100%.

| Time | Screen | Say |
| --- | --- | --- |
| 0:00–0:15 | Overview | "Agents fail quietly: bad tool calls, made-up facts, code that only passes the tests it saw. TraceGuard is a reliability engineer for agents, built on NVIDIA Nemotron running on Nebius Token Factory." |
| 0:15–0:50 | Run **A. Tool-calling agent** → trace page | Point at the red summary: "In one glance: the booking failed because the arguments violate the tool schema. The inspector shows the exception and the blind retries are *symptoms*, not separate bugs." Hover a finding to highlight its events. |
| 0:50–1:25 | Diagnosis: **Hybrid** → Diagnose | "The rule findings and the trace go to Nemotron 3 Super on Token Factory." Show the hypothesis, cited event IDs, confidence, the model ID, tokens, cost and latency. Point at the yellow **hypothesis** badge: "It's a hypothesis until we prove it." |
| 1:25–1:55 | Repair → **Verify in sandbox** | "Nemotron proposed a two-line edit to the agent's tool policy. TraceGuard applies it to a throwaway copy, replays the agent and runs the acceptance checks." Show the diff, the baseline-vs-repaired table, the badge flipping to **supported by replay**, then open the replayed trace: clean. |
| 1:55–2:20 | Run **C. Coding agent** → Hybrid → Verify | "Same loop for code. Nemotron rewrites `parse_duration`; we run the visible tests *and six held-out tests the model never saw*, so an overfitted patch would be caught as a regression." |
| 2:20–2:40 | Evaluation page | "On 26 labelled traces, rules alone get X%; they miss every semantic failure. Hybrid gets Y% at Z cents per diagnosis." Read the **actual** numbers from the page. |
| 2:40–2:50 | Close | "TraceGuard: detect, diagnose with Nemotron, and only trust repairs that pass replay. Open source, MIT." |

If a live model call fails while recording, show it. The UI labels fallbacks explicitly. Don't edit in
results from a different run.
