#!/usr/bin/env python3
"""Build model-level PoC/cPoC weight table from saved model subgroup data."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUT = ROOT / "outputs" / "model_cpoc_weight_table.csv"
SUMMARY_OUTPUT = ROOT / "outputs" / "model_cpoc_weight_summary.csv"


MODEL_LABELS = {
    "moonshotai/Kimi-K2.6": "kimi",
    "Qwen/Qwen3-235B-A22B-Instruct-2507-FP8": "qwen",
}

BASE_COLUMNS = [
    "epoch",
    "address",
    "received_reward",
    "rewarded_gnk",
    "parent_entry_weight",
    "parent_confirmation_weight",
    "parent_voting_power",
]

PER_MODEL_FIELDS = [
    "entry_weight",
    "subgroup_confirmation_weight",
    "voting_power",
    "confirmed_node_weight",
    "preserved_node_weight",
    "node_weight_sum",
    "node_count",
    "preserved_node_count",
]

TOTAL_COLUMNS = [
    "confirmed_node_weight_total",
    "preserved_node_weight_total",
    "node_weight_sum_total",
    "model_entry_weight_sum",
    "model_subgroup_confirmation_weight_sum",
    "model_voting_power_sum",
    "parent_minus_model_entry_weight_sum",
    "notes",
]

SUMMARY_COLUMNS = [
    "epoch",
    "model_id",
    "model_label",
    "participants_in_subgroup",
    "entry_weight_sum",
    "confirmed_node_weight_sum",
    "preserved_node_weight_sum",
    "node_weight_sum",
    "subgroup_confirmation_weight_sum",
    "voting_power_sum",
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


def int_str(value: Decimal) -> str:
    return str(int(value))


def to_gnk(value: Decimal) -> str:
    return format((value / Decimal(1_000_000)).quantize(Decimal("0.000001")), "f")


def performance_index(epoch_dir: Path) -> dict[str, dict[str, Any]]:
    data = read_json(epoch_dir / "epoch_performance_summary.json")
    rows = data.get("epochPerformanceSummary", []) if isinstance(data, dict) else []
    return {str(row.get("participant_id")): row for row in rows if isinstance(row, dict)}


def parent_weight_index(epoch_dir: Path) -> dict[str, dict[str, Any]]:
    data = read_json(epoch_dir / "epoch_group_data.json")
    group = data.get("epoch_group_data", {}) if isinstance(data, dict) else {}
    rows = group.get("validation_weights", []) if isinstance(group, dict) else []
    return {str(row.get("member_address")): row for row in rows if isinstance(row, dict)}


def model_group_paths(epoch_dir: Path) -> list[Path]:
    return sorted((epoch_dir / "model_group_data").glob("*.json"))


def label_for(model_id: str) -> str:
    return MODEL_LABELS.get(model_id, "".join(ch if ch.isalnum() else "_" for ch in model_id).strip("_").lower())


def preserved_lookup(epoch_dir: Path) -> dict[str, dict[str, set[str]]]:
    output: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    parent = read_json(epoch_dir / "epoch_group_data.json")
    group = parent.get("epoch_group_data", {}) if isinstance(parent, dict) else {}
    poc_start = group.get("poc_start_block_height")
    if poc_start in (None, ""):
        return output
    snapshot = read_json(epoch_dir / "model_group_data" / f"preserved_nodes_snapshot_at_{poc_start}.json")
    data = snapshot.get("snapshot", {}) if isinstance(snapshot, dict) else {}
    for model_entry in data.get("model_preserved_nodes", []) or []:
        if not isinstance(model_entry, dict):
            continue
        model_id = str(model_entry.get("model_id", ""))
        if not model_id:
            continue
        for participant in model_entry.get("participants", []) or []:
            if not isinstance(participant, dict):
                continue
            address = str(participant.get("participant_id", ""))
            for node_id in participant.get("node_ids", []) or []:
                output[model_id][address].add(str(node_id))
    return output


def node_buckets(model_id: str, row: dict[str, Any], preserved_nodes: dict[str, dict[str, set[str]]]) -> tuple[Decimal, Decimal, int, int]:
    confirmed = Decimal(0)
    preserved = Decimal(0)
    node_count = 0
    preserved_count = 0
    address = str(row.get("member_address", ""))
    preserved_node_ids = preserved_nodes.get(model_id, {}).get(address, set())
    for node in row.get("ml_nodes", []) or []:
        if not isinstance(node, dict):
            continue
        node_count += 1
        weight = decimal_or_zero(node.get("poc_weight"))
        is_preserved = str(node.get("node_id", "")) in preserved_node_ids
        if is_preserved:
            preserved += weight
            preserved_count += 1
        else:
            confirmed += weight
    return confirmed, preserved, node_count, preserved_count


def build() -> tuple[list[dict[str, str]], list[dict[str, str]], list[str]]:
    rows: list[dict[str, str]] = []
    summary_rows: list[dict[str, str]] = []
    model_labels_seen: list[str] = []

    for epoch_dir in sorted(path for path in RAW_ROOT.glob("epoch_*") if path.is_dir()):
        epoch = epoch_dir.name.replace("epoch_", "")
        perf = performance_index(epoch_dir)
        parent = parent_weight_index(epoch_dir)
        preserved_nodes = preserved_lookup(epoch_dir)

        model_by_address: dict[str, dict[str, dict[str, Decimal | int | str]]] = defaultdict(dict)
        summary: dict[str, dict[str, Decimal | int | str]] = {}

        for path in model_group_paths(epoch_dir):
            data = read_json(path)
            group = data.get("epoch_group_data", {}) if isinstance(data, dict) else {}
            model_id = str(group.get("model_id", ""))
            if not model_id:
                continue
            label = label_for(model_id)
            if label not in model_labels_seen:
                model_labels_seen.append(label)
            summary[label] = {
                "epoch": epoch,
                "model_id": model_id,
                "model_label": label,
                "participants_in_subgroup": 0,
                "entry_weight_sum": Decimal(0),
                "confirmed_node_weight_sum": Decimal(0),
                "preserved_node_weight_sum": Decimal(0),
                "node_weight_sum": Decimal(0),
                "subgroup_confirmation_weight_sum": Decimal(0),
                "voting_power_sum": Decimal(0),
            }
            for vw in group.get("validation_weights", []) or []:
                if not isinstance(vw, dict):
                    continue
                address = str(vw.get("member_address", ""))
                confirmed, preserved, node_count, preserved_count = node_buckets(model_id, vw, preserved_nodes)
                entry_weight = decimal_or_zero(vw.get("weight"))
                confirmation_weight = decimal_or_zero(vw.get("confirmation_weight"))
                voting_power = decimal_or_zero(vw.get("voting_power"))
                node_sum = confirmed + preserved
                model_by_address[address][label] = {
                    "entry_weight": entry_weight,
                    "subgroup_confirmation_weight": confirmation_weight,
                    "voting_power": voting_power,
                    "confirmed_node_weight": confirmed,
                    "preserved_node_weight": preserved,
                    "node_weight_sum": node_sum,
                    "node_count": node_count,
                    "preserved_node_count": preserved_count,
                }
                summary[label]["participants_in_subgroup"] = int(summary[label]["participants_in_subgroup"]) + 1
                for key, value in (
                    ("entry_weight_sum", entry_weight),
                    ("confirmed_node_weight_sum", confirmed),
                    ("preserved_node_weight_sum", preserved),
                    ("node_weight_sum", node_sum),
                    ("subgroup_confirmation_weight_sum", confirmation_weight),
                    ("voting_power_sum", voting_power),
                ):
                    summary[label][key] = summary[label][key] + value  # type: ignore[operator]

        addresses = sorted(set(parent) | set(model_by_address) | set(perf))
        for address in addresses:
            parent_row = parent.get(address, {})
            perf_row = perf.get(address, {})
            reward = decimal_or_zero(perf_row.get("rewarded_coins"))
            output = {
                "epoch": epoch,
                "address": address,
                "received_reward": "yes" if reward > 0 else "no",
                "rewarded_gnk": to_gnk(reward),
                "parent_entry_weight": str(parent_row.get("weight", "")),
                "parent_confirmation_weight": str(parent_row.get("confirmation_weight", "")),
                "parent_voting_power": str(parent_row.get("voting_power", "")),
            }
            totals = defaultdict(Decimal)
            notes: list[str] = []
            for label in model_labels_seen:
                model = model_by_address.get(address, {}).get(label, {})
                for field in PER_MODEL_FIELDS:
                    value = model.get(field, "")
                    output[f"{label}_{field}"] = str(value if isinstance(value, int) else int(value)) if value != "" else ""
                totals["confirmed_node_weight_total"] += decimal_or_zero(model.get("confirmed_node_weight"))
                totals["preserved_node_weight_total"] += decimal_or_zero(model.get("preserved_node_weight"))
                totals["node_weight_sum_total"] += decimal_or_zero(model.get("node_weight_sum"))
                totals["model_entry_weight_sum"] += decimal_or_zero(model.get("entry_weight"))
                totals["model_subgroup_confirmation_weight_sum"] += decimal_or_zero(
                    model.get("subgroup_confirmation_weight")
                )
                totals["model_voting_power_sum"] += decimal_or_zero(model.get("voting_power"))
            parent_weight = decimal_or_zero(parent_row.get("weight"))
            totals["parent_minus_model_entry_weight_sum"] = parent_weight - totals["model_entry_weight_sum"]
            if address not in parent:
                notes.append("not_in_parent_final_validation_weights")
            if address not in model_by_address:
                notes.append("not_in_model_subgroups")
            for column in TOTAL_COLUMNS:
                output[column] = "; ".join(notes) if column == "notes" else int_str(totals[column])
            rows.append(output)

        for label in model_labels_seen:
            if label not in summary:
                continue
            item = summary[label]
            summary_rows.append(
                {
                    key: str(item[key]) if key in {"epoch", "model_id", "model_label"} else int_str(decimal_or_zero(item[key]))
                    for key in SUMMARY_COLUMNS
                }
            )

    columns = [*BASE_COLUMNS]
    for label in model_labels_seen:
        columns.extend(f"{label}_{field}" for field in PER_MODEL_FIELDS)
    columns.extend(TOTAL_COLUMNS)
    return rows, summary_rows, columns


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    rows, summary_rows, columns = build()
    write_csv(OUTPUT, columns, rows)
    write_csv(SUMMARY_OUTPUT, SUMMARY_COLUMNS, summary_rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(rows)} rows.")
    print(f"Wrote {SUMMARY_OUTPUT.relative_to(ROOT)} with {len(summary_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
