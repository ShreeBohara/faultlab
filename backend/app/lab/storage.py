"""One serialized SQLite writer, parameterized records and atomic state transitions."""
from __future__ import annotations
from contextlib import contextmanager, ExitStack
import json
from pathlib import Path
import sqlite3
from threading import RLock
from app.contracts.models import Event, canonical_json, utc_now


class StoreConflict(ValueError):
    pass


class ReadOnlyStore(StoreConflict):
    pass


class LabStore:
    read_only = False

    def __init__(self, path):
        self.path = str(path)
        if self.path != ':memory:':
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        self._closed = False
        self._close_callbacks = []
        self.db = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA foreign_keys=ON')
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.execute('PRAGMA busy_timeout=5000')
            self.db.executescript('''
              CREATE TABLE IF NOT EXISTS records(kind TEXT NOT NULL,id TEXT NOT NULL,payload TEXT NOT NULL,immutable INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(kind,id));
              CREATE TABLE IF NOT EXISTS episode_registry(id TEXT PRIMARY KEY,campaign_id TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS episode_registry_campaign ON episode_registry(campaign_id,id);
              CREATE TABLE IF NOT EXISTS events(episode_id TEXT NOT NULL REFERENCES episode_registry(id),seq INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(episode_id,seq));
              CREATE TABLE IF NOT EXISTS ingestion_keys(project TEXT NOT NULL,root TEXT NOT NULL,episode_id TEXT NOT NULL REFERENCES episode_registry(id),PRIMARY KEY(project,root),UNIQUE(project,episode_id));
              CREATE TABLE IF NOT EXISTS pointers(name TEXT PRIMARY KEY,value TEXT NOT NULL);
            ''')
        except BaseException:
            self.db.close()
            raise

    @contextmanager
    def transaction(self):
        with self.lock:
            # Nested record/ledger helpers participate in an outer atomic change.
            # Savepoints also let a caller catch one inner failure without
            # accidentally committing its partially written records.
            nested = self.db.in_transaction
            self._savepoint_index = getattr(self, '_savepoint_index', 0) + 1
            savepoint = f'faultlab_{self._savepoint_index}'
            self.db.execute(f'SAVEPOINT {savepoint}' if nested else 'BEGIN IMMEDIATE')
            try:
                yield self.db
                self.db.execute(f'RELEASE SAVEPOINT {savepoint}' if nested else 'COMMIT')
            except BaseException:
                if self.db.in_transaction:
                    if nested:
                        self.db.execute(f'ROLLBACK TO SAVEPOINT {savepoint}')
                        self.db.execute(f'RELEASE SAVEPOINT {savepoint}')
                    else:
                        self.db.execute('ROLLBACK')
                raise

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

    def campaign_page(self, *, before=None, limit=20, exclude_import_owners=False):
        """Bounded, stable creation-order history, without parsing other records.

        Updating a campaign preserves its rowid. A new campaign between page
        requests therefore cannot move older results across the cursor.
        """
        if not 1 <= limit <= 100 or (before is not None and before < 1):
            raise ValueError('Invalid campaign history cursor or limit')
        clause = '' if before is None else ' AND rowid < ?'
        if exclude_import_owners:
            clause += " AND id NOT IN (SELECT id FROM records WHERE kind='import_execution_owners')"
        parameters = (limit + 1,) if before is None else (before, limit + 1)
        with self.lock:
            rows = self.db.execute(
                "SELECT rowid,id FROM records WHERE kind='campaigns'" + clause
                + ' ORDER BY rowid DESC LIMIT ?', parameters,
            ).fetchall()
        selected = rows[:limit]
        more = len(rows) > limit
        return {'campaign_ids': [row['id'] for row in selected],
                'next_before': selected[-1]['rowid'] if more else None,
                'has_more': more}

    def regression_execution_page(self, bundle_id, *, before=None, limit=20):
        """Return only executions of the selected immutable bundle."""
        if not 1 <= limit <= 100 or (before is not None and before < 1):
            raise ValueError('Invalid execution history cursor or limit')
        clause = '' if before is None else ' AND rowid < ?'
        parameters = (bundle_id, limit + 1) if before is None else (bundle_id, before, limit + 1)
        with self.lock:
            rows = self.db.execute(
                "SELECT rowid,payload FROM records WHERE kind='regression_executions'"
                " AND json_extract(payload,'$.bundle_id')=?" + clause
                + ' ORDER BY rowid DESC LIMIT ?', parameters,
            ).fetchall()
        selected = rows[:limit]
        more = len(rows) > limit
        return {'executions': [json.loads(row['payload']) for row in selected],
                'next_before': selected[-1]['rowid'] if more else None,
                'has_more': more}

    # The two readers below exist for request handlers that run on the event loop.
    # Parsing every episode (or every evidence bundle) there froze the loop for most
    # of each second while the dashboard polled; a lab request whose 1s connect window
    # fell inside a freeze was never sent, while the lab still counted its tick
    # (Phase 18/19). They return the same rows in the same order as filtering
    # list_records in Python, PROVIDED the registry row was written with the episode
    # and its campaign never changes (put_record keeps the first campaign_id), and
    # evidence/ingestion ids equal their episode_id (evidence.py). Both hold for every
    # writer and for all 214 campaigns in the store as of Phase 19.

    def max_record_rowid(self):
        """The highest record row number now: a record cutoff (discovery v3 history).

        An update keeps a row's number (ON CONFLICT DO UPDATE) and a new record gets a higher
        one, so reading only rows at or below a cutoff never admits a record added later.
        """
        with self.lock:
            row = self.db.execute('SELECT COALESCE(MAX(rowid),0) AS cutoff FROM records').fetchone()
        return int(row['cutoff'])

    def records_upto(self, kind, cutoff, *, where=None):
        """Records of one kind at or below a row-number cutoff, in row order.

        ``where`` maps top-level JSON field names to required exact values; the filter runs in
        SQLite so unrelated payloads are never parsed. Returns (rowid, payload) pairs.
        """
        clauses, parameters = ['kind=?', 'rowid<=?'], [kind, int(cutoff)]
        for field, value in (where or {}).items():
            if not isinstance(field, str) or not field.isidentifier():
                raise ValueError('Invalid record filter field')
            clauses.append(f"json_extract(payload,'$.{field}')=?"); parameters.append(value)
        with self.lock:
            rows = self.db.execute('SELECT rowid,payload FROM records WHERE ' + ' AND '.join(clauses)
                                   + ' ORDER BY rowid', parameters).fetchall()
        return [(row['rowid'], json.loads(row['payload'])) for row in rows]

    def record_fields_upto(self, kind, cutoff, fields):
        """Only the named JSON fields (dotted paths) of records at or below a cutoff, in row order.

        SQLite extracts the values, so large unrelated parts of each payload are never loaded into
        Python. Returns (rowid, {path: value}) pairs; a missing field is None and JSON booleans read
        back as 1/0 (SQLite's json_extract).
        """
        paths = list(fields)
        for path in paths:
            if not isinstance(path, str) or not all(part.isidentifier() for part in path.split('.')):
                raise ValueError('Invalid record field path')
        columns = ','.join(f"json_quote(json_extract(payload,'$.{path}'))" for path in paths)
        with self.lock:
            rows = self.db.execute(f'SELECT rowid,{columns} FROM records WHERE kind=? AND rowid<=? ORDER BY rowid',
                                   (kind, int(cutoff))).fetchall()
        return [(row[0], {path: json.loads(row[index + 1]) for index, path in enumerate(paths)}) for row in rows]

    def record_rowid(self, kind, id):
        with self.lock:
            row = self.db.execute('SELECT rowid FROM records WHERE kind=? AND id=?', (kind, id)).fetchone()
        return None if row is None else int(row['rowid'])

    def list_campaign_episodes(self, campaign_id):
        with self.lock:
            rows = self.db.execute("SELECT r.payload FROM records r JOIN episode_registry e ON e.id=r.id WHERE r.kind='episodes' AND e.campaign_id=? ORDER BY r.rowid",(campaign_id,)).fetchall()
        values = [json.loads(row['payload']) for row in rows]
        return [v for v in values if v.get('campaign_id') == campaign_id]

    def get_records(self, kind, ids):
        ids = list(dict.fromkeys(ids)); found = []
        with self.lock:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start+500]
                marks = ','.join('?' * len(chunk))
                found += self.db.execute(f'SELECT rowid,payload FROM records WHERE kind=? AND id IN ({marks})',(kind,*chunk)).fetchall()
        return [json.loads(row['payload']) for row in sorted(found, key=lambda row: row['rowid'])]

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

    def on_close(self, callback):
        """Release resources tied to this connection even on explicit store close."""
        if not callable(callback):
            raise TypeError('Store close callback must be callable')
        with self.lock:
            if not self._closed:
                self._close_callbacks.append(callback)
                return
        callback()

    def close(self):
        with self.lock:
            if self._closed:
                return
            self._closed = True
            callbacks, self._close_callbacks = self._close_callbacks, []
            # ExitStack runs every callback, including when connection closure or
            # an earlier callback raises. Ownership ends after the DB is closed.
            with ExitStack() as cleanup:
                for callback in callbacks:
                    cleanup.callback(callback)
                self.db.close()


class ReadOnlyLabStore(LabStore):
    """A separate reader; never creates a store, schema, policy or recovery record."""
    read_only = True

    def __init__(self, path):
        if str(path) == ':memory:':
            raise ValueError('A read-only view requires an existing file-backed store')
        target = Path(path).expanduser().resolve()
        self.path = str(target)
        self.lock = RLock()
        self._closed = False
        self._close_callbacks = []
        self.db = sqlite3.connect(target.as_uri() + '?mode=ro', uri=True,
                                  check_same_thread=False, isolation_level=None)
        try:
            self.db.row_factory = sqlite3.Row
            self.db.execute('PRAGMA query_only=ON')
            self.db.execute('PRAGMA busy_timeout=1000')
        except BaseException:
            self.db.close()
            raise

    def begin_snapshot(self):
        self.db.execute('BEGIN')

    @contextmanager
    def transaction(self):
        raise ReadOnlyStore('Saved archive is read-only; select a writable store for new work')
        yield  # pragma: no cover — retain the context-manager protocol
