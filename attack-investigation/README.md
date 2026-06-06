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
| 265 | 53 | 37 | 16 | 51 | 2 | 284,924,015.171652 | 185,565,043.741173 | 99,358,971.430479 | 99,367,460.084386 | 0.000000 | 0.000000 |
| 266 | 48 | 38 | 10 | 46 | 2 | 284,788,676.264445 | 261,173,638.858560 | 23,615,037.405885 | 26,427,646.580643 | 0.000000 | 0.000000 |
| TOTAL | 101 | 75 | 26 | 97 | 4 | 569,712,691.436097 | 446,738,682.599733 | 122,974,008.836364 | 125,795,106.665029 | 0.000000 | 0.000000 |

Notes:

- `reward pool` is calculated from saved chain `bitcoin_reward_params`: `initial_epoch_reward`, `decay_rate`, and `genesis_epoch`.
- `not paid / remainder` is `reward pool - paid to miners`.
- `gov module delta during epoch` is the direct `gov` module-account balance change from `effective_block_height` to `last_block_height`; see [`outputs/module_balance_deltas.csv`](outputs/module_balance_deltas.csv).
- `gov boundary delta` is the direct `gov` module-account balance change from `last_block_height` to `last_block_height + 1`. It is zero for both epochs, so the saved data does not show a one-block settlement transfer to gov at the epoch boundary.
- `did not receive` is the number of participants with `rewarded_coins = 0` in settlement data.
- Per-miner zero-reward reasons are in [`outputs/unpaid_miners_detail.csv`](outputs/unpaid_miners_detail.csv).
- `affected_rows` can be greater than unique affected addresses because one address can have multiple classes, for example `excluded_operator` and `zero_reward_reconstruction`.
- `source_compensation_gonka` is not loaded yet because no source claim files are present under `source_claims/votkon/` or `source_claims/case3/`.

## Unpaid Miner Reasons

Current reason breakdown for participants with `rewarded_coins = 0`. Full address-level detail is in [`outputs/unpaid_miners_detail.csv`](outputs/unpaid_miners_detail.csv); the summary below is from [`outputs/unpaid_reason_summary.csv`](outputs/unpaid_reason_summary.csv).

| epoch | reason | miners |
|---:|---|---:|
| 265 | confirmation_poc_zero_weight | 10 |
| 265 | missed_or_invalidated_work | 4 |
| 265 | excluded_from_final_group | 2 |
| 266 | confirmation_poc_zero_weight | 8 |
| 266 | excluded_from_final_group | 2 |
| TOTAL | confirmation_poc_zero_weight | 18 |
| TOTAL | missed_or_invalidated_work | 4 |
| TOTAL | excluded_from_final_group | 4 |

Reason notes:

- `confirmation_poc_zero_weight`: the participant is still in final `validation_weights`, but saved chain data shows `confirmation_weight = 0`. The saved `poc_validation_snapshot` response has `found=false`, so this is a chain-visible confirmation-weight bucket, not a direct raw cPoC snapshot proof.
- `missed_or_invalidated_work`: the participant has nonzero `confirmation_weight`, but settlement-visible counters include missed requests or invalidated inferences.
- `excluded_from_final_group`: the participant appears in settlement/performance data but is absent from final `validation_weights`.

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
python3 scripts/build_unpaid_miners_detail.py
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
- `outputs/unpaid_miners_detail.csv`: zero-reward miners with chain-visible reason details.
- `outputs/unpaid_reason_summary.csv`: per-epoch counts by zero-reward reason.

`undistributed_remainder_gonka` means "not distributed to participants by settlement." It is not evidence that the same amount went to a government wallet unless a direct wallet balance delta is separately verified.
