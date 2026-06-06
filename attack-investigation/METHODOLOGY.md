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

## Chain summary fields

`build_epoch_summary.py` derives:

- total participants from participant API data when present, otherwise from performance summary rows;
- final group count from `epoch_group_data` validation/member arrays when present;
- excluded count from saved participant API data when available. If that endpoint fails, it uses a chain-derived fallback: `(performance summary participants union epoch group members) - validation_weights`;
- zero reward count from performance summary rows with `rewarded_coins == 0`;
- burned amount from the sum of `burned_coins`;
- actual rewarded amount from the sum of `rewarded_coins`;
- undistributed remainder only when an expected settlement reward can be found in saved raw data.

If expected settlement reward is not discoverable in saved data, `undistributed_remainder_gonka` is left blank.

## Classification classes

`affected_rows.csv` includes chain-derived affected rows even before source claim files are loaded. Source claim rows are appended after those chain rows.

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
- `undistributed_remainder_gonka` is the settlement-visible remainder, if computable from saved chain data;
- `difference` is `source_compensation_gonka - undistributed_remainder_gonka` when both values exist.

The difference is not a fraud finding by itself. It identifies where the source compensation model diverges from chain settlement accounting.
