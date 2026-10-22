import unittest
from cast_audit import counter_audit, resource_corroboration


class CastAuditTests(unittest.TestCase):
    def test_counter_discrepancies_can_have_either_sign(self):
        participants = [{'SPELL1_CAST': 1, 'SPELL2_CAST': 2} for _ in range(10)]
        observations = [{'casterEntityId': 100, 'spellSlot': 0}] * 2
        result = counter_audit(participants, list(range(100, 110)), observations)
        self.assertEqual(result['rows'][0]['counterMinusObservations'], -1)
        self.assertEqual(result['rows'][1]['counterMinusObservations'], 2)
        self.assertFalse(result['matchingTotalsProveCoverage'])

    def test_absent_counter_is_unknown(self):
        result = counter_audit([{} for _ in range(10)], list(range(10)), [])
        self.assertIsNone(result['rows'][0]['counterMinusObservations'])
        with self.assertRaises(ValueError):
            counter_audit([{}], [1], [])

    def test_missing_resource_does_not_become_zero(self):
        rows = [{'entityId': 1, 'timestampSeconds': 1, 'primaryResource': 100},
                {'entityId': 1, 'timestampSeconds': 2, 'currentHealth': 50},
                {'entityId': 1, 'timestampSeconds': 3, 'primaryResource': 60}]
        result = resource_corroboration(1, rows, [])
        self.assertEqual(result['qualifyingTransitions'], 1)
        self.assertEqual(result['transitions'][0]['previousSampleAgeSeconds'], 2)

    def test_future_and_other_casters_do_not_match(self):
        rows = [{'entityId': 1, 'timestampSeconds': 1, 'primaryResource': 100},
                {'entityId': 1, 'timestampSeconds': 2, 'primaryResource': 60}]
        casts = [{'casterEntityId': 1, 'spellSlot': 0, 'timestampSeconds': 2.1},
                 {'casterEntityId': 2, 'spellSlot': 0, 'timestampSeconds': 1.9}]
        self.assertEqual(resource_corroboration(1, rows, casts)['unmatchedTransitions'], 1)
        casts.append({'casterEntityId': 1, 'spellSlot': 0, 'timestampSeconds': 1.9})
        result = resource_corroboration(1, rows, casts)
        self.assertEqual(result['unmatchedTransitions'], 0)
        self.assertFalse(result['oneToOneMatching'])
        for invalid in (0, -1, float('nan'), float('inf')):
            with self.assertRaises(ValueError):
                resource_corroboration(1, rows, casts, window_seconds=invalid)
