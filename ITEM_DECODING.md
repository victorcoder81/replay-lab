# Item updates and gold samples — version 0.4.0

The experimental `--experimental-items` option supports exact build `16.21.829.8620`, protocol `20e09df23c66b85e`, opcode `0x01f6`. It uses derived byte maps and ordinary Python, with no game client, executable, API key or emulator required at runtime. It has been checked on two Summoner's Rift replays; other modes are unvalidated.

## Output scope

Each `ITEM_UPDATE_PREFIX` record contains a replay timestamp, raw entity ID, item ID, reported current gold balance at that update, two raw header flags, an unverified adjacent float and prefix/suffix byte counts. `payloadFullyDecoded` is always false and `transactionType` is always `unknown`.

These are item updates, including purchases, automatic grants, quest transformations and other changes. Gold samples are current balances at item-update timestamps, not total gold earned or continuous gold progression. A negative gold sentinel is preserved rather than interpreted as a valid spendable balance. CS, purchases in other packet families, sales, undo and objectives are not reconstructed.

The known prefix reader checks bounds and refuses unsupported string/default-structure variants. It does not validate uninterpreted suffix bytes. It does not assign participant identity or apply generation-bit masking. Do not derive a complete inventory or spending ledger by summing these updates.

## Recovery provenance

Original client SHA-256: `6f8712cf8ff062d1a914796fe0ad057dae86064d4b651e0ff91d0f3885749d1a`.

| Routine | RVA |
|---|---|
| Packet constructor | `0xc34b50` |
| Packet deserializer | `0xd89cb0` |
| Nested item deserializer | `0xdf4750` |
| Raw item-ID reader | `0xd45a00` |
| Raw gold reader | `0xd49d50` |
| Raw adjacent-float reader | `0xd497d0` |

The derived 256-entry item varuint map was exhaustively checked against the raw native primitive, including continuation bits. Each float byte map was checked on all 256 byte values and an unequal-byte case to establish byte order. Full native packet runs used the same bounded offline emulator and ROFL base-parameter handling described in [VALIDATION.md](VALIDATION.md); no live game process was accessed. Extracted client code/data and emulator checkpoints remain private and are not runtime dependencies.

## Two-replay checks

| Case | Native packets fully consumed | Standalone item ID, gold and adjacent-float fields agreeing with native output |
|---|---:|---:|
| A: existing reference replay | 261 | 261 |
| B: independent newer replay | 256 | 256 |

All **517** records agreed on all three recovered fields. The native reader consumes the full payload; the standalone reader intentionally decodes only the prefix. These checks do not independently establish the meaning of the suffix or all header flags.

Saved Riot Match-v5 data for case A supplied additional evidence:

- Header bit 5 was set on **168** updates. All matched a purchase item/timestamp within **10 milliseconds**, with no unmatched flagged records. There were **170** API purchase events: two control-ward purchases occurred in another packet family (`0x0323`) and are not recovered here. Two initial support-item API events used participant ID zero and were matched without participant identity; the remaining events used an empirical entity mapping checked against the reference participant IDs. This is a promising classification flag, not established universal transaction semantics.
- **Ten** starting gold balances matched API snapshots exactly.
- **Five** later API snapshots had a preceding replay gold sample within two seconds. Differences ranged from approximately **2.45 to 4.08 gold**, with the replay sample lower in each case. This is consistent with gold gained during the time gap; no passive-income model or interpolation is applied.
- Riot's public patch-specific [Data Dragon item definitions](https://ddragon.leagueoflegends.com/cdn/16.21.1/data/en_US/item.json) identified every recovered item ID. The adjacent float equaled the definition's total gold value on **491/517** records. The **26 exceptions** included recall/quest items, elixirs and some control-ward updates. The field is therefore left unverified and must not be treated as purchase price or spent gold.

All automated fixtures are synthetic. No personal identifiers, actual replay payloads, client sections or API credentials are distributed with the source.

## Remaining economy work

1. Recover inventory slots, stack changes, removals, sales and undo.
2. Establish transaction flags and entity identity across lifecycle variants.
3. Recover periodic/stat replication for total gold, CS and other economy fields.
4. Decode objectives and attribution rather than inferring them from timestamp correlations.
5. Expand independent replay and mode coverage.
