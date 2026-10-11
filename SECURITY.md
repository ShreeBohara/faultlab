# Security

FaultLab runs agents against a simulated service on localhost and, with `effectsafe`, sits between an agent and real services. Please report vulnerabilities privately.

## Reporting

Open a private security advisory on GitHub (Security tab, "Report a vulnerability") or email the maintainer listed in `pyproject.toml`. Please include steps to reproduce, the affected version or commit, and the impact you believe it has. We aim to acknowledge within 72 hours.

## Scope

In scope: anything that lets agent-supplied data select or execute code, read the evaluator's private evidence, bypass budget or admission checks, bypass approval binding or single-consumption in `effectsafe`, forge or replay receipts, or exfiltrate credentials.

Out of scope: running untrusted agent code in the subprocess backends, which is a containment measure, not an operating-system sandbox; see the architecture notes.

## Principles we hold ourselves to

- Startup, tests, health checks and evidence browsing never contact a model provider.
- Credentials live only in `.env`, are never printed, traced or committed, and are never copied into the process environment wholesale.
- Request data never selects Python code; adapters and packs resolve through a reviewed local catalog.
- The simulator's control plane is loopback-only and token-protected; business tools never see it.
