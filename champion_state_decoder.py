"""Sparse champion resources and universal shield from a validated prefix.

Unknown later fields are never traversed using an older build's schema.
"""
import math
import struct
from health_decoder import require_profile, decode_vector, iter_records

NAMES = {0: 'currentHealth', 1: 'maxHealth', 3: 'allDamageShield',
         15: 'primaryResource', 16: 'maxPrimaryResource'}


def decode_state_prefix(mask, data):
    cursor = 0
    result = {}
    requested = [bit for bit in NAMES if mask & (1 << bit)]
    if not requested:
        return result
    last_bit = max(requested)
    for bit in range(last_bit + 1):
        if not mask & (1 << bit):
            continue
        if cursor >= len(data):
            raise ValueError('Missing champion state field.')
        if bit == 10:
            if data[cursor] == 255:
                cursor += 1
                continue
            value = 0
            for shift in range(0, 35, 7):
                if cursor >= len(data):
                    raise ValueError('Truncated state varuint.')
                byte = data[cursor]
                cursor += 1
                value |= (byte & 127) << shift
                if value > 0xffffffff:
                    raise ValueError('State varuint overflow.')
                if not byte & 128:
                    break
            else:
                raise ValueError('Overlong state varuint.')
            continue
        if data[cursor] == 255:
            value = 0.0
            cursor += 1
        else:
            if data[cursor] == 254:
                cursor += 1
            if cursor + 4 > len(data):
                raise ValueError('Truncated champion state float.')
            value = struct.unpack_from('<f', data, cursor)[0]
            cursor += 4
            if not math.isfinite(value):
                raise ValueError('Nonfinite champion state float.')
        if bit in NAMES:
            if not 0 <= value < 1000000:
                raise ValueError('Champion state value out of range.')
            result[NAMES[bit]] = value
    # Bits 17..31 have not been established for this build. Their declared
    # group boundary remains authoritative, but their contents are not parsed.
    if not mask >> (last_bit + 1) and cursor != len(data):
        raise ValueError('Unexpected champion prefix suffix.')
    return result


def decode_champion_state(payload, champion_entities):
    data, consumed = decode_vector(payload)
    rows = []
    for entity, groups in iter_records(data):
        if entity not in champion_entities:
            continue
        for group, mask, body in groups:
            if group == 32:
                fields = decode_state_prefix(mask, body)
                if fields:
                    rows.append({'entityId': entity, **fields})
    return rows, {'decodedOuterPrefixBytes': consumed,
                  'undecodedOuterSuffixBytes': len(payload) - consumed,
                  'schemaScope': 'selected_champion_group_32_prefix_fields_through_bit_16',
                  'payloadFullyDecoded': False}
