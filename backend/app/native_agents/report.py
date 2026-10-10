"""Local HTML and Markdown evidence; original reports and process failure remain visible."""
from html import escape
import json
from pathlib import Path

from app.cli.example import _trial_card


def write_report(result):
    output = Path(result["paths"]["output_dir"])
    status = result["status"]
    title = "Native agent healthy control" if result["mode"] == "healthy" else "Native agent rejection regression"
    meaning = {
        "PASS": "The selected constructor passed the required fresh trials under the declared model double.",
        "VIOLATION": "The selected constructor violated a fixed task check; its original report and effects are preserved.",
        "INCOMPLETE": "Required execution or evidence is incomplete. This result cannot establish a pass.",
    }[status]
    cards = []
    for index, trial in enumerate(result["trials"], 1):
        record = trial.get("native_agent_execution") or {}
        cards.append(_trial_card(trial, index))
        details = {key: record.get(key) for key in (
            "protocol_status", "request_count", "process_creation_complete", "cleanup_complete",
            "exit_code", "errors", "source_hash", "ready", "final_report", "requests")}
        cards.append('<details><summary>Native execution and public requests</summary><pre>'
                     + escape(json.dumps(details, indent=2, ensure_ascii=False, allow_nan=False))
                     + '</pre></details>')
    source_hash = result["agent"]["source_hash"]
    checks = ", ".join(result["failed_checks"]) or "None"
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>FaultLab — {title}</title><style>
:root{{font-family:system-ui,-apple-system,sans-serif;color:#183327;background:#f3f6f1}}*{{box-sizing:border-box}}
body{{margin:0}}main{{max-width:1040px;margin:auto;padding:44px 24px}}h1{{font-size:34px;line-height:1.2}}h2{{font-size:22px}}
p{{line-height:1.6}}.eyebrow{{font-size:13px;font-weight:750;letter-spacing:.1em;text-transform:uppercase;color:#4e6857}}
.result{{background:white;border:1px solid #cbd7c8;border-radius:12px;padding:24px;margin:24px 0}}
.badge{{display:inline-block;padding:6px 12px;border-radius:5px;font-weight:750;font-size:13px}}
.pass{{background:#dceee0;color:#1c5735}}.violation{{background:#ffe4dc;color:#863321}}.incomplete{{background:#fff0c7;color:#775400}}
.notice{{border-left:4px solid #52745b;padding:14px 20px;background:#e6eee3}}.muted{{color:#516659;font-size:14px}}
details{{border-top:1px solid #dce5d8;padding:18px 0}}summary{{cursor:pointer;font-weight:650;overflow-wrap:anywhere}}
pre{{font-size:12px;line-height:1.5;background:#edf2e9;padding:14px;overflow:auto;max-height:420px}}
code{{overflow-wrap:anywhere}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;font-size:13px}}
caption{{text-align:left;font-weight:650;padding:12px 0}}th,td{{text-align:left;vertical-align:top;border-bottom:1px solid #dae3d5;padding:8px}}
td:last-child{{overflow-wrap:anywhere}}a{{color:#195b3a}}a:focus-visible,summary:focus-visible{{outline:3px solid #2c7951;outline-offset:4px}}
@media(max-width:600px){{main{{padding:24px 16px}}h1{{font-size:27px}}.result{{padding:18px}}}}
</style></head><body><main><div class="eyebrow">FaultLab / Native agent conformance</div>
<h1>{title}</h1><span class="badge {status.lower()}">{status}</span><p>{meaning}</p>
<div class="notice"><strong>Your constructor and tool guard. Native smolagents control flow.</strong><br>
The framework ran with a deterministic model double. FaultLab retained fault injection, authoritative observations and fixed checks.</div>
<div class="result"><h2>Execution identity</h2><p>Candidate source: <code>{source_hash}</code></p>
<p class="muted">{result['trial_count']} of {result['required_trials']} required trials · {result['model_double_calls']} model-double calls · Failed checks: {escape(checks)}</p>
<p class="muted">Managed provider calls: 0. Arbitrary user-code activity and spending are unmetered. This process is not an operating-system security sandbox.</p>
<p><a href="./summary.json">Complete saved evidence (JSON)</a></p></div>
<div class="result"><h2>Fresh trial evidence</h2>{''.join(cards)}</div>
<footer class="muted">One synthetic scenario under a declared native adapter. This does not establish production-model reliability, a generated repair, an ACCEPTED policy or customer adoption.</footer>
</main></body></html>'''
    (output / "report.html").write_text(page, encoding="utf-8")
    (output / "report.md").write_text(
        f"# FaultLab — {title}\n\n**{status}** — {meaning}\n\n"
        f"Candidate source: `{source_hash}`\n\n"
        f"Trials: {result['trial_count']}/{result['required_trials']}; model-double calls: {result['model_double_calls']}; failed checks: {checks}.\n\n"
        "Native framework conformance with a fixed deterministic model double. Managed provider calls: 0.\n\n"
        "See summary.json for native requests, original reports, actual effects and process completion. "
        "This result does not establish production-model reliability or an ACCEPTED policy.\n", encoding="utf-8")
