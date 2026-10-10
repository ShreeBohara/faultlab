"""Static review of original observations and actual effects, with no remote assets."""
from html import escape
from pathlib import Path

from .models import canonical


def write_report(envelope, path):
    def code(value):
        return "<pre>" + escape(canonical(value)) + "</pre>"

    def rows(values, render, empty):
        return "".join(render(value) for value in values) if values else f"<tr><td colspan='4'>{escape(empty)}</td></tr>"

    operations = rows(envelope.operations, lambda o: "<tr><td>" + escape(o.action) + "</td><td>" + escape(o.scope)
        + "</td><td>" + code(o.payload) + "</td></tr>", "No declared operations recorded")
    effects = rows(envelope.effects, lambda e: "<tr><td>" + escape(e.effect_id) + "</td><td>" + escape(e.intent_id or "Unattributed")
        + "</td><td>" + code(e.payload) + "</td><td>" + code(e.receipt) + "</td></tr>",
        "No recorded effects" if envelope.lifecycle.authority_complete else "Effects remain unknown or partial")
    observations = rows(envelope.observations, lambda o: "<tr><td>" + escape(o.observation_id) + "</td><td>" + escape(o.transport)
        + "</td><td>" + code(o.payload) + "</td></tr>", "No delivered observations recorded")
    checks = rows(envelope.checks, lambda c: "<tr><td>" + escape(c.check_id) + "</td><td>" + ("Passed" if c.passed else "Failed")
        + "</td><td>" + escape(c.details) + "</td></tr>", "Task checks unavailable")
    status = envelope.assessment.status
    reason = ", ".join(envelope.assessment.incomplete_reasons) or "Required evidence is present."
    content = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>FaultLab incident evidence — {escape(status)}</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;margin:0;background:#f6f7fa;color:#162139}}main{{max-width:1100px;margin:40px auto;padding:0 24px}}h1{{font-size:32px}}h2{{margin-top:36px}}.status{{display:inline-block;font-weight:700;padding:8px 14px;border-radius:8px;background:#fff0bd}}.PASS{{background:#d9f1e3}}.VIOLATION{{background:#ffe0de}}.cards{{display:flex;gap:16px;flex-wrap:wrap}}.card{{background:white;padding:18px 24px;border:1px solid #d9dfeb;border-radius:10px}}table{{width:100%;border-collapse:collapse;background:white}}th,td{{border:1px solid #d9dfeb;padding:12px;text-align:left;vertical-align:top}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,monospace;margin:0}}td{{overflow-wrap:anywhere}}.scroll{{overflow-x:auto}}a{{color:#1d4aa3}}details{{background:white;border:1px solid #d9dfeb;padding:16px;margin:20px 0}}footer{{margin:36px 0;color:#42506a}}</style></head>
<body><main><p>FaultLab · synthetic incident evidence</p><h1>Intent, attempts, and actual effects</h1>
<p class="status {escape(status)}">{escape(status)}</p><p>{escape(reason)}</p>
<p>Task: {escape(envelope.identity.task_type)}<br>Subject: {escape(envelope.identity.subject_id)}</p>
<div class="cards"><div class="card">Intended operations<br><strong>{len(envelope.operations)}</strong></div><div class="card">Recorded attempts<br><strong>{len(envelope.attempts)}</strong></div><div class="card">Recorded effects<br><strong>{len(envelope.effects)}</strong></div><div class="card">Original report<br><strong>{escape(envelope.report.status)}</strong></div></div>
<p>Known failed checks remain visible when execution or evidence is incomplete.</p>
<h2>Intended actions</h2><div class="scroll"><table><tr><th>Action</th><th>Scope</th><th>Declared payload</th></tr>{operations}</table></div>
<h2>Recorded effects</h2><div class="scroll"><table><tr><th>Effect</th><th>Intended operation</th><th>Authoritative payload</th><th>Stored receipt</th></tr>{effects}</table></div>
<h2>Task-specific checks</h2><div class="scroll"><table><tr><th>Check</th><th>Result</th><th>Finding</th></tr>{checks}</table></div>
<h2>Original report</h2>{code(envelope.report.original)}<details><summary>Original text and interpreted report, when available</summary>{code(envelope.report.model_dump(mode='json'))}</details>
<details><summary>Delivered observations</summary><div class="scroll"><table><tr><th>Observation</th><th>Transport</th><th>Delivered content</th></tr>{observations}</table></div></details>
<details><summary>Attempts, fault exposure and lifecycle</summary>{code({'attempts':[a.model_dump(mode='json') for a in envelope.attempts],'faults':[f.model_dump(mode='json') for f in envelope.faults],'lifecycle':envelope.lifecycle.model_dump(mode='json')})}</details>
<details><summary>Recorded identities</summary>{code(envelope.identity.model_dump(mode='json'))}<p>Evidence digest: {escape(envelope.digest)}</p></details>
<p><a href="incident.zip">Download data-only evidence bundle</a> · <a href="evidence/evidence.json">Read complete evidence</a></p>
<footer>Offline synthetic evidence. No production-model result, generated repair, ACCEPTED policy or customer validation follows from this report. Hashes establish internal consistency, not independent authenticity.</footer>
</main></body></html>"""
    Path(path).write_text(content, encoding="utf-8")
