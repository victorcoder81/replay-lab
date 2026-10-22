# Gameplay decoder status

Version **0.7.0** adds standalone primary-resource, universal-shield, skill-learning and charge reports, plus an optional bounded emulation adapter for cast observations using the exact locally recovered image. An unexplained final-counter difference is no longer labeled as a proven missing cast. A previously hypothesized rank field is kept raw; verified ranks come from skill-up records. See [RESOURCE_AND_SPELL_STATE.md](RESOURCE_AND_SPELL_STATE.md).

Version **0.6.0** adds explicit cooldown timer reports and experimental team-specific champion visibility. See [COOLDOWNS_AND_VISION.md](COOLDOWNS_AND_VISION.md). The team-byte format matches native output on 3,499 champion reports, and one independent visual sequence confirms the visible/hidden interpretation. Complete spell castability is still unknown; zero timers are not treated as proof of availability.

Version **0.5.0** adds standalone sparse champion health. See [HEALTH_DECODING.md](HEALTH_DECODING.md). Spell-cast fields are recovered in local research, but their coverage is incomplete; no complete spell-availability decoder is included. Experimental visibility reports were added in version 0.6.0.

Version **0.4.0** also adds standalone item-update prefixes and gold-balance samples at item-update times. On two 16.21 replays, all 517 item IDs, gold balances and adjacent numeric fields matched the recovered native reader. This is partial payload decoding, not a complete purchase or economy timeline. See [ITEM_DECODING.md](ITEM_DECODING.md).

Research checked on 2026-10-22. Version **0.3.0** adds an experimental, standalone movement waypoint decoder for exact build **16.21.829.8620**, protocol **20e09df23c66b85e**, map **11**, opcode **0x0291**. Normal decoding requires neither a game executable nor an API connection.

## Working output

The decoder recovers movement entity IDs, speeds and waypoint paths, including NPCs. On one local replay it parsed **31,033 packets into 113,425 paths**, matching every output row from a recovered native deserializer. Independent Riot timeline checks found **140/141** nearby first waypoints within 100 units, with median distance 19.24 units. The remaining comparison crosses a likely respawn boundary. See [VALIDATION.md](VALIDATION.md).

These are waypoint updates, not complete continuous positions. The output preserves entity IDs without assigning champion identities. Do not use the death marker's generation-bit masking for movement: NPC IDs can collide under it. Movement support for 16.20, standalone spell casts and complete spell castability remain unavailable. Explicit timer reports and experimental team visibility are available in version 0.6.0.

## Recovery evidence

The original 16.21 executable's static builder failed to identify packet registration. Its code bytes had near-maximal sampled entropy and no visible `PKT_` names. Bounded offline loader emulation recovered readable code/data sufficiently to identify the packet factory and movement routine. No live game process was attached or launched.

| Item | 16.21 evidence |
|---|---|
| Original executable SHA-256 | `6f8712cf8ff062d1a914796fe0ad057dae86064d4b651e0ff91d0f3885749d1a` |
| Packet factory RVA | `0xc99740` |
| Constructor RVA | `0xc6aa00` |
| Deserializer RVA | `0xdf4360` |
| Base inline parameter reader skipped for ROFL framing | `0xffbea0` |
| Byte-vector reader RVA | `0xd67090` |

Synthetic Windows API responses and bounded guest memory were used. Instrumentation callbacks and queued worker threads were not executed, so this is not a full reproduction of the live loader. Scalar/vector oracle checks and full-replay comparison validate the recovered movement path independently of those unimplemented branches. The bundled profile contains derived byte transforms and provenance addresses, not client code or extracted sections.

`doctor` continues to inspect the original executable's static characteristics. A blocker reported there concerns the old static discovery route; it does not disable the bundled movement profile. Entropy alone does not identify a cipher or prove recovery impossible.

## Remaining work

1. Validate movement on additional independent replays and entity lifecycle cases.
2. Establish safe participant identity tracking across allocation changes and clones.
3. Validate path interpolation around stops, dashes, teleports, deaths and respawns before claiming continuous positions.
4. Extend the optional cast reader to standalone decoding and establish remaining consumer semantics, cast variants and targets.
5. Derive separate profiles for other builds and maps; never relabel an older profile.

The compact inner path format is adapted from [RoflLens](https://github.com/ss26367098/rofllens), with MIT license/notices preserved. Factory-discovery research also consulted [rofl-parser](https://github.com/shyunku-libraries/rofl-parser). Riot's [Replay API](https://developer.riotgames.com/docs/lol#replay-api) supplies playback/render controls, not a replacement position/spell event stream.

No game executable, extracted section, emulator checkpoint or personal replay data is distributed in this repository.
