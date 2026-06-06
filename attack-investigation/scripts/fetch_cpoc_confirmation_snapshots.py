#!/usr/bin/env python3
"""Fetch historical parent epoch_group_data snapshots for cPoC confirmation-weight checks."""

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
MANIFEST = ROOT / "manifests" / "cpoc_confirmation_snapshots_manifest.md"
ENV_PATHS = [ROOT / ".env", ROOT.parent / ".env"]
CONFIRMATION_CHANGE_HEIGHTS = {
    265: [4095963, 4099160, 4103171],
    266: [4115375, 4117265, 4118384],
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


def fetch(url: str, timeout: int, height: int | None = None) -> FetchResult:
    headers = {"User-Agent": "265-attack-investigation/1.0"}
    if height is not None:
        headers["x-cosmos-block-height"] = str(height)
    request = urllib.request.Request(url, headers=headers)
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


def event_generation_heights(epoch: int) -> list[int]:
    data = read_json(RAW_ROOT / f"epoch_{epoch}" / "cpoc_history" / "confirmation_poc_events.json")
    events = data.get("events", []) if isinstance(data, dict) else []
    heights: list[int] = []
    for event in events:
        if isinstance(event, dict) and event.get("generation_start_height") not in (None, ""):
            heights.append(int(event["generation_start_height"]))
    return heights


def snapshot_heights(epoch: int) -> list[int]:
    group = parent_group(epoch)
    heights: set[int] = set()
    for key in ("effective_block_height", "last_block_height"):
        value = group.get(key)
        if value not in (None, ""):
            heights.add(int(value))
    heights.update(event_generation_heights(epoch))
    heights.update(CONFIRMATION_CHANGE_HEIGHTS.get(epoch, []))
    return sorted(heights)


def write_manifest(rows: list[dict[str, str]]) -> None:
    lines = [
        "# cPoC Confirmation Snapshots Manifest",
        "",
        f"Generated at: {utc_now()}",
        "",
        "| epoch | request | height | url | status | artifact | sha256 | stderr | stderr_sha256 | fetched_at_utc |",
        "|---:|---|---:|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| {epoch} | {request} | {height} | {url} | {status} | {artifact} | {sha256} | {stderr} | "
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
        for height in snapshot_heights(epoch):
            epoch_dir = RAW_ROOT / f"epoch_{epoch}" / "cpoc_confirmation_snapshots"
            requests = {
                "parent_epoch_group_data": (
                    f"/chain-api/productscience/inference/inference/epoch_group_data/{epoch}",
                    epoch_dir / f"parent_epoch_group_data_at_{height}.json",
                    height,
                ),
                "block_header": (
                    f"/chain-api/cosmos/base/tendermint/v1beta1/blocks/{height}",
                    epoch_dir / "block_headers" / f"block_{height}.json",
                    None,
                ),
            }
            for request_name, (path, artifact_path, header_height) in requests.items():
                url = join_url(base_url, path)
                result = fetch(url, args.timeout, header_height)
                artifact = write_artifact(artifact_path, result)
                rows.append(
                    {
                        "epoch": str(epoch),
                        "request": request_name,
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
