"""Exact-build skill-learning reports; validated against Riot skill-up events."""
import json
from pathlib import Path


def load_skill_profile(version, protocol):
    profile = json.loads(Path(__file__).with_name('skill-16.21.json').read_text(encoding='utf8'))
    if (version, protocol) != (profile['build'], profile['protocol']):
        raise ValueError('Skill profile requires exact build and protocol.')
    if any(sorted(m) != list(range(256)) for m in profile['maps'].values()):
        raise ValueError('Invalid skill byte map.')
    return profile


def decode_skill(payload, profile):
    if len(payload) < 2:
        raise ValueError('Missing skill header.')
    header = int.from_bytes(payload[:2], 'little')
    cursor = 2
    values = {}
    for field, shift, defaults in (
        ('16', 7, {7: 1, 6: 255, 5: 2, 4: 0}),
        ('17', 4, {6: 0, 2: 2, 7: 1, 4: 255}),
        ('19', 1, {5: 2, 4: 255, 6: 1, 7: 0}),
    ):
        selector = (header >> shift) & 7
        if selector in defaults:
            values[field] = defaults[selector]
        else:
            if cursor >= len(payload):
                raise ValueError('Truncated skill field.')
            values[field] = profile['maps'][field][payload[cursor]]
            cursor += 1
    if cursor != len(payload):
        raise ValueError('Trailing skill bytes.')
    return {'spellSlot': values['16'], 'reportedRank': values['19'],
            'unverifiedByte17': values['17'], 'rawFlag18': not bool(header & 1),
            'scope': 'explicit_skill_learning_report'}
