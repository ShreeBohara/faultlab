"""Private fixed scenario partitions. Runtime optimizers never load this module."""
import json
from pathlib import Path
from app.contracts.models import FaultSpec,content_hash

# app/referee -> app -> backend -> application root
AUDIT_DIR=Path(__file__).resolve().parents[3]/'audit'
NAMES={'development','promotion','final-audit','portability','search-comparison'}

def manifest_hash(value):return content_hash({k:v for k,v in value.items() if k!='manifest_hash'})

def load_manifest(name,*,directory=None):
    if name not in NAMES:raise ValueError('unknown fixed manifest')
    path=(Path(directory) if directory else AUDIT_DIR)/(name+'.json')
    value=json.loads(path.read_text())
    if value['manifest_hash']!=manifest_hash(value):raise ValueError('manifest digest mismatch')
    for case in value.get('cases',[]):FaultSpec.model_validate(case['fault_spec'])
    return value

def development_case(case_id):
    return next(c for c in load_manifest('development')['cases'] if c['case_id']==case_id)
