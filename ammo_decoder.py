"""Exact-build spell/item charge reports; no readiness projection."""
import json
import math
from pathlib import Path
import struct
from movement_decoder import read_varuint


def load_ammo_profile(version, protocol):
    profile = json.loads(Path(__file__).with_name('ammo-16.21.json').read_text(encoding='utf8'))
    if (version, protocol) != (profile['build'], profile['protocol']):
        raise ValueError('Ammo profile requires exact build and protocol.')
    for field in profile['fields']:
        if sorted(field['map']) != list(range(256)):
            raise ValueError('Invalid ammo byte map.')
    return profile


def decode_ammo(payload, profile):
    if len(payload) < 3:
        raise ValueError('Missing ammo header.')
    header = int.from_bytes(payload[:3], 'little')
    cursor = 3
    values = {}
    for field in profile['fields']:
        selector = str((header >> field['shift']) & 7)
        if selector in field['defaults']:
            value = field['defaults'][selector]
        elif field['kind'] == 'varuint32':
            value, cursor = read_varuint(payload, cursor, field['map'], 32)
        else:
            size = 4 if field['kind'] == 'float32' else 1
            if cursor + size > len(payload):
                raise ValueError('Truncated ammo field.')
            raw = bytes(field['map'][b] for b in payload[cursor:cursor + size])
            cursor += size
            if size == 4:
                if field['order'] == 'reverse':
                    raw = raw[::-1]
                value = struct.unpack('<f', raw)[0]
                if not math.isfinite(value):
                    raise ValueError('Nonfinite ammo timer.')
            else:
                value = raw[0]
        values[field['offset']] = value
    if cursor != len(payload):
        raise ValueError('Trailing ammo data.')
    return {'spellSlot': values[36],
            'reportedCharges': None if values[16] == 0xffffffff else values[16],
            'rawReportedMaxCharges': values[28],
            'reportedMaxCharges': None if values[28] == 0xffffffff else values[28],
            'reportedRechargeSeconds': values[20],
            'reportedRemainingRechargeSeconds': values[32],
            'unverifiedByte24': values[24], 'scope': 'explicit_charge_update_only',
            'negativeSentinelSemantics': 'unverified_do_not_clear_existing_capacity',
            'spellCastability': 'unknown'}
