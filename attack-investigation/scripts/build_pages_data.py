#!/usr/bin/env python3
"""Build static GitHub Pages datasets for epoch cPoC investigation.

The script now emits:
- docs/data/epoch_<N>_timeline.json (backward-compatible payload per epoch)
- docs/data/epochs_timeline.json (multi-epoch bundle with transitions)
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUTS = ROOT / "outputs"
DOCS_DATA = REPO_ROOT / "docs" / "data"

GONKA_DENOM = Decimal("1000000000")

MODEL_FILES = {
    "Kimi": "moonshotai_kimi_k2_6.json",
    "Qwen": "qwen_qwen3_235b_a22b_instruct_2507_fp8.json",
}

# The legacy source compensation model is tied to the known epoch 265 source set.
SOURCE_COMPENSATION_EPOCH = 265
E265_SOURCE_COMPENSATION_ADDRESSES = {
    "gonka1j7x6dv42xehe9e5au4ku3wvzwtqlegfjhlvzj6",
    "gonka17pw6099q758qwzewtrqmqpf5c2lrhr97fwqexu",
    "gonka1830lqug50lse998x2lakk4pj5ypfumz5pasz0y",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def as_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(Decimal(str(value)))


def as_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def decimal_param(value: Any) -> Decimal | None:
    if isinstance(value, dict) and "value" in value and "exponent" in value:
        param_value = as_decimal(value.get("value"))
        param_exp = as_int(value.get("exponent"))
        return param_value * (Decimal(10) ** param_exp)
    if value in (None, ""):
        return None
    return as_decimal(value)


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")


def from_ngonka(value: Decimal) -> Decimal:
    return value / GONKA_DENOM


def list_epochs() -> list[int]:
    epochs = []
    for path in RAW_ROOT.glob("epoch_*"):
        if not path.is_dir():
            continue
        suffix = path.name.removeprefix("epoch_")
        if not suffix.isdigit():
            continue
        epochs.append(int(suffix))
    return sorted(epochs)


def short_address(address: str) -> str:
    if len(address) <= 18:
        return address
    return f"{address[:10]}...{address[-6:]}"


def load_params(epoch: int) -> dict[str, Any]:
    return read_json(RAW_ROOT / f"epoch_{epoch}" / "params_current.json")


def epoch_group_data(epoch: int) -> dict[str, Any]:
    return read_json(RAW_ROOT / f"epoch_{epoch}" / "epoch_group_data.json").get("epoch_group_data", {})


def load_epoch_summary() -> dict[str, dict[str, str]]:
    rows = read_csv(OUTPUTS / "epoch_summary.csv")
    return {row["epoch"]: row for row in rows}


def load_gov_settlement() -> dict[str, dict[str, str]]:
    rows = read_csv(OUTPUTS / "gov_settlement_audit.csv")
    return {row["epoch"]: row for row in rows}


def load_model_progression_rows() -> dict[int, list[dict[str, str]]]:
    rows = read_csv(OUTPUTS / "model_confirmed_weight_progression_wide.csv")
    per_epoch: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        per_epoch.setdefault(as_int(row["epoch"]), []).append(row)
    return per_epoch


def load_cpoc_effect_rows() -> dict[int, list[dict[str, str]]]:
    rows = read_csv(OUTPUTS / "per_cpoc_confirmation_effects.csv")
    per_epoch: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        per_epoch.setdefault(as_int(row["epoch"]), []).append(row)
    return per_epoch


def load_performance_rows(epoch: int) -> dict[str, dict[str, Any]]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "epoch_performance_summary.json")
    return {
        str(row["participant_id"]): row
        for row in data.get("epochPerformanceSummary", [])
        if isinstance(row, dict) and row.get("participant_id")
    }


def load_snapshot_rows(epoch: int, height: int) -> dict[str, dict[str, Any]]:
    path = (
        RAW_ROOT / f"epoch_{epoch}" / "cpoc_confirmation_snapshots" / f"parent_epoch_group_data_at_{height}.json"
    )
    if not path.exists():
        return {}
    data = read_json(path)
    rows = data.get("epoch_group_data", {}).get("validation_weights", [])
    return {
        str(row["member_address"]): row
        for row in rows
        if isinstance(row, dict) and row.get("member_address")
    }


def model_members(epoch: int) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    model_dir = RAW_ROOT / f"epoch_{epoch}" / "model_group_data"
    for model_name, filename in MODEL_FILES.items():
        path = model_dir / filename
        if not path.exists():
            continue
        data = read_json(path)
        rows = data.get("epoch_group_data", {}).get("validation_weights", [])
        result[model_name] = {
            str(row["member_address"]): row
            for row in rows
            if isinstance(row, dict) and row.get("member_address")
        }
    return result


def model_membership_by_epoch(epochs: list[int]) -> dict[int, dict[str, list[str]]]:
    result: dict[int, dict[str, list[str]]] = {}
    for epoch in epochs:
        per_epoch: dict[str, set[str]] = {}
        model_dir = RAW_ROOT / f"epoch_{epoch}" / "model_group_data"
        for model_name, filename in MODEL_FILES.items():
            path = model_dir / filename
            if not path.exists():
                continue
            data = read_json(path)
            rows = data.get("epoch_group_data", {}).get("validation_weights", [])
            for row in rows:
                if not (isinstance(row, dict) and row.get("member_address")):
                    continue
                per_epoch.setdefault(str(row["member_address"]), set()).add(model_name)
        result[epoch] = {address: sorted(models) for address, models in per_epoch.items()}
    return result


def cap_factor_value(epoch: int) -> tuple[str, str]:
    params = load_params(epoch)
    raw_cap_factor = params.get("params", {}).get("delegation_params", {}).get("cap_factor")
    cap = decimal_param(raw_cap_factor)
    if cap is None:
        return "", "delegation_params.cap_factor missing in params_current.json"
    return money(cap), f"delegation_params.cap_factor = {raw_cap_factor!r}"


def epoch_reward_raw(epoch: int) -> Decimal:
    params = load_params(epoch)
    bitcoin_params = params.get("params", {}).get("bitcoin_reward_params", {})
    initial = as_decimal(bitcoin_params.get("initial_epoch_reward"))
    decay = decimal_param(bitcoin_params.get("decay_rate"))
    genesis = as_decimal(bitcoin_params.get("genesis_epoch"))
    if decay is None:
        raise ValueError(f"missing decay_rate for epoch {epoch}")
    epochs_since_genesis = int(Decimal(epoch) - genesis)
    with localcontext() as context:
        context.prec = 80
        current_reward = initial * ((decay.exp()) ** epochs_since_genesis)
    return Decimal(int(current_reward))


def model_progression_rows(epoch: int, progression_rows_by_epoch: dict[int, list[dict[str, str]]]) -> list[dict[str, str]]:
    return progression_rows_by_epoch.get(epoch, [])


def checkpoint_defs(epoch: int, progression_rows: list[dict[str, str]], effects_by_epoch: dict[int, list[dict[str, str]]]) -> list[dict[str, Any]]:
    group = epoch_group_data(epoch)
    effects = {as_int(row.get("cpoc_sequence")): row for row in effects_by_epoch.get(epoch, []) if row.get("cpoc_sequence") != ""}
    items: list[dict[str, Any]] = []
    items.append(
        {
            "key": "epoch_entry",
            "label": "Epoch entry",
            "height": as_int(group.get("effective_block_height")),
            "timeUtc": "",
            "type": "epoch_entry",
            "cpocSequence": None,
        },
    )

    for sequence in sorted(effects):
        effect = effects[sequence]
        before_height = as_int(effect.get("before_height"))
        after_height = as_int(effect.get("after_height"))
        items.append(
            {
                "key": f"cpoc_{sequence}_generation_start",
                "label": str(effect.get("before_stage") or f"cPoC {sequence} generation start"),
                "height": before_height,
                "timeUtc": str(effect.get("before_time_utc") or ""),
                "type": "cpoc_generation_start",
                "cpocSequence": sequence,
            },
        )
        items.append(
            {
                "key": f"after_cpoc_{sequence}",
                "label": str(effect.get("after_stage") or f"After cPoC {sequence}"),
                "height": after_height,
                "timeUtc": str(effect.get("after_time_utc") or ""),
                "type": "after_cpoc_confirmed",
                "cpocSequence": sequence,
            },
        )

    # Keep epoch last block for timeline context.
    items.append(
        {
            "key": "epoch_last",
            "label": "Epoch last block",
            "height": as_int(group.get("last_block_height")),
            "timeUtc": "",
            "type": "epoch_last",
            "cpocSequence": None,
        },
    )

    # Resolve missing UTC times from header snapshots where needed.
    for item in items:
        if item["timeUtc"]:
            continue
        item["timeUtc"] = str(
            block_time(epoch, item["height"]),
        )

    # Keep a stable display order.
    def checkpoint_order(item: dict[str, Any]) -> tuple[int, str]:
        if item["key"] == "epoch_entry":
            return (0, "")
        if item["key"] == "epoch_last":
            return (99, "")
        if item["key"].endswith("_generation_start"):
            return (1 + (2 * item["cpocSequence"]), item["key"])
        if item["key"].startswith("after_cpoc_"):
            return (2 + (2 * item["cpocSequence"]), item["key"])
        if item["key"].startswith("cpoc_"):
            return (1 + item["cpocSequence"], item["key"])
        return (0, item["key"])

    items.sort(key=checkpoint_order)

    for index, item in enumerate(items):
        item["order"] = index

    # Ensure progression rows are represented in time order when rendering charts.
    if progression_rows:
        for row in progression_rows:
            checkpoint = row.get("checkpoint")
            if not checkpoint:
                continue
            for item in items:
                if item["key"] == checkpoint and not item["timeUtc"]:
                    item["timeUtc"] = str(row.get("time_utc_seconds") or "")
    return items


def block_time(epoch: int, height: int) -> str:
    header_path_candidates = [
        RAW_ROOT / f"epoch_{epoch}" / "cpoc_confirmation_snapshots" / "block_headers" / f"block_{height}.json",
        RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "block_headers" / f"block_{height}.json",
    ]
    for path in header_path_candidates:
        if not path.exists():
            continue
        header = read_json(path).get("block", {}).get("header", {})
        raw_time = header.get("time")
        if not raw_time:
            continue
        time_text = str(raw_time)
        return time_text.split(".", 1)[0] + "Z" if "." in time_text else time_text
    return ""


def model_checkpoint_keys(checkpoints: list[dict[str, Any]]) -> list[str]:
    return [
        item["key"]
        for item in checkpoints
        if item["key"] in {"epoch_entry"} or item["key"].startswith("after_cpoc_")
    ]


def node_models(address: str, members: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for model, rows in members.items():
        row = rows.get(address)
        if not row:
            continue
        output.append(
            {
                "model": model,
                "entryWeight": as_int(row.get("weight")),
                "entryConfirmationWeight": as_int(row.get("confirmation_weight")),
                "mlNodes": [
                    {
                        "nodeId": str(node.get("node_id", "")),
                        "pocWeight": as_int(node.get("poc_weight")),
                    }
                    for node in row.get("ml_nodes", [])
                    if isinstance(node, dict)
                ],
            },
        )
    return output


def severity(previous: int, current: int) -> str:
    if previous <= 0:
        return "not_applicable"
    drop = previous - current
    if drop <= 0:
        return "stable_or_gain"
    ratio = Decimal(drop) / Decimal(previous)
    if current == 0 or ratio >= Decimal("0.8"):
        return "severe_drop"
    if ratio >= Decimal("0.1"):
        return "moderate_drop"
    return "small_drop"


def allocated_model_weights(models: list[dict[str, Any]], total_weight: int) -> dict[str, int]:
    if not models:
        return {}
    if len(models) == 1:
        return {models[0]["model"]: total_weight}

    model_entry_total = sum(as_int(model.get("entryWeight")) for model in models)
    if model_entry_total <= 0:
        return {model["model"]: 0 for model in models}

    allocated: dict[str, int] = {}
    remainders: list[tuple[Decimal, str]] = []
    assigned = 0
    for model in models:
        exact = Decimal(total_weight) * Decimal(as_int(model.get("entryWeight"))) / Decimal(model_entry_total)
        whole = int(exact)
        allocated[model["model"]] = whole
        assigned += whole
        remainders.append((exact - Decimal(whole), model["model"]))

    for _, model_name in sorted(remainders, reverse=True)[: max(total_weight - assigned, 0)]:
        allocated[model_name] += 1
    return allocated


def node_model_rows(models: list[dict[str, Any]], checkpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    model_weights_by_checkpoint = {
        checkpoint["checkpoint"]: allocated_model_weights(models, checkpoint["confirmationWeight"])
        for checkpoint in checkpoints
    }
    for model in models:
        previous_weight: int | None = None
        rows = []
        for checkpoint in checkpoints:
            current = model_weights_by_checkpoint[checkpoint["checkpoint"]].get(model["model"], 0)
            delta = None if previous_weight is None else current - previous_weight
            rows.append(
                {
                    "checkpoint": checkpoint["checkpoint"],
                    "confirmationWeight": current,
                    "delta": delta,
                    "severity": "entry" if previous_weight is None else severity(previous_weight, current),
                },
            )
            previous_weight = current
        output.append(
            {
                "model": model["model"],
                "entryWeight": model["entryWeight"],
                "splitBasis": "exact" if len(models) == 1 else "allocated_by_entry_split",
                "checkpoints": rows,
            },
        )
    return output


def progression_series(epoch: int, progression_rows_by_epoch: dict[int, list[dict[str, str]]]) -> list[dict[str, Any]]:
    rows = progression_rows_by_epoch.get(epoch, [])
    output: list[dict[str, Any]] = []
    for row in rows:
        output.append(
            {
                "checkpoint": row["checkpoint"],
                "height": as_int(row["height"]),
                "timeUtc": str(row["time_utc_seconds"]),
                "kimiConfirmedWeight": as_int(row["kimi_confirmed_weight"]),
                "qwenConfirmedWeight": as_int(row["qwen_confirmed_weight"]),
                "totalConfirmedWeight": as_int(row["confirmed_weight_union_total"]),
                "kimiDelta": as_int(row["kimi_delta"]),
                "qwenDelta": as_int(row["qwen_delta"]),
                "totalDelta": as_int(row["confirmed_weight_union_delta"]),
                "kimiPassed": as_int(row["kimi_passed"]),
                "qwenPassed": as_int(row["qwen_passed"]),
                "totalPassed": as_int(row["passed_union_total"]),
                "kimiActive": as_int(row["kimi_active"]),
                "qwenActive": as_int(row["qwen_active"]),
                "totalActive": as_int(row["participants_union_total"]),
                "kimiPassedDelta": as_int(row["kimi_passed_delta"]),
                "qwenPassedDelta": as_int(row["qwen_passed_delta"]),
                "totalPassedDelta": as_int(row["passed_union_delta"]),
            },
        )
    return output


def snapshot_rows_for_checkpoint(epoch: int, checkpoints: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    return {
        checkpoint["key"]: load_snapshot_rows(epoch, as_int(checkpoint["height"]))
        for checkpoint in checkpoints
        if checkpoint["key"] in {"epoch_entry"} or checkpoint["key"].startswith("after_cpoc_")
    }


def build_nodes(
    epoch: int,
    checkpoints: list[dict[str, Any]],
    members_by_model: dict[str, dict[str, dict[str, Any]]],
    performance: dict[str, dict[str, Any]],
    progression_keys: list[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshots = snapshot_rows_for_checkpoint(epoch, checkpoints)
    all_addresses: set[str] = set(performance.keys())
    for rows in snapshots.values():
        all_addresses.update(rows.keys())
    for rows in members_by_model.values():
        all_addresses.update(rows.keys())

    reward_raw = epoch_reward_raw(epoch)
    total_epoch_weight = as_decimal(epoch_group_data(epoch).get("total_weight"))
    progressions = {key: 0 for key in progression_keys if key.startswith("after_cpoc_")}

    nodes: list[dict[str, Any]] = []
    positive_drop_by_address: dict[str, int] = {}
    for address in sorted(all_addresses):
        checkpoints_rows = []
        previous_weight: int | None = None
        total_positive_drop = 0
        total_negative_delta = 0
        worst_severity = "stable_or_gain"
        for key in progression_keys:
            row = snapshots.get(key, {}).get(address)
            current = as_int(row.get("confirmation_weight")) if row else 0
            weight = as_int(row.get("weight")) if row else 0
            reputation = as_int(row.get("reputation")) if row else None
            delta = None if previous_weight is None else current - previous_weight
            positive_drop = 0 if delta is None else max(-delta, 0)
            if positive_drop:
                total_positive_drop += positive_drop
                total_negative_delta -= positive_drop
            progressions[key] = progressions.get(key, 0) + positive_drop
            state = "missing" if row is None else ("failed" if current == 0 else "passed")
            sev = "entry" if previous_weight is None else severity(previous_weight, current)
            if sev == "severe_drop":
                worst_severity = "severe_drop"
            elif sev == "moderate_drop" and worst_severity != "severe_drop":
                worst_severity = "moderate_drop"
            elif sev == "small_drop" and worst_severity == "stable_or_gain":
                worst_severity = "small_drop"
            checkpoints_rows.append(
                {
                    "checkpoint": key,
                    "confirmationWeight": current,
                    "weight": weight,
                    "reputation": reputation,
                    "delta": delta,
                    "positiveDrop": positive_drop,
                    "state": state,
                    "severity": sev,
                },
            )
            previous_weight = current

        perf_row = performance.get(address, {})
        rewarded_raw = as_decimal(perf_row.get("rewarded_coins"))
        paid_gnk = from_ngonka(rewarded_raw)
        not_rewarded = rewarded_raw == 0
        models = node_models(address, members_by_model)

        entry_row = snapshots["epoch_entry"].get(address, {})
        source_weight = as_decimal(entry_row.get("weight"))

        correct_reward_raw = Decimal("0")
        compensation_raw = Decimal("0")
        if epoch == SOURCE_COMPENSATION_EPOCH and address in E265_SOURCE_COMPENSATION_ADDRESSES and total_epoch_weight > 0:
            correct_reward_raw = reward_raw * source_weight / total_epoch_weight
            compensation_raw = max(Decimal("0"), correct_reward_raw - rewarded_raw)

        drop_loss_weight = Decimal(total_positive_drop)
        drop_loss_raw = Decimal("0")
        if total_epoch_weight > 0 and drop_loss_weight > 0:
            drop_loss_raw = reward_raw * drop_loss_weight / total_epoch_weight

        node_row = {
            "address": address,
            "shortAddress": short_address(address),
            "models": models,
            "modelNames": [item["model"] for item in models],
            "modelRows": node_model_rows(models, checkpoints_rows),
            "checkpoints": checkpoints_rows,
            "totalPositiveDrop": total_positive_drop,
            "totalNegativeDelta": total_negative_delta,
            "worstSeverity": worst_severity,
            "paidGnk": money(paid_gnk),
            "sourceCompensationEligible": epoch == SOURCE_COMPENSATION_EPOCH and address in E265_SOURCE_COMPENSATION_ADDRESSES,
            "sourceCompensationWeight": int(source_weight),
            "sourceCorrectRewardGnk": money(from_ngonka(correct_reward_raw)),
            "sourceCompensationGnk": money(from_ngonka(compensation_raw)),
            "vote67PaidGnk": money(from_ngonka(compensation_raw)),
            "vote67PaidBasis": f"Vote #67 source model applied to epoch {SOURCE_COMPENSATION_EPOCH} only."
            if epoch == SOURCE_COMPENSATION_EPOCH
            else "",
            "dropLossGnk": money(from_ngonka(drop_loss_raw)),
            "dropLossWeight": int(drop_loss_weight),
            "dropLossBasis": (
                "Observed cPoC drop loss: sum of positive confirmed-weight drops across saved cPoC checkpoints "
                "/ total epoch weight * epoch reward."
                if drop_loss_raw > 0
                else "No observed positive confirmed-weight drop across saved cPoC checkpoints."
            ),
            "sourceCompensationBasis": (
                "max(0, entry weight / total epoch weight * epoch reward - actual rewards)."
                if epoch == SOURCE_COMPENSATION_EPOCH and compensation_raw > 0
                else "Not in source-compensation set for this epoch."
            ),
            "rewarded": not not_rewarded,
            "notRewarded": not_rewarded,
            "inferenceCount": as_int(perf_row.get("inference_count")),
            "missedRequests": as_int(perf_row.get("missed_requests")),
            "validatedInferences": as_int(perf_row.get("validated_inferences")),
            "invalidatedInferences": as_int(perf_row.get("invalidated_inferences")),
            "claimed": bool(perf_row.get("claimed")) if perf_row else False,
        }
        nodes.append(node_row)
        positive_drop_by_address[address] = total_positive_drop

    total_positive_drop = sum(positive_drop_by_address.values())
    unpaid_raw = as_decimal(unpaid_rewards(epoch))

    checkpoint_estimates = []
    for key in sorted(progressions):
        drop = progressions[key]
        estimate = Decimal("0")
        if total_positive_drop > 0 and drop > 0:
            estimate = unpaid_raw * Decimal(drop) / Decimal(total_positive_drop)
        checkpoint_estimates.append(
            {
                "checkpoint": key,
                "positiveDrop": as_int(drop),
                "estimatedLostGnk": money(estimate),
            },
        )

    for node in nodes:
        if total_positive_drop > 0 and node["totalPositiveDrop"] > 0:
            estimate = unpaid_raw * Decimal(node["totalPositiveDrop"]) / Decimal(total_positive_drop)
        else:
            estimate = Decimal("0")
        node["estimatedLostGnk"] = money(estimate)
        node["estimatedLostBasis"] = (
            "Estimated from exact unpaid pool allocated by observed confirmation-weight drops."
            if estimate > 0
            else "No observed positive confirmation-weight drop allocation."
        )

    source_compensation_total = sum(as_decimal(row["sourceCompensationGnk"]) for row in nodes)
    drop_loss_total = sum(as_decimal(row["dropLossGnk"]) for row in nodes)

    return nodes, {
        "totalPositiveDrop": total_positive_drop,
        "checkpointEstimates": checkpoint_estimates,
        "sourceCompensationTotalGnk": money(source_compensation_total),
        "vote67PaidTotalGnk": money(source_compensation_total),
        "dropLossTotalGnk": money(drop_loss_total),
        "sourceCompensationCheckpoint": "after_cpoc_2",
        "sourceCompensationBasis": (
            "Epoch 265 source model from known counterfactual set."
            if source_compensation_total > 0
            else "No source-compensation addresses detected for this epoch."
        ),
        "allocationBasis": "Exact unpaid pool allocated across address-level positive confirmation-weight drops.",
        "precision": "Estimate only; proof-grade per-host amount requires settlement replay.",
    }


def unpaid_rewards(epoch: int) -> str:
    # We keep this helper for parity with the prior behavior.
    summary = read_csv(OUTPUTS / "epoch_summary.csv")
    for row in summary:
        if row.get("epoch") == str(epoch):
            if row.get("undistributed_remainder_gnk"):
                return row["undistributed_remainder_gnk"]
    return "0"


def epoch_totals(epoch: int, unpaid_pool_raw: str) -> dict[str, Any]:
    summary = load_epoch_summary().get(str(epoch))
    gov = load_gov_settlement().get(str(epoch))
    performance = load_performance_rows(epoch)
    paid_raw = sum(as_decimal(row.get("rewarded_coins")) for row in performance.values())
    reward_raw = epoch_reward_raw(epoch)
    unpaid_raw = as_decimal(unpaid_pool_raw)
    if unpaid_raw == 0:
        unpaid_raw = reward_raw - paid_raw
    cap_factor, cap_basis = cap_factor_value(epoch)
    return {
        "epoch": epoch,
        "epochRewardPoolGnk": money(from_ngonka(reward_raw)),
        "paidRewardsGnk": money(from_ngonka(paid_raw)),
        "unpaidPoolGnk": money(from_ngonka(unpaid_raw)),
        "govRemainderEventGnk": money(as_decimal(gov["current_epoch_gov_remainder_event_gnk"]) / Decimal("1000"))
        if gov and gov.get("current_epoch_gov_remainder_event_gnk")
        else "",
        "participantsTotal": as_int(summary.get("participants_total")) if summary else 0,
        "finalGroupCount": as_int(summary.get("final_group_count")) if summary else 0,
        "rewardedCount": as_int(summary.get("rewarded_count")) if summary else 0,
        "notRewardedCount": as_int(summary.get("not_rewarded_count")) if summary else 0,
        "capFactor": cap_factor,
        "capFactorBasis": cap_basis,
        "unpaidPoolBasis": "Derived from epoch_summary. Fallback: epoch reward minus paid rewards.",
    }


def build_events(
    epoch: int,
    checkpoints: list[dict[str, Any]],
    payout: dict[str, Any],
    effects_rows: dict[int, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    payout_by_checkpoint = {row["checkpoint"]: row for row in payout["checkpointEstimates"]}
    effects = {as_int(effect.get("cpoc_sequence")): effect for effect in effects_rows.get(epoch, []) if effect.get("cpoc_sequence")}
    events = []
    for item in checkpoints:
        key = item["key"]
        cpoc_sequence = item["cpocSequence"]
        effect = effects.get(cpoc_sequence, {}) if cpoc_sequence is not None else {}
        estimate = payout_by_checkpoint.get(key, {})
        source_compensation = (
            payout["sourceCompensationTotalGnk"] if key == payout.get("sourceCompensationCheckpoint") else "0.000000"
        )
        events.append(
            {
                **item,
                "parentConfirmationDelta": as_int(effect.get("parent_confirmation_delta")),
                "kimiConfirmationDelta": as_int(effect.get("kimi_confirmation_delta")),
                "parentZeroBefore": as_int(effect.get("parent_zero_confirmation_before")),
                "parentZeroAfter": as_int(effect.get("parent_zero_confirmation_after")),
                "kimiZeroBefore": as_int(effect.get("kimi_zero_confirmation_before")),
                "kimiZeroAfter": as_int(effect.get("kimi_zero_confirmation_after")),
                "positiveDrop": as_int(estimate.get("positiveDrop")),
                "estimatedLostGnk": estimate.get("estimatedLostGnk", "0.000000"),
                "sourceCompensationGnk": source_compensation,
            },
        )
    return events


def transition_from_previous(
    previous_epoch: int | None,
    current_epoch: int,
    members_by_epoch: dict[int, dict[str, dict[str, int]]],
    model_members_by_epoch: dict[int, dict[str, list[str]]],
) -> dict[str, Any] | None:
    if previous_epoch is None:
        return None
    previous_members = members_by_epoch.get(previous_epoch, {})
    current_members = members_by_epoch.get(current_epoch, {})
    previous_models = model_members_by_epoch.get(previous_epoch, {})
    current_models = model_members_by_epoch.get(current_epoch, {})
    previous_addresses = set(previous_members.keys())
    current_addresses = set(current_members.keys())
    dropped_addresses = sorted(previous_addresses - current_addresses)
    added_addresses = sorted(current_addresses - previous_addresses)
    retained_addresses = sorted(previous_addresses & current_addresses)

    dropped_model_counts = {"Kimi": 0, "Qwen": 0, "both": 0, "none": 0}
    added_model_counts = {"Kimi": 0, "Qwen": 0, "both": 0, "none": 0}

    dropped_rows = []
    for address in dropped_addresses:
        models = previous_models.get(address, [])
        if len(models) >= 2:
            dropped_model_counts["both"] += 1
        elif len(models) == 1:
            dropped_model_counts[models[0]] += 1
        else:
            dropped_model_counts["none"] += 1
        dropped_rows.append(
            {
                "address": address,
                "shortAddress": short_address(address),
                "weight": previous_members[address].get("weight", 0),
                "confirmationWeight": previous_members[address].get("confirmationWeight", 0),
                "previousModels": models,
            }
        )

    added_rows = []
    for address in added_addresses:
        models = current_models.get(address, [])
        if len(models) >= 2:
            added_model_counts["both"] += 1
        elif len(models) == 1:
            added_model_counts[models[0]] += 1
        else:
            added_model_counts["none"] += 1
        added_rows.append(
            {
                "address": address,
                "shortAddress": short_address(address),
                "weight": current_members[address].get("weight", 0),
                "confirmationWeight": current_members[address].get("confirmationWeight", 0),
                "currentModels": models,
            }
        )

    return {
        "fromEpoch": previous_epoch,
        "toEpoch": current_epoch,
        "dropped": dropped_rows,
        "added": added_rows,
        "retainedCount": len(retained_addresses),
        "droppedCount": len(dropped_addresses),
        "addedCount": len(added_addresses),
        "previousCount": len(previous_addresses),
        "currentCount": len(current_addresses),
        "modelBreakdown": {
            "dropped": dropped_model_counts,
            "added": added_model_counts,
        },
        "fromWeights": {
            "droppedMin": min((previous_members[address].get("weight", 0) for address in dropped_addresses), default=0),
            "droppedMax": max((previous_members[address].get("weight", 0) for address in dropped_addresses), default=0),
        },
        "toWeights": {
            "addedMin": min((current_members[address].get("weight", 0) for address in added_addresses), default=0),
            "addedMax": max((current_members[address].get("weight", 0) for address in added_addresses), default=0),
        },
    }


def build_epoch_payload(
    epoch: int,
    progression_rows_by_epoch: dict[int, list[dict[str, str]]],
    effects_by_epoch: dict[int, list[dict[str, str]]],
    epoch_summaries: dict[str, dict[str, str]],
    previous_epoch: int | None,
    members_by_epoch: dict[int, dict[str, dict[str, int]]],
    model_members_by_epoch: dict[int, dict[str, list[str]]],
) -> tuple[str, dict[str, Any], list[str]]:
    progression_rows = model_progression_rows(epoch, progression_rows_by_epoch)
    checkpoints = checkpoint_defs(epoch, progression_rows, effects_by_epoch)
    members = model_members(epoch)
    performance = load_performance_rows(epoch)
    progression_keys = model_checkpoint_keys(checkpoints)
    nodes, payout = build_nodes(epoch, checkpoints, members, performance, progression_keys)
    total_unpaid_raw = unpaid_rewards(epoch)
    totals = epoch_totals(epoch, total_unpaid_raw)

    # order: primarily by potential compensation > drop > estimated lost > raw drop
    nodes.sort(
        key=lambda item: (
            as_decimal(item["sourceCompensationGnk"]),
            as_decimal(item["dropLossGnk"]),
            as_decimal(item["estimatedLostGnk"]),
            item["totalPositiveDrop"],
        ),
        reverse=True,
    )

    totals["sourceCompensationGnk"] = payout["sourceCompensationTotalGnk"]
    totals["vote67PaidGnk"] = payout["vote67PaidTotalGnk"]
    totals["dropLossGnk"] = payout["dropLossTotalGnk"]

    epoch_summary = epoch_summaries.get(str(epoch), {})
    reward_basis = (
        "epoch summary rows and performance rewards agree; "
        "source compensation is a counterfactual model."
    )
    if summary_epoch := epoch_summary.get("difference"):
        if str(summary_epoch).strip():
            reward_basis = "Chain settlement fields are preserved for investigation evidence."

    event_rows = build_events(epoch, checkpoints, payout, effects_by_epoch)

    payload: dict[str, Any] = {
        "metadata": {
            "title": f"Epoch {epoch} cPoC timeline",
            "generatedFrom": "saved raw chain cache and derived CSV outputs",
            "epoch": epoch,
        },
        "epochTotals": totals,
        "payoutEstimates": payout,
        "events": event_rows,
        "modelSeries": progression_series(epoch, progression_rows_by_epoch),
        "nodes": nodes,
        "transitionFromPrevious": transition_from_previous(previous_epoch, epoch, members_by_epoch, model_members_by_epoch),
        "warnings": [
            reward_basis,
            "Source compensation is a counterfactual model, not a direct gov-wallet remainder allocation.",
            "Drop-allocation estimates remain diagnostic only and are not shown as primary compensation values.",
            "Chain data shows confirmation-weight drops and settlement effects; attack attribution is investigation context.",
        ],
    }
    return str(epoch), payload, progression_keys


def build_members_by_epoch(epochs: list[int]) -> dict[int, dict[str, dict[str, int]]]:
    members: dict[int, dict[str, dict[str, int]]] = {}
    for epoch in epochs:
        members[epoch] = {}
        for row in epoch_group_data(epoch).get("validation_weights", []):
            if not (isinstance(row, dict) and row.get("member_address")):
                continue
            address = str(row["member_address"])
            members[epoch][address] = {
                "weight": as_int(row.get("weight")),
                "confirmationWeight": as_int(row.get("confirmation_weight")),
            }
    return members


def main() -> None:
    epochs = list_epochs()
    if not epochs:
        raise RuntimeError("No epoch_* directories found in raw_chain_cache.")

    progression_rows_by_epoch = load_model_progression_rows()
    effects_by_epoch = load_cpoc_effect_rows()
    epoch_summaries = load_epoch_summary()

    members_by_epoch = build_members_by_epoch(epochs)
    model_membership = model_membership_by_epoch(epochs)
    payloads: dict[str, dict[str, Any]] = {}
    bundle: dict[str, Any] = {
        "metadata": {
            "title": "GONKA epoch cPoC attack timeline",
            "generatedFrom": "saved raw chain cache and derived CSV outputs",
            "generatedAtUtc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "availableEpochs": epochs,
        "epochs": payloads,
    }

    for index, epoch in enumerate(epochs):
        previous_epoch = epochs[index - 1] if index > 0 else None
        key, payload, _ = build_epoch_payload(
            epoch,
            progression_rows_by_epoch,
            effects_by_epoch,
            epoch_summaries,
            previous_epoch,
            members_by_epoch,
            model_membership,
        )

        payloads[key] = payload

        per_epoch_output = DOCS_DATA / f"epoch_{epoch}_timeline.json"
        per_epoch_output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    output_bundle = DOCS_DATA / "epochs_timeline.json"
    output_bundle.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n")
    print(
        f'Wrote {output_bundle.relative_to(REPO_ROOT)} with {len(payloads)} epoch payloads; '
        f'latest epoch {max(epochs)}.',
    )


if __name__ == "__main__":
    main()
