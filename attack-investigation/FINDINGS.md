# Findings

Current findings from saved raw chain data and currently available source claim files.

## Confirmed

- Raw data was saved for epochs 265 and 266 from the configured archive REST node with SHA-256 entries in `manifests/raw_chain_cache_manifest.md`.
- Epoch 265: 53 settlement-visible participants, 37 rewarded, 16 not rewarded, 51 final group members, 2 chain-derived excluded participants, 284924015.171652 GNK reward pool, 185565043.741173 GNK paid to miners, 99358971.430479 GNK not paid by settlement, 99367460.084386 GNK gov module balance increase during the epoch, 0 GNK gov boundary delta, 0 GNK burned.
- Epoch 266: 48 settlement-visible participants, 38 rewarded, 10 not rewarded, 46 final group members, 2 chain-derived excluded participants, 284788676.264445 GNK reward pool, 261173638.858560 GNK paid to miners, 23615037.405885 GNK not paid by settlement, 26427646.580643 GNK gov module balance increase during the epoch, 0 GNK gov boundary delta, 0 GNK burned.

## Not Confirmed

- No source claim files are currently present under `source_claims/votkon/` or `source_claims/case3/`, so no individual claim rows have been confirmed or rejected yet.
- The gov module balance increased during both epochs, but the increase is not exactly equal to `not_paid_rewards_gnk`.
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

Current chain facts do not prove that any undistributed amount went to a government wallet. That requires a separate direct balance-delta check.
