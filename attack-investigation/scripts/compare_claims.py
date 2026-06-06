#!/usr/bin/env python3
"""Compare source compensation totals with the formula-derived reward remainder."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "outputs" / "epoch_summary.csv"
AFFECTED = ROOT / "outputs" / "affected_rows.csv"
OUTPUT = ROOT / "outputs" / "claim_vs_chain.csv"


COLUMNS = [
    "epoch",
    "source_compensation_gonka",
    "actual_rewarded_gonka",
    "burned_gonka",
    "undistributed_remainder_gonka",
    "difference",
    "notes",
]


def decimal_or_none(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f")


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()

    summary_rows = read_csv(SUMMARY)
    affected_rows = read_csv(AFFECTED)

    claims_by_epoch: dict[str, Decimal] = {}
    claim_rows_by_epoch: dict[str, int] = {}
    for row in affected_rows:
        if row.get("source") == "chain":
            continue
        epoch = row.get("epoch", "")
        if epoch:
            claim_rows_by_epoch[epoch] = claim_rows_by_epoch.get(epoch, 0) + 1
        amount = decimal_or_none(row.get("source_compensation_gonka"))
        if not epoch or amount is None:
            continue
        claims_by_epoch[epoch] = claims_by_epoch.get(epoch, Decimal(0)) + amount

    output_rows: list[dict[str, str]] = []
    for summary in summary_rows:
        epoch = summary.get("epoch", "")
        has_claim_rows = claim_rows_by_epoch.get(epoch, 0) > 0
        source_comp = claims_by_epoch.get(epoch) if has_claim_rows else None
        remainder = decimal_or_none(summary.get("undistributed_remainder_gonka"))
        difference = source_comp - remainder if source_comp is not None and remainder is not None else None
        if not has_claim_rows:
            notes = "no source claim rows loaded"
        elif difference is None:
            notes = "formula-derived remainder not computable from saved raw data"
        else:
            notes = "difference is source compensation minus formula-derived base reward remainder"
        output_rows.append(
            {
                "epoch": epoch,
                "source_compensation_gonka": decimal_text(source_comp),
                "actual_rewarded_gonka": summary.get("actual_rewarded_gonka", ""),
                "burned_gonka": summary.get("burned_gonka", ""),
                "undistributed_remainder_gonka": summary.get("undistributed_remainder_gonka", ""),
                "difference": decimal_text(difference),
                "notes": notes,
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(output_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
