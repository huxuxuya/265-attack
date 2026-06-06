#!/usr/bin/env python3
"""Build cPoC history CSV tables from saved raw artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUT_EVENTS = ROOT / "outputs" / "cpoc_events.csv"
OUTPUT_ENDPOINTS = ROOT / "outputs" / "cpoc_history_endpoint_summary.csv"
OUTPUT_MODEL_MATRIX = ROOT / "outputs" / "cpoc_event_model_weight_matrix.csv"
MODEL_EPOCH_MATRIX = ROOT / "outputs" / "model_cpoc_epoch_matrix.csv"

EVENT_COLUMNS = [
    "epoch",
    "epoch_start_height",
    "epoch_start_time_utc",
    "poc_start_block_height",
    "poc_start_time_utc",
    "event_sequence",
    "trigger_height",
    "trigger_time_utc",
    "generation_start_height",
    "generation_start_time_utc",
    "phase",
    "poc_seed_block_hash",
]

ENDPOINT_COLUMNS = [
    "epoch",
    "poc_start_block_height",
    "artifact",
    "record_key",
    "record_count",
    "found",
    "note",
]

MODEL_MATRIX_COLUMNS = [
    "epoch",
    "epoch_start_height",
    "epoch_start_time_utc",
    "poc_start_block_height",
    "poc_start_time_utc",
    "event_sequence",
    "trigger_height",
    "trigger_time_utc",
    "generation_start_height",
    "generation_start_time_utc",
    "phase",
    "kimi_confirmed_weight",
    "kimi_preserved_weight",
    "kimi_total_weight",
    "qwen_confirmed_weight",
    "qwen_preserved_weight",
    "qwen_total_weight",
    "total_confirmed_weight",
    "total_preserved_weight",
    "total_weight",
    "data_basis",
]

ARTIFACT_KEYS = {
    "confirmation_poc_events": "events",
    "poc_validation_snapshot_by_stage_start": "snapshot",
    "poc_v2_validations_for_stage": "poc_validation",
    "all_poc_v2_store_commits": "commits",
    "all_mlnode_weight_distributions": "distributions",
    "poc_batches_for_stage": "poc_batch",
    "poc_validations_for_stage": "poc_validation",
}


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def poc_start_height(epoch: int) -> str:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "epoch_group_data.json")
    if not isinstance(data, dict):
        return ""
    group = data.get("epoch_group_data")
    if not isinstance(group, dict):
        return ""
    value = group.get("poc_start_block_height")
    return "" if value is None else str(value)


def epoch_start_height(epoch: int) -> str:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "epoch_group_data.json")
    if not isinstance(data, dict):
        return ""
    group = data.get("epoch_group_data")
    if not isinstance(group, dict):
        return ""
    value = group.get("effective_block_height")
    return "" if value is None else str(value)


def block_time_utc(epoch: int, height: str) -> str:
    if not height:
        return ""
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "block_headers" / f"block_{height}.json")
    if not isinstance(data, dict):
        return ""
    header = data.get("block", {}).get("header", {})
    value = header.get("time") if isinstance(header, dict) else ""
    return "" if value is None else str(value)


def record_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value is None:
        return 0
    return 1


def note_for_artifact(artifact: str, data: Any, key: str, count: int) -> str:
    if artifact == "poc_validation_snapshot_by_stage_start":
        if isinstance(data, dict) and data.get("found") is False:
            return "archive endpoint returned found=false"
    if count == 0:
        return "archive endpoint returned empty list"
    return "archive endpoint returned records"


def build_events(epoch: int) -> list[dict[str, str]]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "confirmation_poc_events.json")
    events = data.get("events", []) if isinstance(data, dict) else []
    rows: list[dict[str, str]] = []
    epoch_start = epoch_start_height(epoch)
    poc_start = poc_start_height(epoch)
    for event in events:
        if not isinstance(event, dict):
            continue
        trigger_height = str(event.get("trigger_height", ""))
        generation_start_height = str(event.get("generation_start_height", ""))
        rows.append(
            {
                "epoch": str(epoch),
                "epoch_start_height": epoch_start,
                "epoch_start_time_utc": block_time_utc(epoch, epoch_start),
                "poc_start_block_height": poc_start,
                "poc_start_time_utc": block_time_utc(epoch, poc_start),
                "event_sequence": str(event.get("event_sequence", "")),
                "trigger_height": trigger_height,
                "trigger_time_utc": block_time_utc(epoch, trigger_height),
                "generation_start_height": generation_start_height,
                "generation_start_time_utc": block_time_utc(epoch, generation_start_height),
                "phase": str(event.get("phase", "")),
                "poc_seed_block_hash": str(event.get("poc_seed_block_hash", "")),
            }
        )
    return rows


def build_endpoint_rows(epoch: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    cpoc_dir = RAW_ROOT / f"epoch_{epoch}" / "cpoc_history"
    stage_start = poc_start_height(epoch)
    for artifact, key in ARTIFACT_KEYS.items():
        data = read_json(cpoc_dir / f"{artifact}.json")
        value: Any = None
        found = ""
        if isinstance(data, dict):
            value = data.get(key)
            if "found" in data:
                found = str(data.get("found")).lower()
        count = record_count(value)
        rows.append(
            {
                "epoch": str(epoch),
                "poc_start_block_height": stage_start,
                "artifact": artifact,
                "record_key": key,
                "record_count": str(count),
                "found": found,
                "note": note_for_artifact(artifact, data, key, count),
            }
        )
    return rows


def model_weight_by_epoch() -> dict[str, dict[str, str]]:
    if not MODEL_EPOCH_MATRIX.exists():
        return {}
    with MODEL_EPOCH_MATRIX.open(newline="") as fh:
        return {row["epoch"]: row for row in csv.DictReader(fh)}


def build_model_matrix_rows(event_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    weights = model_weight_by_epoch()
    rows: list[dict[str, str]] = []
    for event in event_rows:
        weight = weights.get(event["epoch"], {})
        rows.append(
            {
                "epoch": event["epoch"],
                "epoch_start_height": event["epoch_start_height"],
                "epoch_start_time_utc": event["epoch_start_time_utc"],
                "poc_start_block_height": event["poc_start_block_height"],
                "poc_start_time_utc": event["poc_start_time_utc"],
                "event_sequence": event["event_sequence"],
                "trigger_height": event["trigger_height"],
                "trigger_time_utc": event["trigger_time_utc"],
                "generation_start_height": event["generation_start_height"],
                "generation_start_time_utc": event["generation_start_time_utc"],
                "phase": event["phase"],
                "kimi_confirmed_weight": weight.get("kimi_confirmed_node_weight", ""),
                "kimi_preserved_weight": weight.get("kimi_preserved_node_weight", ""),
                "kimi_total_weight": weight.get("kimi_node_weight_sum", ""),
                "qwen_confirmed_weight": weight.get("qwen_confirmed_node_weight", ""),
                "qwen_preserved_weight": weight.get("qwen_preserved_node_weight", ""),
                "qwen_total_weight": weight.get("qwen_node_weight_sum", ""),
                "total_confirmed_weight": weight.get("total_confirmed_node_weight", ""),
                "total_preserved_weight": weight.get("total_preserved_node_weight", ""),
                "total_weight": weight.get("total_node_weight_sum", ""),
                "data_basis": "event + epoch model weight snapshot",
            }
        )
    return rows


def main() -> int:
    epochs = [265, 266]
    OUTPUT_EVENTS.parent.mkdir(parents=True, exist_ok=True)

    event_rows: list[dict[str, str]] = []
    endpoint_rows: list[dict[str, str]] = []
    for epoch in epochs:
        event_rows.extend(build_events(epoch))
        endpoint_rows.extend(build_endpoint_rows(epoch))
    model_matrix_rows = build_model_matrix_rows(event_rows)

    with OUTPUT_EVENTS.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=EVENT_COLUMNS)
        writer.writeheader()
        writer.writerows(event_rows)

    with OUTPUT_ENDPOINTS.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=ENDPOINT_COLUMNS)
        writer.writeheader()
        writer.writerows(endpoint_rows)

    with OUTPUT_MODEL_MATRIX.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=MODEL_MATRIX_COLUMNS)
        writer.writeheader()
        writer.writerows(model_matrix_rows)

    print(f"Wrote {OUTPUT_EVENTS.relative_to(ROOT)} with {len(event_rows)} rows.")
    print(f"Wrote {OUTPUT_ENDPOINTS.relative_to(ROOT)} with {len(endpoint_rows)} rows.")
    print(f"Wrote {OUTPUT_MODEL_MATRIX.relative_to(ROOT)} with {len(model_matrix_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
