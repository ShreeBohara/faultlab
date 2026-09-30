import json, re, httpx
B='http://127.0.0.1:18431/api'
pair=json.load(open('pair.json'))
msgs=[json.loads(l) for l in open('ui/lab_messages.jsonl')]
def explorer(cid): return [m for m in msgs if m['campaign_id']==cid and m['role']=='explorer' and m['purpose']!='challenge']
e4,e3=explorer(pair['E4']['campaign_id']),explorer(pair['E3']['campaign_id'])
ID=re.compile(r'(campaign|episode|selection|counterexample|diagnostic|intervention|evidence|obs|policy|reduction|batch|world|trace|call|bundle|regression|proposal)-[0-9a-f]{32}')
def norm(text, cid):
    text=text.replace(cid,'CAMPAIGN')
    text=text.replace('faultlab-discovery/v4-history-replay','PROTOCOL').replace('faultlab-discovery/v3-history','PROTOCOL')
    return ID.sub(lambda m: m.group(1)+'-X', text)
res={'E4_requests':len(e4),'E3_requests':len(e3),'per_request':[]}
for a,b in zip(e4,e3):
    sa,sb=a['messages'][0]['content'],b['messages'][0]['content']
    ua,ub=json.loads(a['messages'][1]['content']),json.loads(b['messages'][1]['content'])
    res['per_request'].append({'slot':(a['selection_index'],b['selection_index']),'system_prompt_identical':sa==sb,
        'v4_section_in_E4':'Discovery protocol v4' in sa,
        'protocol_ids':(ua.get('discovery_protocol'),ub.get('discovery_protocol')),
        'user_context_keys_equal':sorted(ua)==sorted(ub),
        'user_equal_after_normalising_ids_and_protocol':norm(a['messages'][1]['content'],pair['E4']['campaign_id'])==norm(b['messages'][1]['content'],pair['E3']['campaign_id']),
        'differing_top_level_keys_raw':[k for k in ua if ua.get(k)!=ub.get(k)]})
for tag in ('E4','E3'):
    cid=pair[tag]['campaign_id']
    att=sorted(httpx.get(B+f'/campaigns/{cid}/search-attempts').json(),key=lambda r:r['selection_index'])
    res[tag+'_attempts']=[(r['selection_index'],r['provenance'],r['search_decision']['status'],'history_replay' in r) for r in att]
    exp=httpx.get(B+f'/campaigns/{cid}/experiments').json()['counterexamples']
    res[tag+'_sources']=[(x['counterexample']['target_invariant'],x.get('history_replay','ABSENT'),x.get('matches_history_row','ABSENT')) for x in exp]
    rec=httpx.get(B+f'/campaigns/{cid}/recording').json()
    res[tag+'_recording_replays']=rec.get('discovery_history_replays',{}).get('status','ABSENT'), rec.get('discovery_history_replays',{}).get('statement')
    plan=httpx.get(B+f'/campaigns/{cid}/plan').json()['plan']['discovery']
    res[tag+'_plan_keys']=sorted(plan)
print(json.dumps(res,indent=1)); json.dump(res,open('pair_compare.json','w'),indent=1)
