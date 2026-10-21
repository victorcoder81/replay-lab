"""Experimental 16.21 movement paths; no client executable required.

Compact path parsing is adapted from RoflLens (MIT, vendor/rofllens/LICENSE).
Byte transforms were independently derived with an offline native routine oracle.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import struct

PROFILE_PATH = Path(__file__).with_name('movement-16.21.json')
MAX_VECTOR_BYTES = 1024 * 1024

def load_profile(version, protocol, map_id=11):
    profile = json.loads(PROFILE_PATH.read_text(encoding='utf8'))
    if (version, protocol, map_id) != (profile['clientVersion'], profile['protocolDigest'], profile['mapId']):
        raise ValueError('Movement profile requires exact build, protocol and map 11.')
    for key in ('prefix32ByteMap', 'prefix16ByteMap', 'vectorByteMap'):
        if sorted(profile[key]) != list(range(256)):
            raise ValueError('Invalid movement byte map.')
    return profile

def read_varuint(payload, cursor, table, bits):
    value = 0
    for shift in range(0, bits, 7):
        if cursor >= len(payload):
            raise ValueError('Truncated movement integer.')
        byte = table[payload[cursor]]; cursor += 1
        value |= (byte & 127) << shift
        if value >= 1 << bits:
            raise ValueError('Movement integer overflow.')
        if not byte & 128:
            return value, cursor
    raise ValueError('Overlong movement integer.')

def decode_vector(payload, profile):
    if not payload:
        raise ValueError('Missing movement header.')
    header = payload[0]; cursor = 1
    if header & 7 not in profile['prefix32DefaultSelectors']:
        _, cursor = read_varuint(payload, cursor, profile['prefix32ByteMap'], 32)
    if (header >> 4) & 7 not in profile['prefix16DefaultSelectors']:
        _, cursor = read_varuint(payload, cursor, profile['prefix16ByteMap'], 16)
    size = 0
    if header & 8:
        size, cursor = read_varuint(payload, cursor, profile['vectorByteMap'], 32)
    if size > MAX_VECTOR_BYTES or len(payload) - cursor != size:
        raise ValueError('Movement vector size or trailing bytes mismatch.')
    result = bytearray(size)
    table = profile['vectorByteMap']
    for index, raw in enumerate(payload[cursor:]):
        destination = index // 2 if index % 2 == 0 else size - 1 - index // 2
        result[destination] = table[raw]
    return bytes(result)

def parse_paths(payload):
    """Return entity IDs, speeds and waypoint lists; never assign player identity."""
    paths = []; cursor = 0
    def coordinate(previous, delta):
        nonlocal cursor
        size = 1 if delta else 2
        if cursor + size > len(payload):
            raise ValueError('Truncated movement coordinate.')
        value = (previous + struct.unpack_from('<b', payload, cursor)[0]) & 65535 if delta else struct.unpack_from('<H', payload, cursor)[0]
        cursor += size
        return value
    while cursor < len(payload):
        if len(payload) - cursor < 10:
            raise ValueError('Truncated movement record.')
        flags, entity, speed = struct.unpack_from('<HIf', payload, cursor); cursor += 10
        count = (flags & 255) >> 1
        if not 1 <= count <= 64 or not math.isfinite(speed) or not 0 <= speed <= 5000:
            raise ValueError('Invalid movement count or speed.')
        cursor += flags & 1
        bitmap_size = ((count - 2) >> 2) + 1 if count > 1 else 0
        if cursor + bitmap_size > len(payload):
            raise ValueError('Truncated movement bitmap.')
        bitmap = payload[cursor:cursor + bitmap_size]; cursor += bitmap_size
        x = y = 0; waypoints = []
        for index in range(count):
            bit = 2 * (index - 1)
            dx = bool(bitmap[bit // 8] & (1 << (bit % 8))) if index else False
            dy = bool(bitmap[(bit + 1) // 8] & (1 << ((bit + 1) % 8))) if index else False
            x = coordinate(x, dx); y = coordinate(y, dy)
            sx = x - 65536 if x & 32768 else x
            sy = y - 65536 if y & 32768 else y
            waypoints.append({'x': float(sx * 2 + 7358), 'y': float(sy * 2 + 7412)})
        paths.append({'entityId': entity, 'speed': speed, 'waypoints': waypoints, 'recordFlags': flags})
    return paths

def decode_movement(payload, profile):
    return parse_paths(decode_vector(payload, profile))
