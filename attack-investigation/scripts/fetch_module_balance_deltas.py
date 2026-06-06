#!/usr/bin/env python3
"""Fetch module-account balance deltas around investigated epochs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUT = ROOT / "outputs" / "module_balance_deltas.csv"
MANIFEST = ROOT / "manifests" / "module_balance_manifest.md"
ENV_PATHS = [ROOT / ".env", ROOT.parent / ".env"]
DENOM = "ngonka"
DENOM_EXPONENT = 6


@dataclass(frozen=True)
class ModuleAccount:
    name: str
    address: str


OUTPUT_COLUMNS = [
    "epoch",
    "module_name",
    "address",
    "start_height",
    "start_balance_gnk",
    "last_height",
    "last_balance_gnk",
    "next_height",
    "next_balance_gnk",
    "delta_start_to_last_gnk",
    "delta_last_to_next_gnk",
]


def load_dotenv(paths: list[Path]) -> None:
    for path in paths:
        if not path.exists():
            continue
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def normalize_base_url(base_url: str) -> str:
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme:
        return base_url
    return f"http://{base_url}"


def derive_rest_url_from_rpc_url(rpc_url: str) -> str:
    normalized = normalize_base_url(rpc_url)
    parsed = urllib.parse.urlparse(normalized)
    if parsed.port in (None, 80, 26657):
        netloc = parsed.hostname or parsed.netloc
        return urllib.parse.urlunparse((parsed.scheme, f"{netloc}:1317", "", "", "", ""))
    return normalized


def default_base_url() -> str:
    rest_url = os.environ.get("GONKA_REST_URL")
    if rest_url:
        return rest_url
    rpc_url = os.environ.get("GONKA_RPC_URL")
    if rpc_url:
        return derive_rest_url_from_rpc_url(rpc_url)
    raise RuntimeError("GONKA_RPC_URL or GONKA_REST_URL must be set")


def join_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(normalize_base_url(base_url).rstrip("/") + "/", path.lstrip("/"))


def redact_url_for_manifest(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return f"<base-url>{path}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, timeout: int, height: int | None = None) -> tuple[int | str, bytes, str]:
    headers = {"User-Agent": "265-attack-investigation/1.0"}
    if height is not None:
        headers["x-cosmos-block-height"] = str(height)
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), f"HTTPError: {exc.code} {exc.reason}"
    except Exception as exc:  # noqa: BLE001 - saved as investigation artifact.
        return "ERROR", b"", f"{type(exc).__name__}: {exc}"


def write_artifact(path: Path, body: bytes, stderr: str) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if body:
        path.write_bytes(body)
    else:
        path.write_text(json.dumps({"error": stderr}, indent=2) + "\n")

    stderr_path = path.with_suffix(path.suffix + ".stderr")
    if stderr:
        stderr_path.write_text(stderr + "\n")
    elif stderr_path.exists():
        stderr_path.unlink()

    row = {
        "artifact": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        "stderr": "",
        "stderr_sha256": "",
    }
    if stderr_path.exists():
        row["stderr"] = stderr_path.relative_to(ROOT).as_posix()
        row["stderr_sha256"] = sha256_file(stderr_path)
    return row


def parse_json_bytes(body: bytes) -> Any | None:
    try:
        return json.loads(body.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def parse_module_accounts(data: Any) -> list[ModuleAccount]:
    accounts = data.get("accounts", []) if isinstance(data, dict) else []
    parsed: list[ModuleAccount] = []
    for item in accounts:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("base_account", {}).get("name") or item.get("account", {}).get("name")
        address = (
            item.get("address")
            or item.get("base_account", {}).get("address")
            or item.get("account", {}).get("address")
        )
        if name and address:
            parsed.append(ModuleAccount(str(name), str(address)))
    return parsed


def decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def balance_amount(data: Any) -> Decimal:
    if not isinstance(data, dict):
        return Decimal(0)
    balance = data.get("balance")
    if isinstance(balance, dict):
        return decimal_or_zero(balance.get("amount"))
    return Decimal(0)


def to_gnk(value: Decimal) -> str:
    scaled = value / (Decimal(10) ** DENOM_EXPONENT)
    return format(scaled.quantize(Decimal("0.000001")), "f")


def epoch_heights(epoch_dir: Path) -> tuple[int, int, int] | None:
    path = epoch_dir / "epoch_group_data.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    group = data.get("epoch_group_data", {}) if isinstance(data, dict) else {}
    start = group.get("effective_block_height")
    last = group.get("last_block_height")
    if start is None or last is None:
        return None
    return int(start), int(last), int(last) + 1


def write_manifest(rows: list[dict[str, str]]) -> None:
    lines = [
        "# Module Balance Manifest",
        "",
        "| epoch | request | url | height | status | artifact | sha256 | stderr | stderr_sha256 |",
        "|---:|---|---|---:|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {epoch} | {request} | {url} | {height} | {status} | {artifact} | {sha256} | {stderr} | "
            "{stderr_sha256} |".format(**row)
        )
    MANIFEST.write_text("\n".join(lines) + "\n")


def main() -> int:
    load_dotenv(ENV_PATHS)

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--epochs", nargs="+", type=int, default=[265, 266])
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.1)
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url or default_base_url())
    manifest_rows: list[dict[str, str]] = []

    module_url = join_url(base_url, "/cosmos/auth/v1beta1/module_accounts")
    status, body, stderr = fetch(module_url, args.timeout)
    artifact = write_artifact(RAW_ROOT / "module_accounts.json", body, stderr)
    manifest_rows.append(
        {
            "epoch": "",
            "request": "module_accounts",
            "url": redact_url_for_manifest(module_url),
            "height": "",
            "status": str(status),
            **artifact,
        }
    )
    modules = parse_module_accounts(parse_json_bytes(body) or {})
    if not modules:
        write_manifest(manifest_rows)
        print("No module accounts found.", file=sys.stderr)
        return 1

    rows: list[dict[str, str]] = []
    for epoch in args.epochs:
        epoch_dir = RAW_ROOT / f"epoch_{epoch}"
        heights = epoch_heights(epoch_dir)
        if heights is None:
            continue
        start_height, last_height, next_height = heights

        balances_by_module: dict[str, dict[int, Decimal]] = {}
        for module in modules:
            balances_by_module[module.name] = {}
            for height in (start_height, last_height, next_height):
                path = (
                    epoch_dir
                    / "module_balances"
                    / f"{module.name}_{height}_{DENOM}.json"
                )
                url = join_url(
                    base_url,
                    f"/cosmos/bank/v1beta1/balances/{module.address}/by_denom?denom={DENOM}",
                )
                status, body, stderr = fetch(url, args.timeout, height)
                artifact = write_artifact(path, body, stderr)
                manifest_rows.append(
                    {
                        "epoch": str(epoch),
                        "request": f"{module.name}_balance",
                        "url": redact_url_for_manifest(url),
                        "height": str(height),
                        "status": str(status),
                        **artifact,
                    }
                )
                balances_by_module[module.name][height] = balance_amount(parse_json_bytes(body))
                time.sleep(args.delay)

            start_balance = balances_by_module[module.name][start_height]
            last_balance = balances_by_module[module.name][last_height]
            next_balance = balances_by_module[module.name][next_height]
            rows.append(
                {
                    "epoch": str(epoch),
                    "module_name": module.name,
                    "address": module.address,
                    "start_height": str(start_height),
                    "start_balance_gnk": to_gnk(start_balance),
                    "last_height": str(last_height),
                    "last_balance_gnk": to_gnk(last_balance),
                    "next_height": str(next_height),
                    "next_balance_gnk": to_gnk(next_balance),
                    "delta_start_to_last_gnk": to_gnk(last_balance - start_balance),
                    "delta_last_to_next_gnk": to_gnk(next_balance - last_balance),
                }
            )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    write_manifest(manifest_rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
