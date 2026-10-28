# Devpost submission draft

Fill every `<<...>>` with real values before submitting. Do not paste model results that were not
produced by an actual run.

**Project name:** TraceGuard AI

**Tagline:** A reliability engineer for AI agents: Nemotron diagnoses the failure, the sandbox proves the fix.

**Track:** Coding and Agentic Engineering

**Links:** Demo <<hosted URL>> · Video <<YouTube URL>> · Code <<GitHub URL>>

## Inspiration
Agent failures are usually silent. Our research-agent scenario reports "success" while citing a number
that appears nowhere in its sources. Traces tell you what happened; nobody tells you why, or whether
a fix actually works.

## What it does
TraceGuard ingests an agent trace (native JSON or OpenTelemetry GenAI spans), runs 15 deterministic
failure detectors, and asks NVIDIA Nemotron 3 Super on Nebius Token Factory for a root-cause hypothesis
with cited trace events and a minimal patch. Then it applies the patch to an isolated copy of the agent,
replays it, and runs acceptance checks, including held-out tests the model never saw. A repair is marked
validated only if every check passes with no regressions.

## How we built it
FastAPI + Pydantic backend, SQLite store, React/TypeScript dashboard, Docker. Token Factory's
OpenAI-compatible API with JSON-mode responses, schema and evidence validation, one corrective retry,
timeouts, bounded retries with backoff, and per-call token/cost/latency logging. Three diagnosis modes
(rules, Nemotron, hybrid) evaluated on 26 hand-labelled traces.

## How we used NVIDIA Nemotron and Nebius Token Factory
- Model: `<<model ID actually used>>` via `https://api.tokenfactory.nebius.com/v1/`.
- Nemotron decides which finding is the root cause, catches semantic failures rules can't (fabricated
  IDs, misrouted requests, claims contradicting sources), and writes the patch that gets tested.
- Measured: <<hybrid root-cause accuracy>> vs <<rules accuracy>> for rules only;
  <<verified repairs>>/3 scenarios verified; median <<latency>>; mean <<cost>> per diagnosis.

## Challenges
<<your experience: e.g. getting reliably parseable JSON, making edits apply exactly>>

## Accomplishments
A repair loop that refuses to trust the model: our overfitted-patch test passes the visible tests and
is still rejected because the held-out tests regress.

## What we learned / What's next
<<...>> Next: Docker sandbox by default, live OTLP collector, CI integration that comments verified
fixes on PRs, and Nemotron Nano for cheap first-pass triage with Ultra for hard cases.

## Feedback on Nebius Token Factory and NVIDIA models
<<Write your own: onboarding, docs, latency, JSON mode, model catalog, credits, anything that blocked you.>>

## Hosting note
Deploy the Docker image on any container host (e.g. Nebius AI Cloud) with `NEBIUS_API_KEY` set as a
secret. Keep it running through December 15, 2026 for judging.
