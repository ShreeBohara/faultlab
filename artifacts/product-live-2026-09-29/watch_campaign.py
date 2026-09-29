"""Declared stop-rule watcher for a live Learn campaign (reusable). Read-only GETs once a minute; POST /stop only on a declared rule.
Usage: watch_campaign.py <run_dir> <campaign_id> <store_identity> <discovery_max_calls> <discovery_max_dollars> <max_hours>"""
import json, sys, time, urllib.request, pathlib, datetime, shutil
R, C, SID = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
DISC_CALLS, DISC_DOLLARS, MAX_H = int(sys.argv[4]), float(sys.argv[5]), float(sys.argv[6])
B='http://127.0.0.1:8000'; log=open(R/'monitor.log','a')
TERMINAL={'NO_CHANGE','STOPPED','COMPLETED','ERROR'}
POST_DISCOVERY={'REPRODUCING','REDUCING','DIAGNOSING','CANDIDATE_VALIDATION','EVALUATING','CHALLENGING','REJECTED','PROMOTED'}
def get(p):
    with urllib.request.urlopen(B+p, timeout=15) as r: return json.loads(r.read())
def stop(reason):
    req=urllib.request.Request(B+f'/api/campaigns/{C}/stop', data=b'{}', method='POST', headers={'Content-Type':'application/json','X-FaultLab-Store-Identity':SID})
    try: resp=urllib.request.urlopen(req, timeout=15).read().decode()[:300]
    except Exception as e: resp=f'stop failed: {e}'
    log.write(f'STOP {reason} -> {resp}\n'); log.flush(); print('STOP', reason, resp)
t0=time.time(); stopped=False; past_discovery=False; states=[]
while True:
    now=datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')
    try: cam=get(f'/api/campaigns/{C}'); bud=get(f'/api/campaigns/{C}/budget'); sa=get(f'/api/campaigns/{C}/search-attempts')
    except Exception as e:
        log.write(f'{now} poll error {e}\n'); log.flush(); time.sleep(60); continue
    st=cam.get('state'); used=bud.get('used_calls'); ch=bud.get('charged_dollar_upper_bound'); nsel=len(sa) if isinstance(sa,list) else None
    if st in POST_DISCOVERY: past_discovery=True
    if not states or states[-1]!=st: states.append(st)
    reasons=[]
    if not past_discovery:
        if isinstance(used,(int,float)) and used>DISC_CALLS: reasons.append(f'discovery accounting: used_calls {used} > {DISC_CALLS}')
        if isinstance(ch,(int,float)) and ch>DISC_DOLLARS: reasons.append(f'discovery accounting: charged {ch} > {DISC_DOLLARS}')
    if shutil.disk_usage('/Users/shree').free < 2*1024**3: reasons.append('disk < 2 GiB')
    if time.time()-t0 > MAX_H*3600: reasons.append(f'{MAX_H} hours elapsed')
    log.write(f"{now} state={st} used_calls={used} charged={ch} selections={nsel} past_discovery={past_discovery}\n"); log.flush()
    if reasons and not stopped: stop('; '.join(reasons)); stopped=True
    if st in TERMINAL:
        (R/'state-sequence.json').write_text(json.dumps(states)); print('FINAL', st, cam.get('terminal_reason'), 'used', used, 'charged', ch, 'selections', nsel, 'states', states); break
    time.sleep(60)
