# Phase 14 results — September 21, 2026

The control-path investigation [PHASE13_RESULTS.md](PHASE13_RESULTS.md) left open, and the
fix. **Cost: $0.** No paid run, no provider calls, no W&B calls. 16 agents across four
independent investigation angles, each adversarially verified by three separate lenses.

## The failing control call is `create()` — `POST /control/worlds`

Phase 13 lost 11 of 30 attempts (37%) to an unhandled `httpx.ReadError`, and could not say
which of the five control operations raised it. It can now, and the identification is
unanimous across every agent that attacked it.

**The structural squeeze.** `execute_slots` calls `runner.run` with no `try`, so anything
escaping the runner kills the study. `runner.run` has no `finally`; everything from the
actor call to the teardown is covered by two blanket `except Exception` handlers that never
re-raise. The only unprotected code is the few lines before the episode is written, and in
that window `store.get_record` is a local SELECT and `allocate_intent` is pure computation.
Across the whole app outside the simulator and CLI there are exactly **two** async httpx
call sites, and one of them is the wrapped business-tool path. So `create()` is the only
thing in the window that can raise `httpx.ReadError`.

**The forensic signature.** All 14 `ReadError` studies in the store — not just Phase 13's 11
— have exactly one slot left `INTERRUPTED`, always in the validation stage. All 56 studies
with an evidence-channel `error_type` have zero. For all 14, the episode_id has no
`episodes` row, no events and no `episode_registry` row.

**One correction to how I stated that.** Those are **not three independent absences**.
`events.episode_id` is declared `REFERENCES episode_registry(id)` with foreign keys on, and
`episode_registry` is written only by `put_record` when `kind=='episodes'`, in the same
transaction. So all three collapse to one fact: `put_record('episodes', …)` never committed.
That one fact is still decisive, because the slot's episode_id is pre-minted by the study
and handed to the runner, so its absence pins the throw before the episode write.

**A sharper exclusion I had missed.** `completion_study` sets `slot['status']` from the
returned trial *before* the evidence-gateway await. So a `ReadError` from the gateway or the
telemetry publisher would leave **zero** slots RUNNING, not one. The one-INTERRUPTED-slot
signature therefore pins the throw inside `runner.run` specifically.

## The failing request never reached the simulator

Two independent proofs:

1. **Field.** Scanning the `state` row of all 3,730 world files for each of the 14
   interrupted episode_ids returns zero hits. Control: the immediately preceding COMPLETED
   episode in each study was found in exactly its recorded world file. Separately, of the
   1,596 world files with an mtime on the Phase 13 day, **zero are orphans**; the 78 orphan
   files that do exist on disk all date from 09-20, days before any `ReadError` study.
2. **Reproduction.** A reviewer instrumented the server with a request counter: 900 trials,
   884 client successes, server-side count **exactly 884**. Difference zero.

This matters for the fix: a retry cannot double-create, because in every observed case
nothing was created at all.

## Why it fails: FOUND, and proven in uvicorn's own source

**This section replaces an earlier one that reported the mechanism as unknown.** A second
free round of investigation (16 more agents, four angles, three adversarial lenses each)
found it, and it is checkable in three lines of a library on disk.

uvicorn arms its keep-alive timer in `on_response_complete` — when it finishes **writing** a
response (`h11_impl.py:331`):

```python
self.timeout_keep_alive_task = self.loop.call_later(self.timeout_keep_alive, self.timeout_keep_alive_handler)
```

and the handler closes the transport without draining the socket (`h11_impl.py:372`):

```python
def timeout_keep_alive_handler(self) -> None:
    if not self.transport.is_closing():
        event = h11.ConnectionClosed(); self.conn.send(event); self.transport.close()
```

`asyncio`'s `close()` drops the reader and closes the socket **without reading what is in the
receive buffer**. On macOS/BSD, closing a socket that holds unread received bytes emits
**RST, not FIN**.

So: the client writes a `create` request onto a pooled connection; the bytes land in the
simulator's receive buffer; uvicorn's 5-second timer fires before the loop reads them; the
handler closes the transport; the kernel answers RST; the request is discarded **before the
ASGI application ever runs**; and httpcore maps the reset to `httpx.ReadError`.

**Every observation now has a cause.**

| observation | explained by |
|---|---|
| threshold at exactly 5.000s | uvicorn's default `timeout_keep_alive` |
| the app never ran, no world file exists | the request is discarded in the transport, before routing |
| always `ReadError`, never `RemoteProtocolError` | RST from close-with-unread-bytes, not a clean FIN. The store holds **0** `RemoteProtocolError`, `ConnectError`, `ReadTimeout` or `WriteError` across 138 studies — only the 14 `ReadError`s |
| hazard **decays** from 5.0s rather than plateauing | the window is the event loop's scheduling latency between the deadline firing and the close running |
| the server expires before the client, despite equal 5s values | the server's timer starts when it finishes **writing**; the client's when it finishes **reading**. The server is always first |

**The upper edge I asked to be explained does not exist.** Two agents converged on this
independently: the hazard is `[5.0,5.5)` 11/155 = 7.1%, `[5.5,6.0)` 2/67 = 3.0%,
`[6.0,7.0)` 0/76, `[7.0,∞)` 0/109 — a decay with a ~0.4–0.5s scale, not a box. Under the
fitted decay the expected count above 6.0s is 0.39, so observing zero has **P = 0.68**. The
exposure is also not homogeneous: gap length is driven by the preceding episode's telemetry
size, and stratifying moves the "upper edge" from the p = 0.0009 I was given to p = 0.02–0.21.
**The lower edge survives every stratification** (position-stratified permutation p < 5e-6).

**The best single predictor is a straddle, not a band.** Define A as the time from the
previous episode ending to its evidence being retrieved. `A < 5.0 <= gap` — the request was
issued before the server's deadline and the deadline fell during the call — gives 10/110
(9.1%) against 1/761, Fisher **p = 7.0e-09**, and fits 2.9 log-likelihood units better than
the band at equal parameter count. 87 of the 93 exposures above 6.0s have `A >= 5.0` and are
**not in the at-risk class at all**. That is precisely the uvicorn mechanism restated.

**A natural experiment.** One 11-episode study had ten inter-episode gaps of 1.55–4.56s and
exactly one crossing 5.0s, at 5.045s. That crossing is the one that failed.

**Refuted along the way** (so nobody re-proposes them): a TIME_WAIT / ephemeral-port
4-tuple collision — 72/72 served, and macOS recycles a TIME_WAIT socket for a higher-ISS SYN
rather than resetting; teardown racing `accept()` — 216/216 served across nine gaps; and a
genuinely fresh connection being reset — 888 trials, zero resets. **A fresh connection is
never the victim.** The victim is always a *reused* one the server has just closed.

## The fix, and its exact boundary

Two changes, and now that the cause is known the **first one is the real fix** and the retry
is a backstop rather than the remedy.

**1. Close the race: the client retires idle connections before the server does.**
`WorldClient` now builds its pool with `httpx.Limits(keepalive_expiry=2.0)` against the
simulator's 5s. Because the client always closes first, the server never closes a socket
with a request already in it, and the mechanism above cannot occur. Verified deterministically
against a real uvicorn — this is the dangerous state disappearing, not a race being dodged:

| idle before next request | old (`expiry=5.0`) | new (`expiry=2.0`) |
|---:|---|---|
| 1.0s | REUSED | REUSED |
| 2.5s | REUSED | fresh |
| 3.5s | REUSED | fresh |
| 4.5s | **REUSED** — can reach the server deadline | fresh |
| 4.9s | **REUSED** — can reach the server deadline | fresh |

`scripts/start-simulator.sh` also passes `--timeout-keep-alive 75` as defence in depth, so
the server is the slower side even for a client that does not set its own expiry. This
changes only TCP connection lifetime: no handler, response, status, fixture, fault schedule,
world state, tick, evidence record or referee input is touched.

**2. Bounded retry of `create()` only**: 3 attempts, jittered 0.25s then 0.5s backoff,
catching only `WorldControlError` (transport). An `HTTPStatusError` propagates on the first
attempt, so a 422 fixture mismatch or a 403 control denial still fails fast. On exhaustion
the error re-raises still naming `operation='create'`, so an aborted study finally records
`control_operation` instead of Phase 13's bare `ReadError`.

**The retry was measured, not assumed.** Across two independent harnesses driving the real
shipped code against a real uvicorn, **551 of 551** genuine `ReadError`s recovered on attempt
2; attempt 3 was never reached. Zero backoff recovers just as well, so there is no poisoned
pool. Modelled residual after 3 attempts is ~4.6e-5 per create against Phase 13's 1.279% —
roughly a 270× reduction — though one reviewer correctly notes that figure assumes
independence between attempts, which was never varied, so treat it as an estimate rather
than a bound.

**Two real defects in the first version of that retry, found by review and fixed:**

- **No jitter.** A fixed ladder retries at fixed offsets, so a cause recurring on a period
  dividing them is met at the same phase every time. Measured against a 0.25s-period fault,
  the unjittered ladder lost **12 exposures of 14**; multiplying the ladder by U(0.5, 1.5)
  took that to **1 of 14**. Jitter is now applied from an independent random source, so it
  can never perturb a seeded run — there is a test for that.
- **`CREATE_BACKOFF` was indexed without a clamp**, and it is one shorter than
  `CREATE_ATTEMPTS`. Raising the attempt count to 4 without extending the ladder raised
  `IndexError` instead of retrying. Now clamped to the last rung.

Worth recording for whoever tunes this: the ladder's **span**, not the attempt count, is what
buys protection against a cause that simply persists. The shipped ladder covers ~0.75s of
outage; 4 attempts covers 1.5s, 5 covers 3.0s. Widening beats adding.

Retries are recorded on the episode through the existing free-form `episode_started` event
payload — **not** as a field on `Episode` or `TrialResult`, because those are `StrictModel`
with `extra='forbid'` and a new field would move `contract_hash`.

**Why this is safe for `create()` and nowhere else.** Nothing anywhere resolves a world from
an episode_id — verified across the simulator, lab, referee, frontend and CLI. The simulator
writes `episode_id` into world state and uses it only to stamp that world's own private
events; every reference runs episode → world. So a create whose response was lost leaves a
world the lab **cannot even name**, referenced by no episode, trial, verdict or statistic.
Critically, no untriggered-fault count scans the worlds directory — every one reads
`TrialResult`/`episodes` — so FaultLab's fatal-untriggered-fault rule is untouched. Two
worlds for one episode has in fact already shipped 78 times on disk and nothing noticed.

**Measured idempotency of each operation** (in-process, my own run, not taken on trust):

| operation | retried? | measured behaviour on a repeat |
|---|---|---|
| `create` | **yes** | same episode_id → two distinct world_ids, two files. Orphan is inert and unnameable. |
| `advance` non-observer | **no** | tick 2 → **4**. Double-applies, and can flip whether a fault triggers |
| `advance` observer | no | **409 `INVALID_OBSERVER_ADVANCE`, tick still 9** — latched by `horizon_done` |
| `snapshot` | no | byte-identical |
| `faults` | no | byte-identical |

The non-observer `advance` is the reason the retry must never move into `control()`: a
double-applied advance changes `trial.fault_triggered`, hence `valid_trial`, hence whether a
pair can qualify. That is a silent change to what the gate measures and is forbidden. An
anti-regression test asserts each of the other four operations is called exactly once.

**A correction to Phase 13's write-up:** I said the observer `advance` was not retry-safe.
It is — `clock.advance` sets `horizon_done` atomically with the tick. The claim was right
about the non-observer `advance` and wrong about the observer one.

## What this does not fix

**The teardown route is still open, and it is not theoretical.** I previously wrote that the
five protected control calls "failed zero times". That was wrong. The 3
`SIMULATOR_OR_SCORER_ERROR` episodes in the store **each killed a completion study** — they
are the single `LAB_ERROR` slot in 3 of the 20 `EvidenceDenied` studies. Those episodes ran
to completion normally, then lost the teardown, so the evidence gateway rejected them for
`lifecycle != 'COMPLETED'` and the study died as `EvidenceDenied` rather than `ReadError`.
Same class of failure, different obituary. A `create`-only retry leaves that path exposed.

**But the connection-lifetime fix covers it anyway, which the retry alone would not have.**
`keepalive_expiry` applies to every call `WorldClient` makes, so if those 3 episodes lost
their teardown to the same 5-second race, that race is now closed for them too. It is not
proven that they did — the scorer sits inside the same `try`, so a scorer error is
indistinguishable from a transport one in the record — and that is precisely why the
structural fix is worth more than the retry: it does not require knowing which calls were
affected.

What remains genuinely unfixed is the *structural* exposure: any episode that ends
`LAB_ERROR` for any reason is refused by the evidence gateway and kills its study. That is a
separate design question, worth 3 studies across the entire 3,652-episode store, and it
should be measured rather than bundled in here.

**A recommendation I am rejecting.** Review proposed a "strictly better" fix: have
`completion_study` mark a lost slot and continue, as it already does for an invalid trial,
bounding the loss to one episode regardless of cause. It is wrong for this project, and the
reason is in `assess_pairs`: it requires `len(rows) == len(expected)` with `actual ==
expected` over all 42 slots, so a missing slot returns `INCOMPLETE` anyway. Continuing would
pay for roughly 21 more episodes and still produce an unscorable attempt. This is the same
correction recorded as T195 in Phase 12, and it holds. The review's safety argument — that a
stage with a missing slot can only fail to qualify a candidate, never falsely qualify one —
is correct but is about safety, not about value.

## Honest status of the fix

**Built, tested, and not yet exercised by a paid run** — but no longer blind, which is the
difference from Phases 12 and 13. The mechanism is identified in library source, the
connection-lifetime fix removes its precondition deterministically, and the retry backstop
recovered 551 of 551 induced failures. What remains unverified is only that a real 30-attempt
run shows the expected drop; that is a confirmation, not a discovery.

**One honest negative about my own verification.** My first attempt to reproduce the race
myself returned **0 failures in 40 trials in both the old and new configurations** — it did
not reproduce the bug at all, so it confirmed nothing. The window is ~2ms wide and a
sleep-based gap grid overshoots it. I therefore rely on the agents' reproductions plus the
deterministic connection-reuse table above, which needs no race to be observed.

**It changes `configuration_hash`.** Editing `business_tools.py` moves `adapter_hash` and
`runtime_hash`. Post-fix runs are therefore not the same frozen configuration as Phase 13.
The marginal cost is nil — Phase 13's own instrumentation already moved it — but the claim
sometimes made for changes in this file, that `algorithm_hash` being unchanged makes runs
comparable, is narrower than it sounds: `algorithm_hash` covers only `backend/app/lab` and
`backend/app/referee`, so it shows no *acceptance logic* moved. It does not make the
configuration identical.

## Verification

- **592 backend tests** (581 + 11 added here), integration suite 45 passed.
- The three integration tests asserting one world file per trial **still pass unchanged** —
  they inject no transport failure, so the retry never fires in them.
- `checks.py` not opened; `scorer_hash` unchanged.
- **Not unconditionally green**: the intermittent
  `test_failed_attempt_retained_without_replacement_and_reservation_released[untriggered]`
  failure (~1 in 8 full runs, pre-existing, unexplained since Phase 10) still stands.

## What to do next

1. **Restart the simulator before the next run.** The long-running instance still has
   uvicorn's 5s default; the launch script's `--timeout-keep-alive 75` only applies to a
   fresh start. The client-side `keepalive_expiry=2.0` protects regardless, but start clean.
2. **The $91 run is now justified.** The expected create-caused aborts across 30 attempts
   fall from Phase 13's 11 to well under one. Expect roughly 24 of 30 attempts to run all 42
   slots rather than 30 of 30 — the evidence channel (5 `WaitingEvidence` + 1
   `EvidenceDenied`, 20% of attempts) is untouched by any of this.
3. Reaching the declared 20 scored replays is then plausible within one run for the first
   time, instead of the 13 Phase 13 managed.
4. Still separate and unfixed: the `LAB_ERROR` → `EvidenceDenied` structural exposure, and
   the intermittent test failure unexplained since Phase 10.
