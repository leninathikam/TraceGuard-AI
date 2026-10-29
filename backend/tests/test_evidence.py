import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from conftest import completion, fake_client
from traceguard import api
from traceguard.diagnosis import diagnose_rules, scenario_files
from traceguard.evidence import regression_test
from traceguard.live_agent import run_live_agent
from traceguard.sandbox import run_scenario
from traceguard.scenarios import SCENARIOS, for_trace
from traceguard.schema import AcceptanceCheck, FileEdit
from traceguard.verify import verify_repair


def test_live_capture_preserves_exact_model_artifact_and_excludes_hidden_tests():
    calls = []
    source = 'def parse_duration(text):\n    return 123\n'
    run, info = run_live_agent(fake_client([completion(json.dumps({'code': source}))], calls))
    assert run.ok and not run.acceptance_passed
    assert info.prompt_tokens == 1000
    trace = run.trace
    assert trace.metadata['captured_files']['solution.py'] == source
    assert scenario_files(trace)['solution.py'] == source
    assert 'test_hidden' not in json.dumps(calls)
    assert any(e.kind == 'llm_call' and e.tokens_out == 200 for e in trace.events)
    assert for_trace(trace).read('solution.py') == source
    assert SCENARIOS['coding_agent'].read('solution.py') != source


def test_live_healthy_generation_is_not_manufactured_failure(reference_repairs):
    source = reference_repairs['coding_agent'][0].replace
    run, _ = run_live_agent(fake_client([completion(json.dumps({'code': source}))]))
    assert run.acceptance_passed
    d = diagnose_rules(run.trace)
    d.repair.edits = [FileEdit(path='solution.py', find='', replace=source)]
    assert verify_repair(d, run.trace).status == 'not_applicable'


def test_live_artifact_repair_and_generated_witness(reference_repairs):
    run, _ = run_live_agent(fake_client([completion(json.dumps({
        'code': 'def parse_duration(text):\n    return 123\n'}))]))
    d = diagnose_rules(run.trace)
    d.repair.edits = reference_repairs['coding_agent']
    v = verify_repair(d, run.trace)
    assert v.status == 'validated'
    assert v.intervention_tests[0]['outcome'] == 'failure_restored'
    namespace = {}
    exec(compile(regression_test(run.trace, d, v), '<generated-test>', 'exec'), namespace)
    namespace['test_captured_repair_regression']()
    namespace['PAYLOAD']['hashes']['baseline:solution.py'] = 'changed'
    with pytest.raises(AssertionError, match='drift'):
        namespace['test_captured_repair_regression']()


@pytest.mark.parametrize('fault', ['missing_failed_check', 'missing_trace', 'bad_baseline', 'duplicate_check'])
def test_verification_fails_closed(monkeypatch, reference_repairs, fault):
    scenario = SCENARIOS['tool_agent']
    baseline = run_scenario(scenario)
    repaired = run_scenario(scenario, reference_repairs['tool_agent'])
    d = diagnose_rules(baseline.trace)
    d.repair.edits = reference_repairs['tool_agent']
    if fault == 'missing_failed_check':
        repaired.checks = repaired.checks[1:]
    elif fault == 'missing_trace':
        repaired.trace = None
    elif fault == 'bad_baseline':
        baseline.ok = False
    else:
        repaired.checks.append(repaired.checks[0])
    monkeypatch.setattr('traceguard.verify.run_scenario', lambda *a, **kw: repaired)
    assert verify_repair(d, baseline.trace, baseline).status == 'failed'


def test_acceptance_exit_status_cannot_claim_success(monkeypatch):
    from traceguard import sandbox
    original = sandbox._run
    def fake(args, cwd, timeout, mode):
        if args == ['acceptance.py']:
            return subprocess.CompletedProcess(args, 7, '[{"name":"fake","passed":true}]', 'crash')
        return original(args, cwd, timeout, mode)
    monkeypatch.setattr(sandbox, '_run', fake)
    run = run_scenario(SCENARIOS['tool_agent'])
    assert not run.ok and not run.acceptance_passed
    assert 'exit 7' in run.error


def test_live_api_and_evidence_export(monkeypatch):
    monkeypatch.setattr(api, 'client', lambda: fake_client([completion(json.dumps({
        'code': 'def parse_duration(text):\n    return 0\n'}))]))
    http = TestClient(api.app)
    response = http.post('/api/agents/coding/run')
    assert response.status_code == 200
    tid = response.json()['trace_id']
    evidence = http.get(f'/api/traces/{tid}/evidence')
    assert evidence.json()['trace']['metadata']['agent_origin'] == 'live_nebius_generation'
    assert 'attachment' in evidence.headers['content-disposition']
