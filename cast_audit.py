"""Compare unlike cast evidence without inventing events to reconcile totals."""
from collections import Counter
import math


def counter_audit(participants, ordered_entities, observations):
    if len(participants) != 10 or len(ordered_entities) != 10 or len(set(ordered_entities)) != 10:
        raise ValueError('Audit requires the validated ten-participant entity mapping.')
    counts = Counter((row['casterEntityId'], row['spellSlot']) for row in observations)
    rows = []
    for participant, entity in zip(participants, ordered_entities):
        for slot in range(4):
            key = f'SPELL{slot + 1}_CAST'
            reported = int(participant[key]) if key in participant else None
            observed = counts[(entity, slot)]
            rows.append({'entityId': entity, 'spellSlot': slot,
                         'finalReportedCounter': reported, 'observedRecords': observed,
                         'counterMinusObservations': None if reported is None else reported - observed})
    return {'comparisonMeaning': 'counter_discrepancy_not_proven_missing_casts',
            'matchingTotalsProveCoverage': False, 'rows': rows}


def resource_corroboration(entity, state_updates, observations, minimum_drop=25., window_seconds=0.6):
    if not all(math.isfinite(x) and x > 0 for x in (minimum_drop, window_seconds)):
        raise ValueError('Audit thresholds must be positive.')
    resource = sorted((row for row in state_updates if row['entityId'] == entity and 'primaryResource' in row),
                      key=lambda row: row['timestampSeconds'])
    casts = sorted((row for row in observations if row['casterEntityId'] == entity and 0 <= row['spellSlot'] <= 3),
                   key=lambda row: row['timestampSeconds'])
    transitions = []
    index = 0
    for previous, row in zip(resource, resource[1:]):
        drop = previous['primaryResource'] - row['primaryResource']
        if drop < minimum_drop:
            continue
        time = row['timestampSeconds']
        while index < len(casts) and casts[index]['timestampSeconds'] < time - window_seconds:
            index += 1
        matches = []
        for candidate in casts[index:]:
            if candidate['timestampSeconds'] > time:
                break
            matches.append(candidate)
        nearest = max(matches, key=lambda item: item['timestampSeconds']) if matches else None
        transitions.append({'timestampSeconds': time, 'observedResourceDrop': drop,
                            'previousSampleAgeSeconds': time - previous['timestampSeconds'],
                            'nearbyCastTimestampSeconds': None if nearest is None else nearest['timestampSeconds'],
                            'nearbyCastSlot': None if nearest is None else nearest['spellSlot']})
    return {'entityId': entity, 'minimumDrop': minimum_drop, 'windowSeconds': window_seconds,
            'interpretation': 'temporal_corroboration_not_proof_of_causality_or_complete_coverage',
            'oneToOneMatching': False, 'qualifyingTransitions': len(transitions),
            'unmatchedTransitions': sum(row['nearbyCastTimestampSeconds'] is None for row in transitions),
            'transitions': transitions}
