"""The ``faultlab`` command (v2, early): ``python -m faultlab <subcommand>``.

  project   project every episode of a legacy store into trial envelopes
  oracle    score a legacy store with the belief-versus-effect oracle
  schemas   write the evidence JSON schemas to a directory
"""

import sys


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"project": "faultlab.evidence.legacy", "oracle": "faultlab.referee.oracle.__main__", "schemas": "faultlab.evidence.schemas"}
    if not argv or argv[0] in ("-h", "--help") or argv[0] not in commands:
        print(__doc__.strip())
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    import importlib
    module = importlib.import_module(commands[argv[0]])
    return int(module.main(argv[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
