"""PROPOSED (not installed): app/lab/diagnosis_guide.py -- a declared diagnosis-guide block for Mechanic diagnosis requests.

This file is a design draft written by the minimal-change designer on 2026-09-30. It is NOT imported by the product.
It mirrors app/lab/citation_status.py: a thin wrapper adds one separate block to the diagnosis request before the
request-size rule counts it. app/agents/mechanic.py, app/agents/prompts/diagnosis.md, app/lab/diagnosis.py and the
referee are unchanged.

``faultlab-diagnosis-guide/v1-kinds-and-checks`` (``diagnosis_guide`` in the plan) would be frozen into every new Learn
plan. A plan saved before it declares nothing and keeps its diagnosis requests byte for byte.
"""
from __future__ import annotations

from app.agents.explorer import PUBLIC_INVARIANTS
from app.contracts.models import content_hash

DIAGNOSIS_GUIDE_V1 = 'faultlab-diagnosis-guide/v1-kinds-and-checks'
BLOCK = 'diagnosis_guide'
APPLIES_TO = ('mechanic_diagnosis',)

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

CHECKS_NOTE = ('Each episode\'s checks row gives the fixed checks by check_id and category; the checks field gives each '
               'check\'s public meaning. C6 is the check of the report\'s citations: where C6 passed, that report\'s '
               'citations met it. Explain each failed check from its own meaning.')

CONTRACT_NOTE = ('runtime_contract describes how the agent, its adapter and the policy hooks work (tools, report schema, '
                 'evidence labels, hook timing). It is not a list of pass/fail rules; the checks are.')

# Deliberately NOT said here (left out so a later test can attribute any change to the definitions, not to pressure):
# that proposed_kind never changes the verdict, and that an INCONCLUSIVE source gets no repair candidate.
USE = ('Fixed code runs only the intervention you request, as three fresh control/treatment pairs, and assigns the '
       'verdict from the reproduction and that result. With no requested intervention, or an output still invalid after '
       'one format repair, no experiment runs and the verdict is INCONCLUSIVE.')

LENGTH = ('hypothesis is at most 600 characters including spaces (about 90 words); two sentences are enough. If a reply '
          'fails with string_too_long at hypothesis, shortening the hypothesis is the formatting correction.')

RULE = ('For every new Learn plan, each Mechanic diagnosis request gets one separate diagnosis_guide block of fixed text: '
        'the plan\'s task text, the public meaning of checks C1-C8 (the Explorer\'s public_invariants, unchanged), a '
        'definition of each proposed_kind, a note that runtime_contract is not a list of pass/fail rules, how the output is '
        'used, and the hypothesis length limit. It reads nothing from any episode or from scoring. The diagnosis system '
        'prompt, output schema, intervention options, verdict code, candidate requests and Explorer requests are '
        'unchanged. The block is added before the Mechanic request-size rule counts the request and is never compacted.')


def declaration():
    """The rule as frozen into a reviewed Learn plan (proposed run_plans.DiagnosisGuidePlan)."""
    return {'protocol': DIAGNOSIS_GUIDE_V1, 'applies_to': list(APPLIES_TO), 'block': BLOCK,
            'checks_source': 'app.agents.explorer.PUBLIC_INVARIANTS', 'checks_hash': content_hash(PUBLIC_INVARIANTS),
            'reads_episodes': False, 'reads_scoring': False, 'compacted': False, 'system_prompt_changed': False,
            'meaning': MEANING, 'kinds': dict(KINDS), 'checks_note': CHECKS_NOTE, 'contract_note': CONTRACT_NOTE,
            'use': USE, 'length': LENGTH, 'rule': RULE}


def campaign_rule(store, campaign):
    """The declared rule of this campaign's saved plan, or None (every other plan: today's requests exactly)."""
    from app.lab.runner import campaign_run_plan
    return (campaign_run_plan(store, campaign) or {}).get('diagnosis_guide')


def block(task_text):
    """The diagnosis_guide block: constant text plus the plan's own task text. Deterministic; no store reads."""
    return {'protocol': DIAGNOSIS_GUIDE_V1, 'meaning': MEANING, 'task': task_text, 'kinds': dict(KINDS),
            'checks': dict(PUBLIC_INVARIANTS), 'checks_note': CHECKS_NOTE, 'contract_note': CONTRACT_NOTE,
            'use': USE, 'hypothesis_length': LENGTH}


def attach(context, *, task_text):
    """A copy of the diagnosis request context with the block; every other key is unchanged."""
    if BLOCK in context:
        raise RuntimeError('A diagnosis request already carries a diagnosis_guide block')
    return {**context, BLOCK: block(task_text)}


class DiagnosisGuideMechanic:
    """The Mechanic as the Diagnostician sees it under the declared rule: its diagnosis request gets the block first.

    It wraps the real Mechanic, the citation-status wrapper or the request-size rule's BoundedMechanic (which then counts
    the request with the block). Candidate requests (propose, propose_completion) pass through unchanged.
    """
    def __init__(self, mechanic, *, task_text):
        self.mechanic, self.task_text = mechanic, task_text
    def __getattr__(self, name): return getattr(self.mechanic, name)
    async def diagnose(self, context, *, reservation=None):
        return await self.mechanic.diagnose(attach(context, task_text=self.task_text), reservation=reservation)
