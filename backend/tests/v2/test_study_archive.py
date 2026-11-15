"""The study archive: every committed study reads, the read-outs are the comparison command's, and nothing outside a
study's published record files is ever read or served."""

import json
import os
from pathlib import Path
import shutil

import pytest

from faultlab.research.archive import CLAIMS, INDEX_SCHEMA, STUDY_SCHEMA, StudyArchive, StudyNotFound
from faultlab.research.compare import record_readouts

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts"
C4 = "unseen-comparison-4-2026-11-15"
PUBLISHED = ("DECLARATION.json", "DECLARATION.sha256", "comparison.json", "policy-L3.json", "E/unseen-study.json", "Q/unseen-study.json")


def copy_study(root: Path, study_id: str = C4) -> Path:
    """A copy of a committed study's published files under a scratch root."""
    target = root / study_id
    for name in PUBLISHED:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ARTIFACTS / study_id / name, target / name)
    return target


def test_every_committed_study_reads_with_its_declaration_verified():
    index = StudyArchive(ARTIFACTS).index()
    assert index["schema"] == INDEX_SCHEMA
    studies = {study["id"]: study for study in index["studies"]}
    assert len(studies) >= 16
    for study in studies.values():
        assert study["problems"] == [], study["id"]
        assert study["declaration"]["verified"] is True, study["id"]
        assert study["claim"] == CLAIMS[study["kind"]]
        assert study["decisions"] and all(d["decision"] for d in study["decisions"]), study["id"]
    kinds = {study["kind"] for study in studies.values()}
    assert kinds == {"unseen_comparison", "unseen_study", "repair_study", "development_check"}
    c4 = studies[C4]
    assert [(d["arm"], d["decision"], d["model"], d["presentation"]) for d in c4["decisions"]] == [
        ("E", "NOT_TRANSFERRED", "anthropic:claude-sonnet-5-5", "expectation"),
        ("Q", "TRANSFERRED", "anthropic:claude-sonnet-5-5", "requirement")]
    assert studies["repair-study-v3-2026-11-14"]["decisions"][0]["decision"] == "REPAIRED"
    assert studies["advice-final-turn-dev-2-2026-11-15"]["decisions"][0]["decision"] == "INCONCLUSIVE"
    # Newest first; studies of one day by their first record's start.
    dates = [(s["date"], s["started_at"] or "") for s in index["studies"]]
    assert dates == sorted(dates, reverse=True)


def test_read_outs_are_the_comparison_commands_and_the_primary_comparison_is_kept():
    detail = StudyArchive(ARTIFACTS).study(C4)
    assert detail["schema"] == STUDY_SCHEMA and detail["kind"] == "unseen_comparison"
    for arm in detail["arms"]:
        record = json.loads((ARTIFACTS / C4 / arm["record"]).read_text())
        expected = record_readouts(record)
        assert arm["rejected"] == expected["rejected"] and arm["other"] == expected["other"]
        assert arm["failed_cases"] == expected["failed_cases"] and arm["measured"] == expected["measured"]
    comparison = json.loads((ARTIFACTS / C4 / "comparison.json").read_text())
    assert detail["comparison"]["primary"] == comparison["primary"]
    q = next(arm for arm in detail["arms"] if arm["name"] == "Q")
    assert q["rejected"]["L"]["slips"] == 0 and q["rejected"]["B0"]["slips"] == 8 and q["failed_cases"] == []
    assert detail["dollars"] == pytest.approx(5.607318 + 5.616488, abs=1e-6)
    assert detail["declaration"]["question"].startswith("With Sonnet 5.5 as the Actor")
    assert [f["name"] for f in detail["files"]] == ["DECLARATION.json", "comparison.json", "policy-L3.json",
                                                    "E/unseen-study.json", "Q/unseen-study.json"]


def test_records_older_than_their_fields_still_read():
    archive = StudyArchive(ARTIFACTS)
    run1 = archive.study("unseen-study-1-2026-11-08")
    case = run1["arms"][0]["rejected"]["per_case"]["unseen-r1"]
    assert case["acting"] is None and case["clean"] is None and case["passed"] is False    # run 1's gate kept no such counts
    assert run1["arms"][0]["model"] == "anthropic:claude-haiku-5-5"                      # named by the trial stages
    repair = archive.study("repair-study-v3-2026-11-14")["repair"]
    assert repair["decision"] == "REPAIRED" and repair["model"] == "anthropic:claude-haiku-5-5"
    assert repair["proposals"][0]["version"] == "rejection-notification-not-required"
    assert {rule["hook"] for rule in repair["proposals"][0]["rules"]} == {"before_final_report", "before_agent_turn"}
    assert "dev-1" in repair["validation"][0]["cases"]
    dev = archive.study("advice-presentation-dev-1-2026-11-15")["development"]
    assert dev["decision"] == "PROCEED" and set(dev["arms"]) == {"E", "Q"}


def test_sealed_files_stores_and_bundles_are_never_read_or_served(tmp_path):
    folder = copy_study(tmp_path)
    for name in ("sealed/cases.json", "E/trials.sqlite3", "E/bundles/validation-unseen-r1-B0.zip", "preflight.sqlite3", "launch.sh"):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text("{not json: reading this would fail")
    archive = StudyArchive(tmp_path)
    assert archive.index()["studies"][0]["problems"] == []
    detail = archive.study(C4)
    assert all(not f["name"].startswith(("sealed", "E/bundles")) and not f["name"].endswith((".sqlite3", ".sh")) for f in detail["files"])
    for name in ("sealed/cases.json", "E/trials.sqlite3", "E/bundles/validation-unseen-r1-B0.zip", "launch.sh", "DECLARATION.sha256",
                 "../" + C4 + "/DECLARATION.json", "/etc/passwd", "E/../sealed/cases.json", ""):
        with pytest.raises(StudyNotFound):
            archive.record_file(C4, name)
    assert archive.record_file(C4, "Q/unseen-study.json")["decision"] == "TRANSFERRED"


@pytest.mark.parametrize("study_id", ["../artifacts", "a/b", ".hidden", "", "UPPER", "x" * 200, "..", "unseen-comparison-4-2026-11-15/E"])
def test_study_names_outside_the_root_are_refused(tmp_path, study_id):
    copy_study(tmp_path)
    with pytest.raises(StudyNotFound):
        StudyArchive(tmp_path).study(study_id)


def test_a_link_out_of_the_root_is_neither_listed_nor_served(tmp_path):
    outside = tmp_path / "outside"
    copy_study(outside)
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(outside / C4, root / C4)
    archive = StudyArchive(root)
    assert archive.index()["studies"] == []
    with pytest.raises(StudyNotFound):
        archive.study(C4)
    inside = copy_study(tmp_path / "root2")
    (inside / "E" / "unseen-study.json").unlink()
    os.symlink(outside / C4 / "E" / "unseen-study.json", inside / "E" / "unseen-study.json")
    with pytest.raises(StudyNotFound):
        StudyArchive(tmp_path / "root2").record_file(C4, "E/unseen-study.json")


def test_a_record_inside_a_study_that_links_out_of_the_root_is_not_read(tmp_path):
    outside = copy_study(tmp_path / "outside")
    root = tmp_path / "root"
    folder = copy_study(root)
    shutil.rmtree(folder / "E")
    os.symlink(outside / "E", folder / "E")                           # a whole arm folder elsewhere
    archive = StudyArchive(root)
    listed = archive.index()["studies"]
    assert [s["id"] for s in listed] == [C4] and listed[0]["problems"] == ["the records could not be read: StudyNotFound"]
    with pytest.raises(StudyNotFound):
        archive.study(C4)
    (folder / "E").unlink()
    (folder / "E").mkdir()
    shutil.copyfile(outside / "E" / "unseen-study.json", folder / "E" / "unseen-study.json")
    (folder / "DECLARATION.json").unlink()
    os.symlink(outside / "DECLARATION.json", folder / "DECLARATION.json")  # a linked declaration is not read either
    with pytest.raises(StudyNotFound):
        archive.study(C4)


def test_a_changed_or_missing_declaration_digest_is_reported(tmp_path):
    folder = copy_study(tmp_path)
    declaration = json.loads((folder / "DECLARATION.json").read_text())
    declaration["question"] = "a different question"
    (folder / "DECLARATION.json").write_text(json.dumps(declaration))
    detail = StudyArchive(tmp_path).study(C4)
    assert detail["declaration"]["verified"] is False
    assert detail["problems"] == ["the declaration does not match its published sha256"]
    (folder / "DECLARATION.sha256").unlink()
    assert StudyArchive(tmp_path).study(C4)["declaration"]["verified"] is None
    (folder / "DECLARATION.json").unlink()
    detail = StudyArchive(tmp_path).study(C4)
    assert detail["declaration"] is None and detail["problems"] == ["no declaration is published with this study"]


def test_an_unreadable_record_is_listed_with_its_problem_and_does_not_hide_the_rest(tmp_path):
    copy_study(tmp_path)
    broken = tmp_path / "repair-study-broken-2026-11-16"
    broken.mkdir()
    (broken / "repair-study.json").write_text("[")
    (tmp_path / "notes").mkdir()                                     # a folder with no record is not a study
    index = StudyArchive(tmp_path).index()
    assert [s["id"] for s in index["studies"]] == ["repair-study-broken-2026-11-16", C4]
    assert index["studies"][0]["problems"] == ["the records could not be read: JSONDecodeError"]
    with pytest.raises(ValueError):
        StudyArchive(tmp_path).study("repair-study-broken-2026-11-16")


def test_a_missing_root_lists_nothing(tmp_path):
    assert StudyArchive(tmp_path / "absent").index()["studies"] == []
