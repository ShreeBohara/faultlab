import sys,json,sqlite3
sys.dont_write_bytecode=True
sys.path.insert(0,'/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab/backend')
from urllib.parse import quote
from app.contracts.models import FaultSpec,content_hash
from app.referee.reducer import neighbors
L=json.load(open('/Users/shree/FaultLab_Scratch/inv-c/live_enriched.json'))
for r in L:
    if r['agent'].startswith('reference'): continue
    p=r['store']; db=sqlite3.connect(f'file:{quote(p)}?mode=ro&immutable=1',uri=True)
    ret=json.loads(db.execute("select payload from records where kind='retained_recipes' and id=?",(r['counterexample_id'],)).fetchone()[0])['retained_recipe']
    red=json.loads(db.execute("select payload from records where kind='reductions' and id=?",(r['counterexample_id'],)).fetchone()[0])
    recipe=FaultSpec.model_validate(ret)
    tids=[t for a in red.get('attempts',[]) for t in a.get('trial_ids',[])]
    trials=[json.loads(db.execute("select payload from records where kind='trials' and id=?",(t,)).fetchone()[0]) for t in tids]
    def obs(h):
        g=[t for t in trials if t['scenario_hash']==h]
        if not g: return None
        valid=[t for t in g if t['lifecycle']=='COMPLETED' and t['outcome'] not in (None,'LAB_ERROR') and (not t['fault_scheduled'] or t['fault_triggered'])]
        return f"{sum(r['target_invariant'] in t['failed_checks'] for t in valid)}/{len(valid)} valid ({len(g)} run)"
    opts=[]
    for change,treatment in list(neighbors(recipe))[:4]:
        opts.append((change,obs(content_hash(treatment))))
    print(r['diagnostic_id'][11:19],r['agent'][:9],r['target_invariant'],'control',obs(content_hash(recipe)),'options',opts,'| mech',r['mechanic_final_proposed_kind_raw'],'req',r['mechanic_requested_intervention_raw'],'| verdict',r['verdict_kind'])
