# Resources, skill learning, charges and local cast observations (0.7.0)

This version adds working data paths for primary resources, universal shields, learned skill ranks, charge reports and optional emulated cast observations. It also replaces the misleading assumption that every final cast-counter discrepancy proves a missing replay cast.

## Standalone state decoding

```sh
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --experimental-state --experimental-skills --experimental-charges --experimental-cooldowns --experimental-vision --experimental-deaths --out ./runs/state
```

All profiles require exact build `16.21.829.8620`, protocol `20e09df23c66b85e`. The state decoder applies the validated champion entity gate; NPC schemas and unknown later fields are not guessed.

Champion group 32 fields 15/16 report primary resource/current maximum, and field 3 reports a universal damage shield. Resource is not automatically called mana for every champion. Each field is sparse and retains its update timestamp. Only the prefix required for selected fields is traversed, avoiding an unknown trailing-field variant encountered in the loss. Physical/magical shield fields and later state fields are not labeled.

On the reference replay, all 240 maximum-resource comparisons and 231/240 current-resource comparisons against Riot Match-v5 snapshots differ by less than one point. Median current-resource absolute error is 0.5250, maximum 6.6411; comparisons use preceding replay samples at different times. The loss's five observed Barrier uses are each followed by a positive universal-shield update within 33-66 ms, with decay/consumption afterward. A separate experience-based level check agrees with all 240 API levels; all five observed Barrier amounts agree with the expected scaling within 0.00003 points. The scaling is documented in Riot's [Barrier balance notes](https://www.leagueoflegends.com/en-ph/news/game-updates/patch-14-22-notes/). This does not establish every shield mechanic.

Opcode `0x035c` reports skill slot and rank. All 128 reference skill-up participants/slots/timestamps agree with Riot's timeline within 150 ms; all 128 ranks agree with cumulative learning for that participant/slot. All four decoded fields match the native reader. Three scalar byte maps were checked on 768 native byte cases. The loss independently exports 148 reports.

Opcode `0x02c1` reports integer charge counts, a reported capacity/sentinel, recharge duration, remaining recharge, slot and an uninterpreted byte. All six fields match native output on 757 reference and 566 loss records (1,323 total). Six byte maps were derived from 1,536 native byte cases, with separate float-order probes. Integer sentinels are not misread as NaNs, zero charges, or instructions to clear a previous capacity. Positive remaining recharge does not imply zero charges. These are explicit updates; cast consumption and recharge progression are not projected as a complete charge history.

## Optional bounded cast reader

```sh
python -m pip install -r requirements-native.txt
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --native-image /path/to/locally-recovered-client-image.pe --experimental-state --experimental-skills --experimental-charges --out ./runs/casts
```

The optional reader uses Unicorn and a user-supplied, locally recovered flat image. It rejects the original EXE, different builds, different protocols and every recovered image except the fingerprinted research artifact. It is intended for this exact research setup; the repository does not supply a general unpacking/recovery workflow or any game binary.

Required recovered-image SHA-256: `046587872c6e0dc5aae9ac9414597f52025650671912ca2f5574ed2777018865`, size 44,904,448 bytes. Original client SHA-256: `6f8712cf8ff062d1a914796fe0ad057dae86064d4b651e0ff91d0f3885749d1a`. Constructor RVA `0xc38bb0`, reader `0xe76a00`. Every call has a two-million-instruction budget, fixed guest mappings and bounded guest allocation. No image code runs directly on the host CPU. A fixed Python hook models allocation; no Windows imports, live game memory or client-supplied callbacks are executed.

The reader extracts caster ID from the payload, slot, spell hash, selected reported mana/cooldown/time fields and raw fields with unverified meanings. Only known MF ability and Flash/Barrier hashes receive names. Unknown hashes remain unknown. It consumes the complete native payload but extracts selected semantic fields only. It does not label keyframe snapshots as new casts.

All selected fields match the previous native probes on 3,373 reference and 3,725 loss records: 7,098 total. Seven truncated samples are rejected, and a valid decode after those failures succeeds. The previously hypothesized spell-rank word was found to remain 1 after Q upgrades, so it is now explicitly `unverifiedWord196`. Verified ranks come from skill-learning reports. The other opaque cast token remains raw.

## Counter evidence, rather than fabricated missing casts

`cast-evidence-audit.json` compares final counters with observation totals without treating either as an interchangeable event stream. Observed totals can exceed counters for some champions and fall below for others. Matching totals alone do not prove completeness. The reason for each discrepancy is not established.

For MF, all 123 reference and 150 loss resource drops of at least 25 points have an ability observation in the preceding 0.6 seconds. This is temporal corroboration, not one-to-one matching or proof that every activation/input was recovered. Sparse resource updates, multiple nearby spells, refunds and free casts limit this check. No records are invented to reconcile counters.

## Remaining interpretation limits

Complete spell castability is not claimed. Explicit timers, charges, resources and learned ranks are now available, but control/slot locks and all targeting rules have not been established. Team-vision interpretation retains the limited visual validation described in [COOLDOWNS_AND_VISION.md](COOLDOWNS_AND_VISION.md). Neither a zero timer nor a final counter difference is sufficient for coaching blame.

The synthetic suite contains 84 tests. No private replay records, identifiers, game code, recovered images, checkpoints or credentials are published.
