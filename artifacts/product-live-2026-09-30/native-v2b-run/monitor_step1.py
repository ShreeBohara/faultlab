"""Declared stop-rule watcher for the native probe (PLAN.md section 7). Read-only GETs; POSTs /stop only on a stop rule."""
import json, time, urllib.request, pathlib, datetime
B='http://127.0.0.1:8000'; C='campaign-c8063a1166834051b08ae5317ff6f9c2'; S='baseline-study-cb7eb68e0cb045dc97a2c0ffe55561d0'
SID=open('artifacts/product-live-2026-09-30/native-v2b-run/store-identity.txt').read().strip()
D=pathlib.Path('artifacts/product-live-2026-09-30/native-v2b-run'); log=open(D/'monitor.log','a')
EXPECT={'dev-1':'COMPLETED','dev-2':'COMPLETED','dev-3':'COMPLETED','dev-4':'COMPLETED','dev-5':'CORRECTLY_REJECTED','dev-6':'COMPLETED'}
def get(p):
    with urllib.request.urlopen(B+p, timeout=10) as r: return json.loads(r.read())
def stop(reason):
    req=urllib.request.Request(B+f'/api/campaigns/{C}/stop', data=b'{}', method='POST', headers={'Content-Type':'application/json','X-FaultLab-Store-Identity':SID})
    try: resp=urllib.request.urlopen(req, timeout=10).read().decode()[:300]
    except Exception as e: resp=f'stop failed: {e}'
    log.write(f'STOP {reason} -> {resp}\n'); log.flush(); print('STOP', reason, resp)
t0=time.time(); stopped=False
while True:
    now=datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')
    try: st=get(f'/api/baseline-studies/{S}'); bud=get(f'/api/campaigns/{C}/budget')
    except Exception as e:
        log.write(f'{now} poll error {e}\n'); log.flush(); time.sleep(10); continue
    slots=st.get('slots',[]); trials={t.get('episode_id'):t for t in st.get('trials',[])}
    used=bud.get('used_calls', bud.get('usage',{}).get('model_calls'))
    done=sum(1 for s in slots if s.get('status') not in ('NOT_ATTEMPTED','RUNNING','QUEUED'))
    reasons=[]
    for s in slots:
        t=trials.get(s.get('episode_id'))
        if not t: continue
        lc=t.get('lifecycle'); oc=t.get('outcome')
        if lc in ('LAB_ERROR','INTERRUPTED') or oc=='LAB_ERROR': reasons.append(f"S1 {s['case_id']} {s['arm']} lifecycle={lc} outcome={oc}")
        if s.get('arm')=='B1' and lc=='COMPLETED' and oc!=EXPECT.get(s['case_id']): reasons.append(f"S2 B1 {s['case_id']} outcome={oc}")
    if st.get('status')=='INCOMPLETE': reasons.append('S3 study INCOMPLETE')
    if isinstance(used,(int,float)) and used>288: reasons.append(f'S4 used_calls={used}')
    if time.time()-t0>45*60: reasons.append('S5 45 minutes')
    log.write(f"{now} status={st.get('status')} slots_done={done}/{len(slots)} used_calls={used} charged={bud.get('charged_dollar_upper_bound')}\n"); log.flush()
    if reasons and not stopped: stop('; '.join(reasons)); stopped=True
    if st.get('status') in ('COMPLETED','INCOMPLETE','STOPPED','ERROR','CANCELLED','FAILED'):
        (D/'study-final.json').write_text(json.dumps(st,indent=2)); (D/'budget-final.json').write_text(json.dumps(bud,indent=2))
        print('FINAL', st.get('status'), 'used_calls', used, 'charged', bud.get('charged_dollar_upper_bound')); break
    time.sleep(10)
