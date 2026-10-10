# ADR: Explicit local native-agent conformance

**Status:** Accepted for the bounded implementation; release verification is recorded separately.
**Date:** October 9, 2026.

## Context

The portable rejected-upgrade scenario can already exercise a user-owned Python
decision callback. That callback supplies decisions under FaultLab's Actor. A
developer using smolagents also needs to test their framework's real execution
loop and their own tool wrappers. Existing built-in smolagents adapters do not
load a user-owned constructor. Changing a registered built-in agent's behavior
without changing its identity would misattribute results.

The existing simulator, public tool contracts, fixed checks, policy interpreter
and historical evidence must retain their meaning. The first integration must
work offline and preserve interrupted attempts. A passing integration test is
not a live-model reliability result or evidence of customer demand.

## Decision

Add a separate, explicit local interface: `build_agent(model, tools)`. The selected
single Python file returns the pinned `smolagents.ToolCallingAgent`. A dependency
worker invokes the real `agent.run`, with fresh framework memory and a fresh
process per episode. FaultLab supplies a declared model double and five public
tool interfaces. The author may wrap the four business tools, but retains their
schemas and the supplied model and final-answer tool.

The parent retains tool admission, fault injection, budgets, authoritative world
observations, policy hooks and scoring. A bounded protocol carries native model
requests, public tool requests and the original final report. The report remains
provisional until the worker returns the same report and exits cleanly. Crashes,
timeouts, malformed protocol and incomplete cleanup cannot become a pass.

Register the new reviewed adapter separately. A CLI-only immutable plan binds the
constructor snapshot, adapter, framework, model double, scenario, policy and
execution limits before creating a world. The ordinary application cannot load
code from a saved registration or incident bundle. Missing or conflicting native
plan markers fail before the legacy execution path can run.

Keep the prior standard-library decision worker unchanged. Reuse its bounded
process supervision where possible, including cancellation during process
creation; the native worker is a separate protocol and dependency scope.
Record constructor source, native source, resolved prompt/configuration, adapter,
model double, interpreter, shared semantics and scenario identities separately.

The sample correction is authored tool code. One unchanged deterministic double
proposes a confirmation even after rejection. With protection disabled, the
proposal reaches the simulator. With protection enabled, the author's wrapper
requires a successful upgrade receipt before forwarding it. The same double
then returns its original report. This isolates the correction from changes to
the model fixture or evaluator.

## Alternatives and tradeoffs

| Option | Benefit | Cost or limitation |
| --- | --- | --- |
| Keep only `decide(request)` | Small, already verified interface | Does not execute a customer's native framework loop |
| Import user code in the parent | Less protocol code | User code shares evaluator state, credentials and process lifetime |
| Explicit native dependency worker | Real framework orchestration with parent-owned evidence and bounded lifetime | More protocol/identity validation; trusted local code only |
| General SDK and hosted isolated workers now | Broader eventual integration surface | Premature before one independently useful workflow; much larger security and operational scope |

Choose the explicit native worker. The process boundary is an engineering and
accidental-access control, not an operating-system security sandbox. Hostile code
requires a separate isolation design. No dependency installation is driven by
candidate code or bundle contents.

## Consequences and verification

This enables an engineer to copy a scenario, select a constructor outside the
checkout, reproduce a violation, correct their tool guard and retain a portable
regression. The exported test requires explicit selection of the candidate.

Acceptance must establish unsafe C3+C5 reproduction in three fresh worlds,
corrected rejection in three, and one healthy completion with exactly one upgrade
and one confirmation. Verify native requests, registered identities, original
reports, actual effects, fresh memory and worker cleanup. Include malformed,
timeout, cancellation and shutdown-crash cases. Verify the portable test from a
separate dependency installation, alongside existing backend/frontend/browser
checks. Preserve the first failures and any corrected attempts separately.

This scope neither reopens repair experiments nor offers the diagnosis guide.
Production-model behavior needs a separately declared model-backed experiment.
Product validation still requires an independent workflow owner to integrate a
relevant incident and use the regression again. Additional frameworks, hosted
execution and multi-tenant infrastructure should follow concrete requirements.

The framework contract was checked against the pinned [agent API](https://huggingface.co/docs/smolagents/v1.26.0/en/reference/agents)
and [tool API](https://huggingface.co/docs/smolagents/v1.26.0/en/reference/tools),
as well as the installed reviewed source. The public APIs support constructor
configuration and native execution; they do not establish FaultLab's correctness.

Release verification completed on October 9: [results, corrected findings and evidence](NATIVE_AGENT_2026-10-09.md).
