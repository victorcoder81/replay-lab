import struct
import unittest
from ammo_decoder import load_ammo_profile, decode_ammo


class AmmoTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_ammo_profile('16.21.829.8620', '20e09df23c66b85e')

    def encode(self, values):
        header = 0
        body = bytearray()
        for field in self.profile['fields']:
            selector = next(i for i in range(8) if str(i) not in field['defaults'])
            header |= selector << field['shift']
            value = values[field['offset']]
            inverse = {v: i for i, v in enumerate(field['map'])}
            if field['kind'] == 'varuint32':
                while True:
                    byte = value & 127
                    value >>= 7
                    body.append(inverse[byte | (128 if value else 0)])
                    if not value:
                        break
            elif field['kind'] == 'float32':
                raw = struct.pack('<f', value)
                if field['order'] == 'reverse':
                    raw = raw[::-1]
                body.extend(inverse[b] for b in raw)
            else:
                body.append(inverse[value])
        return header.to_bytes(3, 'little') + body

    def test_available_charge_with_positive_recharge_timer(self):
        data = self.encode({16: 1, 20: 16., 24: 0, 28: 2, 32: 10., 36: 0})
        row = decode_ammo(data, self.profile)
        self.assertEqual(row['reportedCharges'], 1)
        self.assertEqual(row['reportedMaxCharges'], 2)
        self.assertEqual(row['reportedRemainingRechargeSeconds'], 10)
        self.assertEqual(row['spellCastability'], 'unknown')

    def test_unsigned_sentinel_is_not_nan_or_zero(self):
        data = self.encode({16: 0xffffffff, 20: 0., 24: 255, 28: 0xffffffff, 32: -1., 36: 12})
        row = decode_ammo(data, self.profile)
        self.assertIsNone(row['reportedCharges'])
        self.assertIsNone(row['reportedMaxCharges'])
        self.assertEqual(row['rawReportedMaxCharges'], 0xffffffff)
        self.assertEqual(row['spellSlot'], 12)

    def test_each_truncation_and_suffix_refused(self):
        data = self.encode({16: 2, 20: 16., 24: 0, 28: 2, 32: 10., 36: 0})
        for end in range(len(data)):
            with self.assertRaises(ValueError):
                decode_ammo(data[:end], self.profile)
        with self.assertRaises(ValueError):
            decode_ammo(data + b'x', self.profile)

    def test_profile_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):
            load_ammo_profile('16.20.824.8524', '20e09df23c66b85e')
        with self.assertRaises(ValueError):
            decode_ammo(self.encode({16: 1, 20: float('nan'), 24: 0, 28: 2, 32: 10., 36: 0}), self.profile)
