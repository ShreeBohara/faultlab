"""Explicit scheduler requests for protected comparison and portability studies."""
import argparse
from app.cli.client import request,print_json

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='study',required=True)
    for name in ('selectors','portability'):
        p=sub.add_parser(name);p.add_argument('--campaign',required=True);p.add_argument('--execute-live',action='store_true')
        if name=='portability':p.add_argument('--agent',required=True)
    args=parser.parse_args()
    if not args.execute_live:parser.error('A protected fresh study requires --execute-live and verified frozen settings')
    body={'execute_live':True}
    suffix='search-comparison' if args.study=='selectors' else 'portability'
    if args.study=='portability':body['agent_registration_id']=args.agent
    try:
        if args.study=='portability':
            from pathlib import Path
            from app.config import Settings
            from app.lab.storage import LabStore
            from app.integrations.registry import AgentRegistry
            from app.referee.freeze import freeze_external
            settings=Settings.from_env();settings.require_live()
            store=LabStore(settings.artifact_path/'lab.sqlite3')
            try:
                frozen=store.get_record('audit_freezes',args.campaign)
                if not frozen or not frozen.get('learned_arm_available'):raise ValueError('Freeze a completed campaign with accepted policy first')
                registry=AgentRegistry(store);reg=registry.get(args.agent)
                registry.verify(args.agent,store.get_record('configurations',reg.configuration_hash))
                value=freeze_external(Path(frozen['path']).parent,reg)
                store.put_record('external_freezes',args.campaign,value,immutable=True)
            finally:store.close()
        print_json(request('POST',f'/api/campaigns/{args.campaign}/{suffix}',body));return 0
    except Exception:print_json({'status':'REJECTED','message':'Local study admission failed; verify completed campaign, immutable freeze, registered target and protected budget.'});return 1

if __name__=='__main__':raise SystemExit(main())
