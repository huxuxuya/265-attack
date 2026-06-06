#!/usr/bin/env python3
"""Compare formula remainder with chain-observed gov balance movements."""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "outputs" / "epoch_summary.csv"
GOV_CHANGES = ROOT / "outputs" / "gov_balance_change_points.csv"
MODULE_DELTAS = ROOT / "outputs" / "module_balance_deltas.csv"
OUTPUT = ROOT / "outputs" / "gov_settlement_audit.csv"


COLUMNS = [
    "epoch",
    "main_gov_jump_height",
    "paid_rewards_gnk",
    "base_reward_formula_gnk",
    "formula_remainder_gnk",
    "main_gov_jump_gnk",
    "other_gov_changes_gnk",
    "gov_delta_during_epoch_gnk",
    "main_gov_jump_minus_formula_remainder_gnk",
    "gov_delta_minus_formula_remainder_gnk",
    "paid_plus_main_gov_jump_gnk",
    "paid_plus_main_gov_jump_minus_base_formula_gnk",
]


def decimal_or_zero(value: str | None) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def fmt(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def read_by_epoch(path: Path) -> dict[str, dict[str, str]]:
    with path.open() as fh:
        return {row["epoch"]: row for row in csv.DictReader(fh)}


def read_gov_delta_by_epoch(path: Path) -> dict[str, Decimal]:
    values: dict[str, Decimal] = {}
    with path.open() as fh:
        for row in csv.DictReader(fh):
            if row.get("module_name") == "gov":
                values[row["epoch"]] = decimal_or_zero(row.get("delta_start_to_last_gnk"))
    return values


def main_gov_jumps(path: Path) -> dict[str, dict[str, str]]:
    jumps: dict[str, dict[str, str]] = {}
    with path.open() as fh:
        for row in csv.DictReader(fh):
            epoch = row["epoch"]
            current = decimal_or_zero(row.get("delta_gnk"))
            previous = decimal_or_zero(jumps.get(epoch, {}).get("delta_gnk"))
            if epoch not in jumps or abs(current) > abs(previous):
                jumps[epoch] = row
    return jumps


def main() -> int:
    summaries = read_by_epoch(SUMMARY)
    gov_deltas = read_gov_delta_by_epoch(MODULE_DELTAS)
    jumps = main_gov_jumps(GOV_CHANGES)

    rows: list[dict[str, str]] = []
    for epoch in sorted(summaries, key=int):
        summary = summaries[epoch]
        jump = jumps.get(epoch, {})
        paid = decimal_or_zero(summary.get("paid_rewards_gnk"))
        base_reward = decimal_or_zero(summary.get("epoch_reward_pool_gnk"))
        formula_remainder = decimal_or_zero(summary.get("not_paid_rewards_gnk"))
        main_jump = decimal_or_zero(jump.get("delta_gnk"))
        gov_delta = gov_deltas.get(epoch, Decimal(0))
        paid_plus_main_jump = paid + main_jump
        rows.append(
            {
                "epoch": epoch,
                "main_gov_jump_height": jump.get("height", ""),
                "paid_rewards_gnk": fmt(paid),
                "base_reward_formula_gnk": fmt(base_reward),
                "formula_remainder_gnk": fmt(formula_remainder),
                "main_gov_jump_gnk": fmt(main_jump),
                "other_gov_changes_gnk": fmt(gov_delta - main_jump),
                "gov_delta_during_epoch_gnk": fmt(gov_delta),
                "main_gov_jump_minus_formula_remainder_gnk": fmt(main_jump - formula_remainder),
                "gov_delta_minus_formula_remainder_gnk": fmt(gov_delta - formula_remainder),
                "paid_plus_main_gov_jump_gnk": fmt(paid_plus_main_jump),
                "paid_plus_main_gov_jump_minus_base_formula_gnk": fmt(paid_plus_main_jump - base_reward),
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
