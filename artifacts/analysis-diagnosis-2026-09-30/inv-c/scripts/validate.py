import sys,json,sqlite3
sys.dont_write_bytecode=True
sys.path.insert(0,'/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend')
from urllib.parse import quote
from pydantic import TypeAdapter,ValidationError
from app.contracts.models import DiagnosticProposal,FaultSpec,content_hash
from app.referee.reducer import neighbors
A=TypeAdapter(DiagnosticProposal)
L=json.load(open('/Users/shree/FaultLab_Scratch/inv-c/live_enriched.json'))
STORE={'artifacts/lab.sqlite3':'/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/artifacts/lab.sqlite3'}
res={}
for r in L:
    p=STORE.get(r['store'],r['store'])
    db=sqlite3.connect(f'file:{quote(p)}?mode=ro&immutable=1',uri=True)
    ret=json.loads(db.execute("select payload from records where kind='retained_recipes' and id=?",(r['counterexample_id'],)).fetchone()[0])['retained_recipe']
    src=json.loads(db.execute("select payload from records where kind='counterexample_recipes' and id=?",(r['counterexample_id'],)).fetchone()[0])['source_recipe']
    recipe=FaultSpec.model_validate(ret or src)
    options={}
    for change,treatment in neighbors(recipe):
        if len(options)>=4: break
        key='intervention-'+content_hash({'counterexample_id':r['counterexample_id'],'control':recipe,'treatment':treatment})[:24]
        options[key]=(change,treatment.model_dump(mode='json'))
    out=[]
    for a in r['mechanic_attempts']:
        raw=json.loads(db.execute("select payload from records where kind='mechanic_outputs' and id=?",(a['mechanic_output_id'],)).fetchone()[0])['raw']
        try:
            v=A.validate_json(raw); errs=[]
            if v.requested_intervention_id is not None and v.requested_intervention_id not in options: errs.append('unknown_intervention_reference')
        except ValidationError as e:
            errs=[f"{'.'.join(map(str,i['loc']))}:{i['type']}" for i in e.errors(include_input=False,include_context=False,include_url=False)]
        req=a['requested_intervention_id']
        out.append({'mechanic_output_id':a['mechanic_output_id'],'attempt':a['attempt'],'schema_and_option_errors':errs,'requested_in_options':(req in options) if req else None,'requested_change':options[req][0] if req in options else None})
    res[r['diagnostic_id']]={'options':{k:v[0] for k,v in options.items()},'attempts':out}
    print(r['diagnostic_id'][11:19],[ (o['attempt'],o['schema_and_option_errors'],o['requested_change']) for o in out],'n_options',len(options),'retained_used',ret is not None)
json.dump(res,open('/Users/shree/FaultLab_Scratch/inv-c/validation.json','w'),indent=1)
