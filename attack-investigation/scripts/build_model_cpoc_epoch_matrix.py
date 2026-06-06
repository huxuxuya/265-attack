#!/usr/bin/env python3
"""Build compact epoch-level model cPoC matrix."""

from __future__ import annotations

import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "outputs" / "model_cpoc_weight_summary.csv"
OUTPUT = ROOT / "outputs" / "model_cpoc_epoch_matrix.csv"


MODEL_ORDER = ["kimi", "qwen"]
FIELDS = [
    "participants",
    "entry_weight",
    "confirmed_node_weight",
    "preserved_node_weight",
    "node_weight_sum",
]


def decimal_or_zero(value: str | None) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def int_str(value: Decimal) -> str:
    return str(int(value))


def main() -> int:
    by_epoch: dict[str, dict[str, dict[str, Decimal]]] = defaultdict(dict)
    with SUMMARY.open() as fh:
        for row in csv.DictReader(fh):
            epoch = row["epoch"]
            model = row["model_label"]
            by_epoch[epoch][model] = {
                "participants": decimal_or_zero(row.get("participants_in_subgroup")),
                "entry_weight": decimal_or_zero(row.get("entry_weight_sum")),
                "confirmed_node_weight": decimal_or_zero(row.get("confirmed_node_weight_sum")),
                "preserved_node_weight": decimal_or_zero(row.get("preserved_node_weight_sum")),
                "node_weight_sum": decimal_or_zero(row.get("node_weight_sum")),
            }

    columns = ["epoch"]
    for field in FIELDS:
        columns.extend(f"{model}_{field}" for model in MODEL_ORDER)
        columns.append(f"total_{field}")

    rows: list[dict[str, str]] = []
    for epoch in sorted(by_epoch, key=int):
        output = {"epoch": epoch}
        for field in FIELDS:
            total = Decimal(0)
            for model in MODEL_ORDER:
                value = by_epoch[epoch].get(model, {}).get(field, Decimal(0))
                output[f"{model}_{field}"] = int_str(value)
                total += value
            output[f"total_{field}"] = int_str(total)
        rows.append(output)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
