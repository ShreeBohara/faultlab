"""Mutation checks for the fixer's changes ($0, offline, no .env read).

Each mutant puts one fix back to its reviewed (unfixed) form in the working tree, runs the named tests, then
restores the fixed file and confirms its SHA-256 is unchanged. The fixed tree must pass every named test; each
mutant must make exactly the tests that pin its fix fail. No git command is run and the index is not touched.

Run from faultlab/backend:  ../.venv/bin/python ../artifacts/product-native-v2-2026-09-29/fixer/mutation_checks.py
Writes mutation-checks.log beside this file.
"""
from hashlib import sha256
import os
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[2] / "backend"
LOG = HERE / "mutation-checks.log"
V2 = BACKEND / "app/integrations/external_agent_v2.py"
PLANS = BACKEND / "app/lab/run_plans.py"

T = "tests/integrations/test_native_adapter_v2.py::"
INT1 = T + "test_a_non_blocking_hook_read_the_agent_never_saw_cannot_be_cited_by_a_guessed_label"
M1 = T + "test_a_write_attempt_the_broker_retried_internally_cannot_be_cited_by_a_guessed_label"
SHOWN = T + "test_citing_only_the_labels_shown_still_decodes_to_what_v1_would_cite"
SNAP = T + "test_decode_uses_only_observations_delivered_by_the_request"
INT2_OVER = T + "test_a_final_request_over_the_limit_only_with_its_schema_is_refused_before_it_is_charged[one-token-over-with-schema]"
INT2_AT = T + "test_a_final_request_over_the_limit_only_with_its_schema_is_refused_before_it_is_charged[exactly-at-the-limit-with-schema]"
INT2_V1 = T + "test_the_final_turn_refusal_matches_v1s_refusal_of_an_over_limit_ordinary_turn"
L4_V1 = "tests/lab/test_native_adapter_v2_product.py::test_start_after_a_runtime_change_names_the_next_step_and_keeps_the_plan_readable[smolagents]"
L4_V2 = "tests/lab/test_native_adapter_v2_product.py::test_start_after_a_runtime_change_names_the_next_step_and_keeps_the_plan_readable[smolagents-v2]"
L4_PIN = "tests/lab/test_native_baseline_study_planned.py::test_study_refuses_when_plan_registration_differs_from_current_runtime[runtime]"
ALL = [INT1, M1, SHOWN, SNAP, INT2_OVER, INT2_AT, INT2_V1, L4_V1, L4_V2, L4_PIN]


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def replace_once(text, old, new):
    assert text.count(old) == 1, old[:80]
    return text.replace(old, new)


def decode_every_delivered_label(text):
    """INT-1 / M1 unfixed: decode any label of a delivered journal row, shown or not."""
    return replace_once(text, "if isinstance(token, str) and token in shown else token", "if isinstance(token, str) else token")


def no_admission_before_charge(text):
    """INT-2 unfixed: no schema-inclusive admission before v1 charges the final turn."""
    return replace_once(text, """            validate_request_input(self.admitted_request, self.context.metadata["model_id"],
                                   response_contract=NATIVE_FINAL_ANSWER_CONTRACT)
""", "")


def old_start_message(text):
    """L4 unfixed: the Start refusal without the next step."""
    return replace_once(text, """        raise StoreConflict('Current source, model or campaign limits differ from the saved plan. Register the agent '
                            'again and create a new campaign; this saved plan stays readable')
""", """        raise StoreConflict('Current source, model or campaign limits differ from the saved plan')
""")


MUTANTS = [
    ("fixed tree (no mutation)", None, None, set()),
    ("reviewed v2 module, exactly as before the fixer (external_agent_v2.before-fix.py)", V2,
     lambda _: (HERE / "external_agent_v2.before-fix.py").read_text(), {INT1, M1, INT2_OVER}),
    ("INT-1/M1 only: decode every delivered label, shown or not", V2, decode_every_delivered_label, {INT1, M1}),
    ("INT-2 only: no schema-inclusive admission before the final turn is charged", V2, no_admission_before_charge, {INT2_OVER}),
    ("L4 only: Start refusal without the next step", PLANS, old_start_message, {L4_V1, L4_V2, L4_PIN}),
]


def run(tests):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1"}
    result = subprocess.run([sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-rA", "-q", *tests],
                            cwd=BACKEND, env=env, capture_output=True, text=True, timeout=900)
    outcomes = {}
    for line in result.stdout.splitlines():
        match = re.match(r"^(PASSED|FAILED|ERROR) (\S+)", line)
        if match:
            outcomes[match.group(2)] = match.group(1)
    return outcomes, result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "(no output)"


def main():
    fixed = {path: digest(path) for path in (V2, PLANS)}
    lines, ok = [], True
    for name, path, mutate, must_fail in MUTANTS:
        original = path.read_text() if path else None
        try:
            if path:
                path.write_text(mutate(original))
            outcomes, summary = run(ALL)
        finally:
            if path:
                path.write_text(original)
        restored = all(digest(p) == h for p, h in fixed.items())
        failed = {t for t in ALL if outcomes.get(t) != "PASSED"}
        verdict = "AS EXPECTED" if failed == must_fail and len(outcomes) == len(ALL) and restored else "UNEXPECTED"
        ok &= verdict == "AS EXPECTED"
        lines.append(f"== {name}")
        lines.append(f"   pytest: {summary}")
        for t in ALL:
            expected = "FAIL" if t in must_fail else "PASS"
            lines.append(f"   {outcomes.get(t, 'NOT RUN'):7} (expected {expected})  {t}")
        lines.append(f"   fixed files restored byte for byte: {restored}")
        lines.append(f"   verdict: {verdict}")
    lines.append(f"OVERALL: {'ALL MUTANTS BEHAVED AS EXPECTED' if ok else 'AT LEAST ONE UNEXPECTED RESULT'}")
    lines.append("fixed file SHA-256: " + ", ".join(f"{p.relative_to(BACKEND)}={h}" for p, h in fixed.items()))
    LOG.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
