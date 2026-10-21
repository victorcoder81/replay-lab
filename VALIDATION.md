# Validation scope

## Automated tests

24 tests exercise container and framing behavior, malformed inputs, output preservation, reference-data mismatch, empirical entity-generation mapping, death-count verification and executable preflight.

The fixtures are synthetic. They contain no real players, replay payloads or game executable code.

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
