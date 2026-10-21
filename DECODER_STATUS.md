# Movement and spell decoder status

Research checked on 2026-10-21. Full movement, positions and individual spell casts remain unavailable. Version 0.2.1 adds reproducible executable diagnostics; it does not add those gameplay decoders.

## Observed blocker

The upstream `rofl-parser` static builder failed on the available 16.21 executable with `Could not identify the common packet registration function`. Inspecting that input explains why using its current static discovery method is not viable: there are no visible `PKT_` type names and the sampled `.text` bytes have near-maximal entropy, alongside `.riot0`, `.riot1` and `.riot2` sections. The available 16.20 input shows the same combined signals.

| Input build label | Executable SHA-256 | Code entropy samples (bits/byte) | Visible packet names |
|---|---|---|---:|
| 16.20.824.8524 | `f6fd49d6fb21c6cec23e329ca8a9a7c0809393cb950daf29ca62cf60a08455c6` | 7.997192, 7.997496, 7.997199 | 0 |
| 16.21.829.8620 | `6f8712cf8ff062d1a914796fe0ad057dae86064d4b651e0ff91d0f3885749d1a` | 7.996992, 7.997392, 7.996561 | 0 |

These build labels identify the local acquisition inputs. `doctor` fingerprints bytes but does not independently establish the executable's version or Authenticode validity. Entropy and section names are evidence consistent with packing/encryption, not identification of a cipher. They do not prove that recovery is impossible.

Riot describes encryption of game code and changing network obfuscation in its [technical explanation](https://www.riotgames.com/en/news/riots-approach-anti-cheat). That background supports the assessment; it does not establish the exact protection implementation in these builds.

## Other paths checked

- The local [rofl-parser](https://github.com/shyunku-libraries/rofl-parser) checkout bundles 16.15 and 16.16 profiles. They must not be applied to 16.20/16.21 by changing an opcode or build label.
- Its documented default registry URL, `https://raw.githubusercontent.com/shyunku/rofl-parser/decoder-artifacts/index.json`, returned HTTP 404. The corresponding `shyunku-libraries` URL also returned 404. This is a point-in-time observation, not a claim that no compatible profile exists anywhere.
- [RoflLens](https://github.com/ss26367098/rofllens) documents exact-build 16.14 semantic support. That profile cannot decode the current files.
- [lol-unpackman](https://github.com/MythicManiac/lol-unpackman) explicitly targets League 8.14 with `stub.dll`. Its hardcoded older offsets are not a verified recovery path for these Windows x64 inputs.
- Riot's [Replay API](https://developer.riotgames.com/docs/lol#replay-api) provides playback and rendering control; the documented interface does not supply a replacement stream of champion positions and spell casts.

## Work required before claiming support

1. Recover an exact-build readable decoder implementation, or obtain a compatible decoder artifact whose provenance and executable hash can be checked.
2. Recover the packet registration, deserializer and consumer field semantics for movement and spells. Packet timing coincidence alone is insufficient.
3. Bind the resulting profile to the executable SHA-256 and replay protocol digest.
4. Validate output across independent replays, including movement discontinuities, deaths/respawns and spell variants. Preserve unknown packets and refuse incompatible builds.

No game executable, extracted section, live-process memory or personal replay data is distributed in this repository. The existing transport and empirical death-marker paths remain usable without an executable.
