"""Print every benchmark case a mode got wrong, from results/evaluation.json."""

import json
from pathlib import Path

result = json.loads((Path(__file__).resolve().parents[2] / "results" / "evaluation.json").read_text(encoding="utf-8"))
for mode, score in result["diagnosis"].items():
    print(f"\n[{mode}] cost/diag={score.get('cost_usd_per_diagnosis_mean')} median latency={score['latency_ms_median']}")
    for row in score["rows"]:
        if not row["correct"]:
            print(f"  {row['case']:34} expected={row['expected']:26} got={row['predicted']}")
for mode, rep in result["repairs"].items():
    for row in rep["rows"]:
        print(f"[{mode} repair] {row['scenario']}: {row['status']} ({row.get('category')}) {row.get('reason', row.get('error', ''))[:120]}")
