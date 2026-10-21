import struct
import unittest
from cooldown_decoder import load_cooldown_profile, decode_cooldown


class CooldownTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_cooldown_profile('16.21.829.8620', '20e09df23c66b85e')

    def packet(self, values=(12., 0., 7.5, 0.), slot=4):
        # Explicit scalar selectors; slot uses its one-byte transform.
        header = 1 | (5 << 4) | (3 << 7) | (6 << 13) | (2 << 10)
        data = bytearray(header.to_bytes(2, 'little'))
        for name, value in zip(('a', 'b', 'c'), values[:3]):
            spec = self.profile['maps'][name]
            inverse = {v: i for i, v in enumerate(spec['byteMap'])}
            raw = struct.pack('<f', value)
            if spec['order'] == 'reverse':
                raw = raw[::-1]
            data.extend(inverse[b] for b in raw)
        rotated = ((slot >> 6) | (slot << 2)) & 255
        value = (rotated + 0x41) & 255
        data.append(((value >> 1) | (value << 7)) & 255)
        spec = self.profile['maps']['d']
        inverse = {v: i for i, v in enumerate(spec['byteMap'])}
        data.extend(inverse[b] for b in struct.pack('<f', values[3]))
        return bytes(data)

    def test_explicit_values_and_slot(self):
        row = decode_cooldown(self.packet(), self.profile)
        self.assertEqual(row['reportedCooldownSeconds'], 12)
        self.assertEqual(row['reportedRemainingCooldownSeconds'], 7.5)
        self.assertEqual(row['spellSlot'], 4)
        self.assertEqual(row['timerStateAtUpdate'], 'positive')

    def test_defaults(self):
        header = 6 | (6 << 4) | (1 << 7) | (7 << 13) | (5 << 10)
        row = decode_cooldown(header.to_bytes(2, 'little'), self.profile)
        self.assertEqual(row['reportedRemainingCooldownSeconds'], 0)
        self.assertEqual(row['spellSlot'], 0)
        self.assertEqual(row['spellCastability'], 'unknown')

    def test_all_slots_round_trip(self):
        for slot in range(256):
            self.assertEqual(decode_cooldown(self.packet(slot=slot), self.profile)['spellSlot'], slot)

    def test_negative_timer_is_not_ready(self):
        row = decode_cooldown(self.packet((0., 0., -0.5, 0.)), self.profile)
        self.assertEqual(row['timerStateAtUpdate'], 'negative_unverified')
        self.assertEqual(row['spellCastability'], 'unknown')

    def test_every_truncation_refused(self):
        data = self.packet()
        for end in range(len(data)):
            with self.subTest(end=end), self.assertRaises(ValueError):
                decode_cooldown(data[:end], self.profile)

    def test_suffix_refused(self):
        with self.assertRaises(ValueError):
            decode_cooldown(self.packet() + b'x', self.profile)

    def test_nonfinite_refused(self):
        with self.assertRaises(ValueError):
            decode_cooldown(self.packet((float('nan'), 0., 0., 0.)), self.profile)

    def test_profile_gate_and_unknown_fields(self):
        with self.assertRaises(ValueError):
            load_cooldown_profile('16.20.824.8524', '20e09df23c66b85e')
        row = decode_cooldown(self.packet(), self.profile)
        self.assertFalse(row['chargesDecoded'])
        self.assertEqual(row['scope'], 'explicit_update_only_no_projection')


if __name__ == '__main__':
    unittest.main()
