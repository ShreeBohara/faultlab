# Diagnosis-rule golden fixtures

These fourteen files are exact byte copies from source commit
`d022228e0e1b19015e09e7a40ef9e8f9f29745e2` (`d022228`). They make
`backend/tests/lab/test_diagnosis_rules.py` and
`backend/tests/experiments/test_diagnosis_probe.py` runnable in a source-only checkout
without the historical `artifacts/` directories.

The fixture requests and recorded answers concern the synthetic, public development
cases **dev-5 and dev-6**, from runs v2d, v2e, v2f, and v2g. The four accompanying
campaign exports also retain those campaigns' other public development trials. They preserve the
September 30, 2026 diagnosis-rule analysis, including the original prototype code,
measurements, and results. These are historical golden inputs and scripted replay
answers, not new provider results or evidence of an accepted generated policy.

No fixture data was changed, reformatted, or regenerated. All eight file SHA-256
pins already present in the diagnosis-rule test match these copies and remain
unchanged. The four export hashes pinned by the production probe script also match
and remain unchanged. The production probe script keeps its original paths and
bytes; its test injects only the fixture input/export paths after loading it. The two
measurement/result JSON files retain their original bytes too; their hashes are
recorded below, and the existing tests still assert their semantic contents.
Test assertions, gate/source pins, and the separate historical-store test were not
changed. Historical artifacts were neither modified nor deleted.

Before copying, the JSON fields (including JSON embedded in messages) and Python
string literals were inspected for credential-shaped values, credential fields,
and protected/private artifact markers; none were found. No protected files or
secret configuration were used. Prototype paths and comments are preserved as
historical context; the test loads the prototypes from this fixture directory.

## Original locations

`probe-inputs/*` came from
`artifacts/product-diagnosis-rules-2026-09-30/probe-inputs/`.
The `inv-a/`, `design-minimal/`, and `designer-integrity/` files came from the same
relative subpaths under `artifacts/analysis-diagnosis-2026-09-30/`.
`exports/<run>.json` came from
`artifacts/product-live-2026-09-30/native-<run>-run/export.json`, for runs v2d, v2e,
v2f, and v2g. These exact exports total 8,369,172 bytes; retaining them preserves
the existing full-file integrity checks. Recursive field and embedded-message
inspection found development splits only and no credential/private artifact flags.
Each copy was retrieved directly with `git show <source-commit>:<original-path>`.

## SHA-256 inventory

| Fixture | SHA-256 | Existing direct file pin |
| --- | --- | --- |
| `probe-inputs/v2d-dev5-diagnosis-request.json` | `7cb9ac8c3338d49b59cde38b8cc58747e18a3073a56426b78b8a48228296d03d` | Yes |
| `probe-inputs/v2e-dev5-diagnosis-request.json` | `905228fbdda067b467a8e1b0e9bf2807854c44720b4e4d1362eb718c53e6f655` | Yes |
| `probe-inputs/v2f-dev5-diagnosis-request.json` | `4ab16a7e3665209fd015255c47a955e17a708e62c6fc3791f7f259fb72011672` | Yes |
| `probe-inputs/v2g-dev5-diagnosis-request.json` | `098c2cda59979cd60e7f86b4dc41cc4382b787886e9e817447756167ac97e13b` | Yes |
| `probe-inputs/v2g-dev6-diagnosis-request.json` | `d76f2e4ad3f7ce7918b5a9b05cebfb62849281902a60962ca6fd530514fe287e` | Yes |
| `inv-a/mechanic-outputs.json` | `fd48d11197d164509fa2345a500429c1df3f4a689db2984c426a552335e3e166` | Yes |
| `design-minimal/proposed_diagnosis_guide.py` | `dde3c9c2abaf503d79e7a1e12c40b28e5165b48354aff1814ac2bf676e3b2f02` | Yes |
| `design-minimal/guide-measurement.json` | `0f9b1312da34af1d3acfb9c92ad2bf2d6fd3a3a84ef91301f94d0167dc6c4bd7` | No; existing semantic assertions |
| `designer-integrity/prototype_declared_semantics.py` | `3b06bfb2928937aa0ef9be24bc30dc950fdee93d671818d8794680a15e5dbdfd` | Yes |
| `designer-integrity/prototype-results.json` | `dab64b4b97a059d3b0fe1d20ed350a4eff03353581116b35ea52ef2afde48890` | No; existing semantic assertions |
| `exports/v2d.json` | `6f83806413c934a1c869f1995cff87ff5aef0daf331a35e34a37de0b0893d0c8` | Yes; production probe export pin |
| `exports/v2e.json` | `25d48347de9ad13281b6ec025ca58648c4836d091678be3d6fab9fe7b8ab163e` | Yes; production probe export pin |
| `exports/v2f.json` | `77f223988079df99cb2f9f4ad65a12403ce2fe6dc805eef514861867d72a891d` | Yes; production probe export pin |
| `exports/v2g.json` | `b0b4db320908afb7d61d0c00fdc48d960cf3f3a002451f9ecc90e99acac397fc` | Yes; production probe export pin |
