"""Shared, read-only helpers for the native citation-status tests and evidence scripts ($0, offline).

They rebuild a live campaign's Mechanic diagnosis request from saved records only, with the real Diagnostician (the
Mechanic is replaced by a capture that raises before anything is sent or saved), so the rebuilt request is exactly the
context the learning loop would have handed to the Mechanic.
"""
from app.contracts.models import (Campaign, Counterexample, EvidenceBundle, FaultSpec, PolicyVersion, ReductionResult,
                                  TrialResult, canonical_json)

SAVED_STORE = '/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/lab.sqlite3'
V2D = 'campaign-ea66672d7a904bd8a011d6922790c963'
V2E = 'campaign-37e66b6c3a544a4d9bde4161db6bf0aa'
MECHANIC_MODEL = 'deepseek-ai/DeepSeek-V4-Pro-0813'   # both campaigns' Mechanic model (their mechanic_outputs records)


class Captured(Exception):
    """Raised by the capture Mechanic after it has kept the request; nothing is sent and nothing is saved."""


class CaptureMechanic:
    def __init__(self): self.contexts = []
    async def diagnose(self, context, *, reservation=None):
        self.contexts.append(context)
        raise Captured()


def _model(store, kind, ident, cls):
    return cls.model_validate_json(canonical_json(store.get_record(kind, ident)))


def _evidence(store, episode_ids):
    return [_model(store, 'evidence', episode_id, EvidenceBundle) for episode_id in episode_ids]


def diagnosed_counterexample(store, campaign_id):
    """The campaign's diagnosed counterexample (the one its diagnostic_campaigns record names)."""
    link = next(r for r in store.list_records('diagnostic_campaigns') if r['campaign_id'] == campaign_id)
    return _model(store, 'counterexamples', link['counterexample_id'], Counterexample)


def diagnosis_inputs(store, campaign_id):
    """The arguments the learning loop passed to Diagnostician.run for this campaign, from saved records only."""
    from app.lab.diagnosis import reduction_context
    campaign = store.get_model('campaigns', campaign_id, Campaign)
    counter = diagnosed_counterexample(store, campaign_id)
    incumbent = _model(store, 'policies', 'policy-v0', PolicyVersion)
    reduction_ids = [row['episode_id'] for row in store.list_records('episodes')
                     if row['campaign_id'] == campaign_id and row['experiment_purpose'] == 'reduction']
    reduced = [_model(store, 'trials', e, TrialResult) for e in reduction_ids]
    reduction = reduction_context(_model(store, 'reductions', counter.counterexample_id, ReductionResult), reduced,
                                  _evidence(store, [t.episode_id for t in reduced if t.lifecycle == 'COMPLETED']))
    retained = FaultSpec.model_validate(store.get_record('retained_recipes', counter.counterexample_id)['retained_recipe'])
    reproduction = [_model(store, 'trials', e, TrialResult) for e in counter.reproduction_trial_ids]
    evidence = _evidence(store, [counter.source_episode_id, *counter.reproduction_trial_ids])
    return campaign, counter, retained, incumbent, reproduction, evidence, reduction


async def rebuild_diagnosis_request(store, campaign_id, *, wrap=None):
    """The campaign's diagnosis request as the Diagnostician builds it. wrap(mechanic) optionally wraps the capture
    Mechanic (for example with citation_status.CitationStatusMechanic) exactly as the learning loop would."""
    from app.lab.diagnosis import Diagnostician
    campaign, counter, retained, incumbent, reproduction, evidence, reduction = diagnosis_inputs(store, campaign_id)
    capture = CaptureMechanic()
    mechanic = wrap(capture) if wrap else capture
    try:
        await Diagnostician(store, None, None, mechanic).run(campaign, counter, retained, incumbent, reproduction,
                                                             evidence=evidence, reduction=reduction)
    except Captured:
        pass
    context, = capture.contexts
    return counter, context


def copy_read_only(source, target):
    """A scratch copy of a saved store, read from the original with mode=ro&immutable=1 (the original is never written)."""
    import sqlite3
    src = sqlite3.connect(f'file:{source}?mode=ro&immutable=1', uri=True); dst = sqlite3.connect(target)
    try:
        src.backup(dst)
        dst.execute('PRAGMA journal_mode=DELETE')   # the copy only, so a read-only open needs no -wal/-shm files
    finally:
        dst.close(); src.close()


def remove_copy(target):
    """Delete a scratch copy and any -wal/-shm/-journal file next to it; returns True when none is left."""
    from pathlib import Path
    target = Path(target)
    paths = [target, *(target.with_name(target.name + suffix) for suffix in ('-wal', '-shm', '-journal'))]
    for path in paths: path.unlink(missing_ok=True)
    return not any(path.exists() for path in paths)
