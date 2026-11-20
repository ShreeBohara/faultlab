"""Run one stage of bookings screen 2 (preflight: the first drawn case x3; rest: the other fifteen x3) with the live provider."""
import asyncio, hashlib, json, sys
from pathlib import Path
R = Path("/Users/shree/FaultLab/faultlab")
sys.path[:0] = [str(R), str(R / "backend")]
from app.config import Settings
from app.providers.runtime import RuntimeProvider
from faultlab.adapters.pack_actor import PackActorAdapter
from faultlab.core import Caps
from faultlab.evidence import EnvSpec, RepetitionPolicy
from faultlab.lab.cli import PROTOCOL_VERSION
from faultlab.lab.scheduler import run_batch, schedule
from faultlab.lab.store import TrialStore
from faultlab.lab.worker import TrialWorker
from faultlab.referee.bookings import BookingsReferee
from faultlab.research.bookings_draw import load_cases, pack_with

d, stage, MODEL = Path(__file__).resolve().parent, sys.argv[1], "anthropic:claude-haiku-5-5"
decl = json.loads((d / "DECLARATION.json").read_text())
assert hashlib.sha256((d / "cases.json").read_bytes()).hexdigest() == decl["design"]["cases_sha256"], "cases changed"
scenarios = load_cases(d / "cases.json")
pack = pack_with(scenarios)
assert pack.digest() == decl["design"]["pack_digest"], "pack changed"
ids = [s.scenario_id for s in scenarios]
chosen = ids[:1] if stage == "preflight" else ids[1:]
adapter = PackActorAdapter(RuntimeProvider(Settings.from_env(), live_authorized=True), MODEL, pack.pack_id)
assert adapter.spec.prompt_digest == decl["design"]["adapter"]["prompt_digest"], "prompt changed"
caps = Caps(model_calls=8, http_attempts=18, wall_seconds=90, dollars=decl["actor"]["per_trial_bound_usd"])
plans = [pack.plan(i, agent=adapter.manifest(), environment=EnvSpec(kind="simulator"), protocol_version=PROTOCOL_VERSION, caps=caps)
         .model_copy(update={"repetition": RepetitionPolicy(k=3)}) for i in chosen]
with TrialStore(d / f"{stage}.sqlite3") as store:
    batch = schedule(store, plans, name=f"bookings-screen-2-{stage}", caps=Caps(dollars=decl["money"]["batch_caps_usd"][stage]))
    worker = TrialWorker(store=store, referee=BookingsReferee(), database_dir=d / f"{stage}-worlds", load=lambda pack_id: pack)
    asyncio.run(run_batch(store, batch.batch_id, worker, adapter))
    print(json.dumps(store.summary(batch_id=batch.batch_id), default=str)[:2000])
