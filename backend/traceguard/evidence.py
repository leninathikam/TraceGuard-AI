"""Executable regression witnesses derived from measured checks, not model assertions."""
import json

from .schema import Diagnosis, Trace, Verification


def regression_test(trace: Trace, diagnosis: Diagnosis, verification: Verification) -> str:
    if verification.status != 'validated' or not verification.fixed_checks:
        raise ValueError('Only validated repairs with reproduced failures can generate regression tests.')
    payload = json.dumps({'trace': trace.model_dump(mode='json'),
                          'diagnosis': diagnosis.model_dump(mode='json'),
                          'fixed': verification.fixed_checks,
                          'hashes': {k: v for k, v in verification.evidence_hashes.items()
                                     if not k.startswith('repaired:')}})
    return '''# Generated TraceGuard regression witness. Run with pytest from backend/.
# Uses the repository's independent acceptance oracle, including held-out tests.
# This is a replay regression, not a newly invented semantic test oracle.
import json
from traceguard.schema import Trace, Diagnosis
from traceguard.scenarios import for_trace
from traceguard.verify import verify_repair, workspace_hashes

PAYLOAD = json.loads(''' + repr(payload) + ''')

def test_captured_repair_regression():
    trace = Trace.model_validate(PAYLOAD['trace'])
    diagnosis = Diagnosis.model_validate(PAYLOAD['diagnosis'])
    assert workspace_hashes(for_trace(trace)) == PAYLOAD['hashes'], 'Workspace/oracle drift'
    result = verify_repair(diagnosis, trace)
    assert result.status == 'validated', result.reason
    assert set(PAYLOAD['fixed']) <= set(result.fixed_checks), 'Original failure did not reproduce'
    assert not result.regressions
'''
