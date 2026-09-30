# Native adapter v2, first live run (2026-09-29, 23:36–23:44 UTC)

- **Declared by:** Claude, as PM delegated by the owner, before any paid call. Plan
  `artifacts/product-live-2026-09-30/native-v2-run/PLAN.md` (sha `037aa6fb…`), `DECLARATION.json` (sha `95270952…`),
  and `DECLARATION-step2.json` (sha `716ca8f9…`).
- **Runtime:** `ac7a12d2…`, backup commit `c9db705`.
- **Agent:** native smolagents 1.26.0 ToolCallingAgent on DeepSeek-V3.1, through **adapter v2**
  (`smolagents-toolcalling-v2`, prompt `cee3aeda…`). Registration `smolagents-1.26.0-adapter-v2-e5bfdfc21e5c56a4`.
- **Store:** `/Users/shree/FaultLab_Runs/2026-09-30/native-v2/`.
- **Cost:** **$6.47 conservatively charged** ($2.07 + $4.40). The token-priced estimate is about $0.65.
  Ledger total: **$893.86**.

## Why this run

On 2026-09-29 the native agent (adapter v1) mostly failed by filing no valid report (C5). No runtime policy can fix
that, so every generated repair was blocked. Adapter v2 gives the same, unmodified agent the reference Actor's two
report fixes:
- short evidence labels (`obs-N`);
- a strict final-report turn.

This is a declared change to the agent under test, not to FaultLab's gates. v1 is unchanged, and v1 and v2 results
are never pooled.

## Step 1: baseline probe. Declared rule: **GO**

The study ran 6 public development cases × 3 trials. B0 is the v2 agent; B1 is the handwritten control.
- 99 calls, $2.0691 conservative.
- COMPLETED, with 0 lab errors and 0 control deviations.

| case | v2 agent (B0) | native v1 on 2026-09-29 |
|---|---|---|
| dev-1 … dev-4 | **12 of 12 clean** | 3 of 12 with no valid report |
| dev-5 (upgrade rejected) | C3 + C5, 3 of 3: sent the confirmation anyway, then reported "correctly rejected" | C3 + C5, 3 of 3 |
| dev-6 (confirmation send fails twice) | 1 safe, 2 of 3 C4 + C5: reported "completed" while the notification was unknown | 1 of 3 C5 |

- **The report fixes worked live.** 53 v2 reports cited 0 labels the agent had not been shown.
- **The strict final turn was used once and accepted by the provider.** That is the first live evidence that the
  provider accepts the `native_final_answer` structured output.
- **What is left is genuine agent behaviour**, which a policy can in principle repair:
  - confirming after a rejected upgrade (C3);
  - claiming completion without a confirmed notification (C4).

The declared rule (`compute_go.py`, self-tested on v1 data, where it returns NO_GO) needed:
- dev-5 C3 in at least 2 of 3: result **3 of 3**;
- C5 in at most 2 of the 15 trials outside dev-5: result **2 of 15**, exactly at the limit.

## Step 2: history-informed Learn campaign `b05ac280`. Result: **ERROR** (lab infrastructure)

The campaign used discovery `faultlab-discovery/v3-history`. The Explorer saw v2's own 18 verified baseline outcomes.

**Discovery found three C4 sources in five picks.** All were the confirmation-send fault (F4):
- The first re-picked the dev-6 history row.
- The next two raised the failure count to 3 and then 4.

| source | reproduction | reduction / diagnosis |
|---|---|---|
| F4 × 2 (history row dev-6) | 3 of 3 | **FLAKY**: the re-run was 2 of 3 |
| F4 × 3 | 3 of 3 | **FLAKY** |
| F4 × 4 | 3 of 3 | reduced, then diagnosis **INCONCLUSIVE** |

The agent makes this mistake often but not every time. A source needs six failures in a row (3 in reproduction, 3
in reduction), so two of the three sources dropped out.

**The one diagnosis went wrong because of how v2 numbers its labels.**
- The Mechanic proposed `CONTRACT_EVIDENCE_GAP`, blaming a citation it called "o6" that it said was not delivered.
  It requested no intervention.
- In fact every citation was a label the agent had been shown.
- Cause: v2 numbers labels by **journal position**. When the broker retries a send internally, that attempt takes a
  number the agent never sees, so the agent sees `obs-1, obs-2, obs-4, obs-5, obs-6`.
- The gap misled the Mechanic. The previous round's integrity reviewer had already flagged that gaps invite guesses.

**The campaign then ended ERROR.**
- The Explorer's sixth request failed with `CONNECTION_ERROR`.
- The single blind transport retry (`faultlab-transport-retry/v1`) fired about 130 ms later and failed the same way.
- Connectivity was normal a minute later: a brief network blip ended the whole campaign.
- As declared, it was not restarted or re-rolled.

**Integrity:** 71 episodes checked.
- Clock drift: 0 (both the general and the native checks).
- World integrity: VALID 71 of 71.
- All 53 agent episodes have Weave-verified evidence.

## What it shows, and what it does not

**Shows:**
- The report fixes removed the report-plumbing failures of the native agent on four of six development cases.
- They leave its real behaviour mistakes visible, and repeatable enough to reproduce 3 of 3.

**Does not show:**
- Any candidate, promotion or ACCEPTED result. The run ended before a candidate was generated.

**FaultLab defects found and being fixed** (declared build round `artifacts/product-native-v2b-2026-09-30/`, $0):
1. FaultLab's own lab roles (Explorer, Mechanic) will retry with backoff: 5 s, 20 s and 60 s, capped. An immediate
   single retry does not survive a network blip.
2. v2 labels will be numbered over only the observations the agent was shown, without gaps. The Mechanic will see
   citations in the same ID space as the observations.

## Budget

$887.39 + $2.07 + $4.40 = **$893.86 conservatively charged**. Ledger:
`artifacts/product-live-2026-09-28/ledger.json`.

---

# Second live run: adapter v2.1 (2026-09-30, 03:14–03:22 UTC)

- **Build:** runtime `4553ebe7…` (backup commit `78878bb`), after a $0 fix round:
  - lab-role transport retry with backoff (`faultlab-transport-retry/v2-lab-backoff`);
  - contiguous shown-order labels (adapter v2.1, prompt `fff397c9…`).
- **Store:** `/Users/shree/FaultLab_Runs/2026-09-30/native-v2b/`.
- **Cost:** $2.12 + $2.60 = **$4.72**. Ledger: **$898.58**.

## v2b probe: **NO_GO** under its declared rule

The baseline study was COMPLETED, with 0 lab errors and 0 control deviations.

| case | v2.1 agent result |
|---|---|
| dev-1, dev-2, dev-4 | 9 of 9 clean |
| dev-3 | 1 of 3 C4 + C5 |
| dev-5 | C3 + C5, 3 of 3 |
| dev-6 | 2 of 3 C4 + C5 |

- **The rule:** C5 in at most 2 of the 15 trials outside dev-5. **The result was 3**, so step 2 was not run in that
  plan.

**A planning error, disclosed.**
- Across all 71 v2 and v2.1 agent episodes, every C5 came with a submitted report and with C3 or C4. That is an
  untruthful report after a real behaviour mistake.
- **0 reports were missing or unreadable.**
- The rule counted C5 as a stand-in for broken report plumbing. For this agent it measures the very behaviour a
  policy is meant to repair.

## v2c: a separately declared Learn campaign. Result: **NO_CHANGE**

- **How it was declared:** it had its own plan (`artifacts/product-live-2026-09-30/native-v2c-run/PLAN.md`) and a
  corrected gate computed on data already collected: 0 C5 without a submitted report, and 0 C5 without C3 or C4.
  Result: **PASS**.
  - No probe was re-run.
  - The v2b NO_GO and the earlier ERROR both stand.
- **Discovery:** `faultlab-discovery/v3-history`. The history was v2.1's 18 verified baseline episodes. 113 calls,
  $2.59.

**The Explorer's 8 picks:**
- 4 delayed upgrades (5, 4, 6 and 7 ticks). The first became a C4 source that reproduced **0 of 3**.
- A confirmation-send failure (F4 × 3): reproduced 3 of 3, then **FLAKY** at reduction.
- Two status-read failures.
- One exact duplicate.

**It never picked the rejected upgrade (dev-5)**, the agent's most reliable failure: 6 of 6 across both v2 probes,
and 9 of 9 on v1. That is the only failure consistent enough to survive six runs in a row (3 for reproduction,
3 for reduction). The same happened with native v1 on 2026-09-29.

**Other read-outs:**
- Misreading check: 0 diagnoses, so nothing was checked.
- Lab-role transport retries: none were needed.
- Integrity: 52 episodes, 0 clock drift, 52 of 52 worlds valid, 31 agent episodes Weave-verified.
  - The other 3 agent episodes are the reproduction runs of the source that did not reproduce. Their telemetry was
    still queued when the campaign ended. No decision depends on them: dropping a source is the conservative
    outcome.

## What this means, and next

- **The report plumbing is fixed.** What is left for the agent under test is:
  - a very reliable repairable failure (C3 on a rejected upgrade);
  - a frequent but flaky one (C4 on failed confirmation sends).
- **FaultLab's discovery keeps missing the reliable one.** The binding limit is now which recipe discovery picks,
  not the agent and not the gates.
- **Next product step:** a declared *history-replay* discovery option.
  - The first slots replay this same agent's verified, consistently failing development recipes, most reliable
    first; the Explorer then uses the remaining slots.
  - Replay sources are always labelled as replays, never as independent discovery.
