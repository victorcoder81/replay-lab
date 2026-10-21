import unittest
from visibility_decoder import decode_visibility, require_visibility_profile, VisibilityState


class VisibilityTests(unittest.TestCase):
    def test_explicit_team_reports(self):
        self.assertEqual(decode_visibility(bytes.fromhex('9a1e'), 0x30)['teamId'], 100)
        self.assertEqual(decode_visibility(bytes.fromhex('9a1a'), 0x246)['teamId'], 200)
        self.assertEqual(decode_visibility(bytes.fromhex('9a1a'), 0x246)['reportedVisibility'], 'hidden')

    def test_initial_state_is_unknown(self):
        self.assertEqual(VisibilityState().get(123, 100)['reportedVisibility'], 'unknown')

    def test_repeated_reports_do_not_toggle(self):
        state = VisibilityState()
        report = decode_visibility(bytes.fromhex('9a1e'), 0x30)
        self.assertTrue(state.apply(1, 123, report))
        self.assertFalse(state.apply(2, 123, report))
        self.assertEqual(state.get(123, 100)['reportedVisibility'], 'visible')
        self.assertEqual(state.get(123, 200)['reportedVisibility'], 'unknown')

    def test_exact_entities_not_masked(self):
        state = VisibilityState()
        state.apply(1, 0x400001ae, decode_visibility(bytes.fromhex('9a1e'), 0x30))
        self.assertEqual(state.get(0x400000ae, 100)['reportedVisibility'], 'unknown')

    def test_setters_and_ordering(self):
        state = VisibilityState()
        report = decode_visibility(bytes.fromhex('9a1e'), 0x246)
        state.apply(2, 123, report)
        self.assertEqual(state.get(123, 100)['reportedVisibility'], 'hidden')
        with self.assertRaises(ValueError):
            state.apply(1, 123, report)

    def test_unknown_shapes_and_profiles_refused(self):
        for payload, opcode in [(b'', 0x30), (b'\x01', 0x30), (b'\x9a', 0x30),
                                (bytes.fromhex('9a1e00'), 0x30), (bytes.fromhex('9a16'), 0x30),
                                (bytes.fromhex('9a1e'), 0xa8)]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                decode_visibility(payload, opcode)
        with self.assertRaises(ValueError):
            require_visibility_profile('16.21.829.8620', 'other')


if __name__ == '__main__':
    unittest.main()
