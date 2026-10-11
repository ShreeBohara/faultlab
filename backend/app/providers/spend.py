"""A monthly spend ledger shared by every store, campaign and smoke check on this machine.

Each admitted model call reserves its *worst-case* dollar bound before it is sent; the
reservation is refused when the calendar month's reserved total would exceed the monthly
cap. After the response the row is settled with the measured cost when tokens are known.
The month's figure that gates admission is the sum of bounds, never the sum of measured
costs, so a runaway loop cannot spend past the cap on optimistic estimates.

The ledger is one SQLite file under the artifact directory. It is append-only: rows are
settled, never deleted, and a crash between reserve and settle leaves the bound charged.
"""

from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


class MonthlyCapExceeded(RuntimeError):
    def __init__(self, *, month: str, reserved: float, bound: float, cap: float):
        super().__init__(f"Monthly cap reached: {reserved:.4f} reserved + {bound:.4f} > {cap:.2f} for {month}")
        self.month, self.reserved, self.bound, self.cap = month, reserved, bound, cap


@dataclass(frozen=True)
class SpendSummary:
    month: str
    reserved_bound: float
    settled_actual: float | None
    calls: int


def current_month(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m")


class SpendLedger:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS charges (
                id INTEGER PRIMARY KEY, month TEXT NOT NULL, at TEXT NOT NULL, provider TEXT NOT NULL,
                model TEXT NOT NULL, role TEXT NOT NULL, bound_usd REAL NOT NULL, actual_usd REAL,
                input_tokens INTEGER, output_tokens INTEGER, note TEXT NOT NULL DEFAULT '')""")
            connection.execute("CREATE INDEX IF NOT EXISTS charges_month ON charges(month)")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def reserve(self, *, provider: str, model: str, role: str, bound_usd: float, cap_usd: float,
                note: str = "", now: datetime | None = None) -> int:
        """Charge the worst-case bound for one call, or refuse without recording anything."""
        if not (bound_usd >= 0 and cap_usd >= 0):
            raise ValueError("bound and cap must be non-negative")
        month = current_month(now)
        at = (now or datetime.now(timezone.utc)).isoformat()
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                reserved = connection.execute("SELECT COALESCE(SUM(bound_usd), 0) FROM charges WHERE month = ?",
                                              (month,)).fetchone()[0]
                if reserved + bound_usd > cap_usd:
                    raise MonthlyCapExceeded(month=month, reserved=reserved, bound=bound_usd, cap=cap_usd)
                cursor = connection.execute(
                    "INSERT INTO charges(month, at, provider, model, role, bound_usd, note) VALUES (?,?,?,?,?,?,?)",
                    (month, at, provider, model, role, bound_usd, note))
                connection.execute("COMMIT")
                return int(cursor.lastrowid)
            except BaseException:
                connection.execute("ROLLBACK")
                raise

    def settle(self, charge_id: int, *, actual_usd: float | None, input_tokens: int | None,
               output_tokens: int | None) -> None:
        with closing(self._connect()) as connection:
            connection.execute("UPDATE charges SET actual_usd = ?, input_tokens = ?, output_tokens = ? WHERE id = ?",
                               (actual_usd, input_tokens, output_tokens, charge_id))

    def summary(self, month: str | None = None) -> SpendSummary:
        month = month or current_month()
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT COALESCE(SUM(bound_usd), 0), SUM(actual_usd), COUNT(*), COUNT(actual_usd) FROM charges WHERE month = ?",
                (month,)).fetchone()
        reserved, actual, calls, settled = row
        return SpendSummary(month=month, reserved_bound=float(reserved),
                            settled_actual=float(actual) if settled == calls and calls else None, calls=int(calls))
