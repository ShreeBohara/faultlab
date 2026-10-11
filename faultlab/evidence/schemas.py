"""Export the v2 evidence schemas as JSON Schema documents (``python -m faultlab.evidence.schemas DIR``)."""

import argparse
import json
from pathlib import Path

from faultlab.evidence.models import (SCHEMA_VERSION, EvidenceEvent, Finding, ResultVector, TrialAttempt, TrialEnvelope,
                                      TrialPlan, schema_digest)

DOCUMENTS = {"TrialEnvelope": TrialEnvelope, "TrialPlan": TrialPlan, "TrialAttempt": TrialAttempt,
             "EvidenceEvent": EvidenceEvent, "Finding": Finding, "ResultVector": ResultVector}


def export(directory) -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in DOCUMENTS.items():
        path = directory / f"{name}.schema.json"
        path.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    readme = directory / "README.md"
    readme.write_text("\n".join([
        "# FaultLab v2 evidence schemas", "",
        f"Generated from `faultlab.evidence.models` (schema version `{SCHEMA_VERSION}`, envelope schema digest",
        f"`{schema_digest()}`). Regenerate with `python -m faultlab.evidence.schemas docs/schemas/v2` from the",
        "repository root; a test fails when the committed files are stale.", "",
        *[f"- `{name}.schema.json`: {model.__doc__.strip().splitlines()[0] if model.__doc__ else name}" for name, model in DOCUMENTS.items()],
        ""]), encoding="utf-8")
    written.append(readme)
    return written


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Write the v2 evidence JSON schemas")
    parser.add_argument("directory")
    args = parser.parse_args(argv)
    for path in export(args.directory):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
