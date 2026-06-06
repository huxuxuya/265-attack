# Findings

Current findings from saved raw chain data and currently available source claim files.

## Confirmed

- Raw data was saved for epochs 265 and 266 from the configured archive REST node with SHA-256 entries in `manifests/raw_chain_cache_manifest.md`.
- Epoch 265: 53 settlement-visible participants, 51 final group members, 2 chain-derived excluded participants, 16 zero-reward addresses, 185565043.741173 GONKA rewarded, 0 burned GONKA.
- Epoch 266: 48 settlement-visible participants, 46 final group members, 2 chain-derived excluded participants, 10 zero-reward addresses, 261173638.85856 GONKA rewarded, 0 burned GONKA.

## Not Confirmed

- No source claim files are currently present under `source_claims/votkon/` or `source_claims/case3/`, so no individual claim rows have been confirmed or rejected yet.
- `undistributed_remainder_gonka` is not computed yet because the saved raw data has not exposed an expected settlement reward value that the script can safely subtract from actual rewarded settlement.

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
