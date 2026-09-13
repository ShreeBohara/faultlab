"""Local REST command transport; no arbitrary remote endpoints."""
from __future__ import annotations
import argparse
import json
import sys
import time
from pathlib import Path
import httpx

BASE_URL='http://127.0.0.1:8000'


def request(method,path,body=None):
    if not path.startswith('/api/') or '://' in path:
        raise ValueError('Only local FaultLab API routes are allowed')
    with httpx.Client(base_url=BASE_URL,timeout=10.0,trust_env=False) as client:
        response=client.request(method,path,json=body)
    if response.status_code>=400:
        try: message=response.json().get('error',{}).get('message','Request rejected')
        except (ValueError,AttributeError): message='Request rejected'
        raise RuntimeError(f'HTTP {response.status_code}: {message}')
    return response.json()


def print_json(value):
    print(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False),flush=True)


def main():
    parser=argparse.ArgumentParser(description='Explicit local FaultLab operator actions')
    commands=parser.add_subparsers(dest='command',required=True)
    demo=commands.add_parser('demo')
    demo.add_argument('--mode',choices=['baseline','learn','compare'],default='baseline')
    demo.add_argument('--task',default='Upgrade the authorized order to express shipping, then record one truthful confirmation.')
    demo.add_argument('--order',default='order-demo')
    demo.add_argument('--execute-live',action='store_true')
    demo.add_argument('--wait',action='store_true')
    baseline=commands.add_parser('baseline-study',help='Six development cases, three fresh B0/B1 pairs per case')
    baseline_target=baseline.add_mutually_exclusive_group()
    baseline_target.add_argument('--campaign',help='Existing unchanged live baseline campaign; otherwise create one')
    baseline_target.add_argument('--status',metavar='STUDY_ID',help='Read saved study status without execution')
    baseline.add_argument('--execute-live',action='store_true')
    baseline.add_argument('--wait',action='store_true')
    audit=commands.add_parser('audit');audit.add_argument('--campaign',required=True);audit.add_argument('--execute-live',action='store_true');audit.add_argument('--policy',action='append',default=[])
    export=commands.add_parser('export');export.add_argument('--campaign',required=True);export.add_argument('--output',type=Path,required=True)
    status=commands.add_parser('status');status.add_argument('--campaign',required=True)
    stop=commands.add_parser('stop');stop.add_argument('--campaign',required=True)
    args=parser.parse_args()
    try:
        if args.command=='demo':
            if args.mode!='baseline' and not args.execute_live:
                parser.error('Learning and comparison require --execute-live plus a configured, confirmed live profile')
            campaign=request('POST','/api/campaigns',{'task_text':args.task,'order_id':args.order,'mode':args.mode,'config_profile_id':'live-v1' if args.execute_live else 'offline-v1'})
            ident=campaign['campaign_id']
            result=request('POST',f'/api/campaigns/{ident}/start',{})
            print_json(result)
            if args.wait:
                while True:
                    result=request('GET',f'/api/campaigns/{ident}')
                    terminal=result['state'] in ('COMPLETED','STOPPED','ERROR','NO_CHANGE','REJECTED')
                    # A rejected candidate can feed another discovery attempt.
                    # Wait for the scheduler (including evidence finalization),
                    # not just a transient campaign state.
                    if result['state']=='WAITING_EVIDENCE' or (terminal and request('GET','/api/config/status')['active_campaign_id']!=ident):
                        print_json(result);break
                    time.sleep(.75)
        elif args.command=='baseline-study':
            if args.status:
                print_json(request('GET',f'/api/baseline-studies/{args.status}'))
            else:
                if not args.execute_live:parser.error('A fresh baseline study requires --execute-live and verified live settings')
                ident=args.campaign
                if not ident:
                    campaign=request('POST','/api/campaigns',{'task_text':'Upgrade the authorized order to express shipping, then record one truthful confirmation.','order_id':'order-baseline-study','mode':'baseline','config_profile_id':'live-v1'})
                    ident=campaign['campaign_id']
                result=request('POST',f'/api/campaigns/{ident}/baseline-study',{'execute_live':True})
                print_json(result)
                if args.wait:
                    while result['status'] in ('QUEUED','RUNNING'):
                        time.sleep(.75)
                        result=request('GET',f'/api/baseline-studies/{result["study_id"]}')
                    print_json(result)
        elif args.command=='audit':
            if not args.execute_live: parser.error('A fresh audit requires --execute-live, frozen campaign and protected budget')
            versions=args.policy or [request('GET',f'/api/campaigns/{args.campaign}')['active_policy_version']]
            print_json(request('POST','/api/evaluations',{'campaign_id':args.campaign,'purpose':'final_audit','policy_versions':versions}))
        elif args.command=='status':print_json(request('GET',f'/api/campaigns/{args.campaign}'))
        elif args.command=='stop':print_json(request('POST',f'/api/campaigns/{args.campaign}/stop',{}))
        elif args.command=='export':
            campaign=request('GET',f'/api/campaigns/{args.campaign}')
            result={'export_version':'faultlab-evidence/v1','campaign':campaign,'matrix':request('GET',f'/api/campaigns/{args.campaign}/matrix'),'counterexamples':request('GET',f'/api/campaigns/{args.campaign}/counterexamples'),'regressions':request('GET',f'/api/campaigns/{args.campaign}/regressions'),'experiments':request('GET',f'/api/campaigns/{args.campaign}/experiments'),'aria':request('GET',f'/api/campaigns/{args.campaign}/aria-evidence')}
            versions={campaign['active_policy_version'],'policy-v0'}
            versions.update(p for regression in result['regressions'] for p in (regression['first_failing_policy'],regression['accepted_policy']) if p)
            result['policies']=[request('GET',f'/api/policies/{version}') for version in sorted(versions)]
            result['proposals']=[request('GET',f'/api/policies/{policy["version"]}/proposal') for policy in result['policies'] if policy['raw_proposal_ref']]
            result['configuration']=request('GET',f'/api/campaigns/{args.campaign}/configuration')
            result['episodes']=[request('GET',f'/api/episodes/{cell["episode_id"]}') for cell in result['matrix']['cells']]
            args.output.parent.mkdir(parents=True,exist_ok=True)
            with args.output.open('x',encoding='utf-8') as file:json.dump(result,file,indent=2,allow_nan=False)
            print_json({'saved':str(args.output.resolve()),'mode':'read_only_export'})
    except (RuntimeError,httpx.HTTPError,FileExistsError) as exc:
        if isinstance(exc,httpx.HTTPError): print('Local FaultLab backend unavailable; start scripts/start-backend.sh.',file=sys.stderr)
        elif isinstance(exc,FileExistsError):print('Export destination exists; select a new output file.',file=sys.stderr)
        else:print(str(exc),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
