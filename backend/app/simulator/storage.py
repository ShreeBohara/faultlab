"""One SQLite database per world. Transactions serialize clock and effects.

The state row is an atomic aggregate, while projection/receipt/event tables are
append-only histories protected by SQL triggers. No database path is public.
"""
from contextlib import contextmanager
from pathlib import Path
import json
import secrets
import sqlite3
from threading import RLock
from app.contracts.models import Event, FaultSpec, Order, TaskIntent, WorldSnapshot, canonical_json, new_id, content_hash

class WorldError(Exception):
    def __init__(self, code, status=409): self.code,self.status=code,status

class WorldStore:
    def __init__(self,directory):
        self.directory=Path(directory)
        self._lock=RLock()

    def _path(self,world_id):
        if not isinstance(world_id,str) or not world_id.startswith('world-') or not world_id[6:].isalnum(): raise WorldError('WORLD_NOT_FOUND',404)
        return self.directory/(world_id+'.sqlite3')

    def create(self,episode_id,intent:TaskIntent,fault_spec:FaultSpec,fixture_id='standard-v1'):
        from .faults import validate_schedule
        initial_version=4 if fixture_id=='history-v1' else 1
        if fixture_id not in ('standard-v1','history-v1'): raise WorldError('UNKNOWN_FIXTURE',422)
        if intent.expected_version!=initial_version: raise WorldError('FIXTURE_VERSION_MISMATCH',422)
        history=[Order(order_id=intent.order_id,applied_shipping='standard',requested_shipping='standard',version=v).model_dump(mode='json') for v in range(1,initial_version+1)]
        validate_schedule(fault_spec,history)
        world_id=new_id('world'); capability=secrets.token_urlsafe(32)
        state={'world_id':world_id,'episode_id':episode_id,'capability_hash':content_hash(capability),'intent':intent.model_dump(mode='json'),'tick':0,'attempts':0,'waits':0,'stopped':False,'decision_tick':None,'horizon_done':False,'order':history[-1],'history':history,'operations':{},'idempotency':{},'notifications':[],'events':[],'occurrences':{},'fault_spec':fault_spec.model_dump(mode='json'),'fault_executions':[{'fault_id':f'fault-{n+1}','scheduled':True,'triggered':False,'trigger_tick':None,'call_id':None,'attempt_id':None,'reason':'target_not_reached'} for n,_ in enumerate(fault_spec.primitives)]}
        self.directory.mkdir(parents=True,exist_ok=True)
        path=self._path(world_id)
        with sqlite3.connect(path) as db:
            db.executescript('CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL); CREATE TABLE projections(version INTEGER PRIMARY KEY, value TEXT NOT NULL); CREATE TABLE receipts(id TEXT PRIMARY KEY,value TEXT NOT NULL); CREATE TABLE events(seq INTEGER PRIMARY KEY,value TEXT NOT NULL);')
            for table in ('projections','receipts','events'):
                for action in ('UPDATE','DELETE'):
                    db.execute(f"CREATE TRIGGER no_{action.lower()}_{table} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable history'); END")
            self._persist(db,state)
        path.chmod(0o600)
        return {'world_id':world_id,'capability':capability,'tick':0}

    def _persist(self,db,state):
        db.execute('INSERT INTO state(id,value) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value',(canonical_json(state),))
        for projection in state['history']:
            db.execute('INSERT OR IGNORE INTO projections VALUES(?,?)',(projection['version'],canonical_json(projection)))
        for op in state['operations'].values():
            receipt=op.get('receipt')
            if receipt: db.execute('INSERT OR IGNORE INTO receipts VALUES(?,?)',(receipt['receipt_id'],canonical_json(receipt)))
        for event in state['events']: db.execute('INSERT OR IGNORE INTO events VALUES(?,?)',(event['seq'],canonical_json(event)))

    @contextmanager
    def transaction(self,world_id):
        path=self._path(world_id)
        if not path.exists(): raise WorldError('WORLD_NOT_FOUND',404)
        with self._lock,sqlite3.connect(path,timeout=10) as db:
            db.execute('BEGIN IMMEDIATE')
            state=json.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])
            yield state
            self._persist(db,state)

    def read(self,world_id):
        path=self._path(world_id)
        if not path.exists(): raise WorldError('WORLD_NOT_FOUND',404)
        with sqlite3.connect(path) as db: return json.loads(db.execute('SELECT value FROM state WHERE id=1').fetchone()[0])

    def snapshot(self,world_id):
        s=self.read(world_id)
        operations=[{k:v for k,v in op.items() if k not in ('expected_version','intent_hash','desired_shipping','failure_code','due_tick')} for op in s['operations'].values()]
        return WorldSnapshot.model_validate_json(canonical_json({'world_id':world_id,'tick':s['tick'],'orders':[s['order']],'operations':operations,'notifications':s['notifications'],'events':s['events']}))

    def authorize(self,world_id,capability):
        s=self.read(world_id)
        if not capability or not secrets.compare_digest(s['capability_hash'],content_hash(capability)): raise WorldError('FORBIDDEN',403)


def event(state,event_type,payload=None,call_id=None):
    value=Event(episode_id=state['episode_id'],seq=len(state['events'])+1,tick=state['tick'],role='coordinator',type=event_type,payload=payload or {},call_id=call_id,visibility='PRIVATE_EVALUATOR').model_dump(mode='json')
    state['events'].append(value)
    return value
