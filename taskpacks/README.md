# taskpacks/

New FaultLab tasks live here, **beside** the order task, never inside it.

- Nothing in `backend/` loads this folder yet. Adding files here moves no order-task hash
  (not even `runtime_hash`, which only covers `backend/app`).
- Each pack is a plain-Python folder with its own world, checks, reference agent and tests.
- The first pack is [`bookings_move_with_hold/`](bookings_move_with_hold/README.md): "move a booking
  using a hold". It is at **phase 1**: offline, standard library only, $0.

Run every pack's tests from the repo root:

```
.venv/bin/python -B -m pytest taskpacks -q -p no:cacheprovider
```

`taskpacks/pytest.ini` keeps these runs separate from `backend/pytest.ini` and stops pytest from
writing a cache into the repo. `-B` stops Python writing `__pycache__` bytecode (without it, pytest
writes one `.pyc` for the tests' `conftest.py`).
