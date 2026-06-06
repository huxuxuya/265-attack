#!/usr/bin/env python3
"""Build per-miner detail table for zero-reward participants."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUT = ROOT / "outputs" / "unpaid_miners_detail.csv"
SUMMARY_OUTPUT = ROOT / "outputs" / "unpaid_reason_summary.csv"
DEFAULT_DENOM_EXPONENT = 6


COLUMNS = [
    "epoch",
    "address",
    "reason_class",
    "reason_detail",
    "reward_gnk",
    "earned_gnk",
    "inference_count",
    "missed_requests",
    "validated_inferences",
    "invalidated_inferences",
    "confirmation_weight",
    "reputation",
    "poc_snapshot_found",
    "claimed",
    "in_final_group",
    "excluded_from_final_group",
]

SUMMARY_COLUMNS = ["epoch", "reason_class", "count"]


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def to_gnk(value: Any, denom_exponent: int) -> str:
    scaled = decimal_or_zero(value) / (Decimal(10) ** denom_exponent)
    return format(scaled.quantize(Decimal("0.000001")), "f")


def rows_from_performance(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict) and isinstance(data.get("epochPerformanceSummary"), list):
        return [row for row in data["epochPerformanceSummary"] if isinstance(row, dict)]
    return []


def final_group_index(group: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(group, dict):
        return {}
    epoch_group = group.get("epoch_group_data", group)
    if not isinstance(epoch_group, dict):
        return {}
    weights = epoch_group.get("validation_weights") or []
    if not isinstance(weights, list):
        return {}
    return {
        str(row.get("member_address")): row
        for row in weights
        if isinstance(row, dict) and row.get("member_address")
    }


def poc_snapshot_found(snapshot: Any) -> str:
    if isinstance(snapshot, dict) and snapshot.get("found") is True:
        return "yes"
    return "no"


def reason_for(
    row: dict[str, Any],
    final_row: dict[str, Any] | None,
    snapshot_found: str,
) -> tuple[str, str]:
    in_final_group = final_row is not None
    missed = decimal_or_zero(row.get("missed_requests"))
    invalidated = decimal_or_zero(row.get("invalidated_inferences"))
    inferences = decimal_or_zero(row.get("inference_count"))
    validated = decimal_or_zero(row.get("validated_inferences"))
    earned = decimal_or_zero(row.get("earned_coins"))
    confirmation_weight = decimal_or_zero(final_row.get("confirmation_weight")) if final_row else Decimal(0)
    reputation = final_row.get("reputation") if final_row else ""
    claimed = row.get("claimed")

    reasons: list[str] = []
    if not in_final_group:
        reasons.append("not in final validation_weights")
    else:
        reasons.append(f"confirmation_weight={confirmation_weight}")
        if reputation != "":
            reasons.append(f"reputation={reputation}")
    if snapshot_found == "no":
        reasons.append("poc_validation_snapshot found=false")
    if claimed is False:
        reasons.append("claimed=false")
    if missed > 0:
        reasons.append(f"missed_requests={missed}")
    if invalidated > 0:
        reasons.append(f"invalidated_inferences={invalidated}")
    if inferences == 0 and validated == 0:
        reasons.append("no recorded inference/validation work")
    if earned == 0:
        reasons.append("earned_coins=0")

    if not in_final_group:
        reason_class = "excluded_from_final_group"
    elif confirmation_weight == 0:
        reason_class = "confirmation_poc_zero_weight"
    elif missed > 0 or invalidated > 0:
        reason_class = "missed_or_invalidated_work"
    elif inferences == 0 and validated == 0:
        reason_class = "no_recorded_work"
    elif claimed is False and earned == 0:
        reason_class = "not_claimed_zero_earned"
    else:
        reason_class = "zero_reward_unresolved"

    return reason_class, "; ".join(reasons)


def build_rows(denom_exponent: int) -> list[dict[str, str]]:
    output_rows: list[dict[str, str]] = []
    for epoch_dir in sorted(path for path in RAW_ROOT.glob("epoch_*") if path.is_dir()):
        epoch = epoch_dir.name.replace("epoch_", "")
        performance = read_json(epoch_dir / "epoch_performance_summary.json")
        group = read_json(epoch_dir / "epoch_group_data.json")
        final_rows = final_group_index(group)
        snapshot_found = poc_snapshot_found(read_json(epoch_dir / "poc_validation_snapshot.json"))

        for row in rows_from_performance(performance):
            reward = decimal_or_zero(row.get("rewarded_coins"))
            if reward != 0:
                continue
            address = str(row.get("participant_id", ""))
            final_row = final_rows.get(address)
            in_final_group = final_row is not None
            reason_class, reason_detail = reason_for(row, final_row, snapshot_found)
            output_rows.append(
                {
                    "epoch": epoch,
                    "address": address,
                    "reason_class": reason_class,
                    "reason_detail": reason_detail,
                    "reward_gnk": to_gnk(row.get("rewarded_coins"), denom_exponent),
                    "earned_gnk": to_gnk(row.get("earned_coins"), denom_exponent),
                    "inference_count": str(row.get("inference_count", "")),
                    "missed_requests": str(row.get("missed_requests", "")),
                    "validated_inferences": str(row.get("validated_inferences", "")),
                    "invalidated_inferences": str(row.get("invalidated_inferences", "")),
                    "confirmation_weight": str(final_row.get("confirmation_weight", "")) if final_row else "",
                    "reputation": str(final_row.get("reputation", "")) if final_row else "",
                    "poc_snapshot_found": snapshot_found,
                    "claimed": str(row.get("claimed", "")).lower(),
                    "in_final_group": "yes" if in_final_group else "no",
                    "excluded_from_final_group": "no" if in_final_group else "yes",
                }
            )
    return output_rows


def build_summary(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    counts = Counter((row["epoch"], row["reason_class"]) for row in rows)
    return [
        {"epoch": epoch, "reason_class": reason_class, "count": str(count)}
        for (epoch, reason_class), count in sorted(counts.items())
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--denom-exponent", type=int, default=DEFAULT_DENOM_EXPONENT)
    args = parser.parse_args()

    rows = build_rows(args.denom_exponent)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    summary_rows = build_summary(rows)
    with SUMMARY_OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(rows)} rows.")
    print(f"Wrote {SUMMARY_OUTPUT.relative_to(ROOT)} with {len(summary_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
