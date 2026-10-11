"""The ``faultlab`` command (v2, early): ``python -m faultlab <subcommand>``.

  packs     list the registered task packs, or print one pack's manifest: packs [<pack_id>] [--digest]
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


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"project": "faultlab.evidence.legacy", "oracle": "faultlab.referee.oracle.__main__", "schemas": "faultlab.evidence.schemas"}
    if not argv or argv[0] in ("-h", "--help") or (argv[0] not in commands and argv[0] != "packs"):
        print(__doc__.strip())
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    if argv[0] == "packs":
        return packs_main(argv[1:])
    import importlib
    module = importlib.import_module(commands[argv[0]])
    return int(module.main(argv[1:]) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
