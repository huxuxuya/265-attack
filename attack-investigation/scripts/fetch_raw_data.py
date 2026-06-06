#!/usr/bin/env python3
"""Fetch raw chain data for the attack investigation.

This script saves every response before any downstream script calculates
derived tables.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
MANIFEST = ROOT / "manifests" / "raw_chain_cache_manifest.md"
ENV_PATHS = [ROOT / ".env", ROOT.parent / ".env"]


@dataclass(frozen=True)
class RequestSpec:
    name: str
    path: str
    required: bool = True


BASE_SPECS = [
    RequestSpec("epoch_group_data", "/chain-api/productscience/inference/inference/epoch_group_data/{epoch}"),
    RequestSpec(
        "epoch_performance_summary",
        "/chain-api/productscience/inference/inference/epoch_performance_summary/{epoch}",
    ),
    RequestSpec("participants", "/api/v1/epochs/{epoch}/participants"),
    RequestSpec("poc_commits", "/chain-api/productscience/inference/inference/poc_commits/{epoch}", False),
    RequestSpec("poc_validations", "/chain-api/productscience/inference/inference/poc_validations/{epoch}", False),
    RequestSpec(
        "poc_validation_snapshot",
        "/chain-api/productscience/inference/inference/poc_validation_snapshot/{epoch}",
        False,
    ),
    RequestSpec("delegation_state", "/chain-api/productscience/inference/inference/delegations/{epoch}", False),
    RequestSpec("params_current", "/chain-api/productscience/inference/inference/params", False),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


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


def find_first_key(obj: Any, keys: set[str]) -> Any | None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in keys:
                return value
        for value in obj.values():
            found = find_first_key(value, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = find_first_key(item, keys)
            if found is not None:
                return found
    return None


def join_url(base_url: str, path: str) -> str:
    path = transform_path_for_base_url(base_url, path)
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


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
    return "http://node1.gonka.ai:8000"


def transform_path_for_base_url(base_url: str, path: str) -> str:
    parsed = urllib.parse.urlparse(normalize_base_url(base_url))
    if parsed.port == 1317 and path.startswith("/chain-api/"):
        return path.removeprefix("/chain-api")
    return path


def redact_url_for_manifest(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    return f"<base-url>{path}"


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


def fetch(url: str, timeout: int) -> tuple[int | str, bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "265-attack-investigation/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read(), ""
    except urllib.error.HTTPError as exc:
        body = exc.read()
        return exc.code, body, f"HTTPError: {exc.code} {exc.reason}"
    except Exception as exc:  # noqa: BLE001 - saved as investigation artifact.
        return "ERROR", b"", f"{type(exc).__name__}: {exc}"


def write_artifact(epoch_dir: Path, spec_name: str, status: int | str, body: bytes, stderr: str) -> dict[str, str]:
    epoch_dir.mkdir(parents=True, exist_ok=True)
    suffix = "json" if isinstance(status, int) and 200 <= status < 300 else "error.json"
    body_path = epoch_dir / f"{spec_name}.{suffix}"
    if suffix == "json":
        stale_error_path = epoch_dir / f"{spec_name}.error.json"
        if stale_error_path.exists():
            stale_error_path.unlink()

    if body:
        body_path.write_bytes(body)
    else:
        body_path.write_text(json.dumps({"error": stderr}, indent=2) + "\n")

    stderr_path = epoch_dir / f"{spec_name}.stderr"
    if stderr:
        stderr_path.write_text(stderr + "\n")
    elif stderr_path.exists():
        stderr_path.unlink()

    result = {
        "body_path": body_path.relative_to(ROOT).as_posix(),
        "body_sha256": sha256_file(body_path),
        "stderr_path": "",
        "stderr_sha256": "",
    }
    if stderr_path.exists():
        result["stderr_path"] = stderr_path.relative_to(ROOT).as_posix()
        result["stderr_sha256"] = sha256_file(stderr_path)
    return result


def discover_height_specs(base_url: str, epoch: int, timeout: int) -> list[RequestSpec]:
    group_path = RAW_ROOT / f"epoch_{epoch}" / "epoch_group_data.json"
    data = read_json(group_path)
    if data is None:
        return []

    height = find_first_key(
        data,
        {
            "poc_start_block_height",
            "pocStartBlockHeight",
            "start_block_height",
            "startBlockHeight",
            "block_height",
            "blockHeight",
        },
    )
    if height in (None, ""):
        return []

    height_text = str(height)
    return [
        RequestSpec(
            f"params_at_height_{height_text}",
            f"/chain-api/productscience/inference/inference/params?height={urllib.parse.quote(height_text)}",
            False,
        ),
        RequestSpec(
            f"params_path_height_{height_text}",
            f"/chain-api/productscience/inference/inference/params/{urllib.parse.quote(height_text)}",
            False,
        ),
    ]


def write_manifest(rows: list[dict[str, str]]) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Raw Chain Cache Manifest",
        "",
        f"Generated at: {utc_now()}",
        "",
        "| epoch | request | required | url | status | artifact | sha256 | stderr | stderr_sha256 | fetched_at_utc |",
        "|---:|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {epoch} | {name} | {required} | {url} | {status} | {body_path} | {body_sha256} | "
            "{stderr_path} | {stderr_sha256} | {fetched_at_utc} |".format(**row)
        )
    MANIFEST.write_text("\n".join(lines) + "\n")


def fetch_specs(base_url: str, epoch: int, specs: list[RequestSpec], timeout: int, delay: float) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    epoch_dir = RAW_ROOT / f"epoch_{epoch}"
    base_url = normalize_base_url(base_url)
    for spec in specs:
        path = spec.path.format(epoch=epoch)
        url = join_url(base_url, path)
        fetched_at = utc_now()
        status, body, stderr = fetch(url, timeout)
        artifact = write_artifact(epoch_dir, spec.name, status, body, stderr)
        rows.append(
            {
                "epoch": str(epoch),
                "name": spec.name,
                "required": "yes" if spec.required else "no",
                "url": redact_url_for_manifest(url),
                "status": str(status),
                "fetched_at_utc": fetched_at,
                **artifact,
            }
        )
        time.sleep(delay)
    return rows


def main() -> int:
    load_dotenv(ENV_PATHS)
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-url",
        default=default_base_url(),
        help=(
            "Base node URL. Defaults to GONKA_REST_URL, then a REST URL derived from "
            "GONKA_RPC_URL, then http://node1.gonka.ai:8000."
        ),
    )
    parser.add_argument("--epochs", nargs="+", type=int, default=[265, 266])
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--delay", type=float, default=0.2)
    args = parser.parse_args()

    all_rows: list[dict[str, str]] = []
    for epoch in args.epochs:
        first_rows = fetch_specs(args.base_url, epoch, BASE_SPECS, args.timeout, args.delay)
        all_rows.extend(first_rows)

        height_specs = discover_height_specs(args.base_url, epoch, args.timeout)
        if height_specs:
            all_rows.extend(fetch_specs(args.base_url, epoch, height_specs, args.timeout, args.delay))

    write_manifest(all_rows)
    failures = [row for row in all_rows if not row["status"].isdigit() or not row["status"].startswith("2")]
    if failures:
        print(f"Fetched {len(all_rows)} requests with {len(failures)} non-2xx/error artifacts.", file=sys.stderr)
    else:
        print(f"Fetched {len(all_rows)} requests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
