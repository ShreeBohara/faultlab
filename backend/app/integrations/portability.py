"""Predeclared, untuned six-case external policy-transfer measurements."""
from __future__ import annotations

import asyncio
from collections import Counter

from app.contracts.models import FaultSpec, PortabilityResult, Usage, content_hash, new_id
from app.integrations.regression_runner import add_usage


class PortabilityStudy:
    def __init__(self, store, registry):
        self.store, self.registry = store, registry

    def _freeze(self, external_freeze, registration, target_configuration, baseline_policy, accepted_policy):
        value = external_freeze
        if value.get("schema_version") != "faultlab-external-freeze/v1" or value.get("status") != "FROZEN" or value.get("freeze_hash") != content_hash({k: v for k, v in value.items() if k != "freeze_hash"}):
            raise ValueError("Verified external experiment freeze required")
        manifest = value["manifest"]
        if manifest.get("manifest_hash") != content_hash({k: v for k, v in manifest.items() if k != "manifest_hash"}):
            raise ValueError("External manifest digest mismatch")
        if manifest.get("scope") != "orders.upgrade_then_confirm/v1" or manifest.get("horizon_ticks") != 5 or manifest.get("http_timeout_seconds") != 1.0 or manifest.get("purpose") != "portability" or manifest.get("partition") != "final_audit" or manifest.get("trials_per_case") != 3 or manifest.get("arms") != ["B0", "L"] or not manifest.get("sealed") or not manifest.get("no_tuning_from_results") or manifest.get("trial_order") != "case_then_trial_alternating_arms":
            raise ValueError("Unsupported external study design")
        cases = manifest.get("cases", [])
        if len(cases) != 6 or len({case["case_id"] for case in cases}) != 6:
            raise ValueError("Six unique frozen external cases required")
        from app.referee.manifests import load_manifest
        if cases != load_manifest("portability")["cases"]:
            raise ValueError("External cases differ from predeclared sealed definitions")
        identity = {"status": "FROZEN", "registration_id": registration.registration_id, "source_hash": registration.source_hash,
            "adapter_hash": registration.adapter_hash, "configuration_hash": registration.configuration_hash}
        if manifest.get("external_identity") != identity or value.get("registration") != registration.model_dump(mode="json"):
            raise ValueError("External registration identity changed after freeze")
        if baseline_policy.decision != "BASELINE" or baseline_policy.content is None or baseline_policy.content.rules or content_hash(baseline_policy.content) != baseline_policy.policy_hash:
            raise ValueError("External B0 must use the immutable empty baseline")
        if accepted_policy.decision != "ACCEPTED" or accepted_policy.content is None or content_hash(accepted_policy.content) != accepted_policy.policy_hash or value.get("policy_hash") != accepted_policy.policy_hash:
            raise ValueError("External L must transfer the exact frozen accepted policy")
        if content_hash(target_configuration) != registration.configuration_hash:
            raise ValueError("Target settings changed after freeze")
        return manifest

    async def run(self, *, external_freeze, source_registration_id, target_registration_id,
        target_configuration, baseline_policy, accepted_policy, run_fresh, explicit_live,
        stop=None, policy_source="transferred_unchanged", source_mode="live"):
        if explicit_live is not True:
            raise ValueError("External sandbox study requires explicit live action")
        if policy_source != "transferred_unchanged":
            raise ValueError("A new target learning campaign requires separately declared lineage and validation cases")
        target = self.registry.verify(target_registration_id, target_configuration)
        source = self.registry.get(source_registration_id)
        if target.provenance_class != "external":
            raise ValueError("Internal smoke cannot satisfy the independent external study")
        if (source.contract_hash, source.capability_hash, source.oracle_hash) != (target.contract_hash, target.capability_hash, target.oracle_hash):
            raise ValueError("Source and target task/oracle semantics differ")
        manifest = self._freeze(external_freeze, target, target_configuration, baseline_policy, accepted_policy)
        freeze_id = external_freeze["freeze_hash"]
        # A declared study cannot be silently repeated after unfavorable results.
        if self.store.get_record("portability_freezes", freeze_id):
            raise ValueError("This frozen external study already has an execution")
        result = PortabilityResult(portability_id=new_id("portability"), source_registration_id=source.registration_id,
            target_registration_id=target.registration_id, provenance_class="external", policy_source=policy_source,
            policy_hash=accepted_policy.policy_hash, manifest_hash=manifest["manifest_hash"], target_configuration_hash=target.configuration_hash,
            trial_pairs=[], compatibility_failures=[], status="PENDING", limitations=["Only this reviewed native agent and six frozen synthetic cases are measured; no general arbitrary-agent claim."])
        self.store.put_record("portability_freezes", freeze_id, {"portability_id": result.portability_id, "freeze": external_freeze}, immutable=True)
        self.store.put_record("portability", result.portability_id, result)
        stop = stop or (lambda: False)
        attempts, seen_episodes, seen_worlds = [], set(), set()
        usage = Usage()
        counters = {arm: Counter() for arm in ("B0", "L")}
        halt = False
        try:
            for case_index, case in enumerate(manifest["cases"]):
                if halt: break
                recipe = FaultSpec.model_validate_json(__import__("json").dumps(case["fault_spec"]))
                for trial_index in range(3):
                    if stop():
                        halt = True
                        result.limitations.append("Study interrupted; unfinished pairs remain incomplete.")
                        break
                    pair, pair_valid = {}, True
                    order = ("B0", "L") if (case_index * 3 + trial_index) % 2 == 0 else ("L", "B0")
                    for arm in order:
                        if stop():
                            halt = True
                            break
                        self.registry.verify(target_registration_id, target_configuration)
                        policy = baseline_policy if arm == "B0" else accepted_policy
                        trial = await run_fresh(case, target, policy, trial_index, arm)
                        episode = self.store.get_record("episodes", trial.episode_id)
                        valid = (trial.episode_id not in seen_episodes and trial.world_id not in seen_worlds
                            and trial.scenario_hash == content_hash(recipe) and trial.policy_hash == policy.policy_hash
                            and trial.arm == arm and trial.trial_index == trial_index and trial.lifecycle == "COMPLETED"
                            and trial.outcome not in (None, "LAB_ERROR", "INTERRUPTED")
                            and (not recipe.primitives or trial.fault_triggered)
                            and episode is not None and episode.get("configuration_hash") == target.configuration_hash
                            and episode.get("agent_registration_id") == target_registration_id
                            and episode.get("experiment_purpose") == "portability" and episode.get("split") == "final_audit"
                            and episode.get("source_mode") == source_mode)
                        attempts.append({"case_id": case["case_id"], "trial_index": trial_index, "arm": arm, "trial": trial, "valid": valid})
                        seen_episodes.add(trial.episode_id); seen_worlds.add(trial.world_id)
                        usage = add_usage(usage, trial.usage)
                        counters[arm]["attempted"] += 1
                        counters[arm]["valid"] += int(valid)
                        counters[arm]["fault_triggered"] += int(trial.fault_triggered)
                        counters[arm][trial.outcome or "NOT_RUN"] += 1
                        pair[arm] = trial.episode_id
                        pair_valid &= valid
                        self.store.put_record("portability_attempts", result.portability_id, {"source_mode": source_mode, "attempts": attempts})
                    if len(pair) == 2:
                        result.trial_pairs.append((pair["B0"], pair["L"]))
                    if len(pair) != 2 or not pair_valid:
                        halt = True
                        result.limitations.append("An invalid, untriggered or interrupted pair ended the study; all attempts retained without favorable reruns.")
                    self.store.put_record("portability", result.portability_id, result)
                    if halt: break
            result.status = "COMPLETED" if len(result.trial_pairs) == 18 and not halt else "INCOMPLETE"
            if source_mode != "live":
                result.status = "INCOMPLETE"
                result.limitations.append("Offline fixture orchestration is not fresh provider-backed external acceptance.")
        except asyncio.CancelledError:
            result.status = "INCOMPLETE"
            result.limitations.append("Study cancelled; no automatic rerun.")
        except Exception:
            result.status = "INCOMPLETE"
            result.limitations.append("Execution or compatibility failed after start; prior attempts retained.")
        self.store.put_record("portability", result.portability_id, result)
        self.store.put_record("portability_metrics", result.portability_id, {
            "required_pairs": 18, "required_trials": 36, "attempted": len(attempts), "pair_count": len(result.trial_pairs),
            "by_arm": {arm: dict(counts) for arm, counts in counters.items()}, "usage": usage,
            "source_mode": source_mode, "policy_source": policy_source, "policy_hash": accepted_policy.policy_hash,
            "target_configuration_hash": target.configuration_hash, "fresh_external_acceptance": result.status == "COMPLETED" and source_mode == "live",
        }, immutable=True)
        return result
