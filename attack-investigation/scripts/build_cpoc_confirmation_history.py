#!/usr/bin/env python3
"""Build cPoC confirmation-weight history tables from saved parent group snapshots."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUT_HISTORY = ROOT / "outputs" / "cpoc_confirmation_weight_history.csv"
OUTPUT_KIMI_DELTA = ROOT / "outputs" / "kimi_cpoc_confirmation_drop_265.csv"
OUTPUT_EFFECTS = ROOT / "outputs" / "per_cpoc_confirmation_effects.csv"
OUTPUT_MODEL_PROGRESSION = ROOT / "outputs" / "model_confirmed_weight_progression.csv"

MODEL_FILES = {
    "Kimi": "moonshotai_kimi_k2_6.json",
    "Qwen": "qwen_qwen3_235b_a22b_instruct_2507_fp8.json",
}

AFTER_CPOC_HEIGHTS = {
    265: {0: 4095963, 1: 4099160, 2: 4103171},
    266: {0: 4115375, 1: 4117265, 2: 4118384},
}

HISTORY_COLUMNS = [
    "epoch",
    "height",
    "height_time_utc",
    "stage",
    "parent_participants",
    "parent_confirmation_weight",
    "parent_zero_confirmation_count",
    "kimi_participants",
    "kimi_confirmation_weight",
    "kimi_zero_confirmation_count",
]

KIMI_DELTA_COLUMNS = [
    "epoch",
    "address",
    "before_height",
    "before_confirmation_weight",
    "after_height",
    "after_confirmation_weight",
    "delta_confirmation_weight",
    "drop_pct",
    "weight_at_after_height",
    "reputation_at_after_height",
    "severity",
]

EFFECT_COLUMNS = [
    "epoch",
    "cpoc_sequence",
    "before_height",
    "before_time_utc",
    "before_stage",
    "after_height",
    "after_time_utc",
    "after_stage",
    "parent_confirmation_before",
    "parent_confirmation_after",
    "parent_confirmation_delta",
    "parent_zero_confirmation_before",
    "parent_zero_confirmation_after",
    "kimi_confirmation_before",
    "kimi_confirmation_after",
    "kimi_confirmation_delta",
    "kimi_zero_confirmation_before",
    "kimi_zero_confirmation_after",
    "kimi_severe_drop_count",
    "data_basis",
]

MODEL_PROGRESSION_COLUMNS = [
    "epoch",
    "checkpoint",
    "cpoc_sequence",
    "height",
    "time_utc_seconds",
    "model",
    "entry_weight",
    "active_participants",
    "passed_participants",
    "failed_participants",
    "confirmed_weight",
    "confirmed_weight_delta_from_previous_checkpoint",
    "data_basis",
]

CLAIM_DROP_BEFORE = 4102892
CLAIM_DROP_AFTER = 4103171


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def parent_group(epoch: int) -> dict[str, Any]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "epoch_group_data.json")
    return data.get("epoch_group_data", {}) if isinstance(data, dict) else {}


def block_time_utc(epoch: int, height: int) -> str:
    paths = [
        RAW_ROOT
        / f"epoch_{epoch}"
        / "cpoc_confirmation_snapshots"
        / "block_headers"
        / f"block_{height}.json",
        RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "block_headers" / f"block_{height}.json",
    ]
    for path in paths:
        data = read_json(path)
        if not isinstance(data, dict):
            continue
        header = data.get("block", {}).get("header", {})
        if isinstance(header, dict) and header.get("time"):
            return str(header["time"])
    return ""


def time_utc_seconds(epoch: int, height: int) -> str:
    value = block_time_utc(epoch, height)
    if "." in value:
        return value.split(".", 1)[0] + "Z"
    return value


def model_group(epoch: int, model: str) -> dict[str, Any]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "model_group_data" / MODEL_FILES[model])
    return data.get("epoch_group_data", {}) if isinstance(data, dict) else {}


def model_addresses(epoch: int, model: str) -> set[str]:
    group = model_group(epoch, model)
    rows = group.get("validation_weights", [])
    return {str(row["member_address"]) for row in rows if isinstance(row, dict) and row.get("member_address")}


def model_entry_weight(epoch: int, model: str) -> int:
    group = model_group(epoch, model)
    if group.get("total_weight") not in (None, ""):
        return int(group["total_weight"])
    rows = group.get("validation_weights", [])
    return sum(int(row.get("weight") or 0) for row in rows if isinstance(row, dict))


def kimi_addresses(epoch: int) -> set[str]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "model_group_data" / MODEL_FILES["Kimi"])
    group = data.get("epoch_group_data", {}) if isinstance(data, dict) else {}
    rows = group.get("validation_weights", [])
    return {str(row["member_address"]) for row in rows if isinstance(row, dict) and row.get("member_address")}


def event_generation_heights(epoch: int) -> dict[int, str]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "confirmation_poc_events.json")
    events = data.get("events", []) if isinstance(data, dict) else []
    result: dict[int, str] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        height = event.get("generation_start_height")
        sequence = event.get("event_sequence")
        if height not in (None, ""):
            result[int(height)] = f"cpoc_{sequence}_generation_start"
    return result


def snapshot_heights(epoch: int) -> dict[int, str]:
    group = parent_group(epoch)
    heights: dict[int, str] = {}
    if group.get("effective_block_height") not in (None, ""):
        heights[int(group["effective_block_height"])] = "epoch_start"
    heights.update(event_generation_heights(epoch))
    for sequence, height in AFTER_CPOC_HEIGHTS.get(epoch, {}).items():
        heights[height] = f"cpoc_{sequence}_after_confirmed"
    if group.get("last_block_height") not in (None, ""):
        heights[int(group["last_block_height"])] = "epoch_last"
    return dict(sorted(heights.items()))


def snapshot_rows(epoch: int, height: int) -> list[dict[str, Any]]:
    data = read_json(
        RAW_ROOT
        / f"epoch_{epoch}"
        / "cpoc_confirmation_snapshots"
        / f"parent_epoch_group_data_at_{height}.json"
    )
    group = data.get("epoch_group_data", {}) if isinstance(data, dict) else {}
    rows = group.get("validation_weights", [])
    return [row for row in rows if isinstance(row, dict)]


def confirmation_weight(row: dict[str, Any]) -> int:
    return int(row.get("confirmation_weight") or 0)


def build_history_rows(epochs: list[int]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for epoch in epochs:
        kimi = kimi_addresses(epoch)
        for height, stage in snapshot_heights(epoch).items():
            snapshot = snapshot_rows(epoch, height)
            by_addr = {str(row["member_address"]): row for row in snapshot if row.get("member_address")}
            kimi_rows = [by_addr[address] for address in kimi if address in by_addr]
            rows.append(
                {
                    "epoch": str(epoch),
                    "height": str(height),
                    "height_time_utc": block_time_utc(epoch, height),
                    "stage": stage,
                    "parent_participants": str(len(snapshot)),
                    "parent_confirmation_weight": str(sum(confirmation_weight(row) for row in snapshot)),
                    "parent_zero_confirmation_count": str(
                        sum(1 for row in snapshot if confirmation_weight(row) == 0)
                    ),
                    "kimi_participants": str(len(kimi_rows)),
                    "kimi_confirmation_weight": str(sum(confirmation_weight(row) for row in kimi_rows)),
                    "kimi_zero_confirmation_count": str(
                        sum(1 for row in kimi_rows if confirmation_weight(row) == 0)
                    ),
                }
            )
    return rows


def severity(before: int, after: int) -> str:
    if before <= 0:
        return "not_applicable"
    drop_pct = (before - after) / before
    if after == 0 or drop_pct >= 0.8:
        return "severe_drop"
    if drop_pct >= 0.1:
        return "moderate_drop"
    return "small_change"


def build_kimi_delta_rows() -> list[dict[str, str]]:
    epoch = 265
    kimi = kimi_addresses(epoch)
    before = {
        str(row["member_address"]): row
        for row in snapshot_rows(epoch, CLAIM_DROP_BEFORE)
        if row.get("member_address")
    }
    after = {
        str(row["member_address"]): row
        for row in snapshot_rows(epoch, CLAIM_DROP_AFTER)
        if row.get("member_address")
    }
    rows: list[dict[str, str]] = []
    for address in sorted(kimi):
        if address not in before or address not in after:
            continue
        before_weight = confirmation_weight(before[address])
        after_weight = confirmation_weight(after[address])
        if before_weight == after_weight:
            continue
        delta = after_weight - before_weight
        drop = "" if before_weight <= 0 else f"{((before_weight - after_weight) / before_weight):.6f}"
        rows.append(
            {
                "epoch": str(epoch),
                "address": address,
                "before_height": str(CLAIM_DROP_BEFORE),
                "before_confirmation_weight": str(before_weight),
                "after_height": str(CLAIM_DROP_AFTER),
                "after_confirmation_weight": str(after_weight),
                "delta_confirmation_weight": str(delta),
                "drop_pct": drop,
                "weight_at_after_height": str(after[address].get("weight", "")),
                "reputation_at_after_height": str(after[address].get("reputation", "")),
                "severity": severity(before_weight, after_weight),
            }
        )
    return rows


def stage_snapshot(epoch: int, height: int) -> dict[str, Any]:
    kimi = kimi_addresses(epoch)
    snapshot = snapshot_rows(epoch, height)
    by_addr = {str(row["member_address"]): row for row in snapshot if row.get("member_address")}
    kimi_rows = [by_addr[address] for address in kimi if address in by_addr]
    return {
        "parent_confirmation": sum(confirmation_weight(row) for row in snapshot),
        "parent_zero": sum(1 for row in snapshot if confirmation_weight(row) == 0),
        "kimi_confirmation": sum(confirmation_weight(row) for row in kimi_rows),
        "kimi_zero": sum(1 for row in kimi_rows if confirmation_weight(row) == 0),
        "rows_by_address": by_addr,
        "kimi_addresses": kimi,
    }


def model_checkpoint(epoch: int, height: int, model: str) -> dict[str, int]:
    addresses = model_addresses(epoch, model)
    snapshot = snapshot_rows(epoch, height)
    by_addr = {str(row["member_address"]): row for row in snapshot if row.get("member_address")}
    model_rows = [by_addr[address] for address in addresses if address in by_addr]
    passed = sum(1 for row in model_rows if confirmation_weight(row) > 0)
    active = len(model_rows)
    return {
        "active_participants": active,
        "passed_participants": passed,
        "failed_participants": active - passed,
        "confirmed_weight": sum(confirmation_weight(row) for row in model_rows),
    }


def model_progression_checkpoints(epoch: int) -> list[tuple[str, str, int]]:
    group = parent_group(epoch)
    rows: list[tuple[str, str, int]] = []
    if group.get("effective_block_height") not in (None, ""):
        rows.append(("epoch_entry", "", int(group["effective_block_height"])))
    for sequence, height in sorted(AFTER_CPOC_HEIGHTS.get(epoch, {}).items()):
        rows.append((f"after_cpoc_{sequence}", str(sequence), height))
    return rows


def build_model_progression_rows(epochs: list[int]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    previous: dict[tuple[int, str], int] = {}
    for epoch in epochs:
        for checkpoint, sequence, height in model_progression_checkpoints(epoch):
            for model in MODEL_FILES:
                stats = model_checkpoint(epoch, height, model)
                current = stats["confirmed_weight"]
                previous_key = (epoch, model)
                delta = "" if previous_key not in previous else str(current - previous[previous_key])
                previous[previous_key] = current
                rows.append(
                    {
                        "epoch": str(epoch),
                        "checkpoint": checkpoint,
                        "cpoc_sequence": sequence,
                        "height": str(height),
                        "time_utc_seconds": time_utc_seconds(epoch, height),
                        "model": model,
                        "entry_weight": str(model_entry_weight(epoch, model)),
                        "active_participants": str(stats["active_participants"]),
                        "passed_participants": str(stats["passed_participants"]),
                        "failed_participants": str(stats["failed_participants"]),
                        "confirmed_weight": str(current),
                        "confirmed_weight_delta_from_previous_checkpoint": delta,
                        "data_basis": "model subgroup membership + parent epoch_group_data confirmation_weight",
                    }
                )
    return rows


def severe_drop_count(epoch: int, before_height: int, after_height: int) -> int:
    before = stage_snapshot(epoch, before_height)
    after = stage_snapshot(epoch, after_height)
    count = 0
    for address in before["kimi_addresses"]:
        before_row = before["rows_by_address"].get(address)
        after_row = after["rows_by_address"].get(address)
        if not before_row or not after_row:
            continue
        before_weight = confirmation_weight(before_row)
        after_weight = confirmation_weight(after_row)
        if severity(before_weight, after_weight) == "severe_drop":
            count += 1
    return count


def cpoc_sequence_from_stage(stage: str) -> str:
    if stage.startswith("cpoc_") and "_generation_start" in stage:
        return stage.split("_", 2)[1]
    return ""


def build_effect_rows(epochs: list[int]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for epoch in epochs:
        generation = {
            int(stage.split("_", 2)[1]): height
            for height, stage in snapshot_heights(epoch).items()
            if stage.startswith("cpoc_") and stage.endswith("_generation_start")
        }
        for sequence_int, before_height in sorted(generation.items()):
            if sequence_int not in AFTER_CPOC_HEIGHTS.get(epoch, {}):
                continue
            sequence = str(sequence_int)
            before_stage = f"cpoc_{sequence}_generation_start"
            after_height = AFTER_CPOC_HEIGHTS[epoch][sequence_int]
            after_stage = f"cpoc_{sequence}_after_confirmed"
            before = stage_snapshot(epoch, before_height)
            after = stage_snapshot(epoch, after_height)
            rows.append(
                {
                    "epoch": str(epoch),
                    "cpoc_sequence": sequence,
                    "before_height": str(before_height),
                    "before_time_utc": block_time_utc(epoch, before_height),
                    "before_stage": before_stage,
                    "after_height": str(after_height),
                    "after_time_utc": block_time_utc(epoch, after_height),
                    "after_stage": after_stage,
                    "parent_confirmation_before": str(before["parent_confirmation"]),
                    "parent_confirmation_after": str(after["parent_confirmation"]),
                    "parent_confirmation_delta": str(after["parent_confirmation"] - before["parent_confirmation"]),
                    "parent_zero_confirmation_before": str(before["parent_zero"]),
                    "parent_zero_confirmation_after": str(after["parent_zero"]),
                    "kimi_confirmation_before": str(before["kimi_confirmation"]),
                    "kimi_confirmation_after": str(after["kimi_confirmation"]),
                    "kimi_confirmation_delta": str(after["kimi_confirmation"] - before["kimi_confirmation"]),
                    "kimi_zero_confirmation_before": str(before["kimi_zero"]),
                    "kimi_zero_confirmation_after": str(after["kimi_zero"]),
                    "kimi_severe_drop_count": str(severe_drop_count(epoch, before_height, after_height)),
                    "data_basis": "parent epoch_group_data snapshots before/after cPoC result application",
                }
            )
    return rows


def write_csv(path: Path, columns: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    history_rows = build_history_rows([265, 266])
    delta_rows = build_kimi_delta_rows()
    effect_rows = build_effect_rows([265, 266])
    model_progression_rows = build_model_progression_rows([265, 266])
    write_csv(OUTPUT_HISTORY, HISTORY_COLUMNS, history_rows)
    write_csv(OUTPUT_KIMI_DELTA, KIMI_DELTA_COLUMNS, delta_rows)
    write_csv(OUTPUT_EFFECTS, EFFECT_COLUMNS, effect_rows)
    write_csv(OUTPUT_MODEL_PROGRESSION, MODEL_PROGRESSION_COLUMNS, model_progression_rows)
    print(f"Wrote {OUTPUT_HISTORY.relative_to(ROOT)} with {len(history_rows)} rows.")
    print(f"Wrote {OUTPUT_KIMI_DELTA.relative_to(ROOT)} with {len(delta_rows)} rows.")
    print(f"Wrote {OUTPUT_EFFECTS.relative_to(ROOT)} with {len(effect_rows)} rows.")
    print(f"Wrote {OUTPUT_MODEL_PROGRESSION.relative_to(ROOT)} with {len(model_progression_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
