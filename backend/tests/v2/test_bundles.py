"""Envelope bundles: data only, every digest checked on the way in and the way out."""
import json
import zipfile

import pytest

from faultlab.core import IntegrityError, content_hash
from faultlab.evidence.bundles import BUNDLE_VERSION, comparable_identities, read_bundle, write_bundle
from faultlab.evidence.legacy import LegacyStore, load_episode_facts, project_episode
from test_legacy_projection import write_legacy_store


def envelopes_from_fixture(tmp_path):
    path = tmp_path / "lab.sqlite3"
    write_legacy_store(path, episode_id="episode-1")
    write_legacy_store(path, episode_id="episode-2", lifecycle="INTERRUPTED", with_verdict=False)
    with LegacyStore(path) as store:
        return [project_episode(load_episode_facts(store, episode_id), store_identity=store.identity()) for episode_id in store.episode_ids()]


def test_bundle_round_trip_keeps_every_envelope_and_its_identity(tmp_path):
    envelopes = envelopes_from_fixture(tmp_path)
    bundle = tmp_path / "incident.zip"
    manifest = write_bundle(envelopes, bundle, name="fixture incident", notes=["two episodes"])
    assert manifest.bundle_version == BUNDLE_VERSION and len(manifest.entries) == 2
    assert manifest.manifest_digest == content_hash({k: v for k, v in manifest.model_dump(mode="json").items() if k != "manifest_digest"})
    read_manifest, read_envelopes = read_bundle(bundle)
    assert read_manifest == manifest and read_envelopes == envelopes
    assert comparable_identities(read_envelopes) == {content_hash(envelopes[0].outcome.identity): 2}
    with zipfile.ZipFile(bundle) as archive:
        assert set(archive.namelist()) == {"manifest.json", "envelopes/episode-1.json", "envelopes/episode-2.json"}
        assert all(not name.endswith(".py") for name in archive.namelist())


def _rewrite(bundle, tmp_path, mutate):
    out = tmp_path / "tampered.zip"
    with zipfile.ZipFile(bundle) as source, zipfile.ZipFile(out, "w") as target:
        for name in source.namelist():
            data = source.read(name)
            target.writestr(name, mutate(name, data))
    return out


@pytest.mark.parametrize("case", ["envelope_bytes", "manifest_entry", "manifest_digest", "extra_file", "missing_file"])
def test_any_change_to_a_bundle_is_refused(tmp_path, case):
    envelopes = envelopes_from_fixture(tmp_path)
    bundle = tmp_path / "incident.zip"
    write_bundle(envelopes, bundle, name="fixture incident")

    def mutate(name, data):
        if case == "envelope_bytes" and name == "envelopes/episode-1.json":
            body = json.loads(data)
            body["outcome"]["task"] = "COMPLETED"
            return json.dumps(body).encode()
        if case == "manifest_entry" and name == "manifest.json":
            body = json.loads(data)
            body["entries"][0]["task"] = "COMPLETED"
            return json.dumps(body).encode()
        if case == "manifest_digest" and name == "manifest.json":
            body = json.loads(data)
            body["manifest_digest"] = "0" * 64
            return json.dumps(body).encode()
        return data
    tampered = _rewrite(bundle, tmp_path, mutate)
    if case == "extra_file":
        with zipfile.ZipFile(tampered, "a") as archive:
            archive.writestr("envelopes/extra.json", "{}")
    if case == "missing_file":
        kept = tmp_path / "missing.zip"
        with zipfile.ZipFile(tampered) as source, zipfile.ZipFile(kept, "w") as target:
            for name in source.namelist():
                if name != "envelopes/episode-2.json":
                    target.writestr(name, source.read(name))
        tampered = kept
    with pytest.raises(IntegrityError):
        read_bundle(tampered)


def test_empty_duplicate_and_unreadable_bundles_are_refused(tmp_path):
    envelopes = envelopes_from_fixture(tmp_path)
    with pytest.raises(IntegrityError, match="at least one"):
        write_bundle([], tmp_path / "empty.zip", name="x")
    with pytest.raises(IntegrityError, match="Duplicate attempt"):
        write_bundle([envelopes[0], envelopes[0]], tmp_path / "dup.zip", name="x")
    (tmp_path / "junk.zip").write_bytes(b"not a zip")
    with pytest.raises(IntegrityError, match="Unreadable bundle"):
        read_bundle(tmp_path / "junk.zip")
