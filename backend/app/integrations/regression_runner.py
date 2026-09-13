"""Fixed data validator and explicit fresh runner; bundle code is never executed."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import stat

from app.contracts.models import (RegressionBundle, RegressionExecution, PolicyVersion,
    FaultSpec, TrialResult, EpisodeBudget, Usage, Counterexample, DiagnosticResult,
    ChallengeResult, ReductionResult, canonical_json, content_hash, new_id)
from app.integrations.registry import ROOT

INVENTORY = frozenset({"policy.json", "configuration.json", "source-recipe.json", "retained-recipe.json", "trials.json", "lineage.json", "harness/test_regression.py"})
TRUSTED_TEMPLATE = Path(__file__).with_name("templates") / "test_regression.py"
HARNESS_VERSION = "faultlab-runner-v1"
PROFILE_ID = "sandbox-v1"
MAX_FILE = 2 * 1024 * 1024
MAX_BUNDLE = 8 * 1024 * 1024


def _json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key rejected")
            result[key] = value
        return result
    return json.loads(content, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("Nonfinite JSON rejected")))


def _read(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        details = os.fstat(fd)
        if not stat.S_ISREG(details.st_mode) or details.st_size > MAX_FILE:
            raise ValueError("Bundle file type/size rejected")
        with os.fdopen(fd, "rb", closefd=False) as source:
            content = source.read(MAX_FILE + 1)
        if len(content) > MAX_FILE:
            raise ValueError("Bundle file too large")
        return content
    finally:
        os.close(fd)


@dataclass(frozen=True)
class InspectedBundle:
    bundle: RegressionBundle
    policy: PolicyVersion
    source_configuration: dict
    trial_results: list[TrialResult]


@dataclass(frozen=True)
class ValidationResult(InspectedBundle):
    target_configuration: dict
    registration: object
    execution: RegressionExecution


def inspect_bundle(bundle_dir):
    """Offline structural and source-integrity validation, without a registry."""
    directory = Path(bundle_dir).absolute()
    if any(p.is_symlink() for p in (directory, *directory.parents)) or not directory.is_dir():
        raise ValueError("Symlink or missing bundle directory rejected")
    actual = set()
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlink bundle entry rejected")
        if path.is_file():
            actual.add(path.relative_to(directory).as_posix())
        elif path.is_dir() and path.relative_to(directory).as_posix() != "harness":
            raise ValueError("Unknown bundle directory rejected")
        elif not path.is_dir():
            raise ValueError("Nonregular bundle entry rejected")
    if actual != INVENTORY | {"manifest.json"}:
        raise ValueError("Exact reviewed bundle inventory required")
    raw_manifest = _json(_read(directory / "manifest.json"))
    bundle = RegressionBundle.model_validate_json(canonical_json(raw_manifest))
    entries = {entry.path: entry for entry in bundle.files}
    if set(entries) != INVENTORY or len(entries) != len(bundle.files):
        raise ValueError("Unknown, duplicate or missing inventory entry")
    if bundle.manifest_hash != content_hash({k: v for k, v in bundle.model_dump(mode="json").items() if k != "manifest_hash"}):
        raise ValueError("Manifest digest mismatch")
    schema_hash = sha256((ROOT / "contracts/RegressionBundle.schema.json").read_bytes()).hexdigest()
    trusted_source = TRUSTED_TEMPLATE.read_bytes()
    if bundle.schema_hash != schema_hash or bundle.harness_version != HARNESS_VERSION or bundle.harness_hash != sha256(trusted_source).hexdigest():
        raise ValueError("Untrusted schema or runner version/digest")
    if bundle.execution_profile_id != PROFILE_ID or bundle.caps != EpisodeBudget():
        raise ValueError("Unsupported execution profile or caps")
    payloads = {}
    total = 0
    for name, entry in entries.items():
        content = _read(directory / name)
        total += len(content)
        if len(content) != entry.size_bytes or sha256(content).hexdigest() != entry.sha256:
            raise ValueError("Bundle file digest/size mismatch")
        if total > MAX_BUNDLE:
            raise ValueError("Bundle exceeds total size bound")
        payloads[name] = content
    if payloads["harness/test_regression.py"] != trusted_source:
        raise ValueError("Runner bytes are not the reviewed installed template")
    policy = PolicyVersion.model_validate_json(canonical_json(_json(payloads["policy.json"])))
    if policy.content is None or content_hash(policy.content) != bundle.policy_hash or policy.policy_hash != bundle.policy_hash:
        raise ValueError("Transferred policy content digest mismatch")
    configuration = _json(payloads["configuration.json"])
    if not isinstance(configuration, dict) or content_hash(configuration) != bundle.configuration_hash:
        raise ValueError("Historical source configuration digest mismatch")
    for field in ("contract_hash", "capability_hash", "scorer_hash", "interpreter_hash", "dependency_lock_hash"):
        if configuration.get(field) != getattr(bundle, field):
            raise ValueError("Historical source identity does not match manifest")
    if configuration.get("episode_budget") != bundle.caps.model_dump(mode="json"):
        raise ValueError("Source budget mismatch")
    from app.integrations.registry import _configuration
    _configuration(configuration)
    source = FaultSpec.model_validate_json(canonical_json(_json(payloads["source-recipe.json"])))
    retained_raw = _json(payloads["retained-recipe.json"])
    retained = FaultSpec.model_validate_json(canonical_json(retained_raw)) if retained_raw is not None else None
    if source != bundle.source_recipe or retained != bundle.retained_recipe:
        raise ValueError("Source/retained recipe mismatch")
    raw_trials = _json(payloads["trials.json"])
    if not isinstance(raw_trials, list) or len(raw_trials) > 200:
        raise ValueError("Invalid trial inventory")
    trials = [TrialResult.model_validate_json(canonical_json(value)) for value in raw_trials]
    if trials != bundle.trial_results:
        raise ValueError("Historical trial inventory mismatch")
    lineage = _json(payloads["lineage.json"])
    classes = {"counterexample": Counterexample, "diagnostic": DiagnosticResult, "challenge": ChallengeResult, "reduction": ReductionResult}
    if not isinstance(lineage, dict) or set(lineage) != set(classes) or lineage["counterexample"] is None:
        raise ValueError("Unsupported lineage fields")
    for field, cls in classes.items():
        if lineage[field] is not None:
            cls.model_validate_json(canonical_json(lineage[field]))
    return InspectedBundle(bundle, policy, configuration, trials)


def add_usage(total, usage):
    known = total.cost_dollars is not None and usage.cost_dollars is not None
    values = {key: getattr(total, key) + getattr(usage, key) for key in Usage.model_fields if key != "cost_dollars"}
    values["cost_dollars"] = total.cost_dollars + usage.cost_dollars if known else None
    return Usage(**values)


class RegressionRunner:
    def __init__(self, store, registry):
        self.store, self.registry = store, registry

    def _check(self, bundle_dir, target_configuration, registration_id):
        inspected = inspect_bundle(bundle_dir)
        registration = self.registry.verify(registration_id, target_configuration)
        # Target native prompt/model/source may differ. Shared service, oracle,
        # interpreter, hooks and task contract must have unchanged semantics.
        for field in ("contract_hash", "capability_hash", "scorer_hash", "interpreter_hash"):
            if target_configuration[field] != getattr(inspected.bundle, field):
                raise ValueError("Target task/oracle/policy semantics are incompatible")
        return inspected, registration

    def _record(self, inspected, registration, mode, *, explicit=False, execution_id=None):
        record = RegressionExecution(execution_id=execution_id or new_id("execution"), bundle_id=inspected.bundle.bundle_id, manifest_hash=inspected.bundle.manifest_hash,
            registration_id=registration.registration_id, profile_id=PROFILE_ID, mode=mode, explicit_action=explicit,
            policy_hash=inspected.bundle.policy_hash, configuration_hash=registration.configuration_hash,
            declared_budget=inspected.bundle.caps, usage=Usage(), episode_ids=[], world_ids=[], status="PENDING" if explicit else "COMPLETED")
        self.store.put_record("regression_executions", record.execution_id, record)
        return record

    def validate(self, bundle_dir, target_configuration, registration_id):
        inspected, registration = self._check(bundle_dir, target_configuration, registration_id)
        record = self._record(inspected, registration, "VALIDATE_ONLY")
        return ValidationResult(inspected.bundle, inspected.policy, inspected.source_configuration, inspected.trial_results, target_configuration, registration, record)

    def playback(self, bundle_dir, target_configuration, registration_id):
        inspected, registration = self._check(bundle_dir, target_configuration, registration_id)
        record = self._record(inspected, registration, "RECORDED_PLAYBACK")
        self.store.put_record("regression_playback", record.execution_id, {"historical_trials": inspected.trial_results, "fresh": False}, immutable=True)
        return record

    async def execute(self, bundle_dir, target_configuration, registration_id, *, explicit_live, profile_id, run_fresh, policy_version=None, execution_id=None):
        if explicit_live is not True or profile_id != PROFILE_ID:
            raise ValueError("Fresh sandbox execution requires explicit action and the reviewed profile")
        inspected, registration = self._check(bundle_dir, target_configuration, registration_id)
        policy = policy_version or inspected.policy
        if policy.policy_hash != inspected.bundle.policy_hash or content_hash(policy.content) != inspected.bundle.policy_hash:
            raise ValueError("Fresh transfer must use the exact bundled policy")
        if policy.decision not in ("BASELINE", "ACCEPTED"):
            raise ValueError("Fresh execution requires an immutable baseline or accepted policy")
        if execution_id is not None:
            previous = self.store.get_record("regression_executions", execution_id)
            if previous is not None and (previous.get("status") != "PENDING" or previous.get("bundle_id") != inspected.bundle.bundle_id or previous.get("registration_id") != registration_id or previous.get("manifest_hash") != inspected.bundle.manifest_hash):
                raise ValueError("Execution identity already used or mismatched")
        record = self._record(inspected, registration, "FRESH_SANDBOX", explicit=True, execution_id=execution_id)
        record.status = "RUNNING"
        self.store.put_record("regression_executions", record.execution_id, record)
        recipe = inspected.bundle.retained_recipe or inspected.bundle.source_recipe
        attempts = []
        existing_episodes = {row.get("episode_id") for row in self.store.list_records("episodes")}
        existing_worlds = {row.get("world_id") for row in self.store.list_records("episodes")}
        try:
            for index in range(3):
                self.registry.verify(registration_id, target_configuration)
                trial = await run_fresh(recipe, registration, policy, index, fixture_id=inspected.bundle.fixture_id)
                persisted = self.store.get_record("episodes", trial.episode_id)
                private_inputs = self.store.get_record("private_episode_inputs", trial.episode_id)
                attempts.append(trial)
                record.usage = add_usage(record.usage, trial.usage)
                self.store.put_record("regression_attempts", record.execution_id, {"trials": attempts})
                valid_identity = trial.episode_id not in record.episode_ids and trial.world_id not in record.world_ids and trial.episode_id not in {t.episode_id for t in inspected.trial_results} and trial.world_id not in {t.world_id for t in inspected.trial_results} and trial.episode_id not in existing_episodes and trial.world_id not in existing_worlds
                valid_persisted = persisted is not None and all(persisted.get(key) == expected for key, expected in {
                    "episode_id": trial.episode_id, "world_id": trial.world_id, "configuration_hash": registration.configuration_hash,
                    "agent_registration_id": registration_id, "policy_hash": policy.policy_hash}.items())
                valid_persisted = valid_persisted and private_inputs is not None and private_inputs.get("fixture_id") == inspected.bundle.fixture_id
                record.episode_ids.append(trial.episode_id)
                record.world_ids.append(trial.world_id)
                self.store.put_record("regression_executions", record.execution_id, record)
                if not valid_identity or not valid_persisted or trial.policy_hash != record.policy_hash or trial.scenario_hash != content_hash(recipe) or trial.trial_index != index:
                    record.stop_reason = "Fresh trial identity or immutable configuration mismatch"
                    break
                if trial.lifecycle != "COMPLETED" or trial.outcome in (None, "LAB_ERROR", "INTERRUPTED") or (recipe.primitives and not trial.fault_triggered):
                    record.stop_reason = "Fresh trial invalid, interrupted or untriggered; all attempts retained"
                    break
            record.status = "COMPLETED" if len(attempts) == 3 and not record.stop_reason else "INCOMPLETE"
        except asyncio.CancelledError:
            record.status = "INCOMPLETE"
            record.stop_reason = "Execution interrupted; no automatic rerun"
        except Exception:
            record.status = "INCOMPLETE"
            record.stop_reason = "Execution failed; no automatic rerun"
        self.store.put_record("regression_executions", record.execution_id, record)
        source_modes = sorted({(self.store.get_record("episodes", trial.episode_id) or {}).get("source_mode", "unknown") for trial in attempts})
        self.store.put_record("regression_assertions", record.execution_id, {
            "target_invariant": inspected.bundle.target_invariant,
            "required_trials": 3, "attempted": len(attempts),
            "target_failures": sum(inspected.bundle.target_invariant in trial.failed_checks for trial in attempts),
            "reproduced": record.status == "COMPLETED" and all(inspected.bundle.target_invariant in trial.failed_checks for trial in attempts),
            "fresh": True,
            "source_modes": source_modes,
            "provider_backed": source_modes == ["live"],
        }, immutable=True)
        return record
