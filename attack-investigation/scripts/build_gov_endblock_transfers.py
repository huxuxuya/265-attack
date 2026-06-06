#!/usr/bin/env python3
"""Build gov EndBlock transfer components from saved RPC block_results."""

from __future__ import annotations

import csv
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
SUMMARY = ROOT / "outputs" / "epoch_summary.csv"
SETTLEMENT_EVENTS = ROOT / "outputs" / "settlement_event_summary.csv"
OUTPUT = ROOT / "outputs" / "gov_endblock_transfers.csv"
DENOM_EXPONENT = 6


COLUMNS = [
    "epoch",
    "height",
    "event_order",
    "sender",
    "receiver",
    "amount_gnk",
    "inferred_role",
    "inference_basis",
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


def fmt(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.000001")), "f")


def ngonk_to_gnk(value: Decimal) -> Decimal:
    return value / (Decimal(10) ** DENOM_EXPONENT)


def event_attrs(event: dict[str, Any]) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for attr in event.get("attributes", []):
        if isinstance(attr, dict):
            attrs[str(attr.get("key", ""))] = str(attr.get("value", ""))
    return attrs


def iter_events(obj: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if isinstance(obj.get("type"), str) and isinstance(obj.get("attributes"), list):
            events.append(obj)
        for value in obj.values():
            events.extend(iter_events(value))
    elif isinstance(obj, list):
        for item in obj:
            events.extend(iter_events(item))
    return events


def read_by_epoch(path: Path, key: str = "epoch") -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open() as fh:
        return {row[key]: row for row in csv.DictReader(fh)}


def module_addresses() -> dict[str, str]:
    accounts = read_json(RAW_ROOT / "module_accounts.json")
    output: dict[str, str] = {}
    for account in accounts.get("accounts", []) if isinstance(accounts, dict) else []:
        if not isinstance(account, dict):
            continue
        name = account.get("name") or account.get("base_account", {}).get("name")
        address = account.get("address") or account.get("base_account", {}).get("address")
        if name and address:
            output[str(name)] = str(address)
    return output


def classify(amount: Decimal, formula_remainder: Decimal, matched_formula: bool) -> tuple[str, str, bool]:
    diff = abs(amount - formula_remainder)
    if not matched_formula and diff <= Decimal("0.000010"):
        return (
            "current_epoch_bitcoin_reward_remainder",
            "amount matches formula remainder from v0.2.13 reward formula and occurs before other gov receives",
            True,
        )
    return (
        "other_inference_to_gov_endblock_transfer",
        "same-height inference->gov EndBlock transfer; code path may include expired/unclaimed settle transfer, memo is not exposed in saved block_results",
        matched_formula,
    )


def main() -> int:
    summary = read_by_epoch(SUMMARY)
    settlement_events = read_by_epoch(SETTLEMENT_EVENTS)
    modules = module_addresses()
    gov = modules.get("gov", "")
    inference = modules.get("inference", "")

    rows: list[dict[str, str]] = []
    for epoch, event_summary in sorted(settlement_events.items(), key=lambda item: int(item[0])):
        height = event_summary.get("settlement_height", "")
        if not height:
            continue
        formula_remainder = decimal_or_zero(summary.get(epoch, {}).get("not_paid_rewards_gnk"))
        raw = read_json(RAW_ROOT / f"epoch_{epoch}" / "settlement_evidence" / f"rpc_block_results_{height}.json")
        pending_sender = ""
        event_order = 0
        matched_formula = False
        for event in iter_events(raw):
            attrs = event_attrs(event)
            if event.get("type") == "transfer" and attrs.get("recipient") == gov:
                pending_sender = attrs.get("sender", "")
                continue
            if event.get("type") != "coin_received" or attrs.get("receiver") != gov:
                continue
            amount_raw = attrs.get("amount", "")
            if not amount_raw.endswith("ngonka"):
                continue
            event_order += 1
            amount_gnk = ngonk_to_gnk(decimal_or_zero(amount_raw.removesuffix("ngonka")))
            role, basis, matched_formula = classify(amount_gnk, formula_remainder, matched_formula)
            sender = pending_sender or inference
            rows.append(
                {
                    "epoch": epoch,
                    "height": height,
                    "event_order": str(event_order),
                    "sender": sender,
                    "receiver": gov,
                    "amount_gnk": fmt(amount_gnk),
                    "inferred_role": role,
                    "inference_basis": basis,
                }
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
