# Replay Lab

An offline research tool for League of Legends ROFL v2 files, with experimental death markers, 16.21 movement paths, item-update IDs, gold-balance samples and sparse champion health.

Replay Lab parses the replay container, extracts end-of-game metadata, exports raw record windows and compares packet timestamps with saved Riot Match-v5 events. Its death-marker profiles recover a timestamp and victim entity/identity from replay records without requiring a running game client or an API connection.

**Version 0.3.0 decodes experimental movement paths on exact build 16.21.829.8620, map 11.** These are waypoint updates, including NPCs, rather than continuous position tracks. Spell availability and team visibility remain unverified. Validation covers one movement replay and a small death-marker corpus.

**Version 0.4.0 adds item-update prefixes and current-gold samples at those updates.** It does not reconstruct continuous gold/CS progression or classify all transactions. See [ITEM_DECODING.md](ITEM_DECODING.md) for the exact scope and validation on two replays.

**Version 0.5.0 adds sparse champion health updates on exact build 16.21.829.8620.** All 27,366 state vectors across two replays matched the recovered native reader. See [HEALTH_DECODING.md](HEALTH_DECODING.md) for independent checks and limits.

```sh
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --experimental-health --out ./runs/health
```

Health rows contain only changed/present fields; an absent value is never zero. The tool checks champion allocation against skill markers and all ten final death totals before applying the champion schema. NPC health, shields, continuous health and team-specific vision remain unavailable.

## Capabilities

- Read-only ROFL v2 parsing and Zstandard decompression.
- Exact-build adapters for 17-byte and 18-byte chunk headers.
- End-of-game participant statistics, items, runes and spell-use totals.
- Experimental champion-death timestamps and victim identities.
- Experimental movement entity IDs, speeds and waypoints; no executable or API key needed.
- Experimental item IDs and reported gold balances at item-update timestamps, with unknown packet suffixes explicit.
- Optional independent checks against saved Riot API match/timeline JSON.
- Packet histograms, raw time-window exports and timing-correlation candidates.
- Read-only executable preflight for static decoder-builder blockers.
- Explicit separation of replay-derived records, imported API events and unverified hypotheses.

## Supported builds

| Exact client version | Chunk header | Experimental death marker | Entity-scope marker |
|---|---:|---|---|
| `16.20.824.8524` | 17 bytes | `0x00a6` | `0x032a` |
| `16.21.829.8620` | 18 bytes | `0x00c9` | `0x035c` |

The experimental profiles check the protocol digest as well as the version. Other builds are unsupported. The additional 16.21 chunk-header byte is checked against the observed value `4`; no game-level meaning is assigned to it.

## Install

Requires Python 3.11 or later.

```sh
git clone https://github.com/victorcoder81/replay-lab.git
cd replay-lab
python -m pip install -r requirements.txt
python replay_lab.py capabilities
```

For isolated dependencies, create and activate a Python virtual environment before installation.

## Analyze a replay

```sh
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --experimental-deaths --out ./runs/game
```

The filename above is an example. Supply a real replay from one of the supported builds. Select a fresh output directory for each run; the tool preserves existing results and refuses output paths containing input files.

The experimental death decoder requires no API inputs. It infers victim identity from the observed champion entity allocation and metadata ordering, masks respawn-generation bits 8â€“15, and checks every participant's decoded death count against end-of-game metadata. This is a narrow empirical interpretation; the death packet's payload fields remain undecoded.

### Decode 16.21 movement

```sh
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --experimental-movement --map-id 11 --out ./runs/movement
```

`--map-id 11` explicitly asserts Summoner's Rift when no API match is supplied. With `--match` and `--timeline`, the map is checked from the match instead. Exact version and protocol digest must match the bundled profile. Unsupported payloads cause failure. Both experimental flags can be combined.

Output preserves entity IDs without assigning player identities. Do not apply the death marker's generation-bit masking to these records: NPC IDs can collide under that transformation. Waypoint paths are useful for movement research, but reliable continuous positions, spell interactions and automatic coaching require further work.

### Decode 16.21 item updates and gold samples

```sh
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --experimental-items --out ./runs/items
```

This requires the exact 16.21 build and protocol, with no API inputs or client executable. It exports item IDs, gold balances at update time, raw header flags and an unverified numeric field. It parses a prefix of the packet, leaving suffix bytes uninterpreted. Unsupported known-prefix variants cause failure. Updates include automatic grants and transformations; they must not all be labeled purchases or summed as spending. Entity IDs are preserved without assigning player identities. See [ITEM_DECODING.md](ITEM_DECODING.md).

## Diagnose full-decoder prerequisites

```sh
python replay_lab.py doctor --client-exe "/path/to/League of Legends.exe" --out ./preflight.json
```

This command checks PE file boundaries, fingerprints the executable, samples code-section entropy and counts visible packet type names. It does not launch or unpack the executable. Exit code `2` means that the combined evidence suggests packed/encrypted code that blocks the current static builder; `1` means invalid input or another inspection error. Exit code `0` means inspection completed without that specific finding, **not** that a gameplay decoder is available. Existing output files are preserved.

The available 16.20 and 16.21 binaries both hit this static-builder blocker. Offline recovery subsequently produced the separate bundled 16.21 movement profile. `doctor` still reports the original executable's static characteristics; it is not a check of installed profile support. See [DECODER_STATUS.md](DECODER_STATUS.md).

### Cross-check with saved API data

```sh
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --experimental-deaths --match /path/to/match.json --timeline /path/to/timeline.json --riot-id "Player#TAG" --out ./runs/checked-game
```

The reference JSON must come from the same match. Match ID, game version, participant identities and selected statistics are checked before comparison. Reference events retain `riot_match_v5_timeline` provenance; they are not counted as replay-decoded events.

Add `--window 1709 1711` to export raw game-chunk records between 28:29 and 28:31. Timing-correlation tolerance defaults to 0.15 seconds and can be set with `--tolerance`.

## Output files

| File | Contents |
|---|---|
| `report.md` | Readable results, limits and timing candidates |
| `summary.json` | Replay hash, exact build, record counts and validation status |
| `participants.json` | End-of-game replay metadata |
| `replay-death-markers.jsonl` | Experimental replay-derived death markers, when enabled and checks pass |
| `replay-movement-paths.jsonl` | Experimental replay-derived entity IDs, speeds and waypoint paths, when enabled |
| `replay-item-updates.jsonl` | Partial item-update records and gold-balance samples, when enabled; transaction types remain unknown |
| `packet-histogram.json` | Packet counts and payload sizes |
| `timing-candidates.json` | Unverified packet/event timing correlations |
| `api-reference-events.jsonl` | Imported API reference events, if supplied |
| `raw-window.jsonl` | Optional raw payload bytes in a requested interval |

Timing coincidence is not proof of packet semantics. The correlation report includes a three-second shifted control, but shared events and temporal clustering can still produce misleading associations.

## Validation

```sh
python -m unittest discover -s . -p "test_*.py" -v
```

Forty-three automated tests cover transport, executable preflight, death markers, movement, item prefixes, gold/numeric selectors, malformed data and output preservation. Fixtures contain no personal replay payloads or client code.

The 16.21 movement decoder parsed **31,033 packets into 113,425 paths** on one local replay. An independent API comparison found **140/141** first waypoints within 100 game units at timestamps within 0.25 seconds; median distance was 19.24 units. The outlier crosses a likely respawn boundary. See [VALIDATION.md](VALIDATION.md) for scope and native-oracle checks.

The experimental death profiles were cross-checked on three local replay/API pairs: **197 of 197 victim/timestamp pairs matched**, with a maximum timestamp difference below 1.4 milliseconds. One replay was decoded without API input and checked separately afterward. This is limited empirical validation, not a universal correctness guarantee. See [VALIDATION.md](VALIDATION.md).

Chunk sizes and the final container boundary are validated. The replay's cryptographic signature is not verified. Original replay files are opened read-only.

## Roadmap

- Expand the independent replay corpus and negative cases.
- Recover additional packet fields with build-specific evidence.
- Expand movement validation across independent replays, respawns and discontinuities.
- Recover spell-cast families and consumer semantics.
- Add reproducible profile fixtures that can be shared without personal replay data.

## Attribution

The transport layer vendors a subset of [RoflLens](https://github.com/ss26367098/rofllens), revision `62a475a8f05e7dfa94df5990758be2156c892496`, under its MIT license. Compact inner movement-path parsing is adapted from that project's movement decoder. The upstream license and notices are preserved in `vendor/rofllens/`. The original initializer was replaced to expose only the copied transport modules. Build-specific byte maps were derived independently with a local offline native-routine oracle.

Replay Lab adds exact-build chunk adapters, empirical death profiles, API-reference checks, timing research, reports and tests. Early container/framing research is also acknowledged in the preserved upstream notices.

This project is independent and is not endorsed by Riot Games. League of Legends, Riot Games and associated marks belong to Riot Games, Inc. The repository does not distribute game executables, replay files or extracted client sections.
