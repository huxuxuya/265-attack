# Epoch 265-266 Attack Investigation

Independent investigation workspace for epochs 265 and 266.

The investigation separates:

- chain facts visible in saved raw data;
- source compensation claims;
- policy-dependent compensation decisions.

The main rule is: save raw data first, calculate later.

## Current Results

Current summary from [`outputs/epoch_summary.csv`](outputs/epoch_summary.csv):

| epoch | participants_total | final_group_count | excluded_count | zero_reward_count | affected_rows | affected_unique_addresses | actual_rewarded_gonka | burned_gonka | undistributed_remainder_gonka | source_compensation_gonka | difference |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| 265 | 53 | 51 | 2 | 16 | 18 | 16 | 185565043.741173 | 0 | not computed | not loaded | not computed |
| 266 | 48 | 46 | 2 | 10 | 12 | 10 | 261173638.85856 | 0 | not computed | not loaded | not computed |

Notes:

- `affected_rows` can be greater than `affected_unique_addresses` because one address can have multiple classes, for example `excluded_operator` and `zero_reward_reconstruction`.
- `source_compensation_gonka` is not loaded yet because no source claim files are present under `source_claims/votkon/` or `source_claims/case3/`.
- `undistributed_remainder_gonka` is left as `not computed` until an expected settlement reward is confirmed from raw chain data or a separately documented reward formula.
- `undistributed_remainder_gonka` means "not distributed to participants by settlement"; it is not evidence of a government wallet balance delta.

## Layout

- `raw_chain_cache/epoch_265/`, `raw_chain_cache/epoch_266/`: raw node responses and request errors.
- `source_claims/votkon/`, `source_claims/case3/`: source claim files. Put CSV or JSON files here.
- `manifests/`: SHA-256 manifests for raw chain data and source claim files.
- `outputs/`: derived CSV tables.
- `scripts/`: collection and analysis scripts.

## Workflow

```bash
cd attack-investigation
python3 scripts/fetch_raw_data.py --base-url http://node1.gonka.ai:8000 --epochs 265 266
python3 scripts/build_epoch_summary.py
python3 scripts/classify_affected.py
python3 scripts/compare_claims.py
```

If `GONKA_REST_URL` is set, `fetch_raw_data.py` uses it as the default base URL. If only
`GONKA_RPC_URL` is set, the script derives a REST URL from it by using port `1317`.

```bash
cd attack-investigation
python3 scripts/fetch_raw_data.py --epochs 265 266
```

`fetch_raw_data.py` writes raw files before any derived calculations are run. If a request fails, the response body and stderr/error metadata are saved and hashed too.

## Outputs

- `outputs/epoch_summary.csv`: per-epoch settlement summary.
- `outputs/affected_rows.csv`: per-address claim classification.
- `outputs/claim_vs_chain.csv`: source compensation compared with settlement-visible undistributed remainder.

`undistributed_remainder_gonka` means "not distributed to participants by settlement." It is not evidence that the same amount went to a government wallet unless a direct wallet balance delta is separately verified.
