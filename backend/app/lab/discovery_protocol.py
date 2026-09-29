"""Declared discovery protocols for the original learning loop's Explorer slots.

v1 (``faultlab-discovery/v1``) is the default and today's exact behaviour: one Explorer
request per slot, every valid pick that is not an exact (v1-identity) duplicate runs one
Actor episode, and nothing is pre-checked.

v2 (``faultlab-discovery/v2-reachability``) must be declared in the reviewed campaign plan.
Before a paid Actor episode it labels each fault with the reachability pre-check
(app.lab.reachability) and runs only picks whose every fault is FORCED. A refused pick
(exact duplicate under the order-aware v2 identity, or not all FORCED) gets ONE re-plan
request in the same slot, with the refusal reasons. Declared budget per campaign: the
unchanged slot cap (8), at most two Explorer requests per slot (16), at most one Actor
episode per slot (8). Every refusal is an immutable selection record. The pre-check never
changes what the Actor sees or how any episode is scored.

Transport retries (both protocols, app.agents.transport_retry): an Explorer request that
received no answer (connection error, timeout, HTTP 503) may be re-sent once. A retry is
the same request, not a new selection request, so it does NOT count toward
``explorer_requests_max`` (counting it would let a network fault use up a slot's re-plan).
It is bounded separately and declared as ``explorer_transport_retries_max`` (one per
request: 8 under v1, 16 under v2), and charged on the campaign ledger before it is sent.
Plans saved before this field existed declare no Explorer retry.
"""
from app.agents.transport_retry import RETRIES_PER_REQUEST
from app.lab.challenge import SCHEDULE_IDENTITY_V1, SCHEDULE_IDENTITY_V2, identity_for

DISCOVERY_V1 = 'faultlab-discovery/v1'
DISCOVERY_V2 = 'faultlab-discovery/v2-reachability'
DISCOVERY_PROTOCOLS = (DISCOVERY_V1, DISCOVERY_V2)
V2_DISPATCH_RULE = ('Before any Actor episode, a free in-process replay of the real simulator labels every fault '
                    'FORCED, NOT_FORCED or IMPOSSIBLE for the registered agent. A pick runs only if every fault is '
                    'FORCED. A refused pick (a duplicate, or any fault not FORCED) gets one re-plan request in the '
                    'same slot with the reasons; if that is refused too, the slot ends without an episode.')
V1_DISPATCH_RULE = 'Every valid pick that is not an exact duplicate runs one Actor episode; nothing is pre-checked.'


def declaration(protocol, caps, *, caller=None):
    """The discovery block frozen into a reviewed learn plan."""
    slots = caps.discovery_selections if hasattr(caps, 'discovery_selections') else caps['discovery_selections']
    if protocol == DISCOVERY_V1:
        return {'protocol': DISCOVERY_V1, 'schedule_identity': SCHEDULE_IDENTITY_V1, 'slots': slots,
                'explorer_requests_max': slots, 'explorer_transport_retries_max': slots * RETRIES_PER_REQUEST,
                'actor_episodes_max': slots, 'replans_per_slot': 0,
                'dispatch_rule': V1_DISPATCH_RULE, 'pre_check': None}
    if protocol == DISCOVERY_V2:
        if caller is None: raise ValueError('Discovery v2 requires a supported caller model')
        from app.lab.reachability import LABELLER_VERSION
        return {'protocol': DISCOVERY_V2, 'schedule_identity': SCHEDULE_IDENTITY_V2, 'slots': slots,
                'explorer_requests_max': 2 * slots, 'explorer_transport_retries_max': 2 * slots * RETRIES_PER_REQUEST,
                'actor_episodes_max': slots, 'replans_per_slot': 1,
                'dispatch_rule': V2_DISPATCH_RULE,
                'pre_check': {'labeller': LABELLER_VERSION, 'caller_model': caller.descriptor()}}
    raise ValueError('Unknown discovery protocol')


def campaign_discovery(store, campaign):
    """The declared discovery block for a campaign; unplanned or older plans are v1."""
    from app.lab.runner import campaign_run_plan
    plan = campaign_run_plan(store, campaign)
    block = (plan or {}).get('discovery')
    return block if block else declaration(DISCOVERY_V1, campaign.caps)


def identity_for_campaign(store, campaign):
    return identity_for(campaign_discovery(store, campaign)['schedule_identity'])


class BudgetViolation(RuntimeError):
    pass


class DiscoveryV2:
    """One campaign's v2 selection state: caller model, labels and the declared budget."""
    protocol = DISCOVERY_V2

    def __init__(self, block, *, agent, incumbent):
        from app.lab.reachability import caller_model_for
        if block.get('protocol') != DISCOVERY_V2:
            raise ValueError('Not a discovery v2 declaration')
        rules = incumbent.content.rules if incumbent.content is not None else []
        self.caller = caller_model_for(agent, rules)  # refuses native agents and policies with rules
        declared = block['pre_check']['caller_model']
        if declared != self.caller.descriptor():
            raise ValueError('Declared pre-check caller model differs from the installed one')
        self.block = block
        self.identity = identity_for(block['schedule_identity'])
        self.explorer_requests = 0
        self.transport_retries = 0
        self.actor_episodes = 0
        self._normal_path = None

    async def label(self, recipe):
        from app.lab.reachability import label_recipe_async
        return await label_recipe_async(recipe, self.caller)

    async def normal_path(self):
        if self._normal_path is None:
            import asyncio
            from app.lab.reachability import normal_path
            self._normal_path = await asyncio.to_thread(normal_path, self.caller)
        return self._normal_path

    async def context(self):
        return {'discovery_protocol': DISCOVERY_V2, 'agent_action_space': self.caller.facts(),
                'normal_path': await self.normal_path(), 'dispatch_rule': V2_DISPATCH_RULE,
                'selection_budget': {key: self.block[key] for key in
                                     ('slots', 'explorer_requests_max', 'actor_episodes_max', 'replans_per_slot')}}

    def admit_request(self):
        if self.explorer_requests >= self.block['explorer_requests_max']:
            raise BudgetViolation('Declared Explorer request budget exhausted')
        self.explorer_requests += 1

    def transport_retry_available(self):
        """Within the declared Explorer transport-retry bound (none if the plan declared none)."""
        return self.transport_retries < (self.block.get('explorer_transport_retries_max') or 0)

    def admit_episode(self):
        if self.actor_episodes >= self.block['actor_episodes_max']:
            raise BudgetViolation('Declared Actor episode budget exhausted')
        self.actor_episodes += 1


def slot_feedback(record):
    """What a re-plan request is told about the refused pick: readable, templated, no hashes."""
    decision = record['search_decision']
    from app.lab.reachability import readable_recipe
    refused = decision.get('refused_fault_spec')
    label = decision.get('reachability') or {}
    return {'refused_selection_id': record['selection_id'], 'status': decision['status'],
            'reason': decision.get('reason'),
            'refused_recipe': readable_recipe(refused) if refused else None,
            'faults': [{key: fault[key] for key in ('fault', 'verdict', 'reason_code', 'explanation')}
                       for fault in label.get('faults', [])],
            'duplicate_of_selection_refs': decision.get('prior_selection_refs', []),
            'duplicate_of_episode_refs': decision.get('prior_episode_refs', []),
            'instruction': 'This slot has one re-plan request left. Choose a recipe whose every fault is FORCED for '
                           'this agent and that is not already listed in search_ledger.'}
