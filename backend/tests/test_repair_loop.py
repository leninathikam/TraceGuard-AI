import pytest

from traceguard.detectors import primary_finding, run_detectors
from traceguard.diagnosis import diagnose_rules
from traceguard.sandbox import RepairRejected, apply_edits, run_scenario
from traceguard.scenarios import SCENARIOS
from traceguard.schema import FileEdit
from traceguard.verify import verify_repair

EXPECTED_PRIMARY = {
    "tool_agent": "invalid_tool_arguments",
    "research_agent": "unsupported_claim",
    "coding_agent": "failing_test",
    "payment_gateway": "failing_test",
}


@pytest.fixture(scope="module")
def baselines():
    return {sid: run_scenario(s) for sid, s in SCENARIOS.items()}


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_baseline_fails_and_is_detected(baselines, sid):
    run = baselines[sid]
    assert run.ok and not run.acceptance_passed
    assert primary_finding(run_detectors(run.trace)).category.value == EXPECTED_PRIMARY[sid]


@pytest.mark.parametrize("sid", list(SCENARIOS))
def test_reference_repair_is_validated(baselines, reference_repairs, sid):
    run = baselines[sid]
    d = diagnose_rules(run.trace)
    d.id, d.repair.edits = "dx_test", reference_repairs[sid]
    v = verify_repair(d, run.trace, baseline=run)
    assert v.status == "validated", (v.reason, [c for c in v.repaired.checks if not c.passed])
    assert v.fixed_checks and not v.regressions and v.diff.startswith("--- a/")


def test_overfit_code_repair_fails_hidden_tests(baselines):
    run = baselines["coding_agent"]
    overfit = FileEdit(path="solution.py", find="", replace='''def parse_duration(text: str) -> int:
    table = {"1h30m": 5400, "45s": 45, "2h": 7200}
    if text not in table:
        raise ValueError(text)
    return table[text]
''')
    d = diagnose_rules(run.trace)
    d.id, d.repair.edits = "dx_overfit", [overfit]
    v = verify_repair(d, run.trace, baseline=run)
    assert v.status == "failed"
    assert "test_hidden:test_minutes_only" in v.regressions  # passed before, broken by the overfit patch


def test_rules_diagnosis_is_not_replayable(baselines):
    run = baselines["tool_agent"]
    d = diagnose_rules(run.trace)
    d.id = "dx_rules"
    assert d.hypothesis_status == "hypothesis"
    assert verify_repair(d, run.trace).status == "not_applicable"


@pytest.mark.parametrize("edit,message", [
    (FileEdit(path="agent.py", find="", replace="x"), "not editable"),
    (FileEdit(path="../../etc/passwd", find="", replace="x"), "not editable"),
    (FileEdit(path="tool_policy.json", find="nope", replace="x"), "matched 0 times"),
    (FileEdit(path="tool_policy.json", find='"max_retries": 2', replace='"max_retries": '), "invalid JSON"),
])
def test_unsafe_or_inapplicable_edits_rejected(edit, message):
    with pytest.raises(RepairRejected, match=message):
        apply_edits(SCENARIOS["tool_agent"], [edit])


@pytest.mark.parametrize("code", [
    "import os\ndef parse_duration(t): return 0\n",
    "import subprocess\n",
    "def parse_duration(t): return eval(t)\n",
    "def parse_duration(t): return open('x').read()\n",
    "def parse_duration(t): return ().__class__.__bases__\n",
])
def test_code_repairs_cannot_escape(code):
    with pytest.raises(RepairRejected):
        apply_edits(SCENARIOS["coding_agent"], [FileEdit(path="solution.py", find="", replace=code)])


def test_sandbox_does_not_touch_original_files(reference_repairs):
    scenario = SCENARIOS["research_agent"]
    before = scenario.read("answer_policy.json")
    run_scenario(scenario, reference_repairs["research_agent"])
    assert scenario.read("answer_policy.json") == before


def test_sandbox_env_has_no_api_key(monkeypatch):
    from traceguard.sandbox import _clean_env

    monkeypatch.setenv("NEBIUS_API_KEY", "secret")
    assert "NEBIUS_API_KEY" not in _clean_env()
