"""One serialized SQLite writer, parameterized records and atomic state transitions."""
from __future__ import annotations
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from threading import RLock
from app.contracts.models import Event, canonical_json, utc_now


class StoreConflict(ValueError):
    pass


class LabStore:
    def __init__(self, path):
        self.path = str(path)
        if self.path != ':memory:':
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA busy_timeout=5000')
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id));
          CREATE TABLE IF NOT EXISTS episode_registry(id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(episode_id TEXT NOT NULL REFERENCES episode_registry(id),seq INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(episode_id,seq));
          CREATE TABLE IF NOT EXISTS ingestion_keys(project TEXT NOT NULL,root TEXT NOT NULL,episode_id TEXT NOT NULL REFERENCES episode_registry(id),PRIMARY KEY(project,root),UNIQUE(project,episode_id));
          CREATE TABLE IF NOT EXISTS pointers(name TEXT PRIMARY KEY,value TEXT NOT NULL);
        ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            self.db.execute('BEGIN IMMEDIATE')
            try:
                yield self.db
            except BaseException:
                self.db.execute('ROLLBACK')
                raise
            else:
                self.db.execute('COMMIT')

    def get_record(self, kind, id):
        with self.lock:
            row = self.db.execute('SELECT payload FROM records WHERE kind=? AND id=?', (kind,id)).fetchone()
        return None if row is None else json.loads(row['payload'])

    def put_record(self, kind, id, payload, *, immutable=False):
        serialized = canonical_json(payload)
        with self.transaction() as db:
            old = db.execute('SELECT payload,immutable FROM records WHERE kind=? AND id=?',(kind,id)).fetchone()
            if old and old['immutable'] and old['payload'] != serialized:
                raise StoreConflict('Immutable record already exists')
            db.execute('INSERT INTO records(kind,id,payload,immutable) VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload,immutable=MAX(records.immutable,excluded.immutable)',(kind,id,serialized,int(immutable)))
            if kind == 'episodes':
                value = json.loads(serialized)
                db.execute('INSERT OR IGNORE INTO episode_registry(id,campaign_id) VALUES(?,?)',(id,value['campaign_id']))
        return payload

    def list_records(self, kind):
        with self.lock:
            rows = self.db.execute('SELECT payload FROM records WHERE kind=? ORDER BY rowid',(kind,)).fetchall()
        return [json.loads(row['payload']) for row in rows]

    def get_model(self, kind, id, cls):
        record = self.get_record(kind,id)
        return cls.model_validate_json(canonical_json(record)) if record is not None else None

    def append_event(self, episode_id, *, tick=0, role='coordinator', type, payload=None, visibility='PUBLIC_OBSERVATION', call_id=None, evidence_id=None):
        with self.transaction() as db:
            row = db.execute('SELECT COALESCE(MAX(seq),0)+1 AS seq FROM events WHERE episode_id=?',(episode_id,)).fetchone()
            event = Event(episode_id=episode_id,seq=row['seq'],tick=tick,at=utc_now(),role=role,type=type,payload=payload or {},visibility=visibility,call_id=call_id,evidence_id=evidence_id)
            db.execute('INSERT INTO events VALUES(?,?,?)',(episode_id,event.seq,canonical_json(event)))
        return event

    def events(self, episode_id, *, after=0, limit=200, include_private=False):
        if after < 0 or not 1 <= limit <= 200:
            raise ValueError('Invalid event cursor')
        with self.lock:
            rows = self.db.execute('SELECT seq,payload FROM events WHERE episode_id=? AND seq>? ORDER BY seq LIMIT ?',(episode_id,after,limit+1)).fetchall()
        selected = rows[:limit]
        events = [json.loads(r['payload']) for r in selected]
        return {'events':[e for e in events if include_private or e['visibility'] != 'PRIVATE_EVALUATOR'], 'next_after': selected[-1]['seq'] if selected else after, 'has_more':len(rows)>limit}

    def associate_ingestion(self, project, root, episode_id):
        with self.transaction() as db:
            existing = db.execute('SELECT episode_id,root FROM ingestion_keys WHERE project=? AND (root=? OR episode_id=?)',(project,root,episode_id)).fetchone()
            if existing:
                if existing['episode_id'] != episode_id or existing['root'] != root:
                    raise StoreConflict('Conflicting evidence identity')
                return False
            db.execute('INSERT INTO ingestion_keys VALUES(?,?,?)',(project,root,episode_id))
            return True

    def get_pointer(self, name):
        with self.lock:
            row = self.db.execute('SELECT value FROM pointers WHERE name=?',(name,)).fetchone()
        return row['value'] if row else None

    def compare_and_set_pointer(self, name, expected, value):
        with self.transaction() as db:
            row = db.execute('SELECT value FROM pointers WHERE name=?',(name,)).fetchone()
            if (row['value'] if row else None) != expected:
                raise StoreConflict('Stale expected parent')
            db.execute('INSERT INTO pointers VALUES(?,?) ON CONFLICT(name) DO UPDATE SET value=excluded.value',(name,value))

    def close(self):
        with self.lock:
            self.db.close()
