import struct
import unittest
from health_decoder import BYTE_MAP, decode_health, decode_vector, health_prefix, require_profile


def packet(data):
    inverse = {value: index for index, value in enumerate(BYTE_MAP)}
    length = len(data)
    prefix = bytearray(b'\0\0')
    while True:
        value = length & 127
        length >>= 7
        prefix.append(inverse[value | (128 if length else 0)])
        if not length:
            break
    for index in range(len(data)):
        position = index // 2 if index % 2 == 0 else len(data) - 1 - index // 2
        prefix.append(inverse[data[position]])
    return bytes(prefix)


def record(entity, mask, body):
    return struct.pack('<BIIB', 32, entity, mask, len(body)) + body


class HealthTests(unittest.TestCase):
    def test_sparse_update_does_not_zero_missing_health(self):
        rows, scope = decode_health(packet(record(123, 2, struct.pack('<f', 2000))), {123})
        self.assertEqual(rows, [{'entityId': 123, 'maxHealth': 2000}])
        self.assertFalse(scope['payloadFullyDecoded'])

    def test_zero_and_escaped_float(self):
        self.assertEqual(health_prefix(3, b'\xff\xfe' + struct.pack('<f', 2048)),
                         {'currentHealth': 0, 'maxHealth': 2048})

    def test_npc_schema_is_not_applied(self):
        data = record(456, 3, b'\x01') + record(123, 1, struct.pack('<f', 100))
        self.assertEqual(decode_health(packet(data), {123})[0],
                         [{'entityId': 123, 'currentHealth': 100}])

    def test_generation_bits_are_not_masked(self):
        self.assertEqual(decode_health(packet(record(0x400001ae, 1, b'\xff')), {0x400000ae})[0], [])

    def test_other_groups_and_suffix_remain_explicit(self):
        data = struct.pack('<BIIB', 33, 123, 1, 2) + b'ab' + struct.pack('<IB', 1, 1) + b'\xff'
        rows, scope = decode_health(packet(data) + b'xyz', {123})
        self.assertEqual(rows[0]['currentHealth'], 0)
        self.assertEqual(scope['undecodedSuffixBytes'], 3)

    def test_malformed_data_refused(self):
        for data in (b'\x20', record(123, 3, b'\xff'), record(123, 1, struct.pack('<f', float('nan'))),
                     record(123, 1, struct.pack('<f', -1)), b'\x80' + bytes(4)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                decode_health(packet(data), {123})
        with self.assertRaises(ValueError):
            decode_vector(packet(b'abc')[:-1])
        with self.assertRaises(ValueError):
            decode_vector(b'')

    def test_vector_bound_and_profile_gate(self):
        inverse = {value: index for index, value in enumerate(BYTE_MAP)}
        with self.assertRaises(ValueError):
            decode_vector(b'\0\0' + bytes([inverse[255]]) * 5)
        with self.assertRaises(ValueError):
            require_profile('16.21.829.8620', 'different')


if __name__ == '__main__':
    unittest.main()
