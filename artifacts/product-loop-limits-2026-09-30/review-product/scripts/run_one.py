import json, sys, time, httpx
B = 'http://127.0.0.1:18531/api'
cid = sys.argv[1]
with httpx.Client(timeout=60) as h:
    r = h.post(B + f'/campaigns/{cid}/start', json={}); assert r.status_code == 202, r.text
    t0 = time.time()
    while True:
        c = h.get(B + f'/campaigns/{cid}').json()
        if c['state'] in ('NO_CHANGE', 'ERROR', 'STOPPED', 'COMPLETED', 'WAITING_EVIDENCE'): break
        if time.time() - t0 > 1500: break
        time.sleep(3)
    print(json.dumps({'campaign_id': cid, 'state': c['state'], 'reason': c.get('terminal_reason'), 'seconds': round(time.time() - t0)}))
