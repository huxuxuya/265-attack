#!/usr/bin/env python3
"""Build detailed and aggregate reward status tables."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
GOV_AUDIT = ROOT / "outputs" / "gov_settlement_audit.csv"
DETAIL_OUTPUT = ROOT / "outputs" / "not_received_hosts_detail.csv"
COUNT_OUTPUT = ROOT / "outputs" / "reward_status_count_summary.csv"
AMOUNT_OUTPUT = ROOT / "outputs" / "reward_status_amount_summary.csv"
DENOM_EXPONENT = 6


REASON_CLASSES = [
    "received_reward",
    "confirmation_poc_zero_weight",
    "missed_or_invalidated_work",
    "excluded_from_final_group",
    "no_recorded_work",
    "not_claimed_zero_earned",
    "zero_reward_unresolved",
]

DETAIL_COLUMNS = [
    "epoch",
    "address",
    "reason_class",
    "chain_received_gnk",
    "reconstructed_not_received_gnk",
    "reconstruction_status",
    "reconstruction_basis",
    "weight",
    "confirmation_weight",
    "settlement_effective_weight",
    "epoch_full_rate_ngnk_per_weight",
    "earned_gnk",
    "inference_count",
    "missed_requests",
    "validated_inferences",
    "invalidated_inferences",
    "claimed",
    "reason_detail",
]

COUNT_COLUMNS = ["epoch", "total_hosts", *REASON_CLASSES]

AMOUNT_COLUMNS = [
    "epoch",
    "chain_paid_to_received_hosts_gnk",
    "chain_main_gov_jump_gnk",
    "reconstructed_not_received_total_gnk",
    "reconstruction_residual_vs_main_gov_jump_gnk",
    *[f"{reason}_gnk" for reason in REASON_CLASSES],
]


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def to_gnk(value: Decimal) -> str:
    scaled = value / (Decimal(10) ** DENOM_EXPONENT)
    return format(scaled.quantize(Decimal("0.000001")), "f")


def fmt_gnk_value(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


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


def gov_audit_by_epoch() -> dict[str, dict[str, str]]:
    if not GOV_AUDIT.exists():
        return {}
    with GOV_AUDIT.open() as fh:
        return {row["epoch"]: row for row in csv.DictReader(fh)}


def reason_for(row: dict[str, Any], final_row: dict[str, Any] | None) -> tuple[str, str]:
    missed = decimal_or_zero(row.get("missed_requests"))
    invalidated = decimal_or_zero(row.get("invalidated_inferences"))
    inferences = decimal_or_zero(row.get("inference_count"))
    validated = decimal_or_zero(row.get("validated_inferences"))
    earned = decimal_or_zero(row.get("earned_coins"))
    confirmation_weight = decimal_or_zero(final_row.get("confirmation_weight")) if final_row else Decimal(0)
    claimed = row.get("claimed")

    details: list[str] = []
    if final_row is None:
        details.append("not in final validation_weights")
    else:
        details.append(f"weight={final_row.get('weight')}")
        details.append(f"confirmation_weight={final_row.get('confirmation_weight')}")
        details.append(f"reputation={final_row.get('reputation')}")
    if claimed is False:
        details.append("claimed=false")
    if missed > 0:
        details.append(f"missed_requests={missed}")
    if invalidated > 0:
        details.append(f"invalidated_inferences={invalidated}")
    if inferences == 0 and validated == 0:
        details.append("no recorded inference/validation work")
    if earned == 0:
        details.append("earned_coins=0")

    if final_row is None:
        return "excluded_from_final_group", "; ".join(details)
    if confirmation_weight == 0:
        return "confirmation_poc_zero_weight", "; ".join(details)
    if missed > 0 or invalidated > 0:
        return "missed_or_invalidated_work", "; ".join(details)
    if inferences == 0 and validated == 0:
        return "no_recorded_work", "; ".join(details)
    if claimed is False and earned == 0:
        return "not_claimed_zero_earned", "; ".join(details)
    return "zero_reward_unresolved", "; ".join(details)


def full_rate(perf_rows: list[dict[str, Any]], final_rows: dict[str, dict[str, Any]]) -> Decimal:
    rates: list[Decimal] = []
    for row in perf_rows:
        reward = decimal_or_zero(row.get("rewarded_coins"))
        if reward <= 0:
            continue
        final_row = final_rows.get(str(row.get("participant_id", "")))
        if not final_row:
            continue
        weight = decimal_or_zero(final_row.get("weight"))
        confirmation_weight = decimal_or_zero(final_row.get("confirmation_weight"))
        effective_weight = min(weight, confirmation_weight)
        if effective_weight > 0:
            rates.append(reward / effective_weight)
    return max(rates) if rates else Decimal(0)


def reconstructed_amount(
    reason_class: str,
    final_row: dict[str, Any] | None,
    rate: Decimal,
) -> tuple[Decimal, str, str]:
    if final_row is None:
        return Decimal(0), "requires_model", "excluded host has no final validation weight in saved chain data"

    weight = decimal_or_zero(final_row.get("weight"))
    confirmation_weight = decimal_or_zero(final_row.get("confirmation_weight"))
    effective_weight = min(weight, confirmation_weight)

    if reason_class == "confirmation_poc_zero_weight":
        return (
            weight * rate,
            "counterfactual_estimate",
            "full-rate estimate using final weight; actual settlement effective weight is zero",
        )
    if reason_class == "missed_or_invalidated_work":
        return (
            effective_weight * rate,
            "counterfactual_estimate",
            "full-rate estimate using min(weight, confirmation_weight)",
        )
    return Decimal(0), "requires_policy_or_model", "no reliable per-host amount from saved chain fields"


def total_row(rows: list[dict[str, str]]) -> dict[str, str]:
    total: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        for key, value in row.items():
            if key == "epoch":
                continue
            total[key] += decimal_or_zero(value)
    output = {"epoch": "TOTAL"}
    for key in rows[0].keys():
        if key == "epoch":
            continue
        if key == "total_hosts" or key in REASON_CLASSES:
            output[key] = str(int(total[key]))
        else:
            output[key] = fmt_gnk_value(total[key])
    return output


def build() -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    gov_audit = gov_audit_by_epoch()
    detail_rows: list[dict[str, str]] = []
    count_rows: list[dict[str, str]] = []
    amount_rows: list[dict[str, str]] = []

    for epoch_dir in sorted(path for path in RAW_ROOT.glob("epoch_*") if path.is_dir()):
        epoch = epoch_dir.name.replace("epoch_", "")
        performance = read_json(epoch_dir / "epoch_performance_summary.json")
        group = read_json(epoch_dir / "epoch_group_data.json")
        perf_rows = rows_from_performance(performance)
        final_rows = final_group_index(group)
        rate = full_rate(perf_rows, final_rows)

        counts: Counter[str] = Counter()
        amount_by_reason: defaultdict[str, Decimal] = defaultdict(Decimal)
        paid_total = Decimal(0)
        reconstructed_total = Decimal(0)

        for row in perf_rows:
            address = str(row.get("participant_id", ""))
            reward = decimal_or_zero(row.get("rewarded_coins"))
            final_row = final_rows.get(address)
            if reward > 0:
                counts["received_reward"] += 1
                paid_total += reward / (Decimal(10) ** DENOM_EXPONENT)
                amount_by_reason["received_reward"] += reward / (Decimal(10) ** DENOM_EXPONENT)
                continue

            reason_class, reason_detail = reason_for(row, final_row)
            estimated_ngonk, reconstruction_status, reconstruction_basis = reconstructed_amount(reason_class, final_row, rate)
            reconstructed_gnk = estimated_ngonk / (Decimal(10) ** DENOM_EXPONENT)
            reconstructed_total += reconstructed_gnk
            amount_by_reason[reason_class] += reconstructed_gnk
            counts[reason_class] += 1

            weight = decimal_or_zero(final_row.get("weight")) if final_row else Decimal(0)
            confirmation_weight = decimal_or_zero(final_row.get("confirmation_weight")) if final_row else Decimal(0)
            effective_weight = min(weight, confirmation_weight) if final_row else Decimal(0)
            detail_rows.append(
                {
                    "epoch": epoch,
                    "address": address,
                    "reason_class": reason_class,
                    "chain_received_gnk": to_gnk(reward),
                    "reconstructed_not_received_gnk": fmt_gnk_value(reconstructed_gnk),
                    "reconstruction_status": reconstruction_status,
                    "reconstruction_basis": reconstruction_basis,
                    "weight": str(weight) if final_row else "",
                    "confirmation_weight": str(confirmation_weight) if final_row else "",
                    "settlement_effective_weight": str(effective_weight) if final_row else "",
                    "epoch_full_rate_ngnk_per_weight": format(rate.quantize(Decimal("0.000001")), "f"),
                    "earned_gnk": to_gnk(decimal_or_zero(row.get("earned_coins"))),
                    "inference_count": str(row.get("inference_count", "")),
                    "missed_requests": str(row.get("missed_requests", "")),
                    "validated_inferences": str(row.get("validated_inferences", "")),
                    "invalidated_inferences": str(row.get("invalidated_inferences", "")),
                    "claimed": str(row.get("claimed", "")).lower(),
                    "reason_detail": reason_detail,
                }
            )

        count_row = {"epoch": epoch, "total_hosts": str(sum(counts.values()))}
        for reason in REASON_CLASSES:
            count_row[reason] = str(counts[reason])
        count_rows.append(count_row)

        main_gov_jump = decimal_or_zero(gov_audit.get(epoch, {}).get("main_gov_jump_gnk"))
        amount_row = {
            "epoch": epoch,
            "chain_paid_to_received_hosts_gnk": fmt_gnk_value(paid_total),
            "chain_main_gov_jump_gnk": fmt_gnk_value(main_gov_jump),
            "reconstructed_not_received_total_gnk": fmt_gnk_value(reconstructed_total),
            "reconstruction_residual_vs_main_gov_jump_gnk": fmt_gnk_value(main_gov_jump - reconstructed_total),
        }
        for reason in REASON_CLASSES:
            amount_row[f"{reason}_gnk"] = fmt_gnk_value(amount_by_reason[reason])
        amount_rows.append(amount_row)

    if count_rows:
        count_rows.append(total_row(count_rows))
    if amount_rows:
        amount_rows.append(total_row(amount_rows))
    return detail_rows, count_rows, amount_rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    detail_rows, count_rows, amount_rows = build()
    write_csv(DETAIL_OUTPUT, DETAIL_COLUMNS, detail_rows)
    write_csv(COUNT_OUTPUT, COUNT_COLUMNS, count_rows)
    write_csv(AMOUNT_OUTPUT, AMOUNT_COLUMNS, amount_rows)
    print(f"Wrote {DETAIL_OUTPUT.relative_to(ROOT)} with {len(detail_rows)} rows.")
    print(f"Wrote {COUNT_OUTPUT.relative_to(ROOT)} with {len(count_rows)} rows.")
    print(f"Wrote {AMOUNT_OUTPUT.relative_to(ROOT)} with {len(amount_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
