# Epoch 265-266 Attack Investigation

Independent investigation workspace for epochs 265 and 266.

The investigation separates:

- chain facts visible in saved raw data;
- source compensation claims;
- policy-dependent compensation decisions.

The main rule is: save raw data first, calculate later.

## Main Numbers

All money values are in GNK, not nGNK. The table separates current-epoch settlement remainder from other gov transfers at the same height.

| epoch | participants | received reward | zero reward | final group | no final weight | reward pool, GNK | paid to miners, GNK | not distributed by settlement, GNK | other same-height gov transfers, GNK | burned, GNK |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 265 | 53 | 37 | 16 | 51 | 2 | 284,932,503.735690 | 185,565,043.741173 | 99,367,459.994521 | 0.000000 | 0.000000 |
| 266 | 48 | 38 | 10 | 46 | 2 | 284,797,192.935274 | 261,173,638.858560 | 23,623,554.076719 | 2,804,142.500324 | 0.000000 |
| TOTAL | 101 | 75 | 26 | 97 | 4 | 569,729,696.670964 | 446,738,682.599733 | 122,991,014.071240 | 2,804,142.500324 | 0.000000 |

Evidence:

- Chain binary observed from the archive node: `inferenced v0.2.13`, git commit `c716df26cb8802e341a007f79b445352c53a3bee`; saved in [`raw_chain_cache/chain_evidence/node_info.json`](raw_chain_cache/chain_evidence/node_info.json).
- `reward pool` is calculated with the v0.2.13 formula: `initial_reward * exp(decay_rate)^epochs_since_genesis`, truncated to integer nGNK like Go `IntPart()`.
- `not distributed by settlement` is the current-epoch bitcoin reward remainder. It matches the gov `coin_received` EndBlock event in saved RPC `block_results`.
- `other same-height gov transfers` are separate inference-to-gov EndBlock transfers at the same height. They are not counted as current-epoch reward remainder without a separate memo/proof.
- There is no user transaction hash for the settlement gov transfer: it is EndBlock module logic, not a user tx. Tx search for gov recipient at the settlement heights returns zero txs.

## Gov EndBlock Evidence

From [`outputs/gov_endblock_transfers.csv`](outputs/gov_endblock_transfers.csv):

| epoch | height | event | amount, GNK | inferred role |
|---:|---:|---:|---:|---|
| 265 | 4,105,641 | 1 | 99,367,459.994521 | current epoch bitcoin reward remainder |
| 266 | 4,121,032 | 1 | 23,623,554.076719 | current epoch bitcoin reward remainder |
| 266 | 4,121,032 | 2 | 1,759,749.687948 | other inference-to-gov EndBlock transfer |
| 266 | 4,121,032 | 3 | 1,044,392.812376 | other inference-to-gov EndBlock transfer |

This resolves the previous discrepancy: epoch 266 `main gov jump` was `26,427,696.577043 GNK`, but only `23,623,554.076719 GNK` is the current epoch settlement remainder. The extra `2,804,142.500324 GNK` is same-height gov movement and must not be merged into miner compensation by default.

## Zero-Reward Hosts

Full address-level detail for the 26 zero-reward hosts is in [`outputs/not_received_hosts_detail.csv`](outputs/not_received_hosts_detail.csv). Per-host forfeited amount is not proof-grade yet because chain settlement stores `rewarded_coins`, not each host's counterfactual forfeited amount. That requires exact v0.2.13 settlement replay with participant status and downtime test state.

Counts from [`outputs/reward_status_count_summary.csv`](outputs/reward_status_count_summary.csv):

| epoch | total hosts | received reward | no final validation weight | downtime punishment candidate | no recorded work / status unresolved | status unresolved |
|---:|---:|---:|---:|---:|---:|---:|
| 265 | 53 | 37 | 2 | 13 | 1 | 0 |
| 266 | 48 | 38 | 2 | 6 | 1 | 1 |
| TOTAL | 101 | 75 | 4 | 19 | 2 | 1 |

Amount summary from [`outputs/reward_status_amount_summary.csv`](outputs/reward_status_amount_summary.csv):

| epoch | paid to rewarded hosts, GNK | current epoch unpaid pool, GNK | other same-height gov transfers, GNK | proof-grade allocated to zero-reward hosts, GNK | unattributed current epoch unpaid pool, GNK |
|---:|---:|---:|---:|---:|---:|
| 265 | 185,565,043.741173 | 99,367,459.994521 | 0.000000 | 0.000000 | 99,367,459.994521 |
| 266 | 261,173,638.858560 | 23,623,554.076719 | 2,804,142.500324 | 0.000000 | 23,623,554.076719 |
| TOTAL | 446,738,682.599733 | 122,991,014.071240 | 2,804,142.500324 | 0.000000 | 122,991,014.071240 |

Reason notes:

- `no_final_validation_weight`: participant appears in settlement/performance data but is absent from final `validation_weights`; v0.2.13 skips them as `No valid weight found`.
- `downtime_punishment_candidate`: settlement-visible counters include missed requests or invalidated inferences. Exact confirmation requires replaying `CheckAndPunishForDowntime` with v0.2.13.
- `zero_reward_no_recorded_work_status_unresolved`: no recorded work and zero reward; v0.2.13 downtime check would not zero reward when total requests are zero, so participant status/state must be replayed.
- `zero_reward_status_unresolved`: zero reward with final weight and no obvious proof-grade reason from the saved summary fields.

## cPoC History

cPoC history and confirmation snapshots were fetched from the archive node configured by `GONKA_RPC_URL`; fetch scripts do not use any public-node fallback. Raw artifacts and SHA-256 hashes are recorded in [`manifests/cpoc_history_manifest.md`](manifests/cpoc_history_manifest.md), [`manifests/cpoc_block_headers_manifest.md`](manifests/cpoc_block_headers_manifest.md), and [`manifests/cpoc_confirmation_snapshots_manifest.md`](manifests/cpoc_confirmation_snapshots_manifest.md).

Main progression table from [`outputs/model_confirmed_weight_progression_wide.csv`](outputs/model_confirmed_weight_progression_wide.csv):

| epoch | checkpoint | height | UTC | Kimi entry | Qwen entry | total entry | Kimi passed/active | Qwen passed/active | total passed/active | Kimi confirmed | Qwen confirmed | total confirmed | total delta |
|---:|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 265 | epoch_entry | 4,090,370 | 2026-05-15T23:22:59Z | 377,276 | 1,227,899 | 1,605,175 | 20/20 | 41/41 | 51/51 | 640,858 | 740,929 | 917,306 |  |
| 265 | after_cpoc_0 | 4,095,963 | 2026-05-16T07:18:59Z | 377,276 | 1,227,899 | 1,605,175 | 15/20 | 38/41 | 43/51 | 487,205 | 624,122 | 739,681 | -177,625 |
| 265 | after_cpoc_1 | 4,099,160 | 2026-05-16T11:49:56Z | 377,276 | 1,227,899 | 1,605,175 | 15/20 | 38/41 | 43/51 | 469,669 | 612,369 | 720,517 | -19,164 |
| 265 | after_cpoc_2 | 4,103,171 | 2026-05-16T17:29:07Z | 377,276 | 1,227,899 | 1,605,175 | 14/20 | 37/41 | 41/51 | 375,972 | 508,838 | 609,918 | -110,599 |
| 266 | epoch_entry | 4,105,761 | 2026-05-16T21:05:03Z | 59,933 | 886,097 | 946,030 | 8/8 | 40/40 | 45/45 | 115,164 | 334,904 | 393,991 |  |
| 266 | after_cpoc_0 | 4,115,375 | 2026-05-17T10:41:34Z | 59,933 | 886,097 | 946,030 | 8/8 | 34/40 | 39/45 | 115,022 | 317,276 | 376,221 | -17,770 |
| 266 | after_cpoc_1 | 4,117,265 | 2026-05-17T13:21:54Z | 59,933 | 886,097 | 946,030 | 8/8 | 33/40 | 38/45 | 113,940 | 313,238 | 371,996 | -4,225 |
| 266 | after_cpoc_2 | 4,118,384 | 2026-05-17T14:56:50Z | 59,933 | 886,097 | 946,030 | 8/8 | 33/40 | 38/45 | 111,574 | 312,409 | 369,530 | -2,466 |

`entry` is model subgroup PoC entry weight at epoch entry. `confirmed` is parent `validation_weights[].confirmation_weight` summed over addresses active in that model. `total` de-duplicates addresses that are active in both Kimi and Qwen, so it can be lower than `Kimi + Qwen`. The `after_cpoc_*` rows use the first saved height where the cPoC result is visible in parent chain state.

For the epoch 265 claim, the key row is Kimi `after_cpoc_2`: confirmed weight `469,669 -> 375,972` from the previous checkpoint, with passed participants `15 -> 14`. Address-level severe drops are in [`outputs/kimi_cpoc_confirmation_drop_265.csv`](outputs/kimi_cpoc_confirmation_drop_265.csv).

## Layout

- `raw_chain_cache/epoch_265/`, `raw_chain_cache/epoch_266/`: raw node responses and request errors.
- `source_claims/votkon/`, `source_claims/case3/`: source claim files. Put CSV or JSON files here.
- `manifests/`: SHA-256 manifests for raw chain data and source claim files.
- `outputs/`: derived CSV tables.
- `scripts/`: collection and analysis scripts.

## Workflow

```bash
cd attack-investigation
python3 scripts/fetch_raw_data.py --epochs 265 266
python3 scripts/build_epoch_summary.py
python3 scripts/classify_affected.py
python3 scripts/compare_claims.py
python3 scripts/fetch_module_balance_deltas.py
python3 scripts/build_unpaid_miners_detail.py
python3 scripts/fetch_gov_balance_change_points.py
python3 scripts/fetch_settlement_evidence.py
python3 scripts/build_gov_endblock_transfers.py
python3 scripts/fetch_model_group_data.py
python3 scripts/build_model_cpoc_weight_table.py
python3 scripts/build_model_cpoc_epoch_matrix.py
python3 scripts/fetch_cpoc_history.py
python3 scripts/fetch_cpoc_block_headers.py
python3 scripts/build_cpoc_history_tables.py
python3 scripts/fetch_cpoc_confirmation_snapshots.py
python3 scripts/build_cpoc_confirmation_history.py
python3 scripts/build_gov_settlement_audit.py
python3 scripts/build_reward_status_tables.py
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
- `outputs/settlement_event_summary.csv`: settlement-height block, tx-search, and RPC block-results evidence summary.
- `outputs/gov_endblock_transfers.csv`: gov `coin_received` EndBlock transfer components from saved RPC `block_results`.
- `outputs/model_cpoc_weight_table.csv`: host-level model subgroup PoC/cPoC weights.
- `outputs/model_cpoc_weight_summary.csv`: per-epoch per-model aggregate weights.
- `outputs/model_cpoc_epoch_matrix.csv`: compact per-epoch Kimi/Qwen matrix.
- `outputs/model_confirmed_weight_progression_wide.csv`: main cPoC progression by epoch/checkpoint with Kimi, Qwen, and de-duplicated total columns.
- `outputs/model_confirmed_weight_progression.csv`: long-form version of the main progression table.
- `outputs/epoch_entry_context.csv`, `outputs/cpoc_events.csv`, `outputs/cpoc_history_endpoint_summary.csv`, `outputs/cpoc_event_model_weight_matrix.csv`, `outputs/cpoc_confirmation_weight_history.csv`, `outputs/per_cpoc_confirmation_effects.csv`, `outputs/kimi_cpoc_confirmation_drop_265.csv`: audit/detail tables behind the main progression table.
- `outputs/gov_settlement_audit.csv`: comparison of formula remainder, gov balance movements, and paid rewards.
- `outputs/not_received_hosts_detail.csv`: per-host zero-reward detail with reason and proof-grade amount status.
- `outputs/reward_status_count_summary.csv`: per-epoch and total counts by received/not-received reason.
- `outputs/reward_status_amount_summary.csv`: per-epoch paid rewards, current-epoch unpaid pool, and unattributed settlement remainder.

`undistributed_remainder_gonka` is formula-derived from v0.2.13 reward parameters minus paid rewards. It is treated as current-epoch settlement remainder only where it matches saved gov `coin_received` EndBlock evidence.
