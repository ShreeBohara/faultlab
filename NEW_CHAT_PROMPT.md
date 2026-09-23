# Starting prompt for a new chat

Copy everything between the lines.

---

You're picking up a research project called FaultLab:

`/Users/shree/Desktop/Coreweave_AGI_Hackthon/faultlab`

**Read these first, in this order, and nothing else yet:**

1. `memory/START_CLAUDE.md`
2. `CLAUDE.md`
3. `memory/context/next-phase.md`
4. `memory/context/pitfalls-and-decisions.md`

**Do not change any code, run anything, or start any experiment yet.** Just read and think.

Then tell me, in plain English and no jargon:

- What is this project, and what has it actually achieved versus not achieved?
- What do you think the next phase should be, and why?
- What would it cost, how long would it take, and what could go wrong?
- Is there anything in there you think is wrong, or that you'd do differently?

**Then stop and wait for me.** After I approve, we go one phase at a time: you propose, I
approve, you run it, you report back honestly — including results that go against the
project. Don't chain phases together without checking in.

Two things that matter to me:

- There's a shared $1,000 budget with **$563.27 left**. Never spend any of it without asking
  me first.
- Tell me plainly when something didn't work or when you were wrong. Don't dress up a null
  result as progress.

---

## Why this prompt looks like this

The previous session's main failure was **drift**: it spent six phases (10–15) fixing
measurement and infrastructure. That work was real and is finished, but the project's actual
goal did not move. The "read, think, plan, wait" structure is there to catch that at the
start of the next phase rather than six phases later.

The single most useful thing in the handoff is in `CLAUDE.md` under **"READ THIS FIRST"**:
the project spent three phases explaining why the Mechanic "never" emits the working repair,
when it actually emits it about **16% of the time**. The claim came from a six-proposal
sample. A new session should check that finding early, because if it holds, the goal may be
a few cheap runs away rather than another rebuild.
