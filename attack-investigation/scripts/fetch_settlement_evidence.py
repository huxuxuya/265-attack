#!/usr/bin/env python3
"""Fetch settlement-specific raw evidence for epochs 265 and 266."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
OUTPUT = ROOT / "outputs" / "settlement_event_summary.csv"
MANIFEST = ROOT / "manifests" / "settlement_evidence_manifest.md"
ENV_PATHS = [ROOT / ".env", ROOT.parent / ".env"]
DENOM_EXPONENT = 6


REST_REQUESTS = {
    "node_info": "/chain-api/cosmos/base/tendermint/v1beta1/node_info",
    "current_plan": "/chain-api/cosmos/upgrade/v1beta1/current_plan",
    "module_versions": "/chain-api/cosmos/upgrade/v1beta1/module_versions",
}


@dataclass(frozen=True)
class FetchResult:
    status: int | str
    body: bytes
    stderr: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme:
        return url.rstrip("/")
    return f"http://{url}".rstrip("/")


def derive_rest_url_from_rpc_url(rpc_url: str) -> str:
    normalized = normalize_url(rpc_url)
    parsed = urllib.parse.urlparse(normalized)
    if parsed.port in (None, 80, 26657):
        host = parsed.hostname or parsed.netloc
        return urllib.parse.urlunparse((parsed.scheme, f"{host}:1317", "", "", "", "")).rstrip("/")
    return normalized


def default_rest_url() -> str:
    if os.environ.get("GONKA_REST_URL"):
        return normalize_url(os.environ["GONKA_REST_URL"])
    if os.environ.get("GONKA_RPC_URL"):
        return derive_rest_url_from_rpc_url(os.environ["GONKA_RPC_URL"])
    return "http://node1.gonka.ai:8000"


def default_rpc_url() -> str:
    if os.environ.get("GONKA_RPC_URL"):
        normalized = normalize_url(os.environ["GONKA_RPC_URL"])
        parsed = urllib.parse.urlparse(normalized)
        if parsed.port is None:
            return urllib.parse.urlunparse((parsed.scheme, f"{parsed.hostname}:26657", "", "", "", "")).rstrip("/")
        return normalized
    return "http://node1.gonka.ai:26657"


def transform_rest_path(base_url: str, path: str) -> str:
    parsed = urllib.parse.urlparse(normalize_url(base_url))
    if parsed.port == 1317 and path.startswith("/chain-api/"):
        return path.removeprefix("/chain-api")
    return path


def join_rest_url(base_url: str, path: str) -> str:
    path = transform_rest_path(base_url, path)
    return urllib.parse.urljoin(normalize_url(base_url) + "/", path.lstrip("/"))


def join_rpc_url(base_url: str, path: str) -> str:
    return urllib.parse.urljoin(normalize_url(base_url) + "/", path.lstrip("/"))


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    redacted = parsed.path or "/"
    if parsed.query:
        redacted = f"{redacted}?{parsed.query}"
    return f"<base-url>{redacted}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(url: str, timeout: int) -> FetchResult:
    request = urllib.request.Request(url, headers={"User-Agent": "265-attack-investigation/1.0"})
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


def read_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def parse_body(result: FetchResult) -> Any | None:
    try:
        return json.loads(result.body.decode())
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def decimal_or_zero(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal(0)


def to_gnk_ngonk(value: Decimal) -> str:
    return format((value / (Decimal(10) ** DENOM_EXPONENT)).quantize(Decimal("0.000001")), "f")


def gov_address() -> str:
    accounts = read_json(RAW_ROOT / "module_accounts.json")
    for account in accounts.get("accounts", []) if isinstance(accounts, dict) else []:
        if not isinstance(account, dict):
            continue
        name = account.get("name") or account.get("base_account", {}).get("name")
        address = account.get("address") or account.get("base_account", {}).get("address")
        if name == "gov" and address:
            return str(address)
    raise RuntimeError("gov module account is missing from raw_chain_cache/module_accounts.json")


def settlement_heights() -> dict[int, int]:
    audit_path = ROOT / "outputs" / "gov_settlement_audit.csv"
    heights: dict[int, int] = {}
    if audit_path.exists():
        with audit_path.open() as fh:
            for row in csv.DictReader(fh):
                try:
                    heights[int(row["epoch"])] = int(row["main_gov_jump_height"])
                except (KeyError, ValueError):
                    continue
    if not heights:
        heights = {265: 4105641, 266: 4121032}
    return heights


def extract_node_version(node_info: Any) -> tuple[str, str]:
    if not isinstance(node_info, dict):
        return "", ""
    version = node_info.get("application_version", {}).get("version", "")
    commit = node_info.get("application_version", {}).get("git_commit", "")
    return str(version), str(commit)


def extract_block_time(block_data: Any) -> str:
    if not isinstance(block_data, dict):
        return ""
    return str(block_data.get("block", {}).get("header", {}).get("time", ""))


def tx_count(txs_data: Any) -> int:
    if not isinstance(txs_data, dict):
        return 0
    value = txs_data.get("total")
    try:
        return int(value)
    except (TypeError, ValueError):
        return len(txs_data.get("tx_responses") or [])


def iter_events(obj: Any) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        maybe_type = obj.get("type")
        maybe_attrs = obj.get("attributes")
        if isinstance(maybe_type, str) and isinstance(maybe_attrs, list):
            events.append(obj)
        for value in obj.values():
            events.extend(iter_events(value))
    elif isinstance(obj, list):
        for item in obj:
            events.extend(iter_events(item))
    return events


def event_attrs(event: dict[str, Any]) -> dict[str, list[str]]:
    attrs: dict[str, list[str]] = {}
    for attr in event.get("attributes", []):
        if not isinstance(attr, dict):
            continue
        key = str(attr.get("key", ""))
        value = str(attr.get("value", ""))
        attrs.setdefault(key, []).append(value)
    return attrs


def summarize_gov_events(block_results: Any, gov: str) -> tuple[int, Decimal, str, str]:
    amount = Decimal(0)
    count = 0
    components: list[str] = []
    memos: list[str] = []
    for event in iter_events(block_results):
        attrs = event_attrs(event)
        if event.get("type") != "coin_received" or gov not in attrs.get("receiver", []):
            continue
        count += 1
        for value in attrs.get("amount", []):
            if value.endswith("ngonka"):
                ngonk = decimal_or_zero(value.removesuffix("ngonka"))
                amount += ngonk
                components.append(to_gnk_ngonk(ngonk))
        for key in ("memo", "reason"):
            memos.extend(attrs.get(key, []))
    return count, amount, " + ".join(components), "; ".join(sorted(set(memos)))


def write_manifest(rows: list[dict[str, str]]) -> None:
    lines = [
        "# Settlement Evidence Manifest",
        "",
        f"Generated at: {utc_now()}",
        "",
        "| epoch | request | url | status | artifact | sha256 | stderr | stderr_sha256 | fetched_at_utc |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {epoch} | {request} | {url} | {status} | {artifact} | {sha256} | {stderr} | "
            "{stderr_sha256} | {fetched_at_utc} |".format(**row)
        )
    MANIFEST.write_text("\n".join(lines) + "\n")


def main() -> int:
    load_dotenv(ENV_PATHS)
    parser = argparse.ArgumentParser()
    parser.add_argument("--rest-url", default=default_rest_url())
    parser.add_argument("--rpc-url", default=default_rpc_url())
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--epochs", nargs="+", type=int, default=[265, 266])
    args = parser.parse_args()

    rest_url = normalize_url(args.rest_url)
    rpc_url = normalize_url(args.rpc_url)
    gov = gov_address()
    heights = settlement_heights()
    manifest_rows: list[dict[str, str]] = []

    node_info_data: Any | None = None
    chain_dir = RAW_ROOT / "chain_evidence"
    for request_name, path in REST_REQUESTS.items():
        url = join_rest_url(rest_url, path)
        fetched_at = utc_now()
        result = fetch(url, args.timeout)
        artifact = write_artifact(chain_dir / f"{request_name}.json", result)
        manifest_rows.append(
            {
                "epoch": "chain",
                "request": request_name,
                "url": redact_url(url),
                "status": str(result.status),
                "fetched_at_utc": fetched_at,
                **artifact,
            }
        )
        if request_name == "node_info":
            node_info_data = parse_body(result)

    node_version, node_commit = extract_node_version(node_info_data)
    summary_rows: list[dict[str, str]] = []

    for epoch in args.epochs:
        height = heights.get(epoch)
        if height is None:
            continue
        epoch_dir = RAW_ROOT / f"epoch_{epoch}" / "settlement_evidence"
        requests = {
            "block": join_rest_url(rest_url, f"/chain-api/cosmos/base/tendermint/v1beta1/blocks/{height}"),
            "txs_at_height": join_rest_url(
                rest_url,
                f"/chain-api/cosmos/tx/v1beta1/txs?query=tx.height%3D{height}&pagination.limit=100",
            ),
            "txs_gov_coin_received": join_rest_url(
                rest_url,
                "/chain-api/cosmos/tx/v1beta1/txs?"
                f"query=coin_received.receiver%3D%27{urllib.parse.quote(gov)}%27%20AND%20tx.height%3D{height}"
                "&pagination.limit=100",
            ),
            "txs_gov_transfer": join_rest_url(
                rest_url,
                "/chain-api/cosmos/tx/v1beta1/txs?"
                f"query=transfer.recipient%3D%27{urllib.parse.quote(gov)}%27%20AND%20tx.height%3D{height}"
                "&pagination.limit=100",
            ),
            "rpc_block_results": join_rpc_url(rpc_url, f"/block_results?height={height}"),
        }

        parsed: dict[str, Any] = {}
        statuses: dict[str, str] = {}
        for request_name, url in requests.items():
            fetched_at = utc_now()
            result = fetch(url, args.timeout)
            artifact = write_artifact(epoch_dir / f"{request_name}_{height}.json", result)
            manifest_rows.append(
                {
                    "epoch": str(epoch),
                    "request": request_name,
                    "url": redact_url(url),
                    "status": str(result.status),
                    "fetched_at_utc": fetched_at,
                    **artifact,
                }
            )
            parsed[request_name] = parse_body(result)
            statuses[request_name] = str(result.status)

        gov_event_count, gov_event_ngonk, gov_event_components, gov_event_memos = summarize_gov_events(
            parsed.get("rpc_block_results"), gov
        )
        summary_rows.append(
            {
                "epoch": str(epoch),
                "settlement_height": str(height),
                "block_time": extract_block_time(parsed.get("block")),
                "node_version_observed": node_version,
                "node_git_commit_observed": node_commit,
                "tx_count_at_height": str(tx_count(parsed.get("txs_at_height"))),
                "gov_tx_count_at_height": str(
                    tx_count(parsed.get("txs_gov_coin_received")) + tx_count(parsed.get("txs_gov_transfer"))
                ),
                "rpc_block_results_status": statuses.get("rpc_block_results", ""),
                "gov_event_count_in_rpc_block_results": str(gov_event_count),
                "gov_event_amount_gnk_in_rpc_block_results": to_gnk_ngonk(gov_event_ngonk),
                "gov_event_amount_components_gnk": gov_event_components,
                "gov_event_memos_in_rpc_block_results": gov_event_memos,
                "evidence_note": (
                    "RPC block_results contains gov coin_received EndBlock events"
                    if gov_event_count
                    else "No gov txs found by tx search; RPC block_results did not expose gov coin_received evidence"
                ),
            }
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(summary_rows[0].keys()) if summary_rows else [])
        if summary_rows:
            writer.writeheader()
            writer.writerows(summary_rows)

    write_manifest(manifest_rows)
    print(f"Wrote {OUTPUT.relative_to(ROOT)} with {len(summary_rows)} rows.")
    print(f"Wrote {MANIFEST.relative_to(ROOT)} with {len(manifest_rows)} rows.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
