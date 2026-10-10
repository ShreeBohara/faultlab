# ADR: a separate incident-evidence contract

Decision date: October 9, 2026. Scope: orders and one persisted synthetic payment fixture.

## Problem

The orders incident showed a rejected upgrade followed by a false confirmation. The
public payment-recovery regression showed both duplicate effects after a lost reply
and false suppression when unrelated intents reuse a fixture key. Final report text
and aggregate counts cannot express the evidence needed to distinguish these failures.

The current optimizer EvidenceBundle intentionally contains public observations and
rejects incomplete episodes. Replacing it with an effect journal would cross its trust
boundary. Existing portable regression bundles also enforce an exact orders inventory.

## Decision

Add `app.incident_evidence` with a bounded versioned envelope, a fixed orders mapper,
a fixed payment mapper, data-only bundle validation and explicit installed-fixture replay.
Do not modify the existing orders wire model, simulator, scorer or promotion path.

Intents are declared independently of attempts. Attempts retain literal provider keys
and actual request bytes/digests when known. Effects come from persisted provider facts;
observations and reports retain what the caller received and claimed, even when wrong.
An overly broad identity, duplicate effects or wrong attribution remains representable.
Structural integrity is distinct from task correctness and completeness.

Each mapper admits a closed source-fact format, validates internal source relationships,
and creates the common projection. Inspection reconstructs that projection with installed
code and compares it with the exported envelope. It never imports bundled code or runs
a subject. The bundle is two bounded JSON files, optionally in a flat ZIP, with strict
inventory, type, size, hash, duplicate-key and source-reference checks.

Orders maps existing journals, tool calls, observations, curated snapshots, fixed check
results and original native reports. Separate clocks remain separate. Missing authority
is unknown, not zero. A late native failure preserves its provisional original report as
WITHHELD. Unsupported subject provenance cannot be promoted into a complete execution.

The payment fixture persists intents, attempts, key/payload bindings, effects, receipts,
observations, fault witnesses and original report text in SQLite. Key binding and commit
occur in one transaction. The fixture deliberately does not make intent/invoice unique
in the effect table: a new key can cause a duplicate that the checker must detect.
Reply loss is a deterministic event after commit, not a network-timing claim.

## Compatibility

The schema is exported under `docs/`, outside the legacy `contracts/*.schema.json`
digest. Common bundles sit outside old bundle inventories. Existing application API,
dashboard campaign types and native/local constructor protocols remain unchanged.
Application runtime identity changes; orders contract/service/scorer/interpreter and
dependency identities must remain the same in release verification.

The first release supports exact installed mapper compatibility. Source hashes and
versions travel with evidence; a mapping change must not silently reinterpret an old
bundle. Inspection does not prove authenticity against wholly fabricated source facts.
Orders retains the existing full application runtime hash. The payment runtime
identity is deliberately narrower: exact payment module, Python implementation/version,
SQLite version and common JSON schema. It does not pin every common helper or Pydantic
version. Complete source reprojection and equality remain required at import. A future
claim of complete transitive runtime identity would require additional pins.
No authoritative records are added to optimizer/model inputs.

## Explicit limits

CLI execution selects installed synthetic candidates. Export supports scripted and
native-user-agent orders records, but common-bundle replay does not execute arbitrary
agent source. The existing native bundle remains the path for testing a constructor.
The public LangGraph pack stays preserved as a separate attributed experiment.

Process-death recovery, concurrent payment service proofs, distributed operation identity,
other frameworks, hosting, customer adoption and generated policies remain outside scope.
A real workflow owner should guide the next abstraction; this feature is engineering
evidence, not evidence of demand or willingness to pay.
