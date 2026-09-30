# Declared-rule deviation: early operator stop (2026-09-30 ~13:10 UTC)

**What:** The PM stopped campaign `campaign-53db74766f4d4635b94a0de89e492577` about 9.4 hours before the declared
10-hour watcher limit. The declared operator-stop reasons did not include this state.

**Why:**
- The campaign was in its 10th evidence wait, status NEEDS_OPERATOR.
- The product's automatic evidence retries were exhausted (6 of 6 per campaign).
- The watcher's declared operator retries were also exhausted (3 of 3).
- Nothing else resolves an evidence wait. On 2026-09-29 an unretried wait sat for 3.75 hours.
- So the campaign could not progress, and the declared rules would have ended it STOPPED at the 10-hour limit.
- Stopping now gives the same STOPPED outcome, spends nothing, and frees the machine.

**Effect on results:** none. No episode, model request or decision is added, removed or changed. Everything recorded
before the stop stands.

**Product finding:** every evidence wait in this campaign cleared on its first retry. The cap of 6 automatic retries
per campaign is too low for a campaign with many waits (10 here).
