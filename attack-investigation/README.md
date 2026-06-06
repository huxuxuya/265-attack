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

## Model cPoC Weights

Model subgroup data was fetched from the archive node configured by `GONKA_RPC_URL`. The full host-level table is in [`outputs/model_cpoc_weight_table.csv`](outputs/model_cpoc_weight_table.csv). Compact epoch-level matrix:

| epoch | Kimi participants | Qwen participants | Kimi entry weight | Qwen entry weight | Kimi confirmed node weight | Qwen confirmed node weight | Kimi preserved node weight | Qwen preserved node weight | Kimi total node weight | Qwen total node weight |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 265 | 20 | 41 | 377,276 | 1,227,899 | 336,641 | 1,106,344 | 40,635 | 121,555 | 377,276 | 1,227,899 |
| 266 | 8 | 40 | 59,933 | 886,097 | 16,235 | 802,093 | 43,698 | 84,004 | 59,933 | 886,097 |

Kimi entry weight drops from `377,276` in epoch 265 to `59,933` in epoch 266: `317,343` less, or `84.11%`. Qwen entry weight drops `27.84%` over the same comparison.

Definitions:

- `entry weight`: model subgroup `validation_weights[].weight`.
- `confirmed node weight`: sum of subgroup `ml_nodes[].poc_weight` for nodes not listed in the historical `preserved_nodes_snapshot` at that epoch's `poc_start_block_height`.
- `preserved node weight`: sum of subgroup `ml_nodes[].poc_weight` for node IDs listed in the historical `preserved_nodes_snapshot`.
- Model participant counts are subgroup memberships, not unique epoch participants; one address can appear in multiple model subgroups.

This is the table to use for the Kimi attack hypothesis: if vLLM failures stopped Kimi nodes from entering or serving, the first chain-visible place to inspect is the Kimi subgroup weight and the confirmed-vs-preserved split.

## cPoC History

cPoC history was fetched from the archive node configured by `GONKA_RPC_URL`; fetch scripts do not use any public-node fallback. Raw artifacts and SHA-256 hashes are recorded in [`manifests/cpoc_history_manifest.md`](manifests/cpoc_history_manifest.md).

Per-cPoC event table from [`outputs/cpoc_events.csv`](outputs/cpoc_events.csv):

| epoch | event | trigger height | generation start height | phase |
|---:|---:|---:|---:|---|
| 265 | 0 | 4,095,682 | 4,095,684 | CONFIRMATION_POC_COMPLETED |
| 265 | 1 | 4,098,879 | 4,098,881 | CONFIRMATION_POC_COMPLETED |
| 265 | 2 | 4,102,890 | 4,102,892 | CONFIRMATION_POC_COMPLETED |
| 266 | 0 | 4,115,094 | 4,115,096 | CONFIRMATION_POC_COMPLETED |
| 266 | 1 | 4,116,984 | 4,116,986 | CONFIRMATION_POC_COMPLETED |
| 266 | 2 | 4,118,103 | 4,118,105 | CONFIRMATION_POC_COMPLETED |

Per-cPoC model weight matrix from [`outputs/cpoc_event_model_weight_matrix.csv`](outputs/cpoc_event_model_weight_matrix.csv):

| epoch | event | trigger height | Kimi confirmed | Kimi preserved | Kimi total | Qwen confirmed | Qwen preserved | Qwen total | total confirmed | total preserved | total weight |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 265 | 0 | 4,095,682 | 336,641 | 40,635 | 377,276 | 1,106,344 | 121,555 | 1,227,899 | 1,442,985 | 162,190 | 1,605,175 |
| 265 | 1 | 4,098,879 | 336,641 | 40,635 | 377,276 | 1,106,344 | 121,555 | 1,227,899 | 1,442,985 | 162,190 | 1,605,175 |
| 265 | 2 | 4,102,890 | 336,641 | 40,635 | 377,276 | 1,106,344 | 121,555 | 1,227,899 | 1,442,985 | 162,190 | 1,605,175 |
| 266 | 0 | 4,115,094 | 16,235 | 43,698 | 59,933 | 802,093 | 84,004 | 886,097 | 818,328 | 127,702 | 946,030 |
| 266 | 1 | 4,116,984 | 16,235 | 43,698 | 59,933 | 802,093 | 84,004 | 886,097 | 818,328 | 127,702 | 946,030 |
| 266 | 2 | 4,118,103 | 16,235 | 43,698 | 59,933 | 802,093 | 84,004 | 886,097 | 818,328 | 127,702 | 946,030 |

The weights in this matrix are `event + epoch model weight snapshot`, not per-event participant validation rows. They repeat inside an epoch because the archive endpoints returned cPoC events, while stage-level participant/commit endpoints did not return per-event host rows for epochs 265 and 266.

Endpoint availability summary from [`outputs/cpoc_history_endpoint_summary.csv`](outputs/cpoc_history_endpoint_summary.csv):

| epoch | poc start height | confirmation events | validation snapshot | v2 validations | v2 commits | weight distributions | batches | legacy validations |
|---:|---:|---:|---|---:|---:|---:|---:|---:|
| 265 | 4,089,970 | 3 | found=false | 0 | 0 | 0 | 0 | 0 |
| 266 | 4,105,361 | 3 | found=false | 0 | 0 | 0 | 0 | 0 |

So the archive node gives proof-grade confirmation cPoC event history for these epochs, but the fetched stage-level participant/commit endpoints returned empty lists or `found=false`. That means host-level cPoC failure reasons still need either exact v0.2.13 replay or additional indexed logs; the saved chain endpoints alone do not currently provide per-host cPoC validation rows.

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
python3 scripts/build_cpoc_history_tables.py
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
- `outputs/cpoc_events.csv`: per-cPoC confirmation event history.
- `outputs/cpoc_history_endpoint_summary.csv`: cPoC endpoint availability and record counts.
- `outputs/cpoc_event_model_weight_matrix.csv`: per-cPoC event rows with epoch-level Kimi/Qwen confirmed, preserved, and total weights.
- `outputs/gov_settlement_audit.csv`: comparison of formula remainder, gov balance movements, and paid rewards.
- `outputs/not_received_hosts_detail.csv`: per-host zero-reward detail with reason and proof-grade amount status.
- `outputs/reward_status_count_summary.csv`: per-epoch and total counts by received/not-received reason.
- `outputs/reward_status_amount_summary.csv`: per-epoch paid rewards, current-epoch unpaid pool, and unattributed settlement remainder.

`undistributed_remainder_gonka` is formula-derived from v0.2.13 reward parameters minus paid rewards. It is treated as current-epoch settlement remainder only where it matches saved gov `coin_received` EndBlock evidence.
