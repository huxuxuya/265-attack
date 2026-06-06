#!/usr/bin/env python3
"""Classify source claim rows against saved chain data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
CLAIMS_ROOT = ROOT / "source_claims"
OUTPUT = ROOT / "outputs" / "affected_rows.csv"
CLAIMS_MANIFEST = ROOT / "manifests" / "source_claims_manifest.md"
DEFAULT_DENOM_EXPONENT = 6


COLUMNS = [
    "source",
    "claim_file",
    "claim_row",
    "epoch",
    "address",
    "classification",
    "confirmation_status",
    "source_compensation_gonka",
    "chain_reward_gonka",
    "chain_evidence",
    "policy_note",
]

ADDRESS_KEYS = {
    "address",
    "participant_id",
    "participantId",
    "member_address",
    "memberAddress",
    "operator_address",
    "operatorAddress",
    "validator_address",
    "validatorAddress",
    "delegator_address",
    "delegatorAddress",
}

EPOCH_KEYS = {"epoch", "epoch_index", "epochIndex"}
COMPENSATION_KEYS = {
    "source_compensation_gonka",
    "compensation_gonka",
    "claimed_compensation_gonka",
    "claimed_gonka",
    "amount_gonka",
    "compensation",
    "amount",
}
REWARD_KEYS = {"rewarded_coins", "rewardedCoins", "reward", "coins", "amount"}


def read_json(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, dict) and "amount" in value:
        value = value["amount"]
    text = str(value).replace(",", "").strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def to_gonka(value: Decimal | None, denom_exponent: int) -> str:
    if value is None:
        return ""
    scaled = value / (Decimal(10) ** denom_exponent)
    return format(scaled.normalize(), "f")


def claim_amount_gonka(row: dict[str, Any]) -> str:
    for key in COMPENSATION_KEYS:
        if key in row and row[key] not in (None, ""):
            parsed = decimal_or_none(row[key])
            if parsed is not None:
                return format(parsed.normalize(), "f")
            return str(row[key])
    return ""


def first_present(row: dict[str, Any], keys: set[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


def load_claim_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="") as fh:
            return [dict(row) for row in csv.DictReader(fh)]

    if path.suffix.lower() == ".json":
        data = read_json(path)
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list) and all(isinstance(row, dict) for row in value):
                    return value
            return [data]

    return []


def write_claims_manifest(paths: list[Path]) -> None:
    lines = [
        "# Source Claims Manifest",
        "",
        "| source | file | sha256 | bytes |",
        "|---|---|---|---:|",
    ]
    if not paths:
        lines.extend(["", "No source claim files were found."])
    for path in paths:
        source = path.parent.name
        lines.append(
            f"| {source} | {path.relative_to(ROOT).as_posix()} | {sha256_file(path)} | {path.stat().st_size} |"
        )
    CLAIMS_MANIFEST.write_text("\n".join(lines) + "\n")


def address_from(row: dict[str, Any]) -> str:
    return first_present(row, ADDRESS_KEYS)


def reward_from(row: dict[str, Any]) -> Decimal | None:
    for key in REWARD_KEYS:
        if key in row:
            parsed = decimal_or_none(row[key])
            if parsed is not None:
                return parsed
    return None


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


def performance_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("epochPerformanceSummary", "epoch_performance_summary", "performance_summary", "participants"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return [item for item in walk(data) if isinstance(item, dict) and any(key in item for key in ADDRESS_KEYS)]


def excluded_rows(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        for key in ("excluded_participants", "excludedParticipants", "excluded"):
            if isinstance(data.get(key), list):
                return [row for row in data[key] if isinstance(row, dict)]
    return []


def build_chain_index(denom_exponent: int) -> dict[str, dict[str, dict[str, str]]]:
    index: dict[str, dict[str, dict[str, str]]] = {}
    for epoch_dir in sorted(path for path in RAW_ROOT.glob("epoch_*") if path.is_dir()):
        epoch = epoch_dir.name.replace("epoch_", "")
        epoch_index: dict[str, dict[str, str]] = {}

        perf = read_json(epoch_dir / "epoch_performance_summary.json")
        for row in performance_rows(perf):
            address = address_from(row)
            if not address:
                continue
            reward = reward_from(row)
            epoch_index.setdefault(address, {})
            epoch_index[address]["reward_gonka"] = to_gonka(reward, denom_exponent)
            if reward == 0:
                epoch_index[address]["zero_reward"] = "yes"

        participants = read_json(epoch_dir / "participants.json")
        for row in excluded_rows(participants):
            address = address_from(row)
            if not address:
                continue
            epoch_index.setdefault(address, {})
            epoch_index[address]["excluded"] = "yes"

        group = read_json(epoch_dir / "epoch_group_data.json")
        member_rows = first_list_key(group, {"member_seed_signatures", "memberSeedSignatures"})
        final_rows = first_list_key(group, {"validation_weights", "validationWeights"})
        if final_rows:
            perf_addresses = {
                address_from(row)
                for row in performance_rows(read_json(epoch_dir / "epoch_performance_summary.json"))
                if address_from(row)
            }
            member_addresses = {address_from(row) for row in member_rows if address_from(row)}
            candidate_addresses = member_addresses | perf_addresses
            final_addresses = {address_from(row) for row in final_rows if address_from(row)}
            for address in candidate_addresses - final_addresses:
                epoch_index.setdefault(address, {})
                epoch_index[address]["excluded"] = "yes"
                epoch_index[address]["excluded_source"] = "participant_minus_final_group"

        for poc_name in ("poc_commits", "poc_validations", "poc_validation_snapshot"):
            data = read_json(epoch_dir / f"{poc_name}.json")
            if data is None:
                continue
            for item in walk(data):
                if not isinstance(item, dict):
                    continue
                address = address_from(item)
                if not address:
                    continue
                epoch_index.setdefault(address, {})
                epoch_index[address][poc_name] = "yes"

        index[epoch] = epoch_index
    return index


def text_blob(row: dict[str, Any]) -> str:
    return " ".join(str(value).lower() for value in row.values() if value is not None)


def classify(row: dict[str, Any], chain: dict[str, str]) -> tuple[str, str, str, str]:
    blob = text_blob(row)

    if "delegator" in blob or "delegation" in blob:
        return (
            "delegator_indirect_loss",
            "policy-dependent",
            "delegator/delegation source claim",
            "Indirect delegator loss requires a separate policy decision.",
        )
    if "groupcap" in blob or "group cap" in blob or "group_cap" in blob:
        return (
            "groupcap_topup",
            "policy-dependent",
            "group cap source claim",
            "Group cap top-up should not be merged with direct cPoC compensation without approval.",
        )
    if chain.get("excluded") == "yes":
        evidence = (
            "address is in excluded_participants"
            if chain.get("excluded_source") != "participant_minus_final_group"
            else "address is in performance/member participant set but not validation_weights"
        )
        return ("excluded_operator", "confirmed", evidence, "")
    if chain.get("zero_reward") == "yes":
        return (
            "zero_reward_reconstruction",
            "policy-dependent",
            "address has zero rewarded_coins in performance summary",
            "Counterfactual reward reconstruction is required.",
        )
    if chain.get("poc_commits") == "yes" or chain.get("poc_validations") == "yes":
        return (
            "direct_cpoc_failure",
            "confirmed",
            "address appears in saved cPoC artifacts",
            "Confirm failure reason from cPoC artifacts before assigning amount.",
        )
    if chain.get("reward_gonka"):
        return (
            "rewarded_topup",
            "policy-dependent",
            "address received non-zero settlement reward",
            "Top-up amount is a compensation model, not settlement remainder.",
        )
    return ("not_confirmed", "not-confirmed", "no matching saved chain evidence", "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--denom-exponent", type=int, default=DEFAULT_DENOM_EXPONENT)
    args = parser.parse_args()

    claim_paths = sorted(
        path
        for path in CLAIMS_ROOT.glob("*/*")
        if path.is_file() and path.suffix.lower() in {".csv", ".json"}
    )
    write_claims_manifest(claim_paths)
    chain_index = build_chain_index(args.denom_exponent)

    output_rows: list[dict[str, str]] = []
    for epoch, addresses in sorted(chain_index.items()):
        for address, chain in sorted(addresses.items()):
            if chain.get("excluded") == "yes":
                output_rows.append(
                    {
                        "source": "chain",
                        "claim_file": "",
                        "claim_row": "",
                        "epoch": epoch,
                        "address": address,
                        "classification": "excluded_operator",
                        "confirmation_status": "confirmed",
                        "source_compensation_gonka": "",
                        "chain_reward_gonka": chain.get("reward_gonka", ""),
                        "chain_evidence": "address is in performance/member participant set but not validation_weights",
                        "policy_note": "",
                    }
                )
            if chain.get("zero_reward") == "yes":
                output_rows.append(
                    {
                        "source": "chain",
                        "claim_file": "",
                        "claim_row": "",
                        "epoch": epoch,
                        "address": address,
                        "classification": "zero_reward_reconstruction",
                        "confirmation_status": "policy-dependent",
                        "source_compensation_gonka": "",
                        "chain_reward_gonka": chain.get("reward_gonka", ""),
                        "chain_evidence": "address has zero rewarded_coins in performance summary",
                        "policy_note": "Counterfactual reward reconstruction is required.",
                    }
                )

    for claim_path in claim_paths:
        source = claim_path.parent.name
        rows = load_claim_file(claim_path)
        for idx, row in enumerate(rows, start=1):
            epoch = first_present(row, EPOCH_KEYS)
            address = address_from(row)
            chain = chain_index.get(epoch, {}).get(address, {}) if epoch and address else {}
            classification, status, evidence, policy_note = classify(row, chain)
            output_rows.append(
                {
                    "source": source,
                    "claim_file": claim_path.relative_to(ROOT).as_posix(),
                    "claim_row": str(idx),
                    "epoch": epoch,
                    "address": address,
                    "classification": classification,
                    "confirmation_status": status,
                    "source_compensation_gonka": claim_amount_gonka(row),
                    "chain_reward_gonka": chain.get("reward_gonka", ""),
                    "chain_evidence": evidence,
                    "policy_note": policy_note,
                }
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)

    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(output_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
