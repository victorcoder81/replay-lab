import math
from pathlib import Path
import struct
import tempfile
import unittest
from champion_state_decoder import decode_state_prefix, decode_champion_state
from skill_decoder import load_skill_profile, decode_skill
from native_cast_decoder import NativeCastDecoder, read_validated_image
from test_health_decoder import packet, record


class ChampionStateTests(unittest.TestCase):
    def test_sparse_resource_and_shield(self):
        values = decode_state_prefix((1 << 3) | (1 << 15), struct.pack('<ff', 200, 75))
        self.assertEqual(values, {'allDamageShield': 200, 'primaryResource': 75})
        self.assertNotIn('maxPrimaryResource', values)

    def test_varuint_before_resource(self):
        values = decode_state_prefix((1 << 10) | (1 << 15), b'\xac\x02' + struct.pack('<f', 80))
        self.assertEqual(values, {'primaryResource': 80})

    def test_unknown_later_schema_is_not_guessed(self):
        values = decode_state_prefix((1 << 15) | (1 << 24), struct.pack('<f', 50) + b'unknown')
        self.assertEqual(values, {'primaryResource': 50})
        with self.assertRaises(ValueError):
            decode_state_prefix(1 << 15, struct.pack('<f', 50) + b'extra')

    def test_exact_champion_filter(self):
        data = record(456, 1 << 15, b'bad') + record(123, 1 << 15, struct.pack('<f', 50))
        values, scope = decode_champion_state(packet(data), {123})
        self.assertEqual(values, [{'entityId': 123, 'primaryResource': 50}])
        self.assertFalse(scope['payloadFullyDecoded'])

    def test_escaped_and_zero_resources(self):
        values = decode_state_prefix((1 << 15) | (1 << 16), b'\xff\xfe' + struct.pack('<f', 300))
        self.assertEqual(values, {'primaryResource': 0, 'maxPrimaryResource': 300})

    def test_bad_scalars_and_varuint(self):
        for mask, data in [((1 << 10) | (1 << 15), b'\xff\x00'), ((1 << 10) | (1 << 15), b'\x80' * 5),
                           ((1 << 10) | (1 << 15), b'\xff\xff\xff\xff\x7f'),
                           (1 << 15, b'\xfe\x00'),
                           (1 << 15, struct.pack('<f', math.nan)),
                           (1 << 15, struct.pack('<f', -1))]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode_state_prefix(mask, data)


class SkillTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_skill_profile('16.21.829.8620', '20e09df23c66b85e')

    def explicit(self, slot, rank):
        header = (6 << 4) | (2 << 1)
        maps = self.profile['maps']
        return header.to_bytes(2, 'little') + bytes([maps['16'].index(slot), maps['19'].index(rank)])

    def test_slots_and_ranks(self):
        for slot in range(4):
            for rank in range(1, 6):
                values = decode_skill(self.explicit(slot, rank), self.profile)
                self.assertEqual((values['spellSlot'], values['reportedRank']), (slot, rank))

    def test_default_slot_zero_and_rank_one(self):
        header = (4 << 7) | (6 << 4) | (6 << 1)
        values = decode_skill(header.to_bytes(2, 'little'), self.profile)
        self.assertEqual((values['spellSlot'], values['reportedRank']), (0, 1))

    def test_truncation_suffix_and_profile(self):
        data = self.explicit(3, 2)
        for end in range(len(data)):
            with self.assertRaises(ValueError):
                decode_skill(data[:end], self.profile)
        with self.assertRaises(ValueError):
            decode_skill(data + b'x', self.profile)
        with self.assertRaises(ValueError):
            load_skill_profile('16.20.824.8524', '20e09df23c66b85e')


class NativeReaderGuards(unittest.TestCase):
    def test_wrong_build_rejected_before_file_read(self):
        with self.assertRaises(ValueError):
            read_validated_image('does-not-exist', 'different', 'different')

    def test_original_or_unrecognized_image_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'synthetic.exe'
            path.write_bytes(b'MZ' + bytes(128))
            with self.assertRaises(ValueError):
                read_validated_image(path, '16.21.829.8620', '20e09df23c66b85e')

    def test_payload_limits_precede_emulation(self):
        decoder = NativeCastDecoder.__new__(NativeCastDecoder)
        for payload in (b'', bytes(65537)):
            with self.assertRaises(ValueError):
                decoder.decode(payload, 123)


if __name__ == '__main__':
    unittest.main()
