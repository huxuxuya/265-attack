# Findings

Current findings from saved raw chain data and currently available source claim files.

## Confirmed

- Raw data was saved for epochs 265 and 266 from the configured archive REST node with SHA-256 entries in `manifests/raw_chain_cache_manifest.md`.
- Epoch 265: 53 settlement-visible participants, 37 rewarded, 16 not rewarded, 51 final group members, 2 chain-derived excluded participants, 185565043.741173 GNK paid to miners, 99367459.994521 GNK main gov balance jump at height 4105641, 99367460.084386 GNK full gov balance increase during the epoch, 0 GNK burned.
- Epoch 266: 48 settlement-visible participants, 38 rewarded, 10 not rewarded, 46 final group members, 2 chain-derived excluded participants, 261173638.858560 GNK paid to miners, 26427696.577043 GNK main gov balance jump at height 4121032, 26427646.580643 GNK full gov balance increase during the epoch, 0 GNK burned.
- The base reward formula currently used by `build_epoch_summary.py` does not match the chain-observed `paid rewards + main gov jump`: epoch 265 differs by 8488.564042 GNK, and epoch 266 differs by 2812659.171158 GNK.
- Across epochs 265 and 266, 75 hosts received rewards and 26 hosts received zero reward: 18 `confirmation_poc_zero_weight`, 4 `missed_or_invalidated_work`, and 4 `excluded_from_final_group`.
- The chain-observed unpaid pool is 125795156.571564 GNK across both epochs, measured as the sum of the main gov jumps. The current per-host reconstruction covers 38208047.615338 GNK and leaves 87587108.956226 GNK requiring an additional compensation model or source data.

## Not Confirmed

- No source claim files are currently present under `source_claims/votkon/` or `source_claims/case3/`, so no individual claim rows have been confirmed or rejected yet.
- The formula remainder is not confirmed as the exact amount sent to gov. Direct gov balance movement is larger than the formula remainder in both investigated epochs.
- The direct `last_block_height -> last_block_height + 1` gov boundary delta is 0 GNK for both epochs, so the data does not confirm a one-block settlement transfer to gov at the epoch boundary.

## Policy-Dependent

- Zero-reward reconstruction and rewarded top-up amounts still require a source compensation model.
- Delegator indirect loss and groupcap top-up classes require separate policy decisions and must not be merged into direct operator compensation by default.

## Recommended Vote Split

- Pending source claim files and committee policy choices.

At minimum, keep separate votes or line items for direct cPoC/operator failures, reconstructed zero-reward compensation, rewarded top-ups, delegator indirect losses, and groupcap top-ups.

## Current Working Hypothesis

The attack can be real while the source compensation amount does not equal the amount that was not distributed to participants by settlement.

The final report must separately show:

- chain facts;
- source compensation model;
- policy questions for the committee.

Current chain facts show direct gov module balance jumps inside both epochs, but those jumps do not equal the current base formula remainder. The report must not equate formula remainder with gov transfer without explaining that formula gap.
