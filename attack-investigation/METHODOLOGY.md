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
- base reward formula from `bitcoin_reward_params`;
- formula remainder as `base reward formula - paid rewards`;
- largest direct gov balance jump inside the epoch;
- full gov balance delta from `effective_block_height` to `last_block_height`.

This distinction matters: formula remainder is not the same measurement as a gov balance transfer. If they differ, the direct balance movement is the chain fact and the formula remainder is a model output that needs explanation.

## Chain summary fields

`build_epoch_summary.py` derives:

- total participants from participant API data when present, otherwise from performance summary rows;
- final group count from `epoch_group_data` validation/member arrays when present;
- excluded count from saved participant API data when available. If that endpoint fails, it uses a chain-derived fallback: `(performance summary participants union epoch group members) - validation_weights`;
- zero reward count from performance summary rows with `rewarded_coins == 0`;
- base reward formula from explicit settlement reward fields when present, otherwise from saved `bitcoin_reward_params` using `initial_epoch_reward * (1 + decay_rate) ^ (epoch - genesis_epoch)`;
- burned amount from the sum of `burned_coins`;
- actual rewarded amount from the sum of `rewarded_coins`;
- formula remainder as base reward formula minus actual rewarded amount.

`undistributed_remainder_gonka` is a formula-derived accounting value in the current script. It is not labeled as a verified gov-wallet transfer unless a separate balance-delta check is performed.

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

The current saved `poc_validation_snapshot` endpoint returns `found=false` for epochs 265 and 266, so `confirmation_poc_zero_weight` is not labeled as direct raw snapshot proof. It means the participant is present in final `validation_weights`, but has `confirmation_weight = 0` in saved chain data.

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
