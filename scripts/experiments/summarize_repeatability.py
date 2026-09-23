#!/usr/bin/env python3
"""Read saved repeatability results and local Actor outputs; never run a trial."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'backend'))
from app.agents.actor import ACTION_ADAPTER
from app.contracts.models import ReportAction, content_hash


def summarize(directory):
    study=json.loads((directory/'summary.json').read_text())
    db=sqlite3.connect(f'file:{directory.resolve()}/lab.sqlite3?mode=ro',uri=True)
    details=[]
    try:
        for slot in study['slots']:
            raw=db.execute("select payload from records where kind='episodes' and id=?",(slot['episode_id'],)).fetchone()
            if raw is None:
                details.append({'case_id':slot['case_id'],'repeat_index':slot['repeat_index'],
                                'episode_id':slot['episode_id'],'status':slot['status'],'attempted':False})
                continue
            episode=json.loads(raw[0]); outputs=[]; submitted=[]
            for (payload,) in db.execute('select payload from events where episode_id=? order by seq',(slot['episode_id'],)):
                event=json.loads(payload)
                if event['type']=='report_submitted': submitted.append(event['payload']['report'])
                if event['type']!='actor_output': continue
                output=event['payload']
                try:
                    action=ACTION_ADAPTER.validate_json(output['raw'])
                    kind='report' if isinstance(action,ReportAction) else 'tool'
                    tool=getattr(action,'tool',None)
                except ValueError:
                    kind='invalid_action'; tool=None
                outputs.append({'turn':output['actor_turn'],'report_required':output['final_report_required'],
                                'action_kind':kind,'tool':tool,'request_hash':output['request_hash']})
            final=outputs[-1] if outputs else None
            present=episode.get('report') is not None
            classification=('report_present' if present else 'provider_or_infrastructure_error' if episode['lifecycle']=='LAB_ERROR'
                else 'no_returned_output' if final is None else 'last_returned_action_'+final['action_kind'])
            verdict=episode.get('verdict') or {}; faults=verdict.get('fault_executions',[])
            scheduled=bool(faults); triggered=scheduled and all(fault['triggered'] for fault in faults)
            valid=(episode['lifecycle']=='COMPLETED' and verdict.get('outcome') not in (None,'LAB_ERROR')
                   and (not scheduled or triggered))
            details.append({'case_id':slot['case_id'],'repeat_index':slot['repeat_index'],'episode_id':slot['episode_id'],
                'world_id':episode['world_id'],'attempted':True,'lifecycle':episode['lifecycle'],
                'outcome':(episode.get('verdict') or {}).get('outcome'),'original_report_present':present,
                'valid':valid,'fault_scheduled':scheduled,'fault_triggered':triggered,
                'report_classification':classification,'reason':episode.get('reason'),
                'submitted_original_report_matches':submitted[-1]==episode.get('report') if submitted else None,
                'actor_turns':outputs,'usage':episode['usage']})
    finally: db.close()
    groups={}
    for case in study['cases']:
        rows=[row for row in details if row['case_id']==case['case_id']]
        attempted=[row for row in rows if row['attempted']]
        groups[case['case_id']]={'planned':len(rows),'attempted':len(attempted),
            'valid':sum(row['valid'] for row in attempted),
            'untriggered':sum(row['fault_scheduled'] and not row['fault_triggered'] for row in attempted),
            'lab_errors':sum(row['lifecycle']=='LAB_ERROR' for row in attempted),
            'interrupted':sum(row['lifecycle']=='INTERRUPTED' for row in attempted),
            'outcomes':dict(Counter(row['outcome'] for row in attempted)),
            'report_classifications':dict(Counter(row['report_classification'] for row in attempted)),
            'final_tools_when_report_required':dict(Counter(row['actor_turns'][-1]['tool'] for row in attempted
                if row['actor_turns'] and row['actor_turns'][-1]['report_required'] and row['actor_turns'][-1]['action_kind']=='tool'))}
    return {'study_id':study['study_id'],'campaign_id':study['campaign_id'],'status':study['status'],
        'configuration_hash':study['configuration_hash'],'by_case':groups,'accounting':study['accounting'],
        'verified_episode_count':sum(value['status']=='weave_verified' for value in study['evidence'].values()),
        'action_schema_hash':content_hash(ACTION_ADAPTER.json_schema()),
        'interpretation':'All planned slots are retained; outcome counters use attempted trials, with planned/attempted/valid/error counts shown separately. Local raw outputs are classified using the recorded action_schema_hash of this analysis runtime; persisted verdicts are unchanged. Actor-output diagnostics are local supplemental evidence; only actual returned reports/observations carry the separately recorded remote verification. This measures combined fresh-identity and provider variation, not a learned-policy effect.',
        'trials':details}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    args=parser.parse_args()
    print(json.dumps(summarize(args.directory),indent=2))
