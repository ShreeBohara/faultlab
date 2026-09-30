import json, time, httpx
B='http://127.0.0.1:18431/api'
out={}
for tag,cid in (('E4','campaign-7c73475426e645af8eb128da59eab03c'),('E3','campaign-a16f39fa2ce9405da33bd62358c977a0')):
    chk=httpx.get(B+f'/campaigns/{cid}/plan/history-check').json()
    r=httpx.post(B+f'/campaigns/{cid}/start',json={}, timeout=60)
    assert r.status_code==202, r.text
    while True:
        c=httpx.get(B+f'/campaigns/{cid}').json()
        if c['state'] in ('NO_CHANGE','ERROR','STOPPED','COMPLETED'): break
        time.sleep(3)
    out[tag]={'campaign_id':cid,'check':chk['status'],'check_message':chk['message'],'state':c['state'],'reason':c.get('terminal_reason')}
print(json.dumps(out,indent=1)); json.dump(out,open('pair.json','w'),indent=1)
