#!/usr/bin/env python3
"""Fetch block headers needed to timestamp saved cPoC history rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_ROOT = ROOT / "raw_chain_cache"
MANIFEST = ROOT / "manifests" / "cpoc_block_headers_manifest.md"
ENV_PATHS = [ROOT / ".env", ROOT.parent / ".env"]


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
    if os.environ.get("GONKA_REST_URL"):
        return normalize_base_url(os.environ["GONKA_REST_URL"])
    if os.environ.get("GONKA_RPC_URL"):
        return derive_rest_url_from_rpc_url(os.environ["GONKA_RPC_URL"])
    raise RuntimeError("GONKA_RPC_URL or GONKA_REST_URL must be set")


def transform_path_for_base_url(base_url: str, path: str) -> str:
    parsed = urllib.parse.urlparse(normalize_base_url(base_url))
    if parsed.port == 1317 and path.startswith("/chain-api/"):
        return path.removeprefix("/chain-api")
    return path


def join_url(base_url: str, path: str) -> str:
    path = transform_path_for_base_url(base_url, path)
    return urllib.parse.urljoin(normalize_base_url(base_url) + "/", path.lstrip("/"))


def redact_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    output = parsed.path or "/"
    if parsed.query:
        output = f"{output}?{parsed.query}"
    return f"<base-url>{output}"


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

    artifact = {
        "artifact": path.relative_to(ROOT).as_posix(),
        "sha256": sha256_file(path),
        "stderr": "",
        "stderr_sha256": "",
    }
    if stderr_path.exists():
        artifact["stderr"] = stderr_path.relative_to(ROOT).as_posix()
        artifact["stderr_sha256"] = sha256_file(stderr_path)
    return artifact


def parent_group(epoch: int) -> dict[str, Any]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "epoch_group_data.json")
    return data.get("epoch_group_data", {}) if isinstance(data, dict) else {}


def block_heights_for_epoch(epoch: int) -> list[int]:
    heights: set[int] = set()
    group = parent_group(epoch)
    for key in ("effective_block_height", "poc_start_block_height"):
        value = group.get(key)
        if value not in (None, ""):
            heights.add(int(value))

    events_data = read_json(RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "confirmation_poc_events.json")
    events = events_data.get("events", []) if isinstance(events_data, dict) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        for key in ("trigger_height", "generation_start_height"):
            value = event.get(key)
            if value not in (None, ""):
                heights.add(int(value))
    return sorted(heights)


def write_manifest(rows: list[dict[str, str]]) -> None:
    lines = [
        "# cPoC Block Headers Manifest",
        "",
        f"Generated at: {utc_now()}",
        "",
        "| epoch | height | url | status | artifact | sha256 | stderr | stderr_sha256 | fetched_at_utc |",
        "|---:|---:|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {epoch} | {height} | {url} | {status} | {artifact} | {sha256} | {stderr} | "
            "{stderr_sha256} | {fetched_at_utc} |".format(**row)
        )
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("\n".join(lines) + "\n")


def main() -> int:
    load_dotenv(ENV_PATHS)
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--epochs", nargs="+", type=int, default=[265, 266])
    parser.add_argument("--timeout", type=int, default=90)
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url or default_base_url())
    rows: list[dict[str, str]] = []
    for epoch in args.epochs:
        for height in block_heights_for_epoch(epoch):
            url = join_url(base_url, f"/chain-api/cosmos/base/tendermint/v1beta1/blocks/{height}")
            result = fetch(url, args.timeout)
            artifact = write_artifact(
                RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "block_headers" / f"block_{height}.json",
                result,
            )
            rows.append(
                {
                    "epoch": str(epoch),
                    "height": str(height),
                    "url": redact_url(url),
                    "status": str(result.status),
                    "fetched_at_utc": utc_now(),
                    **artifact,
                }
            )
    write_manifest(rows)
    print(f"Wrote {MANIFEST.relative_to(ROOT)} with {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
