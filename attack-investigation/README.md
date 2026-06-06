# Epoch 265-266 Attack Investigation

Independent investigation workspace for epochs 265 and 266.

The investigation separates:

- chain facts visible in saved raw data;
- source compensation claims;
- policy-dependent compensation decisions.

The main rule is: save raw data first, calculate later.

## Main Numbers

All money values are in GNK, not nGNK. Current summary from [`outputs/epoch_summary.csv`](outputs/epoch_summary.csv):

| epoch | participants | received reward | did not receive | final group | excluded | reward pool, GNK | paid to miners, GNK | not paid / remainder, GNK | gov module delta during epoch, GNK | gov boundary delta, GNK | burned, GNK |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 265 | 53 | 37 | 16 | 51 | 2 | 284924015.171652 | 185565043.741173 | 99358971.430479 | 99367460.084386 | 0.000000 | 0.000000 |
| 266 | 48 | 38 | 10 | 46 | 2 | 284788676.264445 | 261173638.858560 | 23615037.405885 | 26427646.580643 | 0.000000 | 0.000000 |
| total | 101 | 75 | 26 | 97 | 4 | 569712691.436097 | 446738682.599733 | 122974008.836364 | 125795106.665029 | 0.000000 | 0.000000 |

Notes:

- `reward pool` is calculated from saved chain `bitcoin_reward_params`: `initial_epoch_reward`, `decay_rate`, and `genesis_epoch`.
- `not paid / remainder` is `reward pool - paid to miners`.
- `gov module delta during epoch` is the direct `gov` module-account balance change from `effective_block_height` to `last_block_height`; see [`outputs/module_balance_deltas.csv`](outputs/module_balance_deltas.csv).
- `gov boundary delta` is the direct `gov` module-account balance change from `last_block_height` to `last_block_height + 1`. It is zero for both epochs, so the saved data does not show a one-block settlement transfer to gov at the epoch boundary.
- `did not receive` is the number of participants with `rewarded_coins = 0` in settlement data.
- `affected_rows` can be greater than unique affected addresses because one address can have multiple classes, for example `excluded_operator` and `zero_reward_reconstruction`.
- `source_compensation_gonka` is not loaded yet because no source claim files are present under `source_claims/votkon/` or `source_claims/case3/`.

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
python3 scripts/fetch_module_balance_deltas.py
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
- `outputs/module_balance_deltas.csv`: module-account balance deltas around epoch boundaries.

`undistributed_remainder_gonka` means "not distributed to participants by settlement." It is not evidence that the same amount went to a government wallet unless a direct wallet balance delta is separately verified.
