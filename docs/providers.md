# Model providers

FaultLab's Actor, Explorer and Mechanic can run on any of five providers. Every provider is spoken
to through the OpenAI chat-completions wire format with the official OpenAI SDK, so the engine
has one request path; what differs per provider is a fixed *request profile* and its credentials.
Campaign identity, admission, redaction and the dollar ledgers are provider-independent.

| Provider | Model name in `.env` | Credentials | Notes |
| --- | --- | --- | --- |
| W&B Inference (default) | `deepseek-ai/DeepSeek-V3.1` or `wandb:deepseek-ai/DeepSeek-V3.1` | `WANDB_API_KEY`, `WANDB_ENTITY`, `WANDB_PROJECT` | Unchanged from every earlier campaign. DeepSeek V4 thinking is disabled by `chat_template_kwargs`. |
| OpenAI | `openai:gpt-5-mini` | `OPENAI_API_KEY` | Sends `max_completion_tokens`. Reasoning models (`gpt-5*`, `gpt-6*`, `o*`) reject `temperature`, so it is omitted for them. |
| Anthropic | `anthropic:claude-sonnet-5-5` | `ANTHROPIC_API_KEY` (plus `ANTHROPIC_WORKSPACE_ID` for a key that is not scoped to a workspace) | Anthropic's OpenAI-compatible layer ignores `response_format` and returns 400 for `temperature` below 1 on current models, so neither is sent. Structured output is recorded as *not enforced*; the lab validates every answer anyway. |
| OpenRouter | `openrouter:anthropic/claude-sonnet-5-5` | `OPENROUTER_API_KEY` | Forwards `response_format`; reports the call's own `usage.cost`, which FaultLab records as the measured cost. Vendor parameter rules apply by model prefix. |
| Custom | `custom:my-model` | `FAULTLAB_CUSTOM_BASE_URL`, `FAULTLAB_CUSTOM_API_KEY` | Any OpenAI-compatible endpoint: a local server, a gateway, a proxy. Plain request. The URL must be `https://`, or `http://` to this machine only (localhost, 127.0.0.1, ::1), because the key travels in a header. |

Sources for the profiles, read on 2026-10-10: Anthropic's OpenAI SDK compatibility page
(`response_format: Ignored`; omit `temperature` on Claude 4.7 and later), OpenAI's reasoning guide
(`max_completion_tokens`, no `temperature`), OpenRouter's structured-outputs and usage-accounting pages.

## Naming a model

A model reference is `provider:model_id`. An unprefixed name belongs to `FAULTLAB_DEFAULT_PROVIDER`
(`wandb` unless you change it). Model ids may contain `/` and `:` themselves
(`openrouter:qwen/qwen3-235b:free`); only a known provider prefix is split off.

Per-role selections, in order of precedence:

1. `FAULTLAB_ACTOR_MODEL`, `FAULTLAB_EXPLORER_MODEL`, `FAULTLAB_MECHANIC_MODEL`
2. the legacy `WANDB_MODEL`, `WANDB_EXPLORER_MODEL`, `WANDB_MECHANIC_MODEL`, `FAULTLAB_LAB_MODEL`
3. Explorer and Mechanic fall back to the Actor's model.

Names are recorded in one canonical spelling: a W&B model keeps its bare id, every other provider is
spelled out. So `wandb:deepseek-ai/DeepSeek-V3.1` and `deepseek-ai/DeepSeek-V3.1` are the same
model, campaigns frozen before other providers existed keep their identities byte for byte, and a
frozen configuration never depends on the writing machine's default provider.

For a non-W&B model the frozen `model_settings` additionally record the provider, which token-limit
parameter was sent, whether `temperature` was sent, and whether the API enforced `response_format`.
Two runs that sent different parameters never share an identity.

## Prices and the two dollar caps

The lab never admits a paid call it cannot bound in dollars. Rates come from, in this order:

1. the explicit `FAULTLAB_*_DOLLARS_PER_MILLION` settings earlier campaigns used (matched by model name);
2. the dated pricing table `backend/app/providers/pricing.json` (or `FAULTLAB_PRICING_TABLE`).

A table entry counts only when `verified` is `true` **and** `verified_on` is within 90 days
(`FAULTLAB_ALLOW_STALE_PRICES=true` lifts the second rule). Figures copied from aggregators ship
as `verified: false` on purpose. To price a model: open the provider's official pricing page, check
the two rates, set `verified` to `true` and write the date. `require_live()` names an unpriced role
as `PRICING:<provider:model>`.

Two caps apply to every priced call:

* `FAULTLAB_DOLLAR_CAP` (at most 500): the campaign's own ceiling, as before.
* `FAULTLAB_MONTHLY_DOLLAR_CAP`: a machine-wide ceiling for the calendar month, across every campaign,
  study and smoke check. Before a call is sent, its worst-case bound (32,000 input + 2,000 output
  tokens at the verified rates) is reserved in `~/.faultlab/spend-ledger.sqlite3` (or `FAULTLAB_SPEND_LEDGER`), one ledger
  per machine whatever store a run uses; the reservation
  is refused, before any client exists, when the month's committed total would exceed the cap
  (`RuntimeProviderError` code `MONTHLY_CAP`, never retried). After the response the row is settled
  with the measured cost. The committed total counts every settled call at its measured cost and every
  open call at its bound, so the cap means dollars while a call in flight is still charged for the
  worst it could cost (until 2026-10-24 the gate summed bounds only, and a cap of 400 meant about 50
  dollars of spend). A crash between reserve and settle leaves the bound charged.

Before declaring a paid run, `scripts/experiments/baseline_screen.py --dry-run ...` (the same arguments as
the run) prints what admission would decide: the campaign hold (protected calls plus the study's calls at
the dearest role's per-call bound) against the campaign cap, the live configuration, and the month's
committed total and room. Nothing is created, started or called; exit code 2 means the run would be refused.

Unpriced models (no verified rate) reserve nothing and report `cost_usd` as unknown; campaigns refuse
them at admission, smoke checks allow them.

## Checking a provider

```bash
python backend/check_provider.py check --provider openai --model gpt-5-mini --list-models
```

```bash
python backend/check_provider.py check --provider openai --model gpt-5-mini --generate --max-output-tokens 64
```

`--generate` sends one JSON smoke request through the production path (profile, admission, redaction,
monthly reservation) and prints a report: the model id sent, the per-call bound, the pricing status,
tokens, measured cost, whether structured output was enforced, and whether the reply parsed as JSON.
For `--provider wandb` pass `--confirm-entity` as the older `wandb` subcommand requires. Nothing is
traced to Weave by `check`; `wandb --generate` keeps its verified trace.

## What is not done yet

* **Weave stays coupled to campaign execution.** The coordinator starts the Weave worker for every
  live campaign, and Weave needs the W&B credentials. `FAULTLAB_WEAVE_ENABLED=false` today only lifts
  the `FAULTLAB_CONFIRMED_ENTITY` rule when no role runs on W&B; making the evidence pipeline run
  without Weave is Stage 1 work (plan item 1.11). Until then a campaign on OpenAI or Anthropic models
  still needs the W&B credentials for tracing.
* The pricing entries for OpenAI and Anthropic are unverified placeholders; verify them before use.
* Provider-specific input-token counting is the generic byte bound for non-W&B models; the per-call
  token admission is therefore conservative, not exact. Concretely, `app/contracts/tokens.py` counts one
  token per byte for a model without a registered tokenizer, so a Claude model is refused
  (`INPUT_LIMIT`) once a request exceeds about 32 KB of text, far below the real 32,000-token bound.
  Smoke checks and short episodes are unaffected; long Mechanic or Actor contexts are. The fix is a
  registered admission source per provider (Anthropic's token-count endpoint, or a reviewed
  approximation with a stated margin), planned with the provider work of Stage 1.
