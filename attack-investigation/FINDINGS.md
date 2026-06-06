# Findings

Current findings from saved raw chain data and currently available source claim files.

## Confirmed

- Raw data was saved for epochs 265 and 266 from the configured archive REST node with SHA-256 entries in `manifests/raw_chain_cache_manifest.md`.
- Settlement evidence was saved for the investigated heights with SHA-256 entries in `manifests/settlement_evidence_manifest.md`.
- The archive node reports `inferenced v0.2.13`, git commit `c716df26cb8802e341a007f79b445352c53a3bee`, inference module version `14`.
- Epoch 265: 53 settlement-visible participants, 37 rewarded, 16 zero-reward rows, 51 final group members, 2 rows with no final validation weight, 284932503.735690 GNK reward pool, 185565043.741173 GNK paid to miners, 99367459.994521 GNK current-epoch gov EndBlock remainder, 0 GNK burned.
- Epoch 266: 48 settlement-visible participants, 38 rewarded, 10 zero-reward rows, 46 final group members, 2 rows with no final validation weight, 284797192.935274 GNK reward pool, 261173638.858560 GNK paid to miners, 23623554.076719 GNK current-epoch gov EndBlock remainder, 0 GNK burned.
- Across epochs 265 and 266, 446738682.599733 GNK was paid to rewarded hosts and 122991014.071240 GNK was not distributed to participants by current-epoch settlement.
- Epoch 266 also has 2804142.500324 GNK of other same-height inference-to-gov EndBlock transfers. This is not counted as current-epoch reward remainder without additional memo/proof.
- Across epochs 265 and 266, 75 hosts received rewards and 26 hosts received zero reward: 4 `no_final_validation_weight`, 19 `downtime_punishment_candidate`, 2 `zero_reward_no_recorded_work_status_unresolved`, and 1 `zero_reward_status_unresolved`.
- Model subgroup data from the archive node shows Kimi entry weight dropping from 377276 in epoch 265 to 59933 in epoch 266, an 84.11% drop. Qwen entry weight drops from 1227899 to 886097, a 27.84% drop.
- Historical `preserved_nodes_snapshot` was saved at `poc_start_block_height` for both epochs, so model cPoC tables can split node weight into confirmed vs preserved buckets.
- cPoC history from the archive node shows 3 `CONFIRMATION_POC_COMPLETED` events in epoch 265 and 3 in epoch 266.
- Epoch 265 parent `confirmation_weight` drops at the claimed height 4103171: parent total drops from 720517 at height 4102892 to 609918, and Kimi-subset confirmation weight drops from 469669 to 375972.
- Three Kimi participants have severe `confirmation_weight` degradation at height 4103171: `gonka1830lqug50lse998x2lakk4pj5ypfumz5pasz0y`, `gonka1famtxh54kad6ylwtm60j6d7h6unpc08d4vdqnk`, and `gonka1j7x6dv42xehe9e5au4ku3wvzwtqlegfjhlvzj6`.

## Not Confirmed

- No source claim files are currently present under `source_claims/votkon/` or `source_claims/case3/`, so no individual claim rows have been confirmed or rejected yet.
- Per-host forfeited GNK amounts are not confirmed. The chain stores `rewarded_coins`, but not each host's counterfactual forfeited amount.
- `confirmation_weight = 0` is not confirmed as a standalone zero-reward cause because v0.2.13 skips confirmation rescale when `confirmation_weight_scales` is empty.
- The two extra epoch 266 same-height gov transfers are not confirmed as attack remainder. They require separate memo/state proof.
- The Kimi weight drop is not, by itself, proof of attack causality. It is a chain-visible signal that must be compared with external vLLM failure evidence, inference shutdown timing, and exact participant/node logs.
- Stage-level participant cPoC validations, v2 commits, batches, and weight distributions are not currently available from the fetched archive endpoints for epochs 265 and 266: those endpoints returned empty lists, and validation snapshot returned `found=false`.
- The newly confirmed epoch 265 `confirmation_weight` degradation does not by itself prove external attack causality; it proves the chain-visible weight drop and affected Kimi rows at the claimed height.

## Policy-Dependent

- Per-host zero-reward compensation requires exact v0.2.13 settlement replay and then a source compensation model.
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

Current chain facts show current-epoch gov EndBlock settlement remainder of 122991014.071240 GNK across epochs 265 and 266. This is separate from source compensation and separate from same-height expired/unclaimed gov transfers.
