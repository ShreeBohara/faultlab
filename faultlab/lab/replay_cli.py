"""``faultlab replay``: re-run a recorded trial from a bundle or a trial store into a fresh world.

Offline. The recorded inputs are re-issued through the replay adapter (``faultlab.lab.replay``)
on the kernel in this process; the new envelope lands in the trial store given. ``--scenario``
replays into a different scenario of the same pack (the divergence stop says where the worlds
part); ``--cut-at`` replays the first n steps and then hands over to the reference adapter.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from faultlab.core import Caps, new_id
from faultlab.evidence import TrialAttempt, plan_hash
from faultlab.evidence.bundles import read_bundle
from faultlab.lab.replay import ReplayAdapter
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker
from faultlab.packs import load_pack


def load_recorded(source: str, attempt_id: str | None):
    if source.endswith(".zip"):
        _, envelopes = read_bundle(source)
    else:
        with TrialStore(source) as store:
            envelopes = store.envelopes()
    if not envelopes:
        raise ValueError(f"No envelopes in {source}")
    if attempt_id is None:
        if len(envelopes) > 1:
            raise ValueError("Several envelopes; pick one with --attempt: " + ", ".join(e.attempt.attempt_id for e in envelopes[:20]))
        return envelopes[0]
    for envelope in envelopes:
        if envelope.attempt.attempt_id == attempt_id:
            return envelope
    raise ValueError(f"No envelope for attempt {attempt_id} in {source}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="faultlab replay", description="Replay a recorded trial into a fresh world (offline)")
    parser.add_argument("source", help="a bundle (.zip) or a trial store (.sqlite3) holding the recorded envelope")
    parser.add_argument("--attempt", default=None, help="attempt id of the envelope to replay (needed when the source holds several)")
    parser.add_argument("--store", required=True, help="trial store to write the replayed envelope to")
    parser.add_argument("--scenario", default=None, help="replay into this scenario instead of the recorded one")
    parser.add_argument("--cut-at", type=int, default=None, help="replay the first n steps, then hand over to the reference adapter")
    parser.add_argument("--referee", choices=("legacy", "none"), default="legacy")
    parser.add_argument("--worlds", default=None)
    args = parser.parse_args(argv)
    try:
        recorded = load_recorded(args.source, args.attempt)
        pack = load_pack(recorded.plan.pack_id)
        scenario_id = args.scenario or recorded.plan.scenario_id
        continuation = None
        if args.cut_at is not None:
            from faultlab.adapters import load_adapter
            reference = load_adapter("reference-orders")
            continuation = reference.act
        adapter = ReplayAdapter(recorded, cut_at=args.cut_at, continuation=continuation)
        referee = None
        if args.referee == "legacy":
            from faultlab.referee.legacy import LegacyOrdersReferee
            referee = LegacyOrdersReferee()
        plan = pack.plan(scenario_id, agent=recorded.plan.agent, environment=recorded.plan.environment,
                         protocol_version=recorded.plan.protocol_version, caps=recorded.plan.caps or Caps())
    except (ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 2
    with TrialStore(args.store) as store:
        worker = TrialWorker(store=store, referee=referee, database_dir=args.worlds)
        attempt = TrialAttempt(attempt_id=new_id("replay"), plan_hash=plan_hash(plan), lifecycle="READY")
        envelope = asyncio.run(worker.run(plan, attempt, adapter))
    print(json.dumps({
        "recorded": {"attempt_id": recorded.attempt.attempt_id, "scenario_id": recorded.plan.scenario_id, "task": recorded.outcome.task},
        "replayed": {"attempt_id": envelope.attempt.attempt_id, "scenario_id": scenario_id, "execution": envelope.outcome.execution,
                     "task": envelope.outcome.task, "reason": envelope.attempt.terminal_reason,
                     "violations": [f.property_id for f in envelope.outcome.findings if f.result == "VIOLATION"],
                     "claims": envelope.outcome.claims.mismatches},
        "steps_replayed": adapter.replayed, "divergence": adapter.divergence, "store": args.store}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
