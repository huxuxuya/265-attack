# Epoch 265-266 Attack Investigation

Independent investigation workspace for epochs 265 and 266.

The investigation separates:

- chain facts visible in saved raw data;
- source compensation claims;
- policy-dependent compensation decisions.

The main rule is: save raw data first, calculate later.

## Main Numbers

All money values are in GNK, not nGNK. Current summary from [`outputs/epoch_summary.csv`](outputs/epoch_summary.csv) and [`outputs/gov_settlement_audit.csv`](outputs/gov_settlement_audit.csv):

| epoch | participants | received reward | did not receive | final group | excluded | paid to miners, GNK | main gov jump, GNK | paid + main gov jump, GNK | formula reward, GNK | formula remainder, GNK | full gov delta, GNK | burned, GNK |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 265 | 53 | 37 | 16 | 51 | 2 | 185,565,043.741173 | 99,367,459.994521 | 284,932,503.735694 | 284,924,015.171652 | 99,358,971.430479 | 99,367,460.084386 | 0.000000 |
| 266 | 48 | 38 | 10 | 46 | 2 | 261,173,638.858560 | 26,427,696.577043 | 287,601,335.435603 | 284,788,676.264445 | 23,615,037.405885 | 26,427,646.580643 | 0.000000 |
| TOTAL | 101 | 75 | 26 | 97 | 4 | 446,738,682.599733 | 125,795,156.571564 | 572,533,839.171297 | 569,712,691.436097 | 122,974,008.836364 | 125,795,106.665029 | 0.000000 |

Notes:

- `formula reward` is calculated from saved chain `bitcoin_reward_params`: `initial_epoch_reward`, `decay_rate`, and `genesis_epoch`.
- `formula remainder` is `formula reward - paid to miners`. It is a model output, not a direct gov-wallet transfer.
- `main gov jump` is the largest direct `gov` module-account balance change found inside the epoch by historical balance scan; see [`outputs/gov_balance_change_points.csv`](outputs/gov_balance_change_points.csv).
- `paid + main gov jump` is the chain-observed paid rewards plus the largest gov balance jump. This is the best current chain-observed settlement-sized total, and it does not equal `formula reward`.
- `full gov delta` is the direct `gov` module-account balance change from `effective_block_height` to `last_block_height`; see [`outputs/module_balance_deltas.csv`](outputs/module_balance_deltas.csv).
- `gov boundary delta` is the direct `gov` module-account balance change from `last_block_height` to `last_block_height + 1`. It is zero for both epochs, so the saved data does not show a one-block settlement transfer to gov at the epoch boundary.
- `did not receive` is the number of participants with `rewarded_coins = 0` in settlement data.
- Per-miner zero-reward reasons are in [`outputs/unpaid_miners_detail.csv`](outputs/unpaid_miners_detail.csv).
- `affected_rows` can be greater than unique affected addresses because one address can have multiple classes, for example `excluded_operator` and `zero_reward_reconstruction`.
- `source_compensation_gonka` is not loaded yet because no source claim files are present under `source_claims/votkon/` or `source_claims/case3/`.

## Gov Balance Check

The earlier `formula remainder` and `full gov delta` values differ because they are different measurements. `formula remainder` is based on the current script's base reward formula; `full gov delta` is a direct balance delta and includes every gov balance movement inside the epoch.

| epoch | main gov jump height | main gov jump, GNK | other gov changes, GNK | full gov delta, GNK | formula remainder, GNK | main jump - formula remainder, GNK |
|---:|---:|---:|---:|---:|---:|---:|
| 265 | 4,105,641 | 99,367,459.994521 | 0.089865 | 99,367,460.084386 | 99,358,971.430479 | 8,488.564042 |
| 266 | 4,121,032 | 26,427,696.577043 | -49.996400 | 26,427,646.580643 | 23,615,037.405885 | 2,812,659.171158 |

So the error was treating `formula reward - paid rewards` as the exact amount sent to gov. The chain balance scan shows the gov movement directly, and it is larger than the formula remainder in both epochs.

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
python3 scripts/fetch_gov_balance_change_points.py
python3 scripts/build_gov_settlement_audit.py
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
- `outputs/gov_balance_change_points.csv`: exact gov module-account balance change heights found by historical balance scan.
- `outputs/gov_settlement_audit.csv`: comparison of formula remainder, gov balance movements, and paid rewards.

`undistributed_remainder_gonka` is currently formula-derived from base reward parameters minus paid rewards. It is not evidence that the same amount went to a government wallet unless a direct wallet balance delta is separately verified.
