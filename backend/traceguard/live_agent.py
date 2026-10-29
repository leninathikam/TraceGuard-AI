"""A bounded model-driven coding agent. Inference stays outside the replay sandbox."""
from dataclasses import replace

from .nebius import NebiusClient, NebiusError, extract_json
from .sandbox import apply_edits, run_scenario
from .scenarios import SCENARIOS
from .schema import FileEdit, ModelCallInfo, TraceEvent

TASK = ("Implement parse_duration(text) in solution.py. Return total seconds for non-empty "
        "strings containing optional integer hours, minutes and seconds in that order, e.g. "
        "'1h30m', '45s', '2h', '1h5m10s'. Raise ValueError for invalid input.")


def run_live_agent(client: NebiusClient):
    scenario = SCENARIOS['coding_agent']
    messages = [
        {"role": "system", "content": "You are a coding agent. Implement the user's task. "
         "Return JSON with a single string field code containing solution.py. Use pure Python; "
         "only import re if needed. No file access, introspection, network, or test manipulation."},
        {"role": "user", "content": TASK + "\nVisible tests:\n" + scenario.read('test_visible.py')},
    ]
    completion = client.chat(messages, temperature=0.1)
    info = ModelCallInfo(model=completion.model, attempts=completion.attempts,
                         prompt_tokens=completion.prompt_tokens, completion_tokens=completion.completion_tokens,
                         cost_usd=completion.cost_usd, latency_ms=completion.latency_ms)
    try:
        code = extract_json(completion.content)['code']
        edit = FileEdit(path='solution.py', find='', replace=code)
        apply_edits(scenario, [edit])
    except (ValueError, KeyError, TypeError) as exc:
        error = NebiusError(f"Generated artifact rejected: {exc}")
        error.info = info
        raise error from exc
    result = run_scenario(replace(scenario, captured_files={'solution.py': code}))
    if result.trace:
        trace = result.trace
        trace.workflow = 'Nemotron live coding agent'
        trace.metadata['agent_origin'] = 'live_nebius_generation'
        trace.metadata['generation'] = info.model_dump()
        trace.metadata['served_model'] = completion.raw_model_field
        trace.metadata['replay_semantics'] = 'Frozen generated artifact; replay does not resample the LLM.'
        event = next(e for e in trace.events if e.name == 'generate_code')
        event.kind = 'llm_call'
        event.name = 'nebius_generate_code'
        event.input = {'messages': messages}
        event.output = {'code': code, 'raw_response': completion.content}
        event.tokens_in, event.tokens_out = completion.prompt_tokens, completion.completion_tokens
        event.duration_ms = completion.latency_ms
        event.attributes = {'model': completion.model, 'served_model': completion.raw_model_field}
    return result, info
