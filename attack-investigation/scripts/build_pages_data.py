#!/usr/bin/env python3
"""Build static GitHub Pages data for the epoch 265 attack visualization."""

from __future__ import annotations

import csv
import json
from decimal import Decimal, ROUND_HALF_UP, localcontext
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUTS = ROOT / "outputs"
DOCS_DATA = REPO_ROOT / "docs" / "data"
OUTPUT_JSON = DOCS_DATA / "epoch_265_timeline.json"
EPOCH = 265
GONKA_DENOM = Decimal("1000000000")

E265_SOURCE_COMPENSATION_ADDRESSES = {
    "gonka1j7x6dv42xehe9e5au4ku3wvzwtqlegfjhlvzj6",
    "gonka17pw6099q758qwzewtrqmqpf5c2lrhr97fwqexu",
    "gonka1830lqug50lse998x2lakk4pj5ypfumz5pasz0y",
}

MODEL_FILES = {
    "Kimi": "moonshotai_kimi_k2_6.json",
    "Qwen": "qwen_qwen3_235b_a22b_instruct_2507_fp8.json",
}

AFTER_CPOC_HEIGHTS = {
    0: 4095963,
    1: 4099160,
    2: 4103171,
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def as_int(value: Any) -> int:
    if value in (None, ""):
        return 0
    return int(Decimal(str(value)))


def as_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    return Decimal(str(value))


def money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP), "f")


def from_ngonka(value: Decimal) -> Decimal:
    return value / GONKA_DENOM


def decimal_param(value: Any) -> Decimal | None:
    if isinstance(value, dict) and "value" in value and "exponent" in value:
        parsed_value = as_decimal(value.get("value"))
        parsed_exp = as_int(value.get("exponent"))
        return parsed_value * (Decimal(10) ** parsed_exp)
    if value in (None, ""):
        return None
    return as_decimal(value)


def epoch_reward_raw() -> Decimal:
    params = read_json(RAW_ROOT / f"epoch_{EPOCH}" / "params_current.json")
    bitcoin_params = params.get("params", {}).get("bitcoin_reward_params", {})
    initial = as_decimal(bitcoin_params.get("initial_epoch_reward"))
    decay = decimal_param(bitcoin_params.get("decay_rate"))
    genesis = as_decimal(bitcoin_params.get("genesis_epoch"))
    if decay is None:
        raise ValueError("missing bitcoin reward decay_rate")
    epochs_since_genesis = int(Decimal(EPOCH) - genesis)
    with localcontext() as ctx:
        ctx.prec = 80
        current_reward = initial * ((decay.exp()) ** epochs_since_genesis)
    return Decimal(int(current_reward))


def block_time(height: int) -> str:
    candidates = [
        RAW_ROOT / f"epoch_{EPOCH}" / "cpoc_confirmation_snapshots" / "block_headers" / f"block_{height}.json",
        RAW_ROOT / f"epoch_{EPOCH}" / "cpoc_history" / "block_headers" / f"block_{height}.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        header = read_json(path).get("block", {}).get("header", {})
        if header.get("time"):
            raw = str(header["time"])
            return raw.split(".", 1)[0] + "Z" if "." in raw else raw
    return ""


def snapshot_rows(height: int) -> dict[str, dict[str, Any]]:
    path = (
        RAW_ROOT
        / f"epoch_{EPOCH}"
        / "cpoc_confirmation_snapshots"
        / f"parent_epoch_group_data_at_{height}.json"
    )
    data = read_json(path)
    rows = data.get("epoch_group_data", {}).get("validation_weights", [])
    return {
        str(row["member_address"]): row
        for row in rows
        if isinstance(row, dict) and row.get("member_address")
    }


def model_members() -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for model, filename in MODEL_FILES.items():
        data = read_json(RAW_ROOT / f"epoch_{EPOCH}" / "model_group_data" / filename)
        rows = data.get("epoch_group_data", {}).get("validation_weights", [])
        result[model] = {
            str(row["member_address"]): row
            for row in rows
            if isinstance(row, dict) and row.get("member_address")
        }
    return result


def event_generation_heights() -> dict[int, int]:
    data = read_json(RAW_ROOT / f"epoch_{EPOCH}" / "cpoc_history" / "confirmation_poc_events.json")
    result: dict[int, int] = {}
    for event in data.get("events", []):
        result[as_int(event.get("event_sequence"))] = as_int(event.get("generation_start_height"))
    return result


def epoch_group() -> dict[str, Any]:
    return read_json(RAW_ROOT / f"epoch_{EPOCH}" / "epoch_group_data.json").get("epoch_group_data", {})


def performance_rows() -> dict[str, dict[str, Any]]:
    data = read_json(RAW_ROOT / f"epoch_{EPOCH}" / "epoch_performance_summary.json")
    return {
        str(row["participant_id"]): row
        for row in data.get("epochPerformanceSummary", [])
        if isinstance(row, dict) and row.get("participant_id")
    }


def short_address(address: str) -> str:
    if len(address) <= 18:
        return address
    return f"{address[:10]}...{address[-6:]}"


def checkpoint_defs() -> list[dict[str, Any]]:
    group = epoch_group()
    generation = event_generation_heights()
    checkpoints: list[dict[str, Any]] = [
        {
            "key": "epoch_entry",
            "label": "Epoch entry",
            "height": as_int(group.get("effective_block_height")),
            "type": "epoch_entry",
            "cpocSequence": None,
        }
    ]
    for sequence, after_height in sorted(AFTER_CPOC_HEIGHTS.items()):
        checkpoints.append(
            {
                "key": f"cpoc_{sequence}_generation_start",
                "label": f"cPoC {sequence} generation start",
                "height": generation[sequence],
                "type": "cpoc_generation_start",
                "cpocSequence": sequence,
            }
        )
        checkpoints.append(
            {
                "key": f"after_cpoc_{sequence}",
                "label": f"After cPoC {sequence}",
                "height": after_height,
                "type": "after_cpoc_confirmed",
                "cpocSequence": sequence,
            }
        )
    checkpoints.append(
        {
            "key": "epoch_last",
            "label": "Epoch last block",
            "height": as_int(group.get("last_block_height")),
            "type": "epoch_last",
            "cpocSequence": None,
        }
    )
    for index, item in enumerate(checkpoints):
        item["timeUtc"] = block_time(item["height"])
        item["order"] = index
    return checkpoints


def progression_rows() -> list[dict[str, str]]:
    rows = read_csv(OUTPUTS / "model_confirmed_weight_progression_wide.csv")
    return [row for row in rows if row.get("epoch") == str(EPOCH)]


def epoch_totals() -> dict[str, Any]:
    summary = next(row for row in read_csv(OUTPUTS / "epoch_summary.csv") if row["epoch"] == str(EPOCH))
    gov = next(row for row in read_csv(OUTPUTS / "gov_settlement_audit.csv") if row["epoch"] == str(EPOCH))
    reward_raw = epoch_reward_raw()
    paid_raw = sum(as_decimal(row.get("rewarded_coins")) for row in performance_rows().values())
    unpaid_raw = reward_raw - paid_raw
    return {
        "epoch": EPOCH,
        "epochRewardPoolGnk": money(from_ngonka(reward_raw)),
        "paidRewardsGnk": money(from_ngonka(paid_raw)),
        "unpaidPoolGnk": money(from_ngonka(unpaid_raw)),
        "govRemainderEventGnk": money(as_decimal(gov["current_epoch_gov_remainder_event_gnk"]) / Decimal("1000")),
        "participantsTotal": as_int(summary["participants_total"]),
        "finalGroupCount": as_int(summary["final_group_count"]),
        "rewardedCount": as_int(summary["rewarded_count"]),
        "notRewardedCount": as_int(summary["not_rewarded_count"]),
        "unpaidPoolBasis": "Exact chain settlement remainder; not per-host allocation.",
    }


def model_series() -> list[dict[str, Any]]:
    output = []
    for row in progression_rows():
        output.append(
            {
                "checkpoint": row["checkpoint"],
                "height": as_int(row["height"]),
                "timeUtc": row["time_utc_seconds"],
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
            }
        )
    return output


def model_checkpoint_keys() -> list[str]:
    return ["epoch_entry", "after_cpoc_0", "after_cpoc_1", "after_cpoc_2"]


def snapshot_by_checkpoint() -> dict[str, dict[str, dict[str, Any]]]:
    height_by_key = {
        "epoch_entry": as_int(epoch_group().get("effective_block_height")),
        **{f"after_cpoc_{sequence}": height for sequence, height in AFTER_CPOC_HEIGHTS.items()},
    }
    return {key: snapshot_rows(height) for key, height in height_by_key.items()}


def node_models(address: str, members: dict[str, dict[str, dict[str, Any]]]) -> list[dict[str, Any]]:
    output = []
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
            }
        )
    return output


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
        checkpoint_rows: list[dict[str, Any]] = []
        for checkpoint in checkpoints:
            current = model_weights_by_checkpoint[checkpoint["checkpoint"]].get(model["model"], 0)
            delta = None if previous_weight is None else current - previous_weight
            checkpoint_rows.append(
                {
                    "checkpoint": checkpoint["checkpoint"],
                    "confirmationWeight": current,
                    "delta": delta,
                    "severity": "entry" if previous_weight is None else severity(previous_weight, current),
                }
            )
            previous_weight = current
        output.append(
            {
                "model": model["model"],
                "entryWeight": model["entryWeight"],
                "splitBasis": "exact" if len(models) == 1 else "allocated_by_entry_split",
                "checkpoints": checkpoint_rows,
            }
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


def build_nodes(unpaid_pool_gnk: Decimal) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshots = snapshot_by_checkpoint()
    members = model_members()
    perf = performance_rows()
    reward_raw = epoch_reward_raw()
    total_epoch_weight = as_decimal(epoch_group().get("total_weight"))
    all_addresses = set(perf)
    for rows in snapshots.values():
        all_addresses.update(rows)
    for rows in members.values():
        all_addresses.update(rows)

    positive_drop_by_address: dict[str, int] = {}
    positive_drop_by_checkpoint: dict[str, int] = {key: 0 for key in model_checkpoint_keys()[1:]}
    raw_nodes: list[dict[str, Any]] = []

    for address in sorted(all_addresses):
        checkpoints = []
        previous_weight: int | None = None
        total_positive_drop = 0
        total_negative_delta = 0
        worst = "stable_or_gain"
        for key in model_checkpoint_keys():
            row = snapshots[key].get(address)
            current = as_int(row.get("confirmation_weight")) if row else 0
            weight = as_int(row.get("weight")) if row else 0
            reputation = as_int(row.get("reputation")) if row else None
            delta = None if previous_weight is None else current - previous_weight
            positive_drop = 0 if delta is None else max(-delta, 0)
            if positive_drop:
                total_positive_drop += positive_drop
                total_negative_delta -= positive_drop
                positive_drop_by_checkpoint[key] = positive_drop_by_checkpoint.get(key, 0) + positive_drop
            state = "missing" if row is None else ("failed" if current == 0 else "passed")
            sev = "entry" if previous_weight is None else severity(previous_weight, current)
            if sev == "severe_drop":
                worst = "severe_drop"
            elif sev == "moderate_drop" and worst != "severe_drop":
                worst = "moderate_drop"
            elif sev == "small_drop" and worst == "stable_or_gain":
                worst = "small_drop"
            checkpoints.append(
                {
                    "checkpoint": key,
                    "confirmationWeight": current,
                    "weight": weight,
                    "reputation": reputation,
                    "delta": delta,
                    "positiveDrop": positive_drop,
                    "state": state,
                    "severity": sev,
                }
            )
            previous_weight = current

        perf_row = perf.get(address, {})
        rewarded_ngnk = as_decimal(perf_row.get("rewarded_coins"))
        paid_gnk = from_ngonka(rewarded_ngnk)
        not_rewarded = rewarded_ngnk == 0
        models = node_models(address, members)
        entry_row = snapshots["epoch_entry"].get(address, {})
        source_weight = as_decimal(entry_row.get("weight"))
        correct_reward_raw = Decimal("0")
        compensation_raw = Decimal("0")
        drop_loss_weight = Decimal(total_positive_drop)
        drop_loss_raw = Decimal("0")
        if total_epoch_weight > 0 and drop_loss_weight > 0:
            drop_loss_raw = reward_raw * drop_loss_weight / total_epoch_weight
        if address in E265_SOURCE_COMPENSATION_ADDRESSES and total_epoch_weight > 0:
            correct_reward_raw = reward_raw * source_weight / total_epoch_weight
            compensation_raw = max(Decimal("0"), correct_reward_raw - rewarded_ngnk)
        raw_nodes.append(
            {
                "address": address,
                "shortAddress": short_address(address),
                "models": models,
                "modelNames": [item["model"] for item in models],
                "modelRows": node_model_rows(models, checkpoints),
                "checkpoints": checkpoints,
                "totalPositiveDrop": total_positive_drop,
                "totalNegativeDelta": total_negative_delta,
                "worstSeverity": worst,
                "paidGnk": money(paid_gnk),
                "sourceCompensationEligible": address in E265_SOURCE_COMPENSATION_ADDRESSES,
                "sourceCompensationWeight": int(source_weight),
                "sourceCorrectRewardGnk": money(from_ngonka(correct_reward_raw)),
                "sourceCompensationGnk": money(from_ngonka(compensation_raw)),
                "vote67PaidGnk": money(from_ngonka(compensation_raw)),
                "vote67PaidBasis": "Vote #67 Kimi Restitution e265 amount from the source compensation model.",
                "dropLossGnk": money(from_ngonka(drop_loss_raw)),
                "dropLossWeight": int(drop_loss_weight),
                "dropLossBasis": (
                    "Observed cPoC drop loss: sum of positive confirmed-weight drops across saved cPoC checkpoints "
                    "/ total epoch weight * epoch reward."
                    if drop_loss_raw > 0
                    else "No observed positive confirmed-weight drop across saved cPoC checkpoints."
                ),
                "sourceCompensationBasis": (
                    "E265 source model: max(0, entry weight / total epoch weight * epoch reward - actual rewards)."
                    if compensation_raw > 0
                    else "Not in the epoch 265 source compensation set."
                ),
                "rewarded": not not_rewarded,
                "notRewarded": not_rewarded,
                "inferenceCount": as_int(perf_row.get("inference_count")),
                "missedRequests": as_int(perf_row.get("missed_requests")),
                "validatedInferences": as_int(perf_row.get("validated_inferences")),
                "invalidatedInferences": as_int(perf_row.get("invalidated_inferences")),
                "claimed": bool(perf_row.get("claimed")) if perf_row else False,
            }
        )
        positive_drop_by_address[address] = total_positive_drop

    total_positive_drop = sum(positive_drop_by_address.values())
    for node in raw_nodes:
        if total_positive_drop > 0 and node["totalPositiveDrop"] > 0:
            estimate = unpaid_pool_gnk * Decimal(node["totalPositiveDrop"]) / Decimal(total_positive_drop)
        else:
            estimate = Decimal("0")
        node["estimatedLostGnk"] = money(estimate)
        node["estimatedLostBasis"] = (
            "Estimated from exact unpaid pool allocated by observed confirmation-weight drops."
            if estimate > 0
            else "No observed positive confirmation-weight drop allocation."
        )

    checkpoint_estimates = []
    for key, drop in positive_drop_by_checkpoint.items():
        estimate = Decimal("0")
        if total_positive_drop > 0 and drop > 0:
            estimate = unpaid_pool_gnk * Decimal(drop) / Decimal(total_positive_drop)
        checkpoint_estimates.append(
            {
                "checkpoint": key,
                "positiveDrop": drop,
                "estimatedLostGnk": money(estimate),
            }
        )

    source_compensation_total = sum(as_decimal(row["sourceCompensationGnk"]) for row in raw_nodes)
    drop_loss_total = sum(as_decimal(row["dropLossGnk"]) for row in raw_nodes)
    return raw_nodes, {
        "totalPositiveDrop": total_positive_drop,
        "checkpointEstimates": checkpoint_estimates,
        "sourceCompensationTotalGnk": money(source_compensation_total),
        "vote67PaidTotalGnk": money(source_compensation_total),
        "dropLossTotalGnk": money(drop_loss_total),
        "sourceCompensationCheckpoint": "after_cpoc_2",
        "sourceCompensationBasis": (
            "E265 source model from votkon/gonka-kimi-restitution: max(0, entry weight / total epoch weight "
            "* epoch reward - actual rewards), using GONKA denom 1e9."
        ),
        "allocationBasis": "Exact unpaid pool allocated across address-level positive confirmation-weight drops.",
        "precision": "Estimate only; proof-grade per-host amount requires settlement replay.",
    }


def build_events(payout: dict[str, Any]) -> list[dict[str, Any]]:
    payout_by_checkpoint = {row["checkpoint"]: row for row in payout["checkpointEstimates"]}
    effects = {
        f"after_cpoc_{row['cpoc_sequence']}": row
        for row in read_csv(OUTPUTS / "per_cpoc_confirmation_effects.csv")
        if row["epoch"] == str(EPOCH)
    }
    events = []
    for item in checkpoint_defs():
        key = item["key"]
        effect = effects.get(key, {})
        estimate = payout_by_checkpoint.get(key, {})
        source_compensation = (
            payout["sourceCompensationTotalGnk"]
            if key == payout["sourceCompensationCheckpoint"]
            else "0.000000"
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
            }
        )
    return events


def main() -> None:
    DOCS_DATA.mkdir(parents=True, exist_ok=True)
    totals = epoch_totals()
    unpaid_pool = as_decimal(totals["unpaidPoolGnk"])
    nodes, payout = build_nodes(unpaid_pool)
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
    data = {
        "metadata": {
            "title": "Epoch 265 cPoC attack timeline",
            "generatedFrom": "saved raw chain cache and derived CSV outputs",
            "epoch": EPOCH,
        },
        "epochTotals": totals,
        "payoutEstimates": payout,
        "events": build_events(payout),
        "modelSeries": model_series(),
        "nodes": nodes,
        "warnings": [
            "Source compensation is a counterfactual model, not a direct gov-wallet remainder allocation.",
            "Drop-allocation estimates remain diagnostic only and are not shown as the primary compensation value.",
            "Chain data shows confirmation-weight drops and reward settlement effects; attack attribution is investigation context.",
        ],
    }
    OUTPUT_JSON.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(f"Wrote {OUTPUT_JSON.relative_to(REPO_ROOT)} with {len(nodes)} node rows.")


if __name__ == "__main__":
    main()
