"""The ``faultlab`` command (v2, early): ``python -m faultlab <subcommand>``.

  packs     list the registered task packs, or print one pack's manifest: packs [<pack_id>] [--digest]
  adapters  list the registered adapters
  run       run a pack's scenarios for one adapter, offline, to sealed envelopes (run --help)
  store     summarise a v2 trial store: store <trials.sqlite3> [--batch <id>]
  project   project every episode of a legacy store into trial envelopes
  oracle    score a legacy store with the belief-versus-effect oracle
  schemas   write the evidence JSON schemas to a directory
"""

import sys


def packs_main(argv) -> int:
    import argparse
    import json

    from faultlab.packs import PackError, load_pack, load_packs

    parser = argparse.ArgumentParser(prog="faultlab packs", description="Registered task packs and their manifests")
    parser.add_argument("pack_id", nargs="?", default=None, help="print this pack's manifest as JSON")
    parser.add_argument("--digest", action="store_true", help="with a pack id, print only its manifest digest")
    args = parser.parse_args(argv)
    if args.pack_id is None:
        for pack in load_packs():
            print(f"{pack.pack_id}\tversion {pack.version}\t{len(pack.tools)} tools\t{len(pack.scenarios)} scenarios\t"
                  f"{len(pack.properties.properties)} properties\tdigest {pack.digest()}")
        return 0
    try:
        pack = load_pack(args.pack_id)
    except PackError as error:
        print(str(error), file=sys.stderr)
        return 2
    print(pack.digest() if args.digest else json.dumps(pack.manifest(), indent=2, sort_keys=True))
    return 0


def store_main(argv) -> int:
    import argparse
    import json
    from pathlib import Path

    from faultlab.lab import TrialStore

    parser = argparse.ArgumentParser(prog="faultlab store", description="Summarise a v2 trial store (read-only)")
    parser.add_argument("path", help="path to a trials.sqlite3 written by the trial worker")
    parser.add_argument("--batch", default=None, help="restrict the summary to one batch id")
    args = parser.parse_args(argv)
    if not Path(args.path).is_file():
        print(f"No trial store at {args.path}", file=sys.stderr)
        return 2
    with TrialStore(args.path) as store:
        print(json.dumps(store.summary(batch_id=args.batch), indent=2, sort_keys=True))
    return 0


def adapters_main(argv) -> int:
    from faultlab.adapters import load_adapters

    if argv:
        print("faultlab adapters takes no arguments", file=sys.stderr)
        return 2
    for adapter in load_adapters():
        spec = adapter.spec
        print(f"{spec.adapter_id}\tversion {spec.version}\tmodel {spec.model}\tpacks {','.join(spec.packs) or 'any'}\tdigest {adapter.digest}")
    return 0


def run_main(argv) -> int:
    from faultlab.lab.cli import main as run
    return run(argv)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"project": "faultlab.evidence.legacy", "oracle": "faultlab.referee.oracle.__main__", "schemas": "faultlab.evidence.schemas"}
    local = {"packs": packs_main, "store": store_main, "adapters": adapters_main, "run": run_main}
    if not argv or argv[0] in ("-h", "--help") or (argv[0] not in commands and argv[0] not in local):
        print(__doc__.strip())
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    if argv[0] in local:
        return local[argv[0]](argv[1:])
    import importlib
    module = importlib.import_module(commands[argv[0]])
    return int(module.main(argv[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
