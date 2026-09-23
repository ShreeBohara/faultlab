"""Read-only: how often does the Actor cite an evidence ID that is not real?

Makes no model call and writes nothing to the lab database. C6 requires every cited
evidence_id to be an actual delivered observation of that episode, so a single corrupted
identifier fails the episode and, in a validation batch, the whole candidate.

Usage: python scripts/experiments/analyze_citations.py
"""
from __future__ import annotations

import json
import pathlib
import re
import sqlite3
from collections import Counter, defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[2]
DB = f"file:{ROOT / 'artifacts/lab.sqlite3'}?mode=ro"
HEX = re.compile(r'^evidence-[0-9a-f]{32}$')


def classify(identifier, real_anywhere):
    if identifier in real_anywhere:
        return 'real id, but not from this episode'
    if HEX.fullmatch(identifier):
        return 'well-formed but nonexistent'
    body = identifier.split('evidence-', 1)[-1]
    if re.search(r'[g-z]{3,}', body):
        return 'malformed: word fragment spliced into the hex'
    if len(body) < 32:
        return 'malformed: characters dropped'
    return 'malformed: other'


def main() -> int:
    connection = sqlite3.connect(DB, uri=True)
    try:
        by_episode = defaultdict(set)
        for _, payload in connection.execute(
                "select id,payload from records where kind='observations'"):
            row = json.loads(payload)
            if row.get('episode_id'):
                by_episode[row['episode_id']].add(row['evidence_id'])
        real_anywhere = set().union(*by_episode.values()) if by_episode else set()

        studied = set()
        for _, payload in connection.execute(
                "select id,payload from records where kind='completion_studies'"):
            for trial_row in json.loads(payload).get('trial_rows', []):
                studied.add(trial_row['trial']['episode_id'])

        filed = corrupted = 0
        kinds, offenders = Counter(), []
        for episode_id in sorted(studied):
            row = connection.execute(
                "select payload from records where kind='episodes' and id=?", (episode_id,)).fetchone()
            if not row:
                continue
            episode = json.loads(row[0])
            report = episode.get('report')
            if not report:
                continue
            filed += 1
            bad = [x for x in (report.get('evidence_ids') or [])
                   if x not in by_episode.get(episode_id, set())]
            if not bad:
                continue
            corrupted += 1
            for identifier in bad:
                kinds[classify(identifier, real_anywhere)] += 1
                offenders.append((episode_id, identifier))
    finally:
        connection.close()

    rate = corrupted / filed if filed else 0.0
    print(f'completion-study episodes that filed a report : {filed}')
    print(f'episodes citing at least one unreal evidence id: {corrupted}  ({100 * rate:.2f}%)')
    print()
    for kind, count in kinds.most_common():
        print(f'  {kind:46} {count}')
    print()
    print('C6 fails an episode on a single bad citation, so for a policy that is otherwise')
    print('perfect the gate still rejects it with probability 1 - (1 - rate)^n:')
    for n, label in ((21, 'candidate arm of one validation batch'),
                     (42, 'both arms of one validation batch')):
        print(f'  n={n:>2} ({label:37}) -> pass {100 * (1 - rate) ** n:.1f}%')
    print()
    print('every offending citation:')
    for episode_id, identifier in offenders:
        print(f'  {episode_id[:24]}  {identifier}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
