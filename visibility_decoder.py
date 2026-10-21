"""Experimental team visibility reports for exact 16.21 replay framing.

The opcode interpretation has one human-checked visual sequence. This is
object visibility to a team, not ward locations, true sight, camera attention
or proof that a particular player noticed an enemy.
"""
VERSION = '16.21.829.8620'
PROTOCOL = '20e09df23c66b85e'
OPCODES = {0x30: 'visible', 0x246: 'hidden'}


def require_visibility_profile(version, protocol):
    if (version, protocol) != (VERSION, PROTOCOL):
        raise ValueError('Visibility decoding requires exact build and protocol.')


def decode_visibility(payload, opcode):
    if opcode not in OPCODES:
        raise ValueError('Unsupported visibility opcode.')
    if not payload:
        raise ValueError('Missing visibility header.')
    # The omitted default is intentionally unsupported until independently
    # validated. Both full-replay corpora use the explicit team-byte form.
    if payload[0] & 1:
        raise ValueError('Default visibility team is unsupported.')
    if len(payload) != 2:
        raise ValueError('Visibility report must contain exactly one team byte.')
    value = (payload[1] - 0x16) & 255
    value = ((value >> 2) | (value << 6)) & 255
    team_index = ((value & 0x55) << 1) | ((value >> 1) & 0x55)
    if team_index not in (1, 2):
        raise ValueError('Unsupported team index in visibility report.')
    return {'teamIndex': team_index, 'teamId': team_index * 100,
            'reportedVisibility': OPCODES[opcode], 'rawHeader': payload[0],
            'interpretationValidation': 'limited_human_visual_sequence',
            'personalLineOfSight': 'unknown', 'playerAttention': 'unknown'}


class VisibilityState:
    """Apply ordered, explicit setters; repeated reports never toggle state."""
    def __init__(self):
        self.states = {}
        self.last_timestamp = float('-inf')

    def apply(self, timestamp, entity, report):
        if timestamp < self.last_timestamp:
            raise ValueError('Visibility state requires timestamp-ordered reports.')
        self.last_timestamp = timestamp
        key = (entity, report['teamId'])
        previous = self.states.get(key)
        changed = previous is None or previous['reportedVisibility'] != report['reportedVisibility']
        self.states[key] = {'reportedVisibility': report['reportedVisibility'],
                            'observedAt': timestamp}
        return changed

    def get(self, entity, team_id):
        return self.states.get((entity, team_id), {'reportedVisibility': 'unknown', 'observedAt': None}).copy()
