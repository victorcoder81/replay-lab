# Sparse champion health, version 0.5.0

Exact build `16.21.829.8620`, protocol `20e09df23c66b85e`, opcode `0x001a`. No client executable, API connection or emulation dependency is needed to run this decoder.

## Scope

The outer state vector is decoded and structurally parsed into entity/group records. For caller-validated champion entities, group 32 field bits 0 and 1 are current health and maximum health. NPC groups use different schemas and are not interpreted. Version 0.7.0 additionally decodes universal shields and primary resources through a separate state-prefix decoder; see [RESOURCE_AND_SPELL_STATE.md](RESOURCE_AND_SPELL_STATE.md). Other shield fields and later group fields remain unverified. Outer packet suffix bytes remain explicitly undecoded.

Each JSONL row reports a replay timestamp, exact entity ID, and only the health fields present in that record. Missing fields mean unchanged or unknown, never zero. Preserve each field's own last-observed timestamp when carrying state forward. The time since its last update is not proof that a field changed in the meantime. Never interpolate these into exact continuous HP, or infer that a player/team could see an entity because the spectator replay contains it.

The CLI first validates the empirical champion allocation using skill-marker entities and all ten metadata death totals. Normalization is confined to that prepass; health record IDs must exactly match the resulting set. No participant names are assigned in the health stream. Unrecognized allocation patterns fail closed.

## Evidence

Original client SHA-256: `6f8712cf8ff062d1a914796fe0ad057dae86064d4b651e0ff91d0f3885749d1a`.

Offline reader evidence: inline constructor RVAs `0xc9a09a` through `0xc9a1c2`, packet reader `0xcb8220`, vector reader `0xcab640`. ROFL framing already supplies the base entity parameter. This repository contains independently expressed transforms and synthetic tests, no extracted client code or replay samples.

| Local replay | State packets/native vector matches | Champion health updates |
|---|---:|---:|
| Reference A | 12,308 / 12,308 | 19,506 |
| Loss B | 15,058 / 15,058 | 24,237 |

All decoded vectors parse completely as replication records, with no champion health-prefix errors. This validates the vector transport and observed champion prefix; it does not establish semantics for other fields.

Against 240 champion-minute Riot Match-v5 snapshots from reference A, all 240 maximum-health comparisons and 226 current-health comparisons differ by less than one point. Median current-health absolute difference is 0.43530 HP; maximum is 23.1313 HP. Comparisons use the last preceding replay sample, so timestamps are not identical; mismatches are retained rather than smoothed away. The reference's 43 death markers also independently match API victims/timestamps.

## Spell and vision research

A local native-reader probe recovers spell slot/name hash, mana cost, cast time and reported cooldown from another family. Its observation totals are not established to be equivalent to end-of-game counters. Version 0.7.0 adds an explicit evidence audit and corrects a previously hypothesized rank field. Reported cooldown is not established remaining cooldown or proof of readiness. Reset/charge handling, cast variants, resources and control effects need additional validation. Version 0.6.0 adds experimental team visibility and explicit cooldown reports; see [COOLDOWNS_AND_VISION.md](COOLDOWNS_AND_VISION.md). Complete spell castability remains unresolved. No coaching conclusion should assume an unseen enemy was known to the player.
