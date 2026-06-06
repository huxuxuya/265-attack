# Methodology

## Scope

Default scope:

- epochs: 265, 266;
- models: all models visible in saved epoch data;
- cPoC stages: commits, validations, validation snapshot where node endpoints are available;
- source claims: files saved under `source_claims/votkon/` and `source_claims/case3/`.

## Data rule

Every node request must be handled in this order:

1. save the raw response body or error body;
2. save stderr/error metadata if present;
3. calculate SHA-256 for saved artifacts;
4. record the request in `manifests/raw_chain_cache_manifest.md`;
5. only then build derived CSV outputs.

The build scripts read from `raw_chain_cache/` only. They do not query the node.
The manifest redacts the configured node host as `<base-url>` so environment-provided node URLs are not committed.
Fetch scripts require `GONKA_RPC_URL` or `GONKA_REST_URL`; they do not fall back to a public node.

## Gov Balance Check

`fetch_module_balance_deltas.py` collects module accounts and historical `ngonka` balances at:

- epoch `effective_block_height`;
- epoch `last_block_height`;
- `last_block_height + 1`.

It saves raw JSON under `raw_chain_cache/*/module_balances/`, records SHA-256 values in `manifests/module_balance_manifest.md`, and writes `outputs/module_balance_deltas.csv`.

The key gov-wallet test is `delta_last_to_next_gnk` for the `gov` module. A zero value means the epoch-boundary balance delta does not confirm that the settlement remainder was transferred to the gov module account at that boundary.

`fetch_gov_balance_change_points.py` performs a direct historical balance scan for the `gov` module account inside each investigated epoch. It saves every requested height under `raw_chain_cache/*/gov_balance_change_points/`, records SHA-256 values in `manifests/gov_balance_change_points_manifest.md`, and writes `outputs/gov_balance_change_points.csv`.

`build_gov_settlement_audit.py` compares:

- direct paid rewards from `epoch_performance_summary`;
- base reward formula from `bitcoin_reward_params` using the v0.2.13 formula `initial_reward * exp(decay_rate)^epochs_since_genesis`;
- formula remainder as `base reward formula - paid rewards`;
- largest direct gov balance jump inside the epoch;
- current-epoch gov EndBlock transfer components from `outputs/gov_endblock_transfers.csv`;
- full gov balance delta from `effective_block_height` to `last_block_height`.

This distinction matters: a gov balance jump can include multiple EndBlock transfers. The current-epoch settlement remainder is accepted as a chain fact only when the v0.2.13 formula remainder matches a saved gov `coin_received` EndBlock event. Same-height extra inference-to-gov transfers are reported separately.

`fetch_settlement_evidence.py` saves:

- node info, current upgrade plan, and module versions;
- settlement-height block headers;
- tx search for all txs and gov-recipient txs at settlement heights;
- RPC `block_results` for settlement heights.

`build_gov_endblock_transfers.py` parses saved RPC `block_results` and writes each gov `coin_received` EndBlock component to `outputs/gov_endblock_transfers.csv`.

`fetch_model_group_data.py` reads the archive node from `GONKA_RPC_URL`/`GONKA_REST_URL` and saves:

- model-specific `epoch_group_data/{epoch}?model_id=...` for every model listed in parent `sub_group_models`;
- historical `preserved_nodes_snapshot` at each epoch's `poc_start_block_height` using `x-cosmos-block-height`;
- SHA-256 entries in `manifests/model_group_data_manifest.md`.

`build_model_cpoc_weight_table.py` builds:

- `model_cpoc_weight_table.csv`: host-level parent weight, model subgroup entry weights, model node weights, confirmed node weights, preserved node weights, and totals;
- `model_cpoc_weight_summary.csv`: per-epoch per-model aggregate;
- `model_cpoc_epoch_matrix.csv`: compact Kimi/Qwen matrix.

For model cPoC tables, `preserved_node_weight` is calculated by matching subgroup `ml_nodes[].node_id` against the historical `preserved_nodes_snapshot`. `confirmed_node_weight` is the remaining subgroup node `poc_weight`. Deprecated `timeslot_allocation` is not used as the source of truth when historical snapshot data is available.

`fetch_cpoc_history.py` reads the archive node from `GONKA_RPC_URL`/`GONKA_REST_URL` and saves:

- `confirmation_poc_events/{epoch}`;
- `poc_validation_snapshot/{poc_start_block_height}`;
- `poc_v2_validations_for_stage/{poc_start_block_height}`;
- `all_poc_v2_store_commits/{poc_start_block_height}`;
- `all_mlnode_weight_distributions/{poc_start_block_height}`;
- `poc_batches_for_stage/{poc_start_block_height}`;
- `poc_validations_for_stage/{poc_start_block_height}`;
- SHA-256 entries in `manifests/cpoc_history_manifest.md`.

`fetch_cpoc_block_headers.py` reads saved cPoC events and epoch metadata, then saves block headers for:

- epoch `effective_block_height`;
- epoch `poc_start_block_height`;
- every cPoC `trigger_height`;
- every cPoC `generation_start_height`;
- SHA-256 entries in `manifests/cpoc_block_headers_manifest.md`.

`build_cpoc_history_tables.py` builds:

- `epoch_entry_context.csv`: epoch `effective_block_height`, UTC start time, participant counts, reward status counts, and Kimi/Qwen entry weights;
- `cpoc_events.csv`: one row per confirmation cPoC event with epoch start and UTC block times;
- `cpoc_history_endpoint_summary.csv`: one row per fetched endpoint with record counts and `found=false`/empty-list notes.
- `cpoc_event_model_weight_matrix.csv`: cPoC event rows joined with UTC block times and the epoch-level Kimi/Qwen non-preserved/preserved `poc_weight` matrix.

These tables distinguish available event-level cPoC history from missing stage-level participant validation/commit rows. Empty endpoint responses are reported as data availability facts, not converted into host-level failure reasons.
The model weights repeat for cPoC events inside the same epoch because the available chain data gives event history and epoch model snapshots, but not per-event participant validation rows.

`fetch_cpoc_confirmation_snapshots.py` saves historical parent `epoch_group_data/{epoch}` snapshots at epoch start, cPoC generation-start heights, selected claim-check heights, and epoch last height. It also saves block headers for those heights and records SHA-256 entries in `manifests/cpoc_confirmation_snapshots_manifest.md`.

`build_cpoc_confirmation_history.py` builds:

- `model_confirmed_weight_progression_wide.csv`: the main cPoC progression table by epoch/checkpoint with Kimi, Qwen, and de-duplicated union totals in columns;
- `model_confirmed_weight_progression.csv`: long-form version of the same progression by epoch, model, and checkpoint;
- `cpoc_confirmation_weight_history.csv`: parent and Kimi-subset sums of `validation_weights[].confirmation_weight` at each saved height;
- `per_cpoc_confirmation_effects.csv`: before/after confirmed-weight deltas for every cPoC, where before is the generation-start snapshot and after is the next saved parent snapshot where the cPoC result is visible;
- `kimi_cpoc_confirmation_drop_265.csv`: address-level Kimi `confirmation_weight` deltas from height `4102892` to claimed drop height `4103171`.

This is separate from model subgroup `poc_weight` and preserved-node tables. A cPoC confirmation degradation can appear in parent `confirmation_weight` while model subgroup entry `poc_weight` remains unchanged.

`build_reward_status_tables.py` builds:

- `not_received_hosts_detail.csv`: every host with `rewarded_coins = 0`, the reason class, direct chain received amount, and proof-grade amount status;
- `reward_status_count_summary.csv`: counts by epoch and reason, including rewarded hosts;
- `reward_status_amount_summary.csv`: paid rewards, current-epoch unpaid pool, other same-height gov transfers, and unattributed current-epoch unpaid pool.

The script deliberately does not allocate GNK amounts to individual zero-reward hosts. Chain settlement stores `rewarded_coins`, but not each host's counterfactual forfeited amount. Per-host amount allocation requires exact v0.2.13 settlement replay, including participant status, power cap, and downtime test results.

## Chain summary fields

`build_epoch_summary.py` derives:

- total participants from participant API data when present, otherwise from performance summary rows;
- final group count from `epoch_group_data` validation/member arrays when present;
- excluded count from saved participant API data when available. If that endpoint fails, it uses a chain-derived fallback: `(performance summary participants union epoch group members) - validation_weights`;
- zero reward count from performance summary rows with `rewarded_coins == 0`;
- base reward formula from explicit settlement reward fields when present, otherwise from saved `bitcoin_reward_params` using v0.2.13 `initial_epoch_reward * exp(decay_rate) ^ (epoch - genesis_epoch)`;
- burned amount from the sum of `burned_coins`;
- actual rewarded amount from the sum of `rewarded_coins`;
- formula remainder as base reward formula minus actual rewarded amount.

`undistributed_remainder_gonka` is a formula-derived accounting value. It is labeled as current-epoch settlement remainder only where saved RPC block-results show a matching gov `coin_received` EndBlock event.

## Classification classes

`affected_rows.csv` includes chain-derived affected rows even before source claim files are loaded. Source claim rows are appended after those chain rows.

`unpaid_miners_detail.csv` includes only settlement-visible participants with `rewarded_coins = 0`. Reasons are derived from saved chain fields:

- final group membership from `validation_weights`;
- `confirmation_weight` and `reputation` from `validation_weights`;
- `poc_validation_snapshot` availability flag;
- `claimed`;
- `earned_coins`;
- `missed_requests`;
- `inference_count`;
- `validated_inferences`;
- `invalidated_inferences`.

The current saved `poc_validation_snapshot` endpoint returns `found=false` for epochs 265 and 266. Also, the observed v0.2.13 settlement code skips confirmation rescale when `confirmation_weight_scales` is empty. Therefore `confirmation_weight = 0` is not used as a proof-grade zero-reward reason by itself.

`unpaid_reason_summary.csv` aggregates the address-level detail by epoch and reason class.

Rows are classified into these classes:

- `direct_cpoc_failure`: direct operator cPoC failure evidence is present or claimed with matching chain participation evidence.
- `excluded_operator`: address is present in saved excluded participants.
- `zero_reward_reconstruction`: address appears in performance summary with zero reward.
- `rewarded_topup`: address received a reward but source still requests compensation.
- `delegator_indirect_loss`: source row is a delegator/delegation claim.
- `groupcap_topup`: source row asks for top-up due to group cap/group limit logic.
- `not_confirmed`: no saved chain evidence confirms the row.

These classes are deliberately not merged into one compensation bucket. Any merge requires a policy decision.

## Claim comparison

`compare_claims.py` compares source compensation against chain settlement facts:

- `source_compensation_gonka` is taken from source claim rows;
- `undistributed_remainder_gonka` is the current formula-derived base reward remainder, if computable from saved chain data;
- `difference` is `source_compensation_gonka - undistributed_remainder_gonka` when both values exist.

The difference is not a fraud finding by itself. It identifies where the source compensation model diverges from the current base reward formula. Direct gov balance movements are audited separately in `gov_settlement_audit.csv`.
