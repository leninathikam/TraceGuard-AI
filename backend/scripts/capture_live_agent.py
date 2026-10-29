"""Capture one fresh agent run and paired repair attempts, without selecting failures."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from traceguard.env import load_dotenv
from traceguard.live_agent import run_live_agent
from traceguard.nebius import NebiusClient
from traceguard.diagnosis import diagnose
from traceguard.verify import verify_repair
from traceguard.schema import utcnow

load_dotenv()
client = NebiusClient()
result = {'created_at': utcnow(), 'protocol': 'One generation, no resampling or forced defects',
          'model': client.model, 'repairs': {}}
try:
    run, info = run_live_agent(client)
    result['generation'] = info.model_dump(mode='json')
    result['run'] = run.model_dump(mode='json')
    if run.trace and run.ok and not run.acceptance_passed:
        for mode in ('rules', 'model', 'hybrid'):
            try:
                d = diagnose(run.trace, mode, client)
                v = verify_repair(d, run.trace, baseline=run)
                result['repairs'][mode] = {'diagnosis': d.model_dump(mode='json'),
                                            'verification': v.model_dump(mode='json')}
            except Exception as exc:
                result['repairs'][mode] = {'error': str(exc)}
    else:
        result['repair_note'] = 'No repair attempted: healthy generation or infrastructure failure.'
except Exception as exc:
    result['error'] = str(exc)
out = Path(sys.argv[1] if len(sys.argv) > 1 else '../results/live-agent-2026-10-29.json')
out.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({'output': str(out), 'error': result.get('error'),
                  'acceptance_passed': result.get('run', {}).get('acceptance_passed'),
                  'repairs': {k: v.get('verification', {}).get('status', v.get('error'))
                              for k, v in result['repairs'].items()}}))
