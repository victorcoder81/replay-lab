# Explicit cooldown updates and team visibility, version 0.6.0

Exact client build `16.21.829.8620`, protocol `20e09df23c66b85e` only. Normal decoding runs offline without an executable or API key.

```sh
python replay_lab.py analyze /path/to/EUW1-1234567890.rofl --experimental-cooldowns --experimental-vision --out ./runs/context
```

## Cooldown reports

Opcode `0x008b` exports spell slot, reported cooldown, reported remaining cooldown, two numeric fields with unverified meaning, and a raw flag. All fields are consumed; unknown meanings remain explicitly named as such. Slots are preserved without assuming that every slot is a champion ability.

These are explicit updates, including changes between casts. In the MF reference replay, a W cast at 151.766 seconds is followed by remaining-timer reports of 9.098 seconds at 152.667 and 3.524 seconds at 156.242. A fixed base-cooldown countdown would miss such reductions.

Each report's timestamp is preserved. The decoder does not project readiness between updates. A positive timer describes that report; a zero timer does not prove a spell can be cast, because charges, mana, control effects, skill availability and intervening changes are not fully decoded. Negative timer values are preserved as unverified, never silently converted into ready. The packet family is not a complete cast log.

| Local replay | Native and standalone matches |
|---|---:|
| Reference A | 2,940 / 2,940 |
| Loss B | 3,228 / 3,228 |
| Win C | 3,174 / 3,174 |

All five scalar values match on all 9,342 records, with complete payload consumption. Scalar maps were separately checked on 1,024 repeated-byte cases, with byte-order probes. Eight synthetic tests cover explicit/default values, all 256 slot values, truncation at every byte, extra suffixes, nonfinite fields, negative-timer uncertainty and exact-build rejection.

## Champion visibility reports

Opcodes `0x0030` and `0x0246` carry a team index and are interpreted as visible and hidden reports respectively. Team index 1 maps to team 100, index 2 to team 200. Both low-level team-byte decoding and semantic interpretation have separate evidence:

- All 1,667 champion reports from loss B and 1,832 from win C match the recovered native team-byte reader.
- In an independent MF win, the human replay viewer confirmed the predicted blue-team fog-of-war sequence: hidden around 2:03, visible around 2:04.5, hidden around 2:06, visible around 2:08. Packet timestamps for the corresponding setters are 122.426, 124.365, 124.899 and 127.204 seconds.
- Across loss B, the reported team consistently corresponds to the opposing team for all ten champion IDs, and the reports mostly alternate. This corroborates the interpretation but is not a substitute for the visual check.

**Interpretation remains experimental and visually checked on one short sequence.** It is not established for every stealth, clone, spectator, death or respawn case. No claim is made to have validated a full fog-of-war grid, wards, true sight, personal line of sight or player attention.

The CLI applies the champion-allocation gate used by the health decoder, checking skill-marker entities and every participant's final death total. It preserves exact entity IDs without generation masking in the visibility stream. NPC reports are outside the CLI's output scope.

Initial state is unknown. `VisibilityState` applies timestamp-ordered explicit setters independently for each exact entity and team. Duplicate reports do not toggle state. No own-team or enemy-team state is invented when no explicit report exists. Consumers must keep evidence provenance and must not turn spectator positions into player knowledge.

Six synthetic tests cover team decoding, unknown initial state, repeated setters, separate teams, exact entity IDs, ordering, malformed input and unsupported profiles.

## Native-reader provenance

Original client SHA-256: `6f8712cf8ff062d1a914796fe0ad057dae86064d4b651e0ff91d0f3885749d1a`. Cooldown reader RVA `0xcb4720`; scalar readers `0xc195a0`, `0xc1c000`, `0xc1abf0`, `0xc18bb0`. Team-byte packet reader `0xd1be80`, scalar wrapper `0xd02740`, byte reader `0xd05020`. Team-index constructor mapping is corroborated by routine `0x636650`.

The bounded offline oracle supplies a synthetic guest reader-context flag required by the team-byte reader. The flag only enables parsing instead of taking a logging failure path. No host game process memory is accessed. ROFL framing supplies the base parameter, so its native inline reader is skipped. Source distribution contains derived transforms, scalar maps and synthetic tests; no original client code, extracted image, emulator checkpoint, private replay, player identifiers or credentials are included.

## Cast completeness

Local research extracts MF cast observations, but counts still fall short of final metadata for some abilities. That gap is explicitly retained. Neither missing cast records nor an elapsed estimated cooldown are evidence that a player had a spell available.
