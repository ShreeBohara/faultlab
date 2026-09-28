"""Explicit scheduler requests for protected comparison and portability studies."""
import argparse
from app.cli.client import request,print_json
from app.cli.stores import OWNERSHIP_ERRORS,ownership_error

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
            from app.config import Settings
            from app.cli.stores import expected_store_identity
            from app.lab.storage import ReadOnlyStore
            settings=Settings.from_env()
            if settings.faultlab_read_only:raise ReadOnlyStore()
            body['expected_store_identity']=expected_store_identity(settings)
            suffix='freeze-and-portability'
        print_json(request('POST',f'/api/campaigns/{args.campaign}/{suffix}',body));return 0
    except OWNERSHIP_ERRORS as error:print_json(ownership_error(error));return 1
    except Exception:print_json({'status':'REJECTED','message':'Local study admission failed; verify completed campaign, immutable freeze, registered target and protected budget.'});return 1

if __name__=='__main__':raise SystemExit(main())
