"""Native citation status in Mechanic and challenge Explorer requests (declared September 30, 2026, after live runs v2d, v2e).

``faultlab-mechanic-evidence/v2-native-citation-status`` (``mechanic_evidence`` in the plan) is frozen into every new
Learn plan whose agent is native adapter v2 (``smolagents-v2``). No other plan declares it: a v2 plan saved before it,
the reference Actor, native adapter v1, and every baseline or compare plan keep their requests byte for byte.

Why. In live runs v2d and v2e the diagnosis Mechanic, reading a native adapter v2.1 source, twice hypothesised that the
agent's report cited evidence labels it had never been shown. Both times that was false: in all 8 diagnosed episodes
every cited label had been shown and decoded, and every decoded ID was delivered. The Mechanic could not see this. Its
request described the adapter's labels (the runtime contract's memory text), but not what the adapter recorded for each
report.

What. A Mechanic diagnosis or candidate request, or a challenge Explorer request, that carries evidence of at least one
episode gets one separate block, ``native_citation_status``. The block has one plain sentence saying what it means, and
one row per episode, in the order the request's evidence first lists it. Each row is the adapter's recorded citation
outcome, read only from that episode's ``report_submitted`` event (native adapter v2.1):
  * ``cited``: the number of tokens the report cited;
  * ``decoded``: how many of them were labels the agent had been shown, decoded to the evidence ID of an observation
    delivered to it (the event's own label map gives that ID, and the event recorded it at that position);
  * ``undecoded``: the tokens the adapter recorded as not decoded (usually none).
Nothing is read from scoring (no check, verdict, trial outcome or finding), and nothing is said about why any check
failed. In a Mechanic request, the runtime contract's v2 memory text gets one added sentence that points to the block.

Size. The block is added before the Mechanic request-size rule (``faultlab-mechanic-context/v2-bounded``) counts the
request, so it is inside that bound. That rule compacts only the evidence tables, so this block is never compacted: a
row stays for every episode, kept or omitted.

Scope. Discovery Explorer requests are unchanged (the discovery protocols are unchanged), and so is every gate:
``diagnosis.py`` (``summarize_evidence``, ``trial_outcomes``, ``runtime_contract``), ``mechanic.py``, ``explorer.py``,
``challenge.py``, the referee and the native adapters. The block is added by two thin wrappers and one call in the
learning loop.
"""
from __future__ import annotations

from app.lab.diagnosis import V2_MEMORY

MECHANIC_EVIDENCE_V2 = 'faultlab-mechanic-evidence/v2-native-citation-status'
BLOCK = 'native_citation_status'
AGENTS = ('smolagents-v2',)
APPLIES_TO = ('mechanic_diagnosis', 'mechanic_proposal', 'explorer_challenge')
ROW_FIELDS = ('episode_id', 'cited', 'decoded', 'undecoded')
# The native adapter v2.1 citation record (app.integrations.external_agent_v2.PROTOCOL_VERSION; checked in tests).
SOURCE_PROTOCOL = 'faultlab-native-adapter/v2.1-shown-order-labels'

MEANING = ('Each row is what the native adapter recorded when that episode\'s agent submitted its report: cited is how many '
           'evidence tokens the report cited, decoded is how many of them were obs-N labels the agent had been shown and so '
           'were decoded to the evidence ID of an observation delivered to it, and undecoded lists every cited token that was '
           'not decoded and was kept exactly as written (all three are null when no complete native adapter v2.1 citation '
           'record was recorded for that episode).')
MEMORY_POINTER = ('This request\'s native_citation_status block lists, for each episode in its evidence, the adapter\'s '
                  'recorded outcome of that decoding: how many tokens the report cited, how many decoded to delivered '
                  'evidence, and any token kept as written.')
RULE = ('For a native adapter v2 Learn plan, every Mechanic diagnosis or candidate request and every challenge Explorer '
        'request that carries evidence of at least one episode gets a separate native_citation_status block: one plain '
        'sentence saying what it means, and one row per episode, in the order the request\'s evidence first lists it, with '
        'the adapter\'s recorded citation outcome from that episode\'s report_submitted event (cited tokens, how many decoded '
        'to delivered evidence, and the undecoded tokens). Nothing is read from scoring, and nothing is said about why a '
        'check failed. A Mechanic request\'s runtime-contract memory text gets one added sentence pointing to the block. The '
        'block is added before the Mechanic request-size rule counts the request, and it is never compacted. Discovery '
        'Explorer requests are unchanged.')


def declaration():
    """The rule as frozen into a reviewed Learn plan of native adapter v2 (run_plans.MechanicEvidencePlan)."""
    return {'protocol': MECHANIC_EVIDENCE_V2, 'agents': list(AGENTS), 'applies_to': list(APPLIES_TO), 'block': BLOCK,
            'row_fields': list(ROW_FIELDS), 'source_event': 'report_submitted', 'source_protocol': SOURCE_PROTOCOL,
            'reads_scoring': False, 'compacted': False, 'discovery_requests_changed': False,
            'meaning': MEANING, 'memory_pointer': MEMORY_POINTER, 'rule': RULE}


def campaign_rule(store, campaign):
    """The declared rule of this campaign's saved plan, or None (every other plan: today's requests exactly)."""
    from app.lab.runner import campaign_run_plan
    return (campaign_run_plan(store, campaign) or {}).get('mechanic_evidence')


# The v2 memory text of app.lab.diagnosis (unchanged there) plus the one sentence that points to the block.
V2_MEMORY_WITH_CITATION_STATUS = V2_MEMORY + ' ' + MEMORY_POINTER


def _summary(value):
    return isinstance(value, dict) and isinstance(value.get('episodes'), list)


def episode_ids(context, request_kind):
    """The episodes whose evidence this request carries, in the order its evidence first lists them."""
    if request_kind == 'mechanic_diagnosis':
        blocks = [context.get('observations')]
    elif request_kind == 'mechanic_proposal':
        blocks = [context.get('development_evidence'),
                  *[item.get('evidence') for item in context.get('challenge_counterexamples') or [] if isinstance(item, dict)]]
    elif request_kind == 'explorer_challenge':
        blocks = [context.get('development_evidence')]
    else:
        raise ValueError(f'Unknown request kind {request_kind!r}')
    seen = []
    for block in blocks:
        if not _summary(block): continue
        for row in block['episodes']:
            if isinstance(row, dict) and isinstance(row.get('episode_id'), str) and row['episode_id'] not in seen:
                seen.append(row['episode_id'])
    return seen


def submitted_report(store, episode_id):
    """The payload of this episode's last recorded report_submitted event (public events only), or None."""
    found, after = None, 0
    while True:
        page = store.events(episode_id, after=after, limit=200)
        for event in page['events']:
            if event.get('type') == 'report_submitted' and event.get('role') == 'actor':
                found = event.get('payload') or {}
        if not page['has_more']: return found
        after = page['next_after']


def citation_row(episode_id, payload):
    """One row from one report_submitted payload; all three values are null without a v2.1 citation record."""
    empty = {'episode_id': episode_id, 'cited': None, 'decoded': None, 'undecoded': None}
    if not isinstance(payload, dict) or payload.get('citation_protocol') != SOURCE_PROTOCOL:
        return empty
    cited, shown = payload.get('cited_evidence_tokens'), payload.get('labels_shown_to_agent')
    decoded_ids, labels = payload.get('decoded_evidence_ids'), payload.get('evidence_labels')
    undecoded = payload.get('cited_tokens_not_decoded')
    if not (isinstance(cited, list) and isinstance(shown, list) and isinstance(decoded_ids, list) and isinstance(labels, dict)
            and isinstance(undecoded, list) and len(decoded_ids) == len(cited)):
        return empty
    evidence_of = {label: evidence_id for evidence_id, label in labels.items()}
    decoded = sum(1 for token, evidence_id in zip(cited, decoded_ids)
                  if isinstance(token, str) and token in shown and evidence_of.get(token) == evidence_id)
    return {'episode_id': episode_id, 'cited': len(cited), 'decoded': decoded, 'undecoded': list(undecoded)}


def block(store, episodes):
    """The native_citation_status block for these episodes (deterministic: store events only, in the given order)."""
    return {'protocol': MECHANIC_EVIDENCE_V2, 'meaning': MEANING,
            'episodes': [citation_row(episode_id, submitted_report(store, episode_id)) for episode_id in episodes]}


def _with_pointer(runtime_contract):
    actor = (runtime_contract or {}).get('actor_contract')
    if not isinstance(actor, dict) or actor.get('memory') != V2_MEMORY:
        # Never claim a pointer over another memory text: a v2 plan's runtime contract always carries the v2 text.
        raise RuntimeError('A native citation-status request needs the native adapter v2 runtime contract')
    return {**runtime_contract, 'actor_contract': {**actor, 'memory': V2_MEMORY_WITH_CITATION_STATUS}}


def attach(store, context, *, request_kind):
    """A copy of the request context with the block (and, for a Mechanic request, the memory pointer).

    A request that carries no episode evidence is returned unchanged.
    """
    episodes = episode_ids(context, request_kind)
    if not episodes: return context
    request = {**context, BLOCK: block(store, episodes)}
    if request_kind != 'explorer_challenge':
        request['runtime_contract'] = _with_pointer(context.get('runtime_contract'))
    return request


class CitationStatusMechanic:
    """The Mechanic as the Diagnostician sees it under the declared rule: its diagnosis request gets the block first.

    It wraps the real Mechanic, or the request-size rule's BoundedMechanic (which then counts the request with the
    block). app/agents/mechanic.py and app/lab/diagnosis.py are unchanged.
    """
    def __init__(self, mechanic, store):
        self.mechanic, self.store = mechanic, store
    def __getattr__(self, name): return getattr(self.mechanic, name)
    async def diagnose(self, context, *, reservation=None):
        return await self.mechanic.diagnose(attach(self.store, context, request_kind='mechanic_diagnosis'), reservation=reservation)


class CitationStatusExplorer:
    """The Explorer as the Challenger sees it under the declared rule: a challenge request gets the block first.

    Every other request passes through unchanged. app/agents/explorer.py and app/lab/challenge.py are unchanged.
    """
    def __init__(self, explorer, store):
        self.explorer, self.store = explorer, store
    def __getattr__(self, name): return getattr(self.explorer, name)
    async def select(self, context, *, challenge=False, **kwargs):
        if challenge:
            context = attach(self.store, context, request_kind='explorer_challenge')
        return await self.explorer.select(context, challenge=challenge, **kwargs)
