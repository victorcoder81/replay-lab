# Replay Lab

An offline research tool for League of Legends ROFL v2 files, with a limited experimental decoder for champion death markers on two exact game builds.

Replay Lab parses the replay container, extracts end-of-game metadata, exports raw record windows and compares packet timestamps with saved Riot Match-v5 events. Its death-marker profiles recover a timestamp and victim entity/identity from replay records without requiring a running game client or an API connection.

**This is an experimental research prototype. Movement, individual spell casts, positions, cooldowns and health are not decoded.** The death profiles use empirical rules validated on a small local corpus; unfamiliar layouts and inconsistent counts are refused.

## Capabilities

- Read-only ROFL v2 parsing and Zstandard decompression.
- Exact-build adapters for 17-byte and 18-byte chunk headers.
- End-of-game participant statistics, items, runes and spell-use totals.
- Experimental champion-death timestamps and victim identities.
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

The experimental death decoder requires no API inputs. It infers victim identity from the observed champion entity allocation and metadata ordering, masks respawn-generation bits 8–15, and checks every participant's decoded death count against end-of-game metadata. This is a narrow empirical interpretation; the death packet's payload fields remain undecoded.

## Diagnose full-decoder prerequisites

```sh
python replay_lab.py doctor --client-exe "/path/to/League of Legends.exe" --out ./preflight.json
```

This command checks PE file boundaries, fingerprints the executable, samples code-section entropy and counts visible packet type names. It does not launch or unpack the executable. Exit code `2` means that the combined evidence suggests packed/encrypted code that blocks the current static builder; `1` means invalid input or another inspection error. Exit code `0` means inspection completed without that specific finding, **not** that a gameplay decoder is available. Existing output files are preserved.

The available 16.20 and 16.21 binaries both hit this blocker. Movement and spell support still needs exact-build decoder recovery and validation. See [DECODER_STATUS.md](DECODER_STATUS.md) for measurements and the remaining work. `doctor` is a diagnostic, not a movement/spell decoder.

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
| `packet-histogram.json` | Packet counts and payload sizes |
| `timing-candidates.json` | Unverified packet/event timing correlations |
| `api-reference-events.jsonl` | Imported API reference events, if supplied |
| `raw-window.jsonl` | Optional raw payload bytes in a requested interval |

Timing coincidence is not proof of packet semantics. The correlation report includes a three-second shifted control, but shared events and temporal clustering can still produce misleading associations.

## Validation

```sh
python -m unittest discover -s . -p "test_*.py" -v
```

Twenty-four automated tests cover both layouts, compression, invalid and truncated data, unknown versions, input/output preservation, reference mismatch, respawn generation, death-count checks and executable preflight.

The experimental death profiles were cross-checked on three local replay/API pairs: **197 of 197 victim/timestamp pairs matched**, with a maximum timestamp difference below 1.4 milliseconds. One replay was decoded without API input and checked separately afterward. This is limited empirical validation, not a universal correctness guarantee. See [VALIDATION.md](VALIDATION.md).

Chunk sizes and the final container boundary are validated. The replay's cryptographic signature is not verified. Original replay files are opened read-only.

## Roadmap

- Expand the independent replay corpus and negative cases.
- Recover additional packet fields with build-specific evidence.
- Investigate movement and spell-cast families.
- Add reproducible profile fixtures that can be shared without personal replay data.

## Attribution

The transport layer vendors a subset of [RoflLens](https://github.com/ss26367098/rofllens), revision `62a475a8f05e7dfa94df5990758be2156c892496`, under its MIT license. The upstream license and notices are preserved in `vendor/rofllens/`. The original initializer was replaced to expose only the copied transport modules.

Replay Lab adds exact-build chunk adapters, empirical death profiles, API-reference checks, timing research, reports and tests. Early container/framing research is also acknowledged in the preserved upstream notices.

This project is independent and is not endorsed by Riot Games. League of Legends, Riot Games and associated marks belong to Riot Games, Inc. The repository does not distribute game executables, replay files or extracted client sections.
