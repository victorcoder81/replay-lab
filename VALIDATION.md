# Validation scope

## Automated tests

50 tests exercise container and framing behavior, malformed inputs, output preservation, reference-data mismatch, empirical entity-generation mapping, death-count verification, executable preflight, movement, item-prefix and sparse-health decoding.

The fixtures are synthetic. They contain no real players, replay payloads or game executable code.

Nine item-prefix tests cover item and gold/numeric selectors, explicit partial status, truncation, overflow, scope, unsupported variants, nonfinite gold and unvalidated suffix bytes. Native/reference validation of the new fields is documented in [ITEM_DECODING.md](ITEM_DECODING.md).

Seven executable-preflight tests cover combined packing signals, entropy-only and packet-name counterexamples, low-entropy data, malformed PE boundaries, overlapping section ranges, exclusive report creation and the blocked status code. They do not validate an unpacker or gameplay decoder.

## Local replay checks

| Case | Exact build | Recovered death markers | API victim/timestamp matches |
|---|---|---:|---:|
| A | 16.20.824.8524 | 78 | 78 |
| B | 16.21.829.8620 | 43 | 43 |
| C | 16.20.824.8524 | 76 | 76 |

All 197 recovered victim/timestamp pairs agreed with the corresponding Riot Match-v5 timeline events. Maximum observed timestamp errors were approximately 1.381, 1.247 and 1.266 milliseconds, respectively.

Case C was decoded using the replay file alone. Its resulting death log was compared with the API timeline in a separate step. The decoder's core event outputs are a replay timestamp and entity parameter; API reference events are never substituted for decoded output.

These checks establish behavior on the tested files. They do not establish universal correctness for every replay, mode, champion, clone behavior or entity-allocation pattern. Raw replay data and participant identifiers from the local corpus are not distributed with the source.

## Empirical interpretation

The profiles identify a per-victim marker associated with champion deaths. Its header timestamp and entity parameter are used; the five-byte payload is not interpreted. Entity identity is inferred using a contiguous champion allocation, normalization of generation bits 8–15, and metadata participant order. All ten participants' final death counts must match.

When API references are supplied, metadata order must also agree with API participant IDs, and every recovered marker must match a reference victim/timestamp within the configured tolerance.

Unexpected builds, protocol digests, packet shapes, allocation patterns or counts cause failure rather than silently applying an older mapping. The profiles remain experimental because their internal game-protocol semantics have not been fully established.

## Movement, version 0.3.0

The exact 16.21.829.8620 client input has SHA-256 `6f8712cf8ff062d1a914796fe0ad057dae86064d4b651e0ff91d0f3885749d1a`; the replay protocol digest is `20e09df23c66b85e`. Only map 11 and movement opcode `0x0291` are supported.

Recovery used bounded offline x64 emulation of the local loader, followed by native constructor/deserializer calls in emulated memory. Synthetic Windows API responses were used; instrumentation callbacks and queued worker threads were not executed. This is not a complete reproduction of the live loader. No live game process was attached or launched. Replay framing already carries the base entity parameter, so its native inline reader was skipped in the oracle.

The resulting standalone byte transforms were checked against the recovered scalar routines with 1,024 byte cases. Vector checks covered lengths 0, 1, 2, 3, 255, 256 and 257, including all byte values and odd/even ordering. Synthetic automated tests exercise every header selector combination, those vector lengths, signed coordinates, delta wrapping, multiple records, integer overflow, truncation, trailing bytes and scope rejection.

On one full local replay:

- All **31,033** opcode packets were accepted by both the native oracle and standalone decoder, consuming every payload exactly.
- The decoded byte vector matched exactly for **every packet**. Both pipelines produced **113,425** paths using a common inner path parser; row agreement alone is not independent validation of that parser's semantics.
- All **43** existing death markers still matched API victims/timestamps in a combined CLI run.
- Independent API position checks used exact initial champion IDs and metadata participant order, with a nearest path update within **0.25 seconds**. There were **141** comparisons: median first-waypoint distance **19.24 units**, **140/141 within 100 units**.
- The maximum distance was **12,543.89 units**. That snapshot had zero health and retained the previous death location; a replay update **0.2003 seconds later** was at the team's base. This is consistent with a respawn boundary, not proof of a continuous-position reconstruction. The outlier remains included.

The shipped decoder preserves entity IDs and does **not** assign participant identities. The validation's exact initial-ID rule is an empirical comparison for this file. Generation-bit masking is unsafe for movement records because NPC IDs can collide under it.

Paths include NPCs and describe waypoint updates, not a complete continuous position trace. Map offsets and compact path structure were adapted from RoflLens. Signed byte deltas follow the separately inspected rofl-parser implementation, correcting a difference in the RoflLens helper. The count uses the low byte: the corpus also contains 593 records with high flags `0x0200`, which must not be treated as part of the waypoint count. Raw `recordFlags` are preserved; their additional semantics remain unknown. Native-oracle agreement establishes byte-level agreement with the recovered routine; independent API checks provide limited semantic evidence for first waypoints. Later waypoint semantics have not been independently checked against client playback. Additional replay files, discontinuities, modes and entity lifecycle cases remain unvalidated. Spell casts, health and cooldowns are not decoded.

## Health, version 0.5.0

All 27,366 native state vectors across two full replays match the standalone transform, with no structural parsing errors. Seven synthetic tests cover sparse updates, exact entity filtering, zero/escaped floats, NPC schema exclusion, unknown groups and suffixes, malformed records, nonfinite/range checks, excessive vectors and profile rejection. Independent Riot snapshot checks and timestamp caveats are documented in [HEALTH_DECODING.md](HEALTH_DECODING.md).
