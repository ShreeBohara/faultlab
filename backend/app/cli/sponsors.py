"""Record actual W&B UI setup evidence without inventing an Aria runtime API."""
import argparse
import json
from pathlib import Path
from app.config import Settings, ConfigurationError
from app.lab.storage import LabStore
from app.telemetry.aria_bridge import validate_automation_setup
from app.telemetry.safety import TelemetryError


def main():
    parser=argparse.ArgumentParser(description='Record an observed W&B Aria automation configuration (no invocation)')
    sub=parser.add_subparsers(dest='action',required=True)
    register=sub.add_parser('register-automation')
    register.add_argument('--record',type=Path,required=True)
    args=parser.parse_args()
    try:
        if args.record.is_symlink() or args.record.stat().st_size>32000:
            raise ValueError('Invalid evidence file')
        settings=Settings.from_env()
        if not settings.wandb_entity or not settings.wandb_project:
            raise ValueError('Configure the actual W&B team/project first')
        record=validate_automation_setup(json.loads(args.record.read_text()),project=settings.project_path)
        store=LabStore(settings.artifact_path/'lab.sqlite3')
        try:store.put_record('aria_setup',settings.project_path,record,immutable=True)
        finally:store.close()
        print(json.dumps({'status':'observed_setup_recorded','automation_id':record['automation_id'],'invocation_performed':False,'remote_verification':False}))
    except (ValueError,OSError,TelemetryError,ConfigurationError):
        parser.error('Evidence must match the reviewed project, Finished filter, Aria prompt, entitlement observations and actual UI reference. No record saved.')
    return 0

if __name__=='__main__':raise SystemExit(main())
