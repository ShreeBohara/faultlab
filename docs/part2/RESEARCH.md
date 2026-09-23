# Research for FaultLab Part 2

Reviewed September 20, 2026. These are selected primary papers, official documentation and first-party project materials relevant to the next release. This is a focused technical and product review, not a claim to have exhaustively searched the internet or independently reproduced competitors' results.

The [plan](PLAN.md) is our recommendation. The [current-state report](CURRENT_STATE.md) is evidence from our implementation. Recommendations below are inferences from the sources, not claims made by those sources about FaultLab.

## What the research changes

1. **Fault injection alone is not a new product category.** Existing research and tools cover operational faults, contracts, replay and CI. We need to demonstrate a particularly useful and credible repair workflow.
2. **A single success rate is insufficient.** Repetition, meaningful state errors, healthy behavior, recovery and overhead need separate measurements.
3. **The environment and checker are part of the product.** A generic proxy or MCP connection cannot infer whether a booking, order or job actually happened correctly.
4. **Reuse existing evaluation and optimization work where it helps.** Keep FaultLab's state-aware experiments and bounded repair decisions; avoid rebuilding an entire evaluation platform.
5. **CoreWeave is useful as real execution infrastructure, not just a logo.** Isolated experiments and an optional later training comparison are meaningful uses of the stack.

## Papers and evaluation methods

### 1. τ-bench and τ²-bench

Sources: [τ-bench paper, June 2024](https://arxiv.org/html/2406.12045v1), [τ²-bench paper, June 2025](https://arxiv.org/abs/2506.07982), [official repository](https://github.com/sierra-research/tau2-bench).

These benchmarks evaluate agents against domain policies and state changes. τ-bench's repeated-success measure, `pass^k`, asks whether the agent succeeds consistently across k trials; it is different from getting at least one success. τ² extends the setting to a shared environment affected by both user and agent.

**Use:** adopt repeated state-based evaluation and investigate a small external task subset. Preserve the native evaluator and pin repository/data versions. A custom operational-fault extension should be reported separately from the original benchmark. Do not imply that our order simulator already implements τ-bench.

### 2. Towards a Science of AI Agent Reliability

Source: [paper, February 2026; revised June 2, 2026; ICML 2026](https://arxiv.org/abs/2602.16666).

The paper separates reliability into consistency, robustness, predictability and safety, using twelve metrics. Its central observation is that aggregate capability scores can conceal operational weaknesses.

**Use:** publish a compact reliability profile rather than a single scoreboard number: useful completion, repeatability, harmful effects, honest uncertainty, failure categories and overhead. Describe the tested agent scaffold and scenario population. Temperature zero does not make repeated hosted model calls deterministic.

### 3. AgentChaos

Source: [paper, August 7, 2026; lists ASE 2026 acceptance](https://arxiv.org/abs/2608.06790).

AgentChaos intercepts the HTTP layer around model responses, injecting crash, omission and value faults. It records whether the requested fault was actually triggered, which prevents unreachable faults from being counted as a passed stress test.

**Use:** preserve our trigger ledger and distinguish model-response failures from tool-service failures and state-transition faults. FaultLab's current business-state semantics are different from modifying an LLM response, but the trigger-measurement lesson applies directly. Do not claim runtime agent fault injection is our invention.

### 4. AgentRx

Source: [Microsoft Research release, March 12, 2026](https://www.microsoft.com/en-us/research/blog/systematic-debugging-for-ai-agents-introducing-the-agentrx-framework/).

AgentRx combines executable constraints derived from schemas/policies with evidence-based diagnosis. The release describes a benchmark of 115 annotated failed trajectories and a nine-category failure taxonomy.

**Use:** add a structured failure diagnosis and evaluate it independently from whether a repair worked. Keep the observed sequence, relevant rule, and supporting evidence together. A plausible explanation is not causal proof; our controlled intervention remains useful. Model-generated diagnostic constraints must not silently replace the fixed business oracle.

### 5. GEPA

Sources: [paper, July 2025; revised February 2026](https://arxiv.org/abs/2507.19457), [official adapter guide](https://gepa-ai.github.io/gepa/guides/adapters/).

GEPA uses reflective feedback from executions to evolve text components. Its adapter interface separates candidate evaluation from preparing reflective feedback and supports objective-aware optimization.

**Use:** run one controlled comparison against the corrected Mechanic. Feed verified development evidence and retain a candidate history. Keep policy parsing, permitted actions, budgets and final scoring fixed. Do not assume a paper's gains transfer to our task. GEPA is a proposal/search option; it cannot replace an independent acceptance gate.

### 6. AgentDojo

Source: [paper, v3 November 2024](https://arxiv.org/html/2406.13352v3).

AgentDojo evaluates prompt-injection attacks in dynamic tool-using tasks, distinguishing adversary success from legitimate task utility.

**Use:** borrow that separation if we later add security attacks. A forged instruction in a tool result is a different threat model from a slow API or lost acknowledgement. Keep prompt injection as a separately labeled task/fault family, with its own rules and results, rather than quietly mixing it into the current operational-fault experiment.

### 7. AgentChaosBench

Source: [When Agentic Executions Fail: Detecting and Localizing Runtime Faults from Telemetry, arXiv v1, August 2026](https://arxiv.org/abs/2608.14680).

The paper presents 275 sanitized traces: 250 fault executions and 25 clean controls across five applications. It studies fault detection/localization from telemetry while withholding fault labels from diagnosis.

**Use:** a future FaultLab diagnosis benchmark should include clean/fault pairs and a private fault-truth label. Score diagnosis against that truth without putting the answer in the diagnosing model's input. This is emerging research, not evidence that a universal diagnostic method already exists.

## Tools to reuse or compare

### 8. Inspect

Sources: [official framework](https://inspect.aisi.org.uk/), [sandbox extension contract](https://inspect.aisi.org.uk/extensions-sandboxes.html). Current documentation reviewed; no dependency version selected in this audit.

Inspect provides evaluation tasks, solvers, scorers, logs and sandbox interfaces. Its sandbox documentation calls out retry behavior around non-idempotent execution.

**Use:** consider a task/scorer wrapper or exporter if a pilot team already uses Inspect. Make retry semantics explicit when duplicate side effects are the behavior under test. Do not migrate the working application merely to standardize its framework name.

### 9. Harbor

Sources: [task format](https://docs.harborframework.com/core-concepts/tasks/overview), [separate verifier](https://docs.harborframework.com/core-concepts/tasks/separate-verifier), [ATIF trajectory format](https://docs.harborframework.com/core-concepts/agents/atif). ATIF v1.7 was observed in current documentation.

Harbor packages instructions, environments and verification in reproducible tasks and supports standardized agent trajectories. Separate verifier containers are an explicit option; a container by itself does not imply that the agent and verifier are isolated from each other.

**Use:** borrow the task-package structure and offer compatible exports where useful. Preserve the private oracle boundary. A simple interchange layer is preferable to a full runner replacement during this month.

### 10. Hypothesis and delta debugging

Sources: [Hypothesis stateful testing](https://hypothesis.readthedocs.io/en/latest/stateful.html), [The Debugging Book: reducing failure-inducing inputs](https://www.debuggingbook.org/html/DeltaDebugger.html).

Stateful property tests generate sequences of actions over a defined state machine. Reduction searches for a smaller failure-inducing example.

**Use:** test the simulator and oracle themselves, and build a strong non-LLM search baseline. Actions need legal preconditions and invariants. Reducing a stochastic model failure needs repeated confirmation and an honest finite-search limitation; a smaller example from one lucky run is not a robust explanation.

### 11. Chaos Mesh

Source: [official HTTP fault documentation](https://chaos-mesh.org/docs/simulate-http-chaos-on-kubernetes/). Documentation version 2.8.4 was observed.

Chaos Mesh supplies Kubernetes HTTP perturbations such as aborts, latency and response changes.

**Use:** consider it when the target is real Kubernetes infrastructure. For the current experiments, keep the application-aware simulator: the distinction between failure before a write and a lost reply after a committed write requires knowledge of service state. Infrastructure chaos does not supply that oracle automatically.

### 12. Flakestorm and adjacent open-source work

Sources: [Flakestorm product mechanics](https://flakestorm.com/how-it-works), [published package 2.0.0](https://pypi.org/project/flakestorm/2.0.0/).

Flakestorm already describes tool/model faults, behavioral contracts, reset behavior, incident replay and CI scoring. These are first-party feature claims, not capabilities we executed during this audit.

**Implication:** “agent chaos testing with a dashboard” is insufficient positioning. Compare integration effort, state semantics, reproducible evidence, and independently measured repair behavior. We have not established that any competitor lacks our proposed features; differentiation must be demonstrated through results and user experience.

An additional adjacent project, [Agent Reliability Lab](https://github.com/Hai-qq/agent-reliability-lab), describes state-transition faults and verifiable evidence packages. Its indexed official README reported version 0.4.0 and explicitly limited its live claims. Direct page retrieval failed during this research, so treat it as a lead for follow-up, not a central competitive conclusion.

## Meaningful CoreWeave and W&B integration

### 13. Weave evaluation logging

Source: [official EvaluationLogger documentation](https://docs.wandb.ai/weave/guides/evaluation/evaluation_logger).

The logger can record predictions and scores incrementally from an existing evaluation loop.

**Use:** continue publishing our fixed scores and immutable identities rather than reimplementing them as an LLM judge. Make raw denominators, failures and local/remote status agree. Fixing FaultLab's mislabeled report failures is more valuable than adding another reporting layer.

### 14. W&B Automations and Aria

Sources: [official automations overview](https://docs.wandb.ai/models/automations), [execution history](https://docs.wandb.ai/models/automations/view-automation-history).

Automations can send prompts to Aria after configured events. The documentation distinguishes execution history and supported actions; Trigger ARIA is listed for Multi-tenant Cloud.

**Use:** make campaign publication and attribution reliable through documented surfaces. Distinguish dispatch from completed analysis and observed operator capture from independent verification. Aria can explain trends and suggest follow-up work, while our fixed scorer and promotion rules retain authority. Do not make an undocumented completion endpoint a core product dependency.

### 15. CoreWeave Sandboxes

Sources: [official product page](https://www.coreweave.com/products/coreweave-sandboxes), [parallel sandbox sessions](https://docs.coreweave.com/products/sandboxes/client/tutorial/multiple-sandboxes).

The product is presented as preview infrastructure for isolated agent, evaluation and training workloads, with CKS and serverless deployment options. The client documents multiple sandboxes under shared session defaults and automatic cleanup.

**Use:** an optional backend for independent parallel trials is a direct fit. Pin images, isolate test state, preserve experiment identities and measure startup overhead. Account entitlement, API stability, network policy and workload fit must be checked before implementation depends on it. Keep local execution available.

### 16. ART / Serverless Training

Sources: [official W&B Serverless Training documentation](https://docs.wandb.ai/serverless-training), [ART overview](https://wandb.ai/site/art/).

W&B documents managed SFT and RL, with LoRA artifacts and hosted inference, currently in public preview. ART provides a way to train agentic models from experience.

**Use:** after evaluation is stable, compare a trained small Actor with the original Actor and the recovery-policy overlay. Training is an optional research branch, not a prerequisite for exporting useful failures. Use FaultLab's state-based task checks, retain safety/utility separation, and protect final evaluation data. Provider availability and prices require verification at execution time.

## Decisions this research supports

| Decision | Basis |
|---|---|
| Preserve the fixed state-based oracle | Transactional task correctness cannot be inferred from fluent text alone |
| Keep incident export useful without a repair | Testing and diagnosis are valuable even when an optimizer fails |
| Fix candidate feedback and dedup before larger runs | Current repeated proposals waste trials and confuse search progress with sampling variation |
| Add one independent agent and a second task | This tests whether the product boundary is reusable |
| Compare search/repair strategies under equal conditions | More model calls are not evidence of a better algorithm |
| Separate repeatability, utility and safety metrics | A single success number hides material failure modes |
| Use existing infrastructure selectively | Weave, sandbox runtimes and evaluation interchange can reduce work without replacing the engine |
| Treat training and security as separate experiments | They alter the intervention or threat model and need their own evidence |

The research supports this direction, but does not establish market demand or guarantee a repair will qualify. Two outside integrations, a complete evidence package and a fair before/after result would answer more than a longer feature list.
