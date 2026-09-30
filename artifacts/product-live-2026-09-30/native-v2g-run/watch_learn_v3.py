"""Declared stop-rule watcher v3 for live Learn campaigns.

v2's rules unchanged (past discovery from the durable counterexample record; selection-count guard at all times;
disk; wall-clock). New in v3 (fixes the 2026-09-29 stall): while the campaign is WAITING_EVIDENCE it reads the
product's /evidence-wait record and logs every change. The product now retries evidence by itself (declared rule
faultlab-evidence-retry/v2). Only when the product reports NEEDS_OPERATOR does the watcher apply the declared
operator action: one telemetry-only POST /retry-evidence (re-sends saved trace records; repeats no episode, no
business call, no model request), at most OP_RETRIES times per campaign and at least 10 minutes apart.
Read-only GETs every 30 s otherwise; POST /stop only on a declared rule.
Usage: watch_learn_v3.py <run_dir> <campaign_id> <store_identity> <max_selections> <disc_max_calls>
       <disc_max_dollars> <max_hours> <operator_retries>"""
import json, sys, time, urllib.request, pathlib, datetime, shutil
R, C, SID = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
MAXSEL, DISC_CALLS, DISC_DOLLARS, MAX_H = int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6]), float(sys.argv[7])
OP_RETRIES = int(sys.argv[8])
B = 'http://127.0.0.1:8000'; log = open(R / 'monitor.log', 'a'); TERMINAL = {'NO_CHANGE', 'STOPPED', 'COMPLETED', 'ERROR'}
HDR = {'Content-Type': 'application/json', 'X-FaultLab-Store-Identity': SID}
def get(p):
    with urllib.request.urlopen(B + p, timeout=20) as r: return json.loads(r.read())
def post(p):
    req = urllib.request.Request(B + p, data=b'{}', method='POST', headers=HDR)
    try: return urllib.request.urlopen(req, timeout=20).read().decode()[:300]
    except Exception as e: return f'failed: {e}'
def note(s):
    log.write(s + '\n'); log.flush(); print(s, flush=True)
t0 = time.time(); stopped = False; states = []; last_line = ''; last_wait = ''; op_used = 0; op_last = 0.0
while True:
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%H:%M:%S')
    try:
        cam = get(f'/api/campaigns/{C}'); bud = get(f'/api/campaigns/{C}/budget')
        sa = get(f'/api/campaigns/{C}/search-attempts'); ex = get(f'/api/campaigns/{C}/experiments')
    except Exception as e:
        note(f'{now} poll error {e}'); time.sleep(30); continue
    st = cam.get('state'); used = bud.get('used_calls'); ch = bud.get('charged_dollar_upper_bound')
    nsel = len(sa) if isinstance(sa, list) else None; ncx = len(ex.get('counterexamples') or [])
    if not states or states[-1] != st: states.append(st)
    reasons = []
    if isinstance(nsel, int) and nsel > MAXSEL: reasons.append(f'{nsel} discovery selection records > {MAXSEL}')
    if ncx == 0:
        if isinstance(used, (int, float)) and used > DISC_CALLS: reasons.append(f'discovery accounting: used_calls {used} > {DISC_CALLS} with no counterexample')
        if isinstance(ch, (int, float)) and ch > DISC_DOLLARS: reasons.append(f'discovery accounting: charged {ch} > {DISC_DOLLARS} with no counterexample')
    if shutil.disk_usage('/Users/shree').free < 2 * 1024 ** 3: reasons.append('disk < 2 GiB')
    if time.time() - t0 > MAX_H * 3600: reasons.append(f'{MAX_H} hours elapsed')
    line = f"state={st} used_calls={used} charged={ch} selections={nsel} counterexamples={ncx} policy={cam.get('active_policy_version')}"
    if line != last_line: note(f'{now} {line}'); last_line = line
    if st == 'WAITING_EVIDENCE':
        try:
            w = get(f'/api/campaigns/{C}/evidence-wait')
            cur = w.get('current') or {}
            wl = (f"evidence-wait status={w.get('status')} auto_total={w.get('automatic_retries_total')} "
                  f"waits_total={w.get('waits_total')} current_started={cur.get('started_at')}")
            if wl != last_wait: note(f'{now} {wl}'); last_wait = wl
            if w.get('needs_operator') and op_used < OP_RETRIES and time.time() - op_last > 600 and not stopped:
                op_used += 1; op_last = time.time()
                note(f'{now} OPERATOR evidence retry {op_used}/{OP_RETRIES} (declared, telemetry-only) -> {post(f"/api/campaigns/{C}/retry-evidence")}')
        except Exception as e:
            note(f'{now} evidence-wait read error {e}')
    if reasons and not stopped:
        note(f'STOP {"; ".join(reasons)} -> {post(f"/api/campaigns/{C}/stop")}'); stopped = True
    if st in TERMINAL:
        (R / 'state-sequence.json').write_text(json.dumps(states))
        note(f"FINAL {st} {cam.get('terminal_reason')} {line} operator_retries={op_used} states={states}"); break
    time.sleep(30)
