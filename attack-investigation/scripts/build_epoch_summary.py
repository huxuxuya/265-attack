#!/usr/bin/env python3
"""Build per-epoch summary from saved raw chain data."""

from __future__ import annotations

import argparse
import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUT = ROOT / "outputs" / "epoch_summary.csv"
DEFAULT_DENOM_EXPONENT = 6


SUMMARY_COLUMNS = [
    "epoch",
    "participants_total",
    "final_group_count",
    "rewarded_count",
    "not_rewarded_count",
    "excluded_count",
    "zero_reward_count",
    "epoch_reward_pool_gnk",
    "paid_rewards_gnk",
    "not_paid_rewards_gnk",
    "affected_rows",
    "affected_unique_addresses",
    "actual_rewarded_gonka",
    "burned_gonka",
    "undistributed_remainder_gonka",
    "source_compensation_gonka",
    "difference",
]


ADDRESS_KEYS = {
    "address",
    "participant_id",
    "participantId",
    "member_address",
    "memberAddress",
    "validator_address",
    "validatorAddress",
    "operator_address",
    "operatorAddress",
}

REWARD_KEYS = {
    "rewarded_coins",
    "rewardedCoins",
    "reward",
    "coins",
    "amount",
}
BURNED_KEYS = {"burned_coins", "burnedCoins"}

EXPECTED_REWARD_KEYS = {
    "epoch_reward",
    "epochReward",
    "total_epoch_reward",
    "totalEpochReward",
    "settlement_reward",
    "settlementReward",
    "fixed_epoch_reward",
    "fixedEpochReward",
}


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, dict) and "amount" in value:
        value = value["amount"]
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def to_gonka(value: Decimal | None, denom_exponent: int) -> str:
    if value is None:
        return ""
    scaled = value / (Decimal(10) ** denom_exponent)
    return format(scaled.normalize(), "f")


def to_gnk_6(value: Decimal | None, denom_exponent: int) -> str:
    if value is None:
        return ""
    scaled = value / (Decimal(10) ** denom_exponent)
    return format(scaled.quantize(Decimal("0.000001")), "f")


def decimal_param(value: Any) -> Decimal | None:
    if isinstance(value, dict) and "value" in value and "exponent" in value:
        parsed_value = decimal_or_none(value.get("value"))
        parsed_exp = decimal_or_none(value.get("exponent"))
        if parsed_value is None or parsed_exp is None:
            return None
        return parsed_value * (Decimal(10) ** int(parsed_exp))
    return decimal_or_none(value)


def first_key(obj: Any, keys: set[str]) -> Any | None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys:
                return value
        for value in obj.values():
            found = first_key(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = first_key(item, keys)
            if found is not None:
                return found
    return None


def first_list_key(obj: Any, keys: set[str]) -> list[dict[str, Any]]:
    value = first_key(obj, keys)
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    return []


def all_dicts_with_any_key(obj: Any, keys: set[str]) -> list[dict[str, Any]]:
    return [item for item in walk(obj) if isinstance(item, dict) and any(key in item for key in keys)]


def address_from(row: dict[str, Any]) -> str:
    for key in ADDRESS_KEYS:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def reward_from(row: dict[str, Any]) -> Decimal | None:
    for key in REWARD_KEYS:
        if key in row:
            value = decimal_or_none(row[key])
            if value is not None:
                return value
    return None


def burned_from(row: dict[str, Any]) -> Decimal | None:
    for key in BURNED_KEYS:
        if key in row:
            value = decimal_or_none(row[key])
            if value is not None:
                return value
    return None


def performance_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("epochPerformanceSummary", "epoch_performance_summary", "performance_summary", "participants"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return all_dicts_with_any_key(data, REWARD_KEYS | ADDRESS_KEYS)


def excluded_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("excluded_participants", "excludedParticipants", "excluded"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
    return []


def active_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        active = data.get("active_participants") or data.get("activeParticipants")
        if isinstance(active, dict):
            participants = active.get("participants")
            if isinstance(participants, list):
                return [row for row in participants if isinstance(row, dict)]
        for key in ("participants", "active"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
    return []


def final_group_count(data: Any) -> int | str:
    if data is None:
        return ""
    for key in ("validation_weights", "validationWeights", "members", "participants", "group"):
        value = first_key(data, {key})
        if isinstance(value, list):
            return len(value)
    count = first_key(data, {"final_group_count", "finalGroupCount", "group_count", "groupCount"})
    if count not in (None, ""):
        return str(count)
    return ""


def expected_reward(data_items: list[Any]) -> Decimal | None:
    for data in data_items:
        value = first_key(data, EXPECTED_REWARD_KEYS)
        parsed = decimal_or_none(value)
        if parsed is not None:
            return parsed
    return None


def calculated_epoch_reward_from_params(params: Any, epoch: int) -> Decimal | None:
    bitcoin_params = first_key(params, {"bitcoin_reward_params", "bitcoinRewardParams"})
    if not isinstance(bitcoin_params, dict):
        return None

    initial = decimal_or_none(bitcoin_params.get("initial_epoch_reward"))
    decay = decimal_param(bitcoin_params.get("decay_rate"))
    genesis = decimal_or_none(bitcoin_params.get("genesis_epoch"))
    if initial is None or decay is None or genesis is None:
        return None

    epochs_since_genesis = int(Decimal(epoch) - genesis)
    if epochs_since_genesis < 0:
        return None
    return initial * ((Decimal(1) + decay) ** epochs_since_genesis)


def load_epoch(epoch_dir: Path, denom_exponent: int) -> dict[str, str]:
    epoch = epoch_dir.name.replace("epoch_", "")
    perf = read_json(epoch_dir / "epoch_performance_summary.json")
    participants = read_json(epoch_dir / "participants.json")
    group = read_json(epoch_dir / "epoch_group_data.json")
    params = read_json(epoch_dir / "params_current.json")

    perf_rows = performance_rows(perf)
    excl_rows = excluded_rows(participants)
    act_rows = active_rows(participants)
    member_rows = first_list_key(group, {"member_seed_signatures", "memberSeedSignatures"})
    final_rows = first_list_key(group, {"validation_weights", "validationWeights"})

    total_reward = Decimal(0)
    total_burned = Decimal(0)
    zero_reward_addresses: set[str] = set()
    rewarded_addresses: set[str] = set()
    for row in perf_rows:
        reward = reward_from(row)
        address = address_from(row)
        if reward is not None:
            total_reward += reward
            if reward == 0:
                zero_reward_addresses.add(address)
            elif address:
                rewarded_addresses.add(address)
        burned = burned_from(row)
        if burned is not None:
            total_burned += burned

    excluded_addresses = {address_from(row) for row in excl_rows if address_from(row)}
    if not excluded_addresses and final_rows:
        member_addresses = {address_from(row) for row in member_rows if address_from(row)}
        member_addresses |= {address_from(row) for row in perf_rows if address_from(row)}
        final_addresses = {address_from(row) for row in final_rows if address_from(row)}
        excluded_addresses = member_addresses - final_addresses

    participant_addresses = {
        address
        for address in [*(address_from(row) for row in act_rows), *(address_from(row) for row in excl_rows)]
        if address
    }
    if not participant_addresses:
        participant_addresses = {address_from(row) for row in perf_rows if address_from(row)}
    if not participant_addresses and member_rows:
        participant_addresses = {address_from(row) for row in member_rows if address_from(row)}

    expected = expected_reward([group, params, perf])
    if expected is None:
        expected = calculated_epoch_reward_from_params(params, int(epoch))
    remainder = expected - total_reward if expected is not None else None

    affected_unique = {addr for addr in zero_reward_addresses | excluded_addresses if addr}
    affected_rows = len(zero_reward_addresses) + len(excluded_addresses)

    return {
        "epoch": epoch,
        "participants_total": str(len(participant_addresses) or len(perf_rows)),
        "final_group_count": str(final_group_count(group)),
        "rewarded_count": str(len(rewarded_addresses)),
        "not_rewarded_count": str(len(zero_reward_addresses)),
        "excluded_count": str(len(excluded_addresses)),
        "zero_reward_count": str(len(zero_reward_addresses)),
        "epoch_reward_pool_gnk": to_gnk_6(expected, denom_exponent),
        "paid_rewards_gnk": to_gnk_6(total_reward, denom_exponent),
        "not_paid_rewards_gnk": to_gnk_6(remainder, denom_exponent),
        "affected_rows": str(affected_rows),
        "affected_unique_addresses": str(len(affected_unique)),
        "actual_rewarded_gonka": to_gnk_6(total_reward, denom_exponent),
        "burned_gonka": to_gnk_6(total_burned, denom_exponent),
        "undistributed_remainder_gonka": to_gnk_6(remainder, denom_exponent),
        "source_compensation_gonka": "",
        "difference": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--denom-exponent", type=int, default=DEFAULT_DENOM_EXPONENT)
    args = parser.parse_args()

    epoch_dirs = sorted(path for path in RAW_ROOT.glob("epoch_*") if path.is_dir())
    rows = [load_epoch(epoch_dir, args.denom_exponent) for epoch_dir in epoch_dirs]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=SUMMARY_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
