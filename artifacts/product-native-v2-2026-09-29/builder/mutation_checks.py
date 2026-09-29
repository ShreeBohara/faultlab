"""Apply one mutation at a time to the real source, run the targeted tests, restore the exact bytes ($0, offline).

Run from faultlab/:  .venv/bin/python artifacts/product-native-v2-2026-09-29/builder/mutation_checks.py
Each mutation must make at least one test fail; the file's sha256 is checked after every restore.
"""
import hashlib, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
B = ROOT / 'backend'
V2 = 'app/integrations/external_agent_v2.py'
T_V2 = ['tests/integrations/test_native_adapter_v2.py']
MUTATIONS = [
    ('labels removed from tool results', V2, 'return canonical_json(value)\n', 'return text\n', T_V2),
    ('decode removed', V2, 'answer = {**answer, "evidence_ids": [decode_citations([token], delivered)[0] if isinstance(token, str)',
     'answer = {**answer, "evidence_ids": [token if isinstance(token, str)', T_V2),
    ('decode against the live journal, not the request', V2, '        delivered = self.request_observations\n',
     '        delivered = self._journal_rows()\n', T_V2),
    ('no response contract on the final turn', V2, '            kwargs = {**kwargs, "response_contract": NATIVE_FINAL_ANSWER_CONTRACT}',
     '            kwargs = kwargs', T_V2),
    ('all tools offered on the final turn', V2, 'for tool in tools if tool.name == "final_answer"]', 'for tool in tools]', T_V2),
    ('step guard removed', V2, '        if context.broker.meter.caps.actor_calls != ALIGNED_STEPS:\n',
     '        if False:\n', T_V2),
    ('blocked-report observations not labelled', V2, '                self._shown(o.model_dump(mode="json"), labels) for o in result.observations]}))',
     '                o.model_dump(mode="json") for o in result.observations]}))', T_V2),
    ('validation error quotes decoded answer', V2, '            TaskReport.model_validate_json(canonical_json(arguments["answer"]))\n            raise',
     '            raise', T_V2),
    ('v2 adapter hash omits its module', 'app/integrations/registry.py',
     'NATIVE_V2: ("registry.py", "external_agent.py", "external_agent_v2.py")}', 'NATIVE_V2: ("registry.py", "external_agent.py")}',
     ['tests/lab/test_native_adapter_v2_product.py::test_adapter_hashes_cover_their_own_modules']),
    ('v2 history treated as non-native', 'app/lab/agent_history.py',
     "    if entry in NATIVE_ENTRYPOINTS:\n        identity['source_hash']", "    if entry == NATIVE_ENTRYPOINT:\n        identity['source_hash']",
     ['tests/lab/test_native_adapter_v2_product.py::test_v1_and_v2_histories_never_merge']),
    ('bundle target kind lost', 'app/lab/bundle_imports.py', "'agent': ENTRYPOINT_AGENTS.get(registration.adapter_entrypoint_id, 'unsupported')}",
     "'agent': {'orders-prototype-v1': 'reference', 'smolagents-toolcalling-v1': 'smolagents'}.get(registration.adapter_entrypoint_id, 'unsupported')}",
     ['tests/lab/test_native_adapter_v2_product.py::test_bundle_round_trip_from_a_v2_episode_to_a_fresh_v2_rerun']),
    ('native contract changes the reference contract', 'app/providers/runtime.py', '"name": "FaultLabActorFinalReport", "strict": True,',
     '"name": "FaultLabActorFinalReport", "strict": True, "native": False,', ['tests/providers/test_native_final_answer_contract.py']),
    ('v1 transport text changed (golden must catch it)', 'app/integrations/external_agent.py', 'No markdown.', 'No markdown at all.',
     ['tests/integrations/test_native_adapter_v1_golden.py']),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    rows, ok = [], True
    for name, rel, old, new, tests in MUTATIONS:
        path = B / rel
        original = path.read_bytes(); before = sha(path)
        text = original.decode()
        if text.count(old) != 1:
            rows.append(f'SETUP-ERROR  {name}: pattern found {text.count(old)} times'); ok = False; continue
        try:
            path.write_text(text.replace(old, new))
            result = subprocess.run([str(ROOT / '.venv/bin/python'), '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '-x', *tests],
                                    cwd=B, capture_output=True, text=True, timeout=900)
            last = [line for line in result.stdout.strip().splitlines() if line.strip()][-1]
            caught = result.returncode != 0
            ok &= caught
            rows.append(f"{'CAUGHT ' if caught else 'MISSED '}  {name}: {last}")
        finally:
            path.write_bytes(original)
            assert sha(path) == before, f'restore failed for {rel}'
    rows.append('all restored byte-identical (sha256 checked after each)')
    print('\n'.join(rows))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
