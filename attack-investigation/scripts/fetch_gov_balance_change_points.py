#!/usr/bin/env python3
"""Fetch gov module balance change points inside investigated epochs."""

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
OUTPUT = ROOT / "outputs" / "gov_balance_change_points.csv"
MANIFEST = ROOT / "manifests" / "gov_balance_change_points_manifest.md"
ENV_PATHS = [ROOT / ".env", ROOT.parent / ".env"]
DENOM = "ngonka"
DENOM_EXPONENT = 6
GOV_MODULE = "gov"


OUTPUT_COLUMNS = [
    "epoch",
    "prev_height",
    "height",
    "balance_before_gnk",
    "balance_after_gnk",
    "delta_gnk",
]


@dataclass(frozen=True)
class FetchResult:
    status: int | str
    body: bytes
    stderr: str


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
        return base_url.rstrip("/")
    return f"http://{base_url}".rstrip("/")


def derive_rest_url_from_rpc_url(rpc_url: str) -> str:
    normalized = normalize_base_url(rpc_url)
    parsed = urllib.parse.urlparse(normalized)
    if parsed.port in (None, 80, 26657):
        host = parsed.hostname or parsed.netloc
        return urllib.parse.urlunparse((parsed.scheme, f"{host}:1317", "", "", "", "")).rstrip("/")
    return normalized


def default_base_url() -> str:
    rest_url = os.environ.get("GONKA_REST_URL")
    if rest_url:
        return normalize_base_url(rest_url)
    rpc_url = os.environ.get("GONKA_RPC_URL")
    if rpc_url:
        return derive_rest_url_from_rpc_url(rpc_url)
    raise RuntimeError("GONKA_RPC_URL or GONKA_REST_URL must be set")


def join_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(normalize_base_url(base_url).rstrip("/") + "/", path.lstrip("/"))


def redact_url(url: str) -> str:
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


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def gov_address() -> str | None:
    accounts = read_json(RAW_ROOT / "module_accounts.json")
    for account in accounts.get("accounts", []) if isinstance(accounts, dict) else []:
        if not isinstance(account, dict):
            continue
        name = account.get("name") or account.get("base_account", {}).get("name")
        address = account.get("address") or account.get("base_account", {}).get("address")
        if name == GOV_MODULE and address:
            return str(address)
    return None


def epoch_heights(epoch: int) -> tuple[int, int] | None:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "epoch_group_data.json")
    group = data.get("epoch_group_data", {}) if isinstance(data, dict) else {}
    start = group.get("effective_block_height")
    last = group.get("last_block_height")
    if start is None or last is None:
        return None
    return int(start), int(last)


def fetch(url: str, timeout: int, height: int) -> FetchResult:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "265-attack-investigation/1.0",
            "x-cosmos-block-height": str(height),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return FetchResult(response.status, response.read(), "")
    except urllib.error.HTTPError as exc:
        return FetchResult(exc.code, exc.read(), f"HTTPError: {exc.code} {exc.reason}")
    except Exception as exc:  # noqa: BLE001 - saved as investigation artifact.
        return FetchResult("ERROR", b"", f"{type(exc).__name__}: {exc}")


def write_artifact(path: Path, result: FetchResult) -> dict[str, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if result.body:
        path.write_bytes(result.body)
    else:
        path.write_text(json.dumps({"error": result.stderr}, indent=2) + "\n")
    stderr_path = path.with_suffix(path.suffix + ".stderr")
    if result.stderr:
        stderr_path.write_text(result.stderr + "\n")
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
    return format((value / (Decimal(10) ** DENOM_EXPONENT)).quantize(Decimal("0.000001")), "f")


def write_manifest(rows: list[dict[str, str]]) -> None:
    lines = [
        "# Gov Balance Change Points Manifest",
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
    parser.add_argument("--delay", type=float, default=0.02)
    args = parser.parse_args()

    gov = gov_address()
    if gov is None:
        print("No gov module account found in raw_chain_cache/module_accounts.json", file=sys.stderr)
        return 1

    base_url = normalize_base_url(args.base_url or default_base_url())
    url = join_url(base_url, f"/cosmos/bank/v1beta1/balances/{gov}/by_denom?denom={DENOM}")
    manifest_rows: list[dict[str, str]] = []
    output_rows: list[dict[str, str]] = []

    for epoch in args.epochs:
        heights = epoch_heights(epoch)
        if heights is None:
            continue
        start, last = heights
        cache: dict[int, Decimal] = {}

        def get_balance(height: int) -> Decimal:
            if height in cache:
                return cache[height]
            path = RAW_ROOT / f"epoch_{epoch}" / "gov_balance_change_points" / f"gov_{height}_{DENOM}.json"
            result = fetch(url, args.timeout, height)
            artifact = write_artifact(path, result)
            manifest_rows.append(
                {
                    "epoch": str(epoch),
                    "request": "gov_balance",
                    "url": redact_url(url),
                    "height": str(height),
                    "status": str(result.status),
                    **artifact,
                }
            )
            cache[height] = balance_amount(parse_json_bytes(result.body))
            time.sleep(args.delay)
            return cache[height]

        def scan(left: int, right: int) -> None:
            left_balance = get_balance(left)
            right_balance = get_balance(right)
            if left_balance == right_balance:
                return
            if right - left == 1:
                output_rows.append(
                    {
                        "epoch": str(epoch),
                        "prev_height": str(left),
                        "height": str(right),
                        "balance_before_gnk": to_gnk(left_balance),
                        "balance_after_gnk": to_gnk(right_balance),
                        "delta_gnk": to_gnk(right_balance - left_balance),
                    }
                )
                return
            midpoint = (left + right) // 2
            scan(left, midpoint)
            scan(midpoint, right)

        scan(start, last)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(output_rows)
    write_manifest(manifest_rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(output_rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
