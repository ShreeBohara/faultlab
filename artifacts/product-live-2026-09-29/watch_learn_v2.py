"""Declared stop-rule watcher v2 for live Learn campaigns (fixes review B3): past discovery is detected from the
durable counterexample record (/experiments), not from polled states; the selection-count guard applies at all
times. Read-only GETs every 30 s; POST /stop only on a declared rule.
Usage: watch_learn_v2.py <run_dir> <campaign_id> <store_identity> <max_selections> <disc_max_calls> <disc_max_dollars> <max_hours>"""
import json, sys, time, urllib.request, pathlib, datetime, shutil
R, C, SID = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
MAXSEL, DISC_CALLS, DISC_DOLLARS, MAX_H = int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7])
B='http://127.0.0.1:8000'; log=open(R/'monitor.log','a'); TERMINAL={'NO_CHANGE','STOPPED','COMPLETED','ERROR'}
def get(p):
    with urllib.request.urlopen(B+p, timeout=20) as r: return json.loads(r.read())
def stop(reason):
    req=urllib.request.Request(B+f'/api/campaigns/{C}/stop', data=b'{}', method='POST', headers={'Content-Type':'application/json','X-FaultLab-Store-Identity':SID})
    try: resp=urllib.request.urlopen(req, timeout=20).read().decode()[:300]
    except Exception as e: resp=f'stop failed: {e}'
    log.write(f'STOP {reason} -> {resp}\n'); log.flush(); print('STOP', reason, resp)
t0=time.time(); stopped=False; states=[]; last_line=''
while True:
    now=datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')
    try:
        cam=get(f'/api/campaigns/{C}'); bud=get(f'/api/campaigns/{C}/budget'); sa=get(f'/api/campaigns/{C}/search-attempts'); ex=get(f'/api/campaigns/{C}/experiments')
    except Exception as e:
        log.write(f'{now} poll error {e}\n'); log.flush(); time.sleep(30); continue
    st=cam.get('state'); used=bud.get('used_calls'); ch=bud.get('charged_dollar_upper_bound')
    nsel=len(sa) if isinstance(sa,list) else None; ncx=len(ex.get('counterexamples') or [])
    past=ncx>0
    if not states or states[-1]!=st: states.append(st)
    reasons=[]
    if isinstance(nsel,int) and nsel>MAXSEL: reasons.append(f'{nsel} discovery selection records > {MAXSEL}')
    if not past:
        if isinstance(used,(int,float)) and used>DISC_CALLS: reasons.append(f'discovery accounting: used_calls {used} > {DISC_CALLS} with no counterexample')
        if isinstance(ch,(int,float)) and ch>DISC_DOLLARS: reasons.append(f'discovery accounting: charged {ch} > {DISC_DOLLARS} with no counterexample')
    if shutil.disk_usage('/Users/shree').free < 2*1024**3: reasons.append('disk < 2 GiB')
    if time.time()-t0 > MAX_H*3600: reasons.append(f'{MAX_H} hours elapsed')
    line=f"state={st} used_calls={used} charged={ch} selections={nsel} counterexamples={ncx} policy={cam.get('active_policy_version')}"
    if line!=last_line: log.write(f'{now} {line}\n'); log.flush(); last_line=line
    if reasons and not stopped: stop('; '.join(reasons)); stopped=True
    if st in TERMINAL:
        (R/'state-sequence.json').write_text(json.dumps(states)); print('FINAL', st, cam.get('terminal_reason'), line, 'states', states); break
    time.sleep(30)
