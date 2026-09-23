# Offline CI

The `Offline checks` GitHub Actions workflow runs on pushes, pull requests and manual dispatch. It uses Python 3.12, Node 22, the existing Python and npm lockfiles, and Playwright Chromium. The official checkout/setup actions are pinned to commit hashes; the workflow has read-only repository access and receives no provider credentials.

The workflow runs the same `./scripts/test.sh` used locally:

1. Backend tests check contracts, budgets, lifecycle, simulator behavior and integrations. Tests block outbound network access; explicitly marked integration tests may use loopback HTTP.
2. Frontend tests check state and controls.
3. The production build checks TypeScript and bundles the frontend.
4. Browser fixture tests check the interface. The optional real local browser smoke remains disabled in CI; it requires an explicitly started backend and simulator.

Dependency and browser installation downloads packages. The checks do not call model providers, publish Weave evidence, run Aria or deploy the application. A failing command stops the job with a nonzero exit code.

To run locally, use `./scripts/setup.sh`, install the browser with `cd frontend && ./node_modules/.bin/playwright install chromium` if needed, then run `./scripts/test.sh` from the repository root. These checks establish offline correctness; live provider access, observed agent performance and sponsor verification remain separate evidence.
