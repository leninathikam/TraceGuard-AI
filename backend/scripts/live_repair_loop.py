"""Run the full live pipeline on each scenario: baseline -> Nemotron diagnosis -> sandbox verification."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from traceguard.env import load_dotenv  # noqa: E402

load_dotenv()

from traceguard.diagnosis import diagnose  # noqa: E402
from traceguard.sandbox import run_scenario  # noqa: E402
from traceguard.scenarios import SCENARIOS  # noqa: E402
from traceguard.verify import verify_repair  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "hybrid"
for sid, scenario in SCENARIOS.items():
    baseline = run_scenario(scenario)
    trace = baseline.trace
    trace.id = f"live_{sid}"
    d = diagnose(trace, mode)
    d.id = f"live_dx_{sid}"
    print(f"\n=== {sid} [{mode}] category={d.category.value} confidence={d.confidence}")
    if d.fallback_reason:
        print("FALLBACK:", d.fallback_reason)
    print("hypothesis:", d.root_cause_hypothesis)
    print("evidence:", d.supporting_event_ids)
    if d.model_call:
        m = d.model_call
        print(f"model={m.model} attempts={m.attempts} tokens={m.prompt_tokens}+{m.completion_tokens} "
              f"cost=${m.cost_usd:.5f} latency={m.latency_ms / 1000:.1f}s validation_errors={m.validation_errors}")
    v = verify_repair(d, trace, baseline=baseline)
    print(f"verification: {v.status} - {v.reason}")
    if v.regressions:
        print("regressions:", v.regressions)
    if v.diff:
        print(v.diff)
