"""A dated, operator-verified price table for admitted model calls.

The lab never admits a paid call it cannot bound in dollars. Rates come from two places, in
this order: the explicit ``FAULTLAB_*_DOLLARS_PER_MILLION`` settings that older campaigns
used, then this table. A table entry counts only if the operator marked it ``verified`` and
its ``verified_on`` date is within the staleness window (90 days unless
``FAULTLAB_ALLOW_STALE_PRICES`` is set). Figures copied from aggregators ship unverified.

Importing this module performs no I/O; the table is read when first asked for.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache
import json
import math
from pathlib import Path

DEFAULT_TABLE_PATH = Path(__file__).with_name("pricing.json")
STALE_AFTER = timedelta(days=90)


class PricingTableError(ValueError):
    """The pricing table could not be read or has an invalid entry."""


@dataclass(frozen=True)
class PriceEntry:
    ref: str
    input_per_million: float
    output_per_million: float
    verified: bool
    verified_on: date
    source: str

    def usable(self, *, today: date, allow_stale: bool) -> bool:
        if not self.verified:
            return False
        if allow_stale:
            return True
        return today - self.verified_on <= STALE_AFTER


def _entry(raw: dict) -> PriceEntry:
    try:
        ref = raw["ref"]
        input_rate = float(raw["input_per_million"])
        output_rate = float(raw["output_per_million"])
        verified = raw.get("verified", False)
        verified_on = date.fromisoformat(raw["verified_on"])
        source = str(raw.get("source", ""))
    except (KeyError, TypeError, ValueError) as error:
        raise PricingTableError(f"Invalid pricing entry: {error}") from None
    if not isinstance(ref, str) or ":" not in ref or type(verified) is not bool:
        raise PricingTableError(f"Invalid pricing entry for {ref!r}")
    if not (math.isfinite(input_rate) and math.isfinite(output_rate) and input_rate >= 0 and output_rate >= 0):
        raise PricingTableError(f"Invalid rates for {ref!r}")
    return PriceEntry(ref, input_rate, output_rate, verified, verified_on, source)


def load_table(path: Path | None = None) -> dict[str, PriceEntry]:
    """Read the table; a missing custom path or malformed file is a configuration error.

    Every admitted call prices itself, so one parse is kept per file version (path and mtime).
    """
    table_path = Path(path) if path else DEFAULT_TABLE_PATH
    try:
        stamp = table_path.stat().st_mtime_ns
    except OSError as error:
        raise PricingTableError(f"Cannot read pricing table {table_path.name}: {error}") from None
    return dict(_load_table_version(str(table_path), stamp))


@lru_cache(maxsize=16)
def _load_table_version(table_path_text: str, stamp: int) -> dict[str, PriceEntry]:
    table_path = Path(table_path_text)
    try:
        document = json.loads(table_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise PricingTableError(f"Cannot read pricing table {table_path.name}: {error}") from None
    if not isinstance(document, dict) or document.get("schema") != "faultlab-pricing-table/v1":
        raise PricingTableError("Pricing table schema must be faultlab-pricing-table/v1")
    entries = {}
    for raw in document.get("entries", []):
        entry = _entry(raw)
        if entry.ref in entries:
            raise PricingTableError(f"Duplicate pricing entry for {entry.ref}")
        entries[entry.ref] = entry
    return entries


def table_rates(ref: str, *, path: Path | None = None, allow_stale: bool = False,
                today: date | None = None) -> tuple[float, float] | None:
    """Verified, fresh (input, output) rates for a canonical ``provider:model`` reference, else None."""
    entry = load_table(path).get(ref)
    if entry is None:
        return None
    if not entry.usable(today=today or date.today(), allow_stale=allow_stale):
        return None
    return (entry.input_per_million, entry.output_per_million)


def describe(ref: str, *, path: Path | None = None, today: date | None = None, allow_stale: bool = False) -> dict:
    """A plain summary for operators: whether a model is priced and why not."""
    entry = load_table(path).get(ref)
    if entry is None:
        return {"ref": ref, "status": "unpriced", "reason": "no entry in the pricing table"}
    if not entry.verified:
        return {"ref": ref, "status": "unverified", "reason": "entry is not marked verified", "source": entry.source}
    if not entry.usable(today=today or date.today(), allow_stale=allow_stale):
        return {"ref": ref, "status": "stale", "reason": f"verified_on {entry.verified_on} is older than {STALE_AFTER.days} days",
                "source": entry.source}
    return {"ref": ref, "status": "priced", "input_per_million": entry.input_per_million,
            "output_per_million": entry.output_per_million, "verified_on": entry.verified_on.isoformat(),
            "source": entry.source}
