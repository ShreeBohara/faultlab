#!/usr/bin/env python3
"""Reviewer ($0, offline): make scratch copies of the saved native-v2b store as it stood at a record row cutoff.
Source: the reviewer's own scratch copy (itself made read-only from the saved store). Deletes records above the cutoff,
and the episode-registry, event and ingestion-key rows of episodes that no longer have a record. Prints what was removed
and the pointers table (names only + whether they point at a removed record)."""
import shutil, sqlite3, sys
SRC = '/Users/shree/FaultLab_Scratch/followup-review/store/lab.sqlite3'
for cut in map(int, sys.argv[1:]):
    dst = f'/Users/shree/FaultLab_Scratch/followup-review/store/lab-upto-{cut}.sqlite3'
    shutil.copyfile(SRC, dst)
    d = sqlite3.connect(dst)
    removed = d.execute('SELECT COUNT(*) FROM records WHERE rowid>?', (cut,)).fetchone()[0]
    d.execute('DELETE FROM records WHERE rowid>?', (cut,))
    orphan = "SELECT id FROM episode_registry WHERE id NOT IN (SELECT id FROM records WHERE kind='episodes')"
    ev = d.execute(f'DELETE FROM events WHERE episode_id IN ({orphan})').rowcount
    ik = d.execute(f'DELETE FROM ingestion_keys WHERE episode_id IN ({orphan})').rowcount
    er = d.execute(f'DELETE FROM episode_registry WHERE id IN ({orphan})').rowcount
    ptr = d.execute('SELECT name FROM pointers').fetchall()
    d.commit(); d.execute('VACUUM'); d.close()
    print(f'cutoff {cut}: removed records {removed}, events {ev}, ingestion_keys {ik}, episode_registry {er}; pointers {[p[0] for p in ptr]}')
