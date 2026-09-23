# Phase 3 B2: one controlled Mechanic-model follow-up

Declared September 20, 2026 after B closed and before any B2 model requests. B remains a completed `NO_CHANGE` experiment, not a discarded warm-up.

## Evidence for this change

B completed all six controls and both six-trial source comparisons: 18 valid trials, 18 verified Weave episode traces, 129 model requests. Healthy controls completed 3/3. Neither generated policy completed any of its three source trials; each paired baseline also completed 0/3. Both policies only waited and read status. Neither retried the original notification write, which the original observations showed had been rejected before acceptance. The runtime contract explicitly explains that a status read does not submit a confirmation. The second proposal received all 12 preceding verified control/source episodes and the first candidate's zero-completion assessment, yet described it as showing potential. That explanation is preserved as an unsupported model claim.

Manual trace review and independent review found that the interpreter executed those rules as written. There is no evidence here requiring a capability change, relaxed checker, or rewritten report. The next specific question is whether a different available Mechanic can use the same evidence and instruction contract better.

## Fixed change and stopping rule

- Change only the Mechanic role from `deepseek-ai/DeepSeek-V3.1` to `deepseek-ai/DeepSeek-V4-Pro-0813`, using its existing provider-specific settings (thinking disabled) and already configured matching prices. This model is already running as the Explorer.
- Keep the Actor, Explorer, prompt text, runtime source, tools, interpreter, original checks, episode limits, public manifest, pairing and exact acceptance rules unchanged. Record the new configuration hash and the necessarily changed Mechanic model/settings/pricing fields before dispatch. The runtime hash stays unchanged.
- Use one new campaign and study. Repeat the same three failure controls and three healthy controls before proposing. Retain the same maximum of two proposal slots, four physical Mechanic requests and 60 trial slots / 484 requests overall.
- B2 receives its own verified source/control evidence. B's candidates are not inserted as advice, no human-authored rule is supplied, and validation remains excluded from optimization. B had no validation trials because no candidate qualified.
- Preserve B and B2 separately and compare their complete outcomes. Do not pool selectively. This is a sequential development comparison, not a randomized model benchmark or a claim that the model switch caused a general reliability gain.
- Stop after this alternative-model study whatever the result. No third model, extra proposal, lucky retry or validation-driven retuning in this round. An infrastructure failure is retained as incomplete.

## Continued accounting

Phase 2 charge bound: $18.92256. Phase 3 A: $1.50642. Phase 3 B: $2.69610. Cumulative bound before B2: **$23.12508**, leaving **$976.87492** of the same $1,000 authorization. B2's $400 campaign allocation is inside that remaining allowance. Full declared requests and protected reserves must pass admission. Actual billed dollars remain unavailable; these figures are conservative request bounds.

Manual verification and preservation requirements from [the original protocol](PHASE3_EXPERIMENT.md) still apply. A completion-study improvement never activates a policy or satisfies the original invariant-repair promotion/final-audit/transfer gates.
