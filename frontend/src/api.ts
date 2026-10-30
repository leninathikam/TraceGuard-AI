export type Finding = {
  category: string;
  severity: "critical" | "high" | "medium" | "low";
  event_ids: string[];
  title: string;
  detail: string;
  detector: string;
  is_symptom_of: string | null;
};

export type TraceEvent = {
  id: string;
  seq: number;
  kind: string;
  name: string;
  parent_id: string | null;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  status: "ok" | "error";
  error: string | null;
  duration_ms: number;
  tokens_in: number;
  tokens_out: number;
  attributes: Record<string, unknown>;
};

export type Trace = {
  id: string;
  workflow: string;
  scenario: string | null;
  task: string;
  final_status: string;
  created_at: string;
  metadata: Record<string, unknown>;
  events: TraceEvent[];
};

export type ModelCall = {
  model: string;
  attempts: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  latency_ms: number;
  validation_errors: string[];
};

export type Diagnosis = {
  id: string;
  trace_id: string;
  mode: "rules" | "model" | "hybrid";
  created_at: string;
  category: string;
  supporting_event_ids: string[];
  root_cause_hypothesis: string;
  hypothesis_status: "hypothesis" | "supported_by_replay" | "not_supported_by_replay";
  confidence: "low" | "medium" | "high";
  confidence_rationale: string;
  limitations: string;
  repair: { summary: string; edits: { path: string; find: string; replace: string }[] };
  verification_procedure: string[];
  model_call: ModelCall | null;
  fallback_reason: string | null;
};

export type Check = { name: string; passed: boolean; detail: string };
export type SandboxRun = {
  ok: boolean;
  acceptance_passed: boolean;
  checks: Check[];
  duration_ms: number;
  sandbox: string;
  error: string | null;
};

export type Verification = {
  id: string;
  diagnosis_id: string;
  status: "validated" | "failed" | "rejected" | "not_applicable";
  reason: string;
  diff: string;
  baseline: SandboxRun | null;
  repaired: SandboxRun | null;
  fixed_checks: string[];
  regressions: string[];
  still_failing: string[];
  remaining_findings: Finding[];
  repaired_trace_id: string | null;
  created_at: string;
  causal_scope?: string;
  evidence_hashes?: Record<string, string>;
  intervention_tests?: { omitted_edit: number; path?: string; outcome: string; restored_failures?: string[]; error?: string }[];
};

export type TraceDetail = {
  trace: Trace;
  findings: Finding[];
  diagnoses: Diagnosis[];
  verifications: Verification[];
  scenario: string | null;
};

export type TraceSummary = {
  id: string;
  workflow: string;
  scenario: string | null;
  final_status: string;
  created_at: string;
  source: string;
  finding_count: number;
  categories: string[];
  diagnoses: number;
  last_verification: string | null;
};

export type Scenario = { id: string; title: string; summary: string; editable_files: string[] };
export type Health = { nebius_configured: boolean; model: string; fallback_model?: string | null; sandbox: string; version: string };
export type SandboxStatus = {
  current_mode: "subprocess" | "docker";
  docker_available: boolean;
  docker_detail: string;
  image: string;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export const api = {
  runLiveAgent: () => request<{ trace_id: string }>("/api/agents/coding/run", { method: "POST" }),
  sandboxStatus: () => request<SandboxStatus>("/api/sandbox/status"),
  setSandboxMode: (mode: "subprocess" | "docker") =>
    request<SandboxStatus>("/api/sandbox/mode", { method: "POST", body: JSON.stringify({ mode }) }),
  health: () => request<Health>("/api/health"),
  scenarios: () => request<Scenario[]>("/api/scenarios"),
  runScenario: (id: string) => request<{ trace_id: string }>(`/api/scenarios/${id}/run`, { method: "POST" }),
  traces: () => request<TraceSummary[]>("/api/traces"),
  trace: (id: string) => request<TraceDetail>(`/api/traces/${id}`),
  ingest: (body: string) => request<{ trace_id: string }>("/api/traces", { method: "POST", body }),
  diagnose: (id: string, mode: string) =>
    request<Diagnosis>(`/api/traces/${id}/diagnose`, { method: "POST", body: JSON.stringify({ mode }) }),
  verify: (diagnosisId: string) =>
    request<Verification>(`/api/diagnoses/${diagnosisId}/verify`, { method: "POST" }),
  latestEvaluation: () => request<Evaluation | null>("/api/evaluations/latest"),
  runEvaluation: (modes: string[]) =>
    request<Evaluation>("/api/evaluations", { method: "POST", body: JSON.stringify({ modes }) }),
  scenarioFiles: (id: string) => request<CodebaseFile[]>(`/api/scenarios/${id}/files`),
  usage: () => request<UsageSummary>("/api/usage"),
};

export type Prf = { precision: number | null; recall: number | null; f1: number | null; tp: number; fp: number; fn: number };
export type ModeScore = {
  mode: string;
  cases: number;
  failure_detection: Prf & { tn: number };
  root_cause_accuracy: number;
  accuracy_by_kind: Record<string, number>;
  invalid_or_failed_outputs: number;
  latency_ms_median: number | null;
  tokens_per_diagnosis_mean?: number | null;
  cost_usd_per_diagnosis_mean?: number | null;
  cost_usd_total?: number;
  rows: { case: string; kind: string; expected: string; predicted: string; correct: boolean; error: string | null }[];
};
export type RepairScore = {
  mode: string;
  scenarios: number;
  proposal_validity_rate: number;
  verified_repair_rate: number;
  regression_rate: number;
  rows: { scenario: string; status: string; reason?: string; category?: string; error?: string }[];
};
export type Evaluation = {
  id: string;
  created_at: string;
  model: string;
  diagnosis: Record<string, ModeScore>;
  repairs: Record<string, RepairScore>;
  skipped: Record<string, string>;
};


export type CodebaseFile = {
  path: string;
  size_bytes: number;
  line_count: number;
  is_editable: boolean;
  is_context: boolean;
  is_test: boolean;
  content: string;
};

export type UsageSummary = {
  by_model: {
    model: string;
    n: number;
    ok: number;
    pt: number;
    ct: number;
    cost: number;
    lat: number;
  }[];
  recent: {
    id: number;
    created_at: string;
    purpose: string;
    trace_id: string | null;
    model: string;
    attempts: number;
    prompt_tokens: number;
    completion_tokens: number;
    cost_usd: number;
    latency_ms: number;
    ok: number;
    error: string | null;
  }[];
};
