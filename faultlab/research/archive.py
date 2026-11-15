"""The saved study records, read for people: the dashboard's study pages and anything else that browses results.

A study folder (one under ``artifacts/``, for example) publishes a declaration and one kind of record: unseen-case study
records with a comparison, one unseen-case study record, a repair study record, or a development check's read-outs. This
module lists those folders and summarizes each record with the same read-outs ``faultlab study compare`` prints.

Offline and read-only. It reads the published record files named in ``record_files`` and nothing else: no case file,
trial store, bundle or world, so a sealed draw stays sealed. It calls no provider and refuses any path outside the folder
it was given, a symbolic link included.
"""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from faultlab.research.compare import record_readouts

INDEX_SCHEMA = "faultlab-study-index/v1"
STUDY_SCHEMA = "faultlab-study/v1"
STUDY_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
ARM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$")
POLICY_FILE = re.compile(r"^policy[A-Za-z0-9_.-]{0,64}\.json$")
MAX_RECORD_BYTES = 16 * 1024 * 1024
KINDS = ("unseen_comparison", "unseen_study", "repair_study", "development_check")
# What each kind of record may claim, in the project's terms: development qualification, unseen-case results and an active
# policy are different claims.
CLAIMS = {
    "unseen_comparison": "Unseen-case comparison: each study's own decision is its claim. Not an active policy.",
    "unseen_study": "Unseen-case result on new schedules of the same task, fixtures and fault types. Not an active policy.",
    "repair_study": "Development qualification on the public cases. Not an unseen-case result and not an active policy.",
    "development_check": "Development check on a public case: it decides whether an unseen-case test is worth running.",
}
_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})$")
_WORDS = {"api": "API", "dev": "dev"}


class StudyNotFound(LookupError):
    """No published study, or no published record file, under that name."""


class StudyArchive:
    """The study folders under one root directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    # -- listing -------------------------------------------------------------------------------------------------------

    def index(self) -> dict:
        """Every study folder under the root, newest first. A folder whose records cannot be read is listed with its
        problem rather than hiding the others."""
        studies = []
        if self.root.is_dir():
            for folder in sorted(self.root.iterdir()):
                if not folder.is_dir() or not STUDY_ID.match(folder.name) or not self._contained(folder):
                    continue
                kind = _kind(folder)
                if kind is None:
                    continue
                try:
                    studies.append(self._summary(folder, kind))
                except (OSError, ValueError, KeyError, TypeError, StudyNotFound) as error:
                    studies.append({"id": folder.name, "kind": kind, "title": _title(folder.name), "date": _date(folder.name, None, None), "started_at": None,
                                    "claim": CLAIMS[kind], "question": None, "decisions": [], "dollars": None, "declaration": None,
                                    "problems": [f"the records could not be read: {type(error).__name__}"]})
        studies.sort(key=lambda s: (s["date"] or "", s["started_at"] or "", s["id"]), reverse=True)
        return {"schema": INDEX_SCHEMA, "root": str(self.root), "studies": studies}

    def study(self, study_id: str) -> dict:
        """One study in full: its declaration, each record's decision and read-outs, and the record files it publishes."""
        folder = self._folder(study_id)
        kind = _kind(folder)
        if kind is None:
            raise StudyNotFound(study_id)
        declaration, declared = _declaration(folder, self._read_bytes)
        detail: dict[str, Any] = {"schema": STUDY_SCHEMA, "id": study_id, "kind": kind, "title": _title(study_id), "claim": CLAIMS[kind],
                                  "declaration": declaration, "arms": [], "comparison": None, "repair": None, "development": None,
                                  "files": self._files(folder), "problems": []}
        record_dates: list[str | None] = []
        if kind in ("unseen_comparison", "unseen_study"):
            comparison = self._read(folder / "comparison.json") if kind == "unseen_comparison" else None
            for name, path in _unseen_records(folder, comparison):
                record = self._read(path)
                detail["arms"].append(_unseen_arm(name, path.relative_to(folder).as_posix(), record, declared))
                record_dates.append(record.get("created_at"))
            if comparison is not None:
                detail["comparison"] = {"order": comparison.get("order"), "primary": comparison.get("primary"), "note": comparison.get("note")}
        elif kind == "repair_study":
            record = self._read(folder / "repair-study.json")
            detail["repair"] = _repair(record)
            record_dates.append(record.get("created_at"))
        else:
            detail["development"] = _development(self._read(folder / "readouts.json"), declared)
        started = sorted(d for d in record_dates if isinstance(d, str))
        detail["started_at"] = started[0] if started else None
        detail["date"] = _date(study_id, declaration, detail["started_at"])
        detail["dollars"] = _dollars(detail)
        if declaration is None:
            detail["problems"].append("no declaration is published with this study")
        elif declaration["verified"] is False:
            detail["problems"].append("the declaration does not match its published sha256")
        return detail

    def record_file(self, study_id: str, name: str) -> dict:
        """A published record file as saved, for people who want the whole record. Only the files ``study`` lists."""
        folder = self._folder(study_id)
        if name not in {entry["name"] for entry in self._files(folder)}:
            raise StudyNotFound(f"{study_id}/{name}")
        return self._read(folder / name)

    # -- internals -----------------------------------------------------------------------------------------------------

    def _summary(self, folder: Path, kind: str) -> dict:
        detail = self.study(folder.name)
        declaration = detail["declaration"]
        decisions = [{"arm": arm["name"], "decision": arm["decision"], "model": arm["model"], "presentation": arm["presentation"]}
                     for arm in detail["arms"]]
        if detail["repair"] is not None:
            decisions = [{"arm": None, "decision": detail["repair"]["decision"], "model": detail["repair"]["model"], "presentation": None}]
        if detail["development"] is not None:
            decisions = [{"arm": None, "decision": detail["development"]["decision"], "model": detail["development"]["model"], "presentation": None}]
        question = None
        if declaration is not None:
            question = declaration["question"] or declaration["purpose"]
        return {"id": detail["id"], "kind": kind, "title": detail["title"], "date": detail["date"], "started_at": detail["started_at"],
                "claim": detail["claim"],
                "question": question, "decisions": decisions, "dollars": detail["dollars"],
                "declaration": None if declaration is None else {"sha256": declaration["sha256"], "verified": declaration["verified"]},
                "problems": detail["problems"]}

    def _folder(self, study_id: str) -> Path:
        if not isinstance(study_id, str) or not STUDY_ID.match(study_id):
            raise StudyNotFound(str(study_id))
        folder = self.root / study_id
        if not folder.is_dir() or not self._contained(folder):
            raise StudyNotFound(study_id)
        return folder

    def _read_bytes(self, path: Path) -> bytes:
        """Every read goes through here: a file that resolves outside the root (a link out, say) is not read."""
        if not self._contained(path):
            raise StudyNotFound(path.name)
        if path.stat().st_size > MAX_RECORD_BYTES:
            raise ValueError(f"{path.name} is larger than {MAX_RECORD_BYTES} bytes")
        return path.read_bytes()

    def _read(self, path: Path) -> dict:
        value = json.loads(self._read_bytes(path))
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} is not a JSON object")
        return value

    def _contained(self, path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(self.root.resolve())
        except OSError:
            return False

    def _files(self, folder: Path) -> list[dict]:
        names = [name for name in ("DECLARATION.json", "comparison.json", "unseen-study.json", "repair-study.json", "readouts.json")
                 if (folder / name).is_file()]
        names += sorted(p.name for p in folder.iterdir() if p.is_file() and POLICY_FILE.match(p.name))
        if (folder / "comparison.json").is_file():
            try:
                order = self._read(folder / "comparison.json").get("order") or []
            except (OSError, ValueError, StudyNotFound):
                order = []
            names += [f"{arm}/unseen-study.json" for arm in order if isinstance(arm, str) and ARM.match(arm)
                      and (folder / arm / "unseen-study.json").is_file()]
        return [{"name": name, "bytes": (folder / name).stat().st_size} for name in names if self._contained(folder / name)]


def _kind(folder: Path) -> str | None:
    if (folder / "comparison.json").is_file():
        return "unseen_comparison"
    if (folder / "unseen-study.json").is_file():
        return "unseen_study"
    if (folder / "repair-study.json").is_file():
        return "repair_study"
    if (folder / "readouts.json").is_file() and (folder / "DECLARATION.json").is_file():
        return "development_check"
    return None


def _title(study_id: str) -> str:
    words = _DATE.sub("", study_id).strip("-").split("-")
    text = " ".join(_WORDS.get(word, word) for word in words if word)
    return text[:1].upper() + text[1:]


def _date(study_id: str, declaration: dict | None, created_at: str | None) -> str | None:
    match = _DATE.search(study_id)
    if match:
        return match.group(1)
    if declaration and isinstance(declaration.get("declared_at"), str):
        return declaration["declared_at"][:10]
    return created_at[:10] if isinstance(created_at, str) else None


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _lines(value: Any) -> list[str]:
    """Declared read-outs and stop rules, as a list of sentences whatever shape the declaration gave them."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item if isinstance(item, str) else json.dumps(item, sort_keys=True) for item in value]
    if isinstance(value, dict):
        return [f"{key}: {item if isinstance(item, str) else json.dumps(item, sort_keys=True)}" for key, item in value.items()]
    return []


def _declaration(folder: Path, read_bytes) -> tuple[dict | None, dict]:
    """The declaration's statements and whether it matches the sha256 published beside it (None when none is)."""
    path = folder / "DECLARATION.json"
    if not path.is_file():
        return None, {}
    raw = read_bytes(path)
    digest = sha256(raw).hexdigest()
    verified = None
    published = folder / "DECLARATION.sha256"
    if published.is_file():
        tokens = read_bytes(published).decode("utf-8", errors="replace").split()
        verified = bool(tokens) and tokens[0].lower() == digest
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("DECLARATION.json is not a JSON object")
    readouts = value.get("comparison_readouts", value.get("pre_registered_readouts", value.get("readouts")))
    return {"sha256": digest, "verified": verified, "schema": _text(value.get("schema")), "name": _text(value.get("name")),
            "declared_at": _text(value.get("declared_at")), "purpose": _text(value.get("purpose")), "question": _text(value.get("question")),
            "claim_scope": _text(value.get("claim_scope")), "decision_rule": _text(value.get("decision_rule")),
            "readouts": _lines(readouts), "stop_rules": _lines(value.get("stop_rules")),
            "expected_cost": _text(value.get("expected_cost"))}, value


def _unseen_records(folder: Path, comparison: dict | None) -> list[tuple[str, Path]]:
    if comparison is None:
        return [("study", folder / "unseen-study.json")]
    order = comparison.get("order")
    if not isinstance(order, list) or not order or not all(isinstance(arm, str) and ARM.match(arm) for arm in order):
        raise ValueError("the comparison names no valid records")
    return [(arm, folder / arm / "unseen-study.json") for arm in order]


def _stage_model(record: dict) -> str | None:
    """The Actor model of a record written before records named their Actor (2026-11-15): each trial stage names its
    adapter. The walk skips trial rows and stops a few levels down."""
    def walk(value: Any, depth: int) -> str | None:
        if not isinstance(value, dict) or depth > 4:
            return None
        adapter = value.get("adapter")
        if isinstance(adapter, dict) and isinstance(adapter.get("model"), str):
            return adapter["model"]
        for key, item in value.items():
            found = None if key == "rows" else walk(item, depth + 1)
            if found:
                return found
        return None
    return walk(record.get("stages"), 0)


def _unseen_arm(name: str, relative: str, record: dict, declared: dict) -> dict:
    readouts = record_readouts(record)
    actor = record.get("actor") if isinstance(record.get("actor"), dict) else {}
    studies = declared.get("studies") if isinstance(declared.get("studies"), dict) else {}
    declared_arm = studies.get(name) if isinstance(studies.get(name), dict) else {}
    design = record.get("design") if isinstance(record.get("design"), dict) else {}
    return {"name": name, "record": relative, "study_name": _text(record.get("name")), "decision": record.get("decision"),
            "reason": record.get("reason"), "model": actor.get("model") or _stage_model(record),
            "presentation": actor.get("advice_presentation") or declared_arm.get("advice_presentation"),
            "policy_digest": record.get("policy_digest"), "created_at": record.get("created_at"), "ended_at": record.get("ended_at"),
            "design": {"pairs": design.get("pairs"), "other_pairs": design.get("other_pairs"), "gap_min": design.get("gap_min"),
                       "caps": design.get("caps"), "rejected_cases": len(design.get("rejected_cases") or []),
                       "other_cases": len(design.get("other_cases") or [])},
            "failed_cases": readouts["failed_cases"], "rejected": readouts["rejected"], "other": readouts["other"],
            "no_report": _no_report(record), "measured": readouts["measured"]}


def _no_report(record: dict) -> dict:
    """Trials of the rejected cases that ended with no delivered report, per arm (the rule arm's read-outs count them only
    inside other measures)."""
    rejected = (record.get("stages") or {}).get("rejected") or {}
    return {side: sum(1 for case in rejected.values() for row in case[side]["rows"] if row["report"] != "DELIVERED") for side in ("L", "B0")}


def _repair(record: dict) -> dict:
    readouts = record.get("readouts") if isinstance(record.get("readouts"), dict) else {}
    design = record.get("design") if isinstance(record.get("design"), dict) else {}
    proposals = []
    for proposal in readouts.get("3_proposals") or []:
        if isinstance(proposal, dict):
            policy = proposal.get("policy") if isinstance(proposal.get("policy"), dict) else None
            proposals.append({"slot": proposal.get("slot"), "valid": proposal.get("valid"), "ended": proposal.get("ended"),
                              "turns": proposal.get("turns"), "attempts": proposal.get("attempts"),
                              "version": policy.get("version") if policy else None,
                              "rules": [rule for rule in (policy.get("rules") or []) if isinstance(rule, dict)] if policy else []})
    validation = []
    for entry in readouts.get("5_validation") or []:
        if isinstance(entry, dict) and isinstance(entry.get("cases"), dict):
            validation.append({"slot": entry.get("slot"), "passed": entry.get("passed"),
                               "cases": {case_id: {"passed": case.get("passed"), "inert": case.get("inert"), "acting": case.get("acting"),
                                                   "clean": case.get("clean"), "B0": case.get("B0"), "L": case.get("L")}
                                         for case_id, case in entry["cases"].items() if isinstance(case, dict)}})
    mechanic = record.get("mechanic") if isinstance(record.get("mechanic"), dict) else {}
    cost = record.get("cost") if isinstance(record.get("cost"), dict) else {}
    return {"decision": record.get("decision"), "reason": record.get("reason"), "created_at": record.get("created_at"),
            "ended_at": record.get("ended_at"), "notes": [note for note in record.get("notes") or [] if isinstance(note, str)],
            "model": _stage_model(record), "mechanic_model": mechanic.get("model"),
            "design": {key: design.get(key) for key in ("source_scenario", "healthy_scenario", "must_complete", "pairs", "slots", "gap_min",
                                                         "target_rule", "caps")},
            "gap": readouts.get("1_gap"), "gate_opened": readouts.get("2_gate_opened"), "proposals": proposals,
            "candidates": [c for c in readouts.get("4_candidate") or [] if isinstance(c, dict)], "validation": validation,
            "measured": cost.get("measured")}


def _development(readouts: dict, declared: dict) -> dict:
    arms = readouts.get("arms") if isinstance(readouts.get("arms"), dict) else {}
    keys = ("trials", "slips", "acted", "trials_with_block", "side_effect_trials", "correct_refusals", "advice_turns", "dollars")
    actor = declared.get("actor") if isinstance(declared.get("actor"), dict) else {}
    model = actor.get("model")
    if model is None:
        code = declared.get("design") if isinstance(declared.get("design"), dict) else {}
        model = code.get("model") if isinstance(code.get("model"), str) else None
    primary = {key: value for key, value in readouts.items() if key not in ("arms", "decision") and isinstance(value, dict)}
    return {"decision": readouts.get("decision"), "model": model,
            "arms": {name: {key: arm.get(key) for key in keys} for name, arm in arms.items() if isinstance(arm, dict)},
            "primary": primary}


def _dollars(detail: dict) -> float | None:
    """API money the records measured. A launcher's preflight trial is in the ledger, not in these records."""
    values = []
    for arm in detail["arms"]:
        measured = arm.get("measured") or {}
        values.append(measured.get("dollars"))
    if detail["repair"] is not None:
        values.append((detail["repair"].get("measured") or {}).get("dollars"))
    if detail["development"] is not None:
        values += [arm.get("dollars") for arm in detail["development"]["arms"].values()]
    known = [v for v in values if isinstance(v, (int, float))]
    return round(sum(known), 6) if known else None


__all__ = ["CLAIMS", "INDEX_SCHEMA", "KINDS", "STUDY_SCHEMA", "StudyArchive", "StudyNotFound"]
