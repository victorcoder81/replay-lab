"""Sparse champion health updates for one exact replay protocol.

Only group 32 fields 0 and 1 have established health semantics. Other fields
and the outer packet suffix are deliberately left uninterpreted.
"""
import math
import struct

VERSION = '16.21.829.8620'
PROTOCOL = '20e09df23c66b85e'
OPCODE = 0x1a
MAX_VECTOR_BYTES = 1024 * 1024


def require_profile(version, protocol):
    if (version, protocol) != (VERSION, PROTOCOL):
        raise ValueError('Health decoding requires exact build and protocol.')


def transform_byte(value):
    value ^= 0xfa
    value = ((value & 0x55) << 1) | ((value >> 1) & 0x55)
    return ((value >> 2) | (value << 6)) & 255


BYTE_MAP = bytes(transform_byte(x) for x in range(256))


def decode_vector(payload):
    if len(payload) < 2:
        raise ValueError('Missing state header.')
    if int.from_bytes(payload[:2], 'little') & 512:
        return b'', 2
    cursor = 2
    length = 0
    for shift in range(0, 32, 7):
        if cursor >= len(payload):
            raise ValueError('Truncated state length.')
        value = BYTE_MAP[payload[cursor]]
        cursor += 1
        length |= (value & 127) << shift
        if length > MAX_VECTOR_BYTES:
            raise ValueError('Excessive state length.')
        if not value & 128:
            break
    else:
        raise ValueError('Overlong state length.')
    if cursor + length > len(payload):
        raise ValueError('Truncated state vector.')
    result = bytearray(length)
    for index, value in enumerate(payload[cursor:cursor + length]):
        position = index // 2 if index % 2 == 0 else length - 1 - index // 2
        result[position] = BYTE_MAP[value]
    return bytes(result), cursor + length


def iter_records(data):
    cursor = 0
    while cursor < len(data):
        if cursor + 5 > len(data):
            raise ValueError('Truncated replication record.')
        groups_mask, entity = struct.unpack_from('<BI', data, cursor)
        cursor += 5
        if not groups_mask or groups_mask & 128:
            raise ValueError('Invalid replication group mask.')
        groups = []
        for group in (1, 2, 4, 8, 16, 32, 64):
            if not groups_mask & group:
                continue
            if cursor + 5 > len(data):
                raise ValueError('Truncated replication group.')
            fields, size = struct.unpack_from('<IB', data, cursor)
            cursor += 5
            if cursor + size > len(data):
                raise ValueError('Truncated replication fields.')
            groups.append((group, fields, data[cursor:cursor + size]))
            cursor += size
        yield entity, groups


def health_prefix(mask, data):
    cursor = 0
    result = {}
    for bit, name in enumerate(('currentHealth', 'maxHealth')):
        if not mask & (1 << bit):
            continue
        if cursor >= len(data):
            raise ValueError('Missing health value.')
        if data[cursor] == 255:
            value = 0.0
            cursor += 1
        else:
            if data[cursor] == 254:
                cursor += 1
            if cursor + 4 > len(data):
                raise ValueError('Truncated health float.')
            value = struct.unpack_from('<f', data, cursor)[0]
            cursor += 4
        if not math.isfinite(value) or not 0 <= value < 1000000:
            raise ValueError('Invalid health value.')
        result[name] = value
    return result


def decode_health(payload, champion_entities):
    """Return updates only for exact caller-validated champion IDs.

    NPC groups use different layouts. Entity generation bits are never masked
    here. Unchanged/absent fields are omitted, never converted to zero.
    """
    data, consumed = decode_vector(payload)
    updates = []
    for entity, groups in iter_records(data):
        if entity not in champion_entities:
            continue
        for group, mask, body in groups:
            if group == 32:
                fields = health_prefix(mask, body)
                if fields:
                    updates.append({'entityId': entity, **fields})
    return updates, {'decodedPrefixBytes': consumed,
                     'undecodedSuffixBytes': len(payload) - consumed,
                     'payloadFullyDecoded': False}
