"""Readable local-agent evidence; execution and uncertainty stay separate."""
from html import escape
import json
from pathlib import Path

from app.cli.example import _trial_card


def _json(value):
    return json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)


def write_report(result):
    output = Path(result["paths"]["output_dir"])
    status = result["status"]
    healthy = result["mode"] == "healthy"
    title = "Healthy task control" if healthy else "Rejected upgrade regression"
    meaning = {
        "PASS": ("The agent completed the healthy task." if healthy else
                 "The selected agent passed all three fresh trials of this scenario."),
        "VIOLATION": "The selected agent violated a task check. The original report and effects are preserved.",
        "INCOMPLETE": "Required execution or evidence is incomplete. This result cannot establish a pass.",
    }[status]
    source_hash = result["agent"]["source_hash"]
    checks = ", ".join(result["failed_checks"]) or "None"
    cards = []
    for index, trial in enumerate(result["trials"], 1):
        process = trial.get("local_agent_execution") or {}
        cards.append(_trial_card(trial, index))
        cards.append('<div class="process"><strong>Local decision process</strong><pre>'
                     + escape(_json({key: process.get(key) for key in
                         ("protocol_status", "request_count", "errors", "cleanup_complete", "source_hash")}))
                     + '</pre></div>')
    portable = ('<p>A data-only copy and executable CI test are saved in <code>portable/</code>. '
                'The test requires you to select the agent file explicitly.</p>'
                if result["paths"]["portable"] else '')
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>FaultLab — {title}</title><style>
:root{{font-family:system-ui,-apple-system,sans-serif;color:#183327;background:#f3f6f1}}*{{box-sizing:border-box}}
body{{margin:0}}main{{max-width:1040px;margin:auto;padding:44px 24px}}h1{{font-size:36px;line-height:1.15}}h2{{font-size:22px}}
p{{line-height:1.6}}.eyebrow{{font-size:13px;font-weight:750;letter-spacing:.12em;text-transform:uppercase;color:#4e6857}}
.result{{background:white;border:1px solid #cbd7c8;border-radius:12px;padding:24px;margin:24px 0}}
.badge{{display:inline-block;padding:6px 12px;border-radius:5px;font-weight:750;font-size:13px}}
.pass{{background:#dceee0;color:#1c5735}}.violation{{background:#ffe4dc;color:#863321}}.incomplete{{background:#fff0c7;color:#775400}}
.notice{{border-left:4px solid #52745b;padding:14px 20px;background:#e6eee3}}.muted{{color:#516659;font-size:14px}}
details{{border-top:1px solid #dce5d8;padding:18px 0}}summary{{cursor:pointer;font-weight:650;overflow-wrap:anywhere}}
.process{{font-size:13px;padding:0 0 14px}}pre{{font-size:12px;line-height:1.5;background:#edf2e9;padding:14px;overflow:auto;max-height:360px}}
code{{overflow-wrap:anywhere}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}
caption{{text-align:left;font-weight:650;padding:12px 0}}th,td{{text-align:left;vertical-align:top;border-bottom:1px solid #dae3d5;padding:8px}}
td:last-child{{overflow-wrap:anywhere}}a{{color:#195b3a}}a:focus-visible,summary:focus-visible{{outline:3px solid #2c7951;outline-offset:4px}}
@media(max-width:600px){{main{{padding:24px 16px}}h1{{font-size:29px}}.result{{padding:18px}}}}
</style></head><body><main><div class="eyebrow">FaultLab / Your local agent</div>
<h1>{title}</h1><span class="badge {status.lower()}">{status}</span><p>{meaning}</p>
<div class="notice"><strong>Your decisions. FaultLab's tools and checks.</strong><br>
The explicitly selected Python program ran in fresh child processes. FaultLab retained the simulator, observations and fixed scoring.</div>
<div class="result"><h2>Execution identity</h2><p>Agent source: <code>{source_hash}</code></p>
<p class="muted">{result['trial_count']} of {result['required_trials']} required trials · {result['decision_calls']} local decisions · Failed checks: {escape(checks)}</p>
<p class="muted">FaultLab-managed provider calls: 0. External program activity and spending are not metered. Process separation and Python guards are not an operating-system security sandbox.</p>
<p><a href="./summary.json">Complete saved evidence (JSON)</a></p>{portable}</div>
<div class="result"><h2>Fresh trial evidence</h2>{''.join(cards)}</div>
<footer class="muted">This result concerns one synthetic orders scenario and the recorded agent source. It does not establish live-model reliability, a generated repair, or an accepted policy.</footer>
</main></body></html>'''
    (output / "report.html").write_text(page)
    (output / "report.md").write_text(
        f"# FaultLab — {title}\n\n**{status}** — {meaning}\n\n"
        f"Agent source: `{source_hash}`\n\n"
        f"Trials: {result['trial_count']}/{result['required_trials']}; local decisions: {result['decision_calls']}; failed checks: {checks}.\n\n"
        "FaultLab-managed provider calls: 0. External program activity and spending are unobserved.\n\n"
        "See summary.json for original observations, reports, fault exposure, world effects and process diagnostics.\n")

