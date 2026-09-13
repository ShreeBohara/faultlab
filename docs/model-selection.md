# Model selection for the live flow

**The live launcher now defaults to `deepseek-ai/DeepSeek-V4-Pro-0813`, with thinking disabled.** Its action, report, Explorer and diagnosis compatibility checks returned nonempty, schema-valid answers. W&B describes this model as intended for complex agentic work; the observed response compatibility makes it the current practical choice for FaultLab. This is not a universal model ranking or a claim that the complete V4 learning cycle has passed. Actual live outcomes belong in [learning results](learning-results.md) and [baseline results](baseline-results.md).

## Documentation and request settings

The user-linked [W&B Models quickstart](https://docs.wandb.ai/models/quickstart) covers experiment tracking. Hosted model calls use the [Inference API](https://docs.wandb.ai/inference/api-reference/chat-completions). The current model and its rates appear on [W&B's DeepSeek V4 Pro 0813 page](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/).

FaultLab sends documented [JSON response mode](https://docs.wandb.ai/inference/response-settings/json-mode), temperature 0, and no automatic retries. JSON mode provides valid JSON; the existing validators still enforce the exact action, report, and proposal contracts. The backend supplies the actual action schema and returns useful validation feedback for rejected answers without rewriting them. Model settings and role prompts are frozen for each campaign.

W&B documents V4 Pro 0813 as thinking-enabled by default and supports disabling it through `extra_body={"chat_template_kwargs":{"enable_thinking":false}}`. FaultLab sends this setting for this exact model in both smoke and campaign calls. The [reasoning documentation](https://docs.wandb.ai/inference/response-settings/reasoning) also distinguishes GPT OSS, whose reasoning cannot be disabled. No reasoning text is substituted for the required final answer.

## Compatibility checks: model requests only

These checks used saved task and observation contexts. They did not execute business actions or count as learning trials. The action/report/Explorer probes allowed up to 4,000 output tokens and 30 seconds, with zero automatic retries. The separate V4 disabled-thinking diagnosis check used the actual runtime ceiling of 2,000 output tokens and 20 seconds.

| Model | Observed result | Decision |
|---|---|---|
| GPT OSS 120B | The first-action request returned empty final content with `finish_reason=stop` after 442 reported output tokens. The report request encountered a connection error; the Explorer request timed out. | The larger output allowance did not resolve compatibility. |
| Llama 3.3 70B Instruct | All three replies were nonempty in 0.701–2.259 seconds. Report and Explorer outputs passed their schemas. The first action included a disallowed `order_id` argument; a separate diagnostic request confirmed that mismatch. | Supply the complete action schema and validation feedback, then test the real workflow. |
| DeepSeek V3.1 | All three replies were nonempty and schema-valid in 1.743, 1.831, and 3.171 seconds. Its Explorer chose one first-upgrade delay instead of repeating an unreachable composite from the supplied history. | Earlier default; completed live attempts are retained below. |
| DeepSeek V4 Pro 0813, default thinking | The separate diagnosis check returned no final content, `finish_reason=length`, and 4,000 reported output tokens after 30.062 seconds. | Keep this failed check; do not use the default thinking setting for the bounded flow. |
| DeepSeek V4 Pro 0813, thinking disabled | Action, report and Explorer passed in 1.055, 1.456 and 1.616 seconds using 22, 127 and 251 output tokens. A separate diagnosis reply passed its schema in 2.497 seconds using 240 output tokens. | Current default; live healthy execution and learning NO_CHANGE verified, automatic repair still unverified. |

The DeepSeek checks used the corrected action schema and later accumulated Explorer history. These are compatibility observations across development stages, not a controlled model-quality comparison. A valid Explorer or diagnosis proposal does not prove a successful fault reproduction or repair.

Saved request records: `artifacts/model-readiness-20260913.json`, `artifacts/llama-action-schema-20260913.json`, `artifacts/model-readiness-deepseek-20260913.json`, `artifacts/v4-diagnosis-readiness-20260913.json`, `artifacts/model-readiness-v4-direct-20260913.json` and `artifacts/v4-direct-diagnosis-readiness-20260913.json`.

## Completed Llama live measurements

After the schema and request fixes, Llama completed a healthy order with all eight checks passing, five model calls, and verified Weave evidence. Its six-case baseline study completed **36 valid trials with zero infrastructure errors**; all **30 scheduled fault trials** triggered their full recipes. The real model made two incorrect reports. The fixed baseline scores were read back from an actual [Weave evaluation](https://wandb.ai/shreetbohara-quinstreet/Faultlab/r/call/01a09b7b-1890-78da-b9f9-1d7c162daf23).

The separate Llama learning campaign made **64 model calls with zero provider failures** and ended **NO_CHANGE**. Its eight discovery episodes produced three completed orders, four safe unresolved reports, and one violation. Six Explorer proposals were schema-valid; two invalid proposals used recorded fallbacks. Repeated unreachable composite schedules prevented a fully triggered violation from qualifying for repair. These retained Llama results motivated the DeepSeek compatibility check; they are not DeepSeek results or evidence of a learned improvement.

## Completed V3.1 live attempt

Campaign `campaign-e6ac7b05ebc049f6804d34dc04d4ef72` completed `NO_CHANGE`: 119 episodes and 829 model calls, with zero provider failures and all 119 episode traces verified. It reached repeated reproduction, reduction and diagnostic interventions, but all four fixed diagnoses were inconclusive. No diagnosis qualified for repair, and no learned policy was accepted. The saved record is `artifacts/deepseek-learning-final-20260913.json`; its conservative admitted inference ceiling was $17.3261 and actual billing is unknown. V4 subsequently completed healthy execution and the final 44-call learning attempt without provider errors; no fixed-check violation qualified for repair. See the retained final outcome in `docs/learning-results.md`.

## Token accounting and pricing

The current runtime allows 32,000 input and 2,000 output tokens, a 20-second timeout and no automatic retry. The previous 8,000-input limit blocked a complete measured repair context at 8,772 tokens; the increased allowance accommodates trial feedback and bounded format corrections. The total token ceiling is 204 million; call and trial limits remain unchanged, and the campaign still enforces $100. The disabled-thinking V4 probes returned their required final answers well within the current output ceiling.

Official tokenizers are available locally for GPT OSS, Llama, DeepSeek V3.1 and V4 Pro 0813. This avoids rejecting ordinary evidence merely because its UTF-8 byte count exceeds its token count. Digests are verified, literal control-token spellings remain ordinary evidence for admission, and no tokenizer downloads happen at runtime. Pinned sources and licenses are recorded in the [V4 provenance](../contracts/tokenizer/deepseek-v4-pro-0813/provenance.json), [V3.1 provenance](../contracts/tokenizer/deepseek-v3.1/provenance.json) and [Llama provenance](../contracts/tokenizer/llama3/provenance.json).

The [W&B token prices](https://wandb.ai/site/pricing/tokens/), including the [V4 model page](https://wandb.ai/site/inference-model/deepseek-v4-pro-0813/), were verified on 2026-09-13:

| Model | Input per million tokens | Output per million tokens | Conservative runtime allowance per request |
|---|---:|---:|---:|
| DeepSeek V4 Pro 0813, current default | $1.31 | $3.96 | $0.04984 |
| DeepSeek V3.1, earlier 32K-input run | $0.55 | $1.65 | $0.0209 |
| Llama 3.3 70B Instruct, earlier 8K-input runs | $0.71 | $0.71 | $0.0071 |

The current V4 ceiling uses 32,000 input and 2,000 output tokens. Its 1,064 protected calls reserve $53.02976, leaving the remaining campaign dollar capacity for development. The Llama row preserves its smaller historical allowance. These are admission ceilings, not actual billed totals. The existing $100 authorization remains. Credentials stay in `.env`, while the live launcher applies non-secret model and pricing overrides. Each model's results retain their separate frozen configuration.
