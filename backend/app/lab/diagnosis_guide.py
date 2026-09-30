"""Diagnosis guide block (built September 30, 2026; NOT OFFERED until its pre-registered probe passes).

``faultlab-diagnosis-guide/v1-kinds-and-checks`` (``diagnosis_guide`` in the plan). A Mechanic diagnosis request of a
Learn plan that declares it gets one separate block of fixed text, ``diagnosis_guide``: the campaign's own task text,
the public meaning of checks C1-C8 (app.agents.explorer.PUBLIC_INVARIANTS, verbatim; its content hash is frozen in the
plan), a two-sentence note on reading them (``checks_note``), a definition of each proposed_kind, a note that
runtime_contract is not a list of pass/fail rules, how the output is used, and the hypothesis length limit. It reads
nothing from any episode or from scoring.

Why (artifacts/analysis-diagnosis-2026-09-30/RECOMMENDATION.md, sections 1.4 and 2). The diagnosis request never
defines the three kinds, never says what C1-C8 mean and never gives the task text, while its only agent-specific text is
about evidence labels and citations; the V4-Pro Mechanic kept telling a citation story that the recorded data refute.

Not offered. DIAGNOSIS_GUIDE_OFFERED is False: run options do not offer the rule and new Learn plans do not freeze it.
It is offered only after the pre-registered request-only probe (RECOMMENDATION.md section 7; P1 and P2 must pass) and a
reviewed change that flips the constant. A plan that declares it (for example one saved after such a change) is still
validated exactly and, if exact, applied by the learning loop.

PM decisions (2026-09-30). The draft's interpretive sentence about C6 (the middle sentence of its ``checks_note``) is
dropped, because it cannot be verified without opening checks.py. The C1-C8 public meanings are included verbatim only,
with no interpretation. The draft's other two ``checks_note`` sentences name no check and interpret none; they are kept
exactly as drafted (PM decision on review finding F4, which pointed out that the builder had dropped all three).

Placement. A thin wrapper adds the block to the diagnosis request outside the native citation-status wrapper, which
sits outside the request-size rule, so the size rule counts the block; that rule compacts only evidence tables, so the
block is never compacted. The diagnosis system prompt, output schema, intervention options, verdict code, candidate
requests and Explorer requests are unchanged. The block contains no worked example.
"""
from __future__ import annotations

from app.agents.explorer import PUBLIC_INVARIANTS
from app.contracts.models import content_hash

DIAGNOSIS_GUIDE_V1 = 'faultlab-diagnosis-guide/v1-kinds-and-checks'
PLAN_KEY = 'diagnosis_guide'
BLOCK = 'diagnosis_guide'
APPLIES_TO = ('mechanic_diagnosis',)
CHECKS_SOURCE = 'app.agents.explorer.PUBLIC_INVARIANTS'
TASK_SOURCE = 'plan.task_text'

# Reviewed constant. False until the pre-registered probe (RECOMMENDATION.md section 7: P1 and P2) passes and the PM
# approves offering the rule. While False, build_run_options does not offer it and prepare_run_plan does not freeze it.
DIAGNOSIS_GUIDE_OFFERED = False

MEANING = ('Fixed lab text for this diagnosis request: the public task, the public meaning of each check, what each '
           'proposed_kind means, and how your output is used. It says nothing about any episode.')

KINDS = {
    'POLICY_GAP': ('The delivered observations were enough for the agent to act and report correctly, and it did not; '
                   'a different recovery policy (the hook rules FaultLab can change) could plausibly prevent the target '
                   'violation.'),
    'CONTRACT_EVIDENCE_GAP': ('Through every declared public tool and status path, the terminal evidence needed to act or '
                              'report correctly could not be delivered within the episode limits, so no recovery policy '
                              'could make the agent right. Contract here means the public service API (its tools, '
                              'statuses and receipts), not the report schema or the adapter\'s evidence labels.'),
    'INCONCLUSIVE': 'The supplied observations and offered interventions cannot distinguish the explanations you consider.',
}

# The draft's checks_note without its middle (C6) sentence; the two sentences kept are the draft's exact text.
CHECKS_NOTE = ('Each episode\'s checks row gives the fixed checks by check_id and category; the checks field gives each '
               'check\'s public meaning. Explain each failed check from its own meaning.')

CONTRACT_NOTE = ('runtime_contract describes how the agent, its adapter and the policy hooks work (tools, report schema, '
                 'evidence labels, hook timing). It is not a list of pass/fail rules; the checks are.')

# Deliberately not said (so a measured change can be attributed to the definitions, not to pressure): that proposed_kind
# never changes the verdict, that requesting an intervention is not a claim it will be SUPPORTED, and that an
# INCONCLUSIVE source gets no repair candidate.
USE = ('Fixed code runs only the intervention you request, as three fresh control/treatment pairs, and assigns the '
       'verdict from the reproduction and that result. With no requested intervention, or an output still invalid after '
       'one format repair, no experiment runs and the verdict is INCONCLUSIVE.')

HYPOTHESIS_LENGTH = ('hypothesis is at most 600 characters including spaces (about 90 words); two sentences are enough. If '
                     'a reply fails with string_too_long at hypothesis, shortening the hypothesis is the formatting correction.')

RULE = ('For a Learn plan that declares it, each Mechanic diagnosis request gets one separate diagnosis_guide block of fixed '
        'text: the plan\'s task text, the public meaning of checks C1-C8 (the Explorer\'s public_invariants, verbatim, with '
        'their content hash frozen in the plan), a definition of each proposed_kind, a note that runtime_contract is not a '
        'list of pass/fail rules, how the output is used, and the hypothesis length limit. It interprets no check and reads '
        'nothing from any episode or from scoring. The diagnosis system prompt, output schema, intervention options, verdict '
        'code, candidate requests and Explorer requests are unchanged. The block is added before the Mechanic request-size '
        'rule counts the request and is never compacted.')

FIXED_TEXT = {'meaning': MEANING, 'kinds': KINDS, 'checks_note': CHECKS_NOTE, 'contract_note': CONTRACT_NOTE,
              'use': USE, 'hypothesis_length': HYPOTHESIS_LENGTH, 'rule': RULE}


def declaration():
    """The rule as it would be frozen into a Learn plan (run_plans.DiagnosisGuidePlan), with today's PUBLIC_INVARIANTS."""
    return {'protocol': DIAGNOSIS_GUIDE_V1, 'applies_to': list(APPLIES_TO), 'block': BLOCK,
            'checks_source': CHECKS_SOURCE, 'checks': dict(PUBLIC_INVARIANTS), 'checks_hash': content_hash(PUBLIC_INVARIANTS),
            'task_source': TASK_SOURCE, 'reads_episodes': False, 'reads_scoring': False, 'compacted': False,
            'system_prompt_changed': False, 'verdict_code_changed': False, 'interprets_checks': False,
            'meaning': MEANING, 'kinds': dict(KINDS), 'checks_note': CHECKS_NOTE, 'contract_note': CONTRACT_NOTE,
            'use': USE, 'hypothesis_length': HYPOTHESIS_LENGTH, 'rule': RULE}


def campaign_rule(store, campaign):
    """The declared rule of this campaign's saved plan, or None (every other plan: today's requests exactly)."""
    from app.lab.runner import campaign_run_plan
    return (campaign_run_plan(store, campaign) or {}).get(PLAN_KEY)


def block(task_text, rule=None):
    """The diagnosis_guide block: the declared fixed text plus the campaign's own task text. Deterministic; no store reads.

    rule is the plan's frozen declaration (Start has checked that it equals the installed one); None uses the installed one.
    """
    rule = declaration() if rule is None else rule
    return {'protocol': rule['protocol'], 'meaning': rule['meaning'], 'task': task_text, 'kinds': dict(rule['kinds']),
            'checks': dict(rule['checks']), 'checks_note': rule['checks_note'], 'contract_note': rule['contract_note'],
            'use': rule['use'], 'hypothesis_length': rule['hypothesis_length']}


def attach(context, *, task_text, rule=None):
    """A copy of the diagnosis request context with the block; every other key is unchanged."""
    if BLOCK in context:
        raise RuntimeError('A diagnosis request already carries a diagnosis_guide block')
    return {**context, BLOCK: block(task_text, rule)}


class DiagnosisGuideMechanic:
    """The Mechanic as the Diagnostician sees it under the declared rule: its diagnosis request gets the block first.

    It wraps the citation-status wrapper, the request-size rule's BoundedMechanic (which then counts the request with the
    block) or the real Mechanic. Candidate requests (propose, propose_completion) pass through unchanged.
    """
    def __init__(self, mechanic, *, task_text, rule=None):
        self.mechanic, self.task_text, self.rule = mechanic, task_text, rule

    def __getattr__(self, name):
        return getattr(self.mechanic, name)

    async def diagnose(self, context, **kwargs):
        return await self.mechanic.diagnose(attach(context, task_text=self.task_text, rule=self.rule), **kwargs)
