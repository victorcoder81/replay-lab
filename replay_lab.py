"""Offline ROFL transport research and API-reference correlation tool.

Gameplay semantics are never inferred solely from packet timing correlations.
"""
from __future__ import annotations
import argparse
from array import array
from bisect import bisect_left
from collections import Counter, defaultdict
from contextlib import ExitStack
import json
import math
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'vendor'))
from rofllens import ReplayReader, RoflParseError
from rofllens.models import ChunkRecord, STREAM_NAMES

VERSION = '0.5.0'
LAYOUTS = {'16.20.824.8524': (17, None), '16.21.829.8620': (18, 4)}
DEATH_PROFILES = {
    '16.20.824.8524': {'protocol':'142cabd45e45d83f','deathOpcode':0x00a6,'skillOpcode':0x032a},
    '16.21.829.8620': {'protocol':'20e09df23c66b85e','deathOpcode':0x00c9,'skillOpcode':0x035c},
}
MAX_CHUNK_BYTES = 64 * 1024 * 1024

class LabReader(ReplayReader):
    def _walk_chunks(self):
        layout = LAYOUTS.get(self.header.client_version)
        if layout is None:
            raise ValueError(f'Unsupported build {self.header.client_version}; refusing to guess its layout.')
        size, extra = layout
        cursor = self.header.header_size
        while cursor < self.signature_offset:
            if cursor + size > self.signature_offset:
                raise ValueError('Truncated chunk header.')
            chunk_id, slot, stream_raw, raw_size, compressed_size = struct.unpack_from('<IBIII', self._mapped, cursor)
            if extra is not None and self._mapped[cursor+17] != extra:
                raise ValueError('Unexpected chunk extension byte.')
            stream = (stream_raw >> 24) & 255
            stored = compressed_size or raw_size
            if stream not in STREAM_NAMES or max(raw_size, stored) > MAX_CHUNK_BYTES:
                raise ValueError('Invalid stream or excessive chunk size.')
            end = cursor + size + stored
            if end > self.signature_offset:
                raise ValueError('Chunk body extends beyond signature boundary.')
            yield ChunkRecord(cursor, cursor+size, chunk_id, slot, stream, raw_size, compressed_size)
            cursor = end
        if cursor != self.signature_offset:
            raise ValueError('Chunk boundary mismatch.')

def load_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def write_json(path, obj):
    target = Path(path)
    temporary = target.with_name(target.name+'.part')
    temporary.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf8')
    temporary.replace(target)

def ensure_outputs_safe(replay, output, other_inputs=()):
    output = Path(output).resolve()
    inputs = [Path(replay).resolve(), *[Path(p).resolve() for p in other_inputs if p]]
    for source in inputs:
        if source == output or output in source.parents:
            raise ValueError('Output directory must not contain an input file; choose a separate directory.')
    if output.exists() and any(output.iterdir()):
        raise ValueError('Output directory is not empty; choose a fresh directory.')
    output.mkdir(parents=True, exist_ok=True)
    return output

def reference_data(replay, match_path, timeline_path, riot_id):
    if not match_path and not timeline_path:
        return None
    if not match_path or not timeline_path:
        raise ValueError('--match and --timeline must be supplied together.')
    match, timeline = load_json(match_path), load_json(timeline_path)
    match_id = match['metadata']['matchId']
    if timeline['metadata']['matchId'] != match_id:
        raise ValueError('Match and timeline IDs differ.')
    expected = re.fullmatch(r'([A-Za-z0-9]+)[_-](\d+)', replay.path.stem)
    if not expected or match_id != f'{expected[1]}_{expected[2]}':
        raise ValueError('Replay filename must contain the same match ID as the reference files.')
    if match['info']['gameVersion'] != replay.header.client_version:
        raise ValueError('Replay and reference game versions differ.')
    api_participants = match['info']['participants']
    metadata_order_matches = True
    for index, p in enumerate(replay.metadata.participants,1):
        peers = [q for q in api_participants if q.get('riotIdGameName','').casefold()==p.get('RIOT_ID_GAME_NAME','').casefold()
                 and q.get('riotIdTagline','').casefold()==p.get('RIOT_ID_TAG_LINE','').casefold()]
        if len(peers) != 1:
            raise ValueError('Participant identity mismatch between replay and reference match.')
        q = peers[0]
        metadata_order_matches &= q['participantId']==index
        for rk, ak in [('CHAMPIONS_KILLED','kills'),('NUM_DEATHS','deaths'),('ASSISTS','assists'),('SPELL1_CAST','spell1Casts'),('SPELL2_CAST','spell2Casts'),('SPELL3_CAST','spell3Casts'),('SPELL4_CAST','spell4Casts')]:
            if rk in p and ak in q and int(p[rk]) != q[ak]:
                raise ValueError(f'Reference statistic mismatch: {rk}.')
    player = None
    if riot_id:
        name, sep, tag = riot_id.rpartition('#')
        if not sep:
            raise ValueError('--riot-id must be name#tag.')
        players = [p for p in api_participants if p.get('riotIdGameName','').casefold()==name.casefold() and p.get('riotIdTagline','').casefold()==tag.casefold()]
        if len(players) != 1:
            raise ValueError('Requested Riot ID not uniquely identified in match.')
        player = players[0]
    events = []
    for frame in timeline['info']['frames']:
        for event in frame.get('events', []):
            if 'timestamp' in event:
                events.append({'provenance':'riot_match_v5_timeline','timestampSeconds':event['timestamp']/1000,'event':event})
    events.sort(key=lambda e:e['timestampSeconds'])
    return {'matchId':match_id,'mapId':match['info']['mapId'],'events':events,'player':player,'participants':api_participants,'metadataOrderMatches':metadata_order_matches}

def decode_death_markers(rows, entities, participants, reference=None, tolerance=0.15):
    """Narrow empirical decoder: header timestamp + victim entity, no payload fields.

    Entity-to-participant ordering is an empirical rule, checked against metadata
    death totals, and against every API victim/timestamp when a reference exists.
    Unknown allocation patterns and mismatched counts are refused.
    """
    # In the tested builds, bits 8..15 change when a champion entity respawns.
    # This empirical normalization is validated by metadata and API checks below.
    canonical=lambda entity:entity & ~0xff00
    entities=sorted({canonical(entity) for entity in entities})
    if len(participants)!=10 or len(entities)!=10 or entities!=list(range(entities[0],entities[0]+10)) or entities[0]>>28!=4:
        raise ValueError('Death decoder requires ten contiguous champion entities from the profiled skill marker.')
    actual=Counter()
    decoded=[]
    for row in rows:
        if row['payloadLength']!=5 or canonical(row['entity']) not in entities:
            raise ValueError('Death marker shape or entity differs from the empirical profile.')
        pid=canonical(row['entity'])-entities[0]+1
        actual[pid]+=1
        p=participants[pid-1]
        decoded.append({'kind':'CHAMPION_DEATH_MARKER','provenance':'rofl_transport_empirical_profile',
            'confidence':'experimental','timestampSeconds':row['time'],'packetId':row['opcode'],
            'victimEntityId':row['entity'],'victimParticipantId':pid,
            'victimRiotId':p.get('RIOT_ID_GAME_NAME','')+'#'+p.get('RIOT_ID_TAG_LINE',''),
            'victimChampion':p.get('SKIN'),'fieldsNotDecoded':['killer','assists','position','payloadFields']})
    expected={i:int(p.get('NUM_DEATHS',-1)) for i,p in enumerate(participants,1)}
    if any(actual[i]!=expected[i] for i in expected):
        raise ValueError('Death-marker counts do not match end-of-game participant death totals.')
    checks={'metadataDeathCountsMatch':True,'apiVictimTimestampCheck':None,'events':len(decoded),
            'entityMapping':'empirical contiguous allocation after masking generation bits 8..15, plus metadata order; not a universally established protocol rule'}
    if reference:
        if not reference['metadataOrderMatches']:
            raise ValueError('Metadata participant order differs from API participant IDs.')
        refs=[r for r in reference['events'] if r['event']['type']=='CHAMPION_KILL']
        used=set()
        for event in decoded:
            matches=[(abs(r['timestampSeconds']-event['timestampSeconds']),i) for i,r in enumerate(refs)
                     if i not in used and r['event']['victimId']==event['victimParticipantId'] and abs(r['timestampSeconds']-event['timestampSeconds'])<=tolerance]
            if not matches:
                raise ValueError('A replay death marker has no matching API victim/timestamp.')
            used.add(min(matches)[1])
        if len(used)!=len(refs):
            raise ValueError('Not all API champion deaths have a replay marker.')
        checks['apiVictimTimestampCheck']={'matched':len(used),'references':len(refs),'toleranceSeconds':tolerance}
    return decoded,checks

def temporal_score(packet_times, reference_times, tolerance):
    """Timing coincidence only, with both precision and reference-event coverage."""
    if not packet_times or not reference_times:
        return {'precision':0.0,'recall':0.0,'f1':0.0,'matchedPackets':0,'matchedReferences':0}
    def near(values, value):
        i = bisect_left(values, value)
        return any(abs(values[j]-value)<=tolerance for j in (i-1,i) if 0<=j<len(values))
    mp = sum(near(reference_times,t) for t in packet_times)
    mr = sum(near(packet_times,t) for t in reference_times)
    precision, recall = mp/len(packet_times), mr/len(reference_times)
    return {'precision':precision,'recall':recall,'f1':2*precision*recall/(precision+recall) if precision+recall else 0.0,'matchedPackets':mp,'matchedReferences':mr}

def correlate(times, reference, tolerance):
    if not reference:
        return []
    groups = defaultdict(list)
    allowed = {'CHAMPION_KILL','ITEM_PURCHASED','WARD_PLACED','WARD_KILL','SKILL_LEVEL_UP','ELITE_MONSTER_KILL','BUILDING_KILL'}
    for row in reference['events']:
        kind = row['event']['type']
        if kind in allowed:
            groups[kind].append(row['timestampSeconds'])
    results = []
    for kind, refs in groups.items():
        if len(refs)<3:
            continue
        candidates = []
        for opcode, packet_times in times.items():
            if not 0.4*len(refs) <= len(packet_times) <= 3*len(refs):
                continue
            score = temporal_score(packet_times, refs, tolerance)
            if score['f1']<0.35:
                continue
            control = temporal_score(packet_times, [t+3 for t in refs], tolerance)
            candidates.append({'packetId':opcode,'packetIdHex':f'0x{opcode:04x}','packetCount':len(packet_times),**score,'shiftedControlF1':control['f1']})
        candidates.sort(key=lambda p:(p['f1']-p['shiftedControlF1'],p['f1']),reverse=True)
        results.append({'referenceKind':kind,'referenceCount':len(refs),'toleranceSeconds':tolerance,
                        'status':'unverified_timing_candidates','warning':'Shared timing does not prove packet meaning or field layout. No gameplay labels are assigned to raw records.',
                        'candidates':candidates[:8]})
    return results

def format_time(seconds):
    return f'{int(seconds)//60}:{int(seconds)%60:02d}'

def analyze(args):
    with LabReader.open(args.replay) as replay:
        reference = reference_data(replay,args.match,args.timeline,args.riot_id)
        movement_profile = None; item_profile = None
        health_entities = None; health_counts = Counter()
        if args.experimental_health:
            from health_decoder import require_profile, decode_health, OPCODE as HEALTH_OPCODE
            require_profile(replay.header.client_version, replay.header.protocol_digest)
            death_profile = DEATH_PROFILES[replay.header.client_version]
            markers = []; skill_entities = set()
            for block in replay.iter_blocks(streams={'gameChunk'}, opcodes={death_profile['skillOpcode'], death_profile['deathOpcode']}):
                if block.packet_id == death_profile['skillOpcode']:
                    skill_entities.add(block.param)
                else:
                    markers.append({'time': block.timestamp, 'entity': block.param, 'opcode': block.packet_id, 'payloadLength': block.payload_length})
            decode_death_markers(markers, skill_entities, list(replay.metadata.participants), reference, args.tolerance)
            # Normalization is confined to the validated skill-marker prepass.
            # Health records themselves must contain these exact IDs.
            health_entities = {entity & ~0xff00 for entity in skill_entities}
        if args.experimental_items:
            from item_decoder import load_item_profile, decode_item_prefix
            item_profile=load_item_profile(replay.header.client_version,replay.header.protocol_digest)
        if args.experimental_movement:
            from movement_decoder import load_profile, decode_movement
            map_id = reference['mapId'] if reference else args.map_id
            if args.map_id is not None and map_id != args.map_id:
                raise ValueError('--map-id differs from API match map.')
            movement_profile = load_profile(replay.header.client_version,replay.header.protocol_digest,map_id)
        output = ensure_outputs_safe(args.replay,args.out,[args.match,args.timeline])
        chunks = list(replay.chunks())
        summary = replay.summary().as_dict()
        counts, stream_counts, lengths = Counter(), Counter(), Counter()
        times = defaultdict(lambda:array('d'))
        first, last, raw_count = math.inf, 0.0, 0
        profile=DEATH_PROFILES.get(replay.header.client_version) if args.experimental_deaths else None
        if profile and profile['protocol']!=replay.header.protocol_digest:
            raise ValueError('Death decoder protocol digest mismatch.')
        death_rows=[];entities=set()
        sample_file = None; movement_counts = Counter(); item_counts = Counter()
        with ExitStack() as stack:
            if health_entities is not None:
                health_file = stack.enter_context((output/'replay-health-updates.jsonl').open('w',encoding='utf8'))
            if item_profile:
                item_file=stack.enter_context((output/'replay-item-updates.jsonl').open('w',encoding='utf8'))
            if movement_profile:
                movement_file = stack.enter_context((output/'replay-movement-paths.jsonl').open('w',encoding='utf8'))
            if args.window:
                sample_file = stack.enter_context((output/'raw-window.jsonl').open('w',encoding='utf8'))
            for block in replay.iter_blocks(include_payload=bool(args.window or movement_profile or item_profile or health_entities is not None),verify=True):
                counts[block.packet_id]+=1
                stream_counts[block.stream]+=1
                lengths[block.packet_id]+=block.payload_length
                first=min(first,block.timestamp);last=max(last,block.timestamp)
                if block.stream=='gameChunk':
                    if health_entities is not None and block.packet_id == HEALTH_OPCODE:
                        health_updates, health_prefix = decode_health(block.payload, health_entities)
                        health_counts['packets'] += 1
                        health_counts['updates'] += len(health_updates)
                        for fields in health_updates:
                            health_file.write(json.dumps({'kind':'CHAMPION_HEALTH_UPDATE',
                                'provenance':'rofl_payload_exact_build_profile', 'confidence':'experimental',
                                'timestampSeconds':block.timestamp, 'packetId':block.packet_id,
                                'sampling':'sparse_updates', 'teamVisibility':'unknown',
                                **fields, **health_prefix})+'\n')
                    if item_profile and block.packet_id==item_profile['opcode']:
                        fields=decode_item_prefix(block.payload,item_profile)
                        item_counts['updates']+=1
                        item_file.write(json.dumps({'kind':'ITEM_UPDATE_PREFIX','provenance':'rofl_payload_exact_build_profile',
                            'confidence':'experimental','timestampSeconds':block.timestamp,'packetId':block.packet_id,
                            'entityId':block.param,**fields})+'\n')
                    if movement_profile and block.packet_id==movement_profile['opcode']:
                        paths=decode_movement(block.payload,movement_profile)
                        movement_counts['packets']+=1
                        movement_counts['paths']+=len(paths)
                        if not paths:movement_counts['emptyPackets']+=1
                        for path in paths:
                            movement_file.write(json.dumps({'kind':'MOVEMENT_PATH','provenance':'rofl_payload_exact_build_profile',
                                'confidence':'experimental','timestampSeconds':block.timestamp,'packetId':block.packet_id,**path})+'\n')
                    times[block.packet_id].append(block.timestamp)
                    if profile and block.packet_id==profile['skillOpcode']:
                        entities.add(block.param)
                    if profile and block.packet_id==profile['deathOpcode']:
                        death_rows.append({'time':block.timestamp,'entity':block.param,'opcode':block.packet_id,'payloadLength':block.payload_length})
                    if sample_file and args.window[0]<=block.timestamp<=args.window[1]:
                        row={'status':'undecoded','timestampSeconds':block.timestamp,'packetId':block.packet_id,'param':block.param,'payloadHex':block.payload.hex()}
                        sample_file.write(json.dumps(row)+'\n');raw_count+=1
        for opcode in times:
            times[opcode]=sorted(times[opcode])
        summary.update({'toolVersion':VERSION,'chunkHeaderBytes':LAYOUTS[replay.header.client_version][0],
            'validation':{'allChunkSizesVerified':True,'exactEndBoundary':True,'recordsParsed':sum(stream_counts.values()),'cryptographicReplaySignatureChecked':False},
            'transport':{'records':sum(stream_counts.values()),'byStream':dict(stream_counts),'distinctPacketIds':len(counts),'firstTimestamp':first if math.isfinite(first) else None,'lastTimestamp':last},
            'gameplayDecoding':{'status':'unavailable','decodedGameplayEvents':0,'referenceEventsAreNotReplayDecodedEvents':True},
            'reference':{'matchId':reference['matchId'],'participantStatsCrossChecked':True} if reference else None})
        histogram=[{'packetId':op,'hex':f'0x{op:04x}','recordsAllStreams':count,'gameChunkRecords':len(times[op]),'payloadBytes':lengths[op]} for op,count in counts.most_common()]
        hypotheses=correlate(times,reference,args.tolerance)
        decoded=[];death_validation=None
        if profile:
            decoded,death_validation=decode_death_markers(death_rows,entities,list(replay.metadata.participants),reference,args.tolerance)
            summary['gameplayDecoding']={'status':'limited_experimental','decodedDeathMarkers':len(decoded),
                'profileScope':'Header timestamps and victim entity only; payload is not decoded.',
                'validation':death_validation,'movementDecoded':False,'spellCastsDecoded':False,
                'referenceEventsAreNotReplayDecodedEvents':True}
            with (output/'replay-death-markers.jsonl').open('w',encoding='utf8') as f:
                for event in decoded:f.write(json.dumps(event,ensure_ascii=False)+'\n')
        if movement_profile:
            summary['gameplayDecoding'].update({'status':'limited_experimental','movementDecoded':True,
                'decodedGameplayEvents':movement_counts['paths']+len(decoded),
                'movement':{'kind':'waypoint_paths','counts':dict(movement_counts),'mapId':11,
                    'continuousPositions':False,'participantIdentityAssigned':False,'profile':movement_profile['schema']},
                'spellCastsDecoded':False})
        if item_profile:
            summary['gameplayDecoding'].update({'status':'limited_experimental','itemUpdatesDecoded':True,
                'items':{'counts':dict(item_counts),'scope':'item ID, gold balance at update time, and an unverified numeric field from a partial packet prefix',
                    'transactionsClassified':False,'participantIdentityAssigned':False,'payloadFullyDecoded':False}})
            summary['gameplayDecoding']['decodedGameplayEvents']=len(decoded)+movement_counts['paths']+item_counts['updates']
        if health_entities is not None:
            summary['gameplayDecoding'].update({'status':'limited_experimental', 'healthDecoded':True,
                'health':{'counts':dict(health_counts), 'scope':'sparse current/max champion health updates',
                    'identityGate':'skill entities and all ten metadata death totals',
                    'participantIdentityAssigned':False, 'npcHealthDecoded':False,
                    'continuousHealth':False, 'teamVisibility':'unknown', 'payloadFullyDecoded':False}})
            summary['gameplayDecoding']['decodedGameplayEvents'] = len(decoded)+movement_counts['paths']+item_counts['updates']+health_counts['updates']
        write_json(output/'summary.json',summary)
        write_json(output/'participants.json',list(replay.metadata.participants))
        write_json(output/'packet-histogram.json',histogram)
        write_json(output/'timing-candidates.json',hypotheses)
        deaths=[]
        if reference:
            with (output/'api-reference-events.jsonl').open('w',encoding='utf8') as f:
                for event in reference['events']:
                    f.write(json.dumps(event,ensure_ascii=False)+'\n')
            if reference['player']:
                pid=reference['player']['participantId']
                deaths=[e for e in reference['events'] if e['event']['type']=='CHAMPION_KILL' and e['event']['victimId']==pid]
        lines=[f'# Replay Lab: {replay.path.stem}','',f'Build **{replay.header.client_version}**. Parsed **{len(chunks)} chunks** and **{sum(stream_counts.values()):,} transport records** through {format_time(last)}.',
            '', '**Gameplay decoder status: '+('limited experimental' if profile or movement_profile or item_profile or health_entities is not None else 'unavailable')+'.** Spell availability and team visibility remain unverified.',
            '', 'All chunk sizes and the final container boundary were checked. The cryptographic replay signature was not verified. Original replay files are opened read-only.',
            '', '## Extracted data', '', '- Final participant stats are in `participants.json`.', '- Timestamp and opcode counts are in `summary.json` and `packet-histogram.json`.',
            '- Timing candidates are research hypotheses, not recovered gameplay events.']
        if health_entities is not None:
            lines += ['', f'Experimental health profile decoded **{health_counts["updates"]:,} sparse champion health updates** from **{health_counts["packets"]:,} packets**.',
                'Each row contains only fields present in that update. Absent fields are unknown/unchanged, never zero. Do not interpolate these into exact continuous health or infer team visibility.']
        if movement_profile:
            lines += ['',f'Experimental movement profile decoded **{movement_counts["paths"]:,} waypoint paths** from **{movement_counts["packets"]:,} packets**.',
                'Paths include NPCs. Entity IDs are preserved without assigning champion identities. These are waypoint updates, not a complete continuous position trace.']
        if item_profile:
            lines += ['',f'Experimental item profile decoded **{item_counts["updates"]} item-update prefixes**.',
                'Item IDs and gold balances at update time are recovered. A second numeric field has no established meaning. Updates are not classified as purchases; suffix fields and participant identity remain undecoded.']
        if profile:
            lines+=['',f'Experimental death-marker profile produced **{len(decoded)} records** from replay timestamps and victim entities. Counts match all ten participants\' final death totals.',
                'Identity mapping uses an empirical allocation/order rule. These checks do not prove the meaning of other payload fields.']
            if death_validation['apiVictimTimestampCheck']:
                c=death_validation['apiVictimTimestampCheck'];lines.append(f'Independent API cross-check: **{c["matched"]}/{c["references"]} victims and timestamps match** within {args.tolerance} seconds.')
        if reference:
            lines+=['- Imported reference events come from Riot Match-v5 and are explicitly tagged with that provenance.', '', '## API-reference deaths', '', '| Time | Killer participant | Shutdown gold |','|---|---:|---:|']
            for death in deaths:
                e=death['event'];lines.append(f'| {format_time(death["timestampSeconds"])} | {e.get("killerId",0)} | {e.get("shutdownBounty",0)} |')
        lines+=['','## Packet research candidates','','Correlation uses record timestamps within '+str(args.tolerance)+' seconds of API events. A three-second shifted reference provides a simple negative control. Both can be influenced by co-occurring events.']
        for group in hypotheses:
            lines+=['',f'### {group["referenceKind"]} ({group["referenceCount"]} API events)','', '| Opcode | Raw records | Timing precision | Event coverage | F1 | Shifted F1 |','|---|---:|---:|---:|---:|---:|']
            for c in group['candidates']:
                lines.append(f'| {c["packetIdHex"]} | {c["packetCount"]} | {c["precision"]:.1%} | {c["recall"]:.1%} | {c["f1"]:.3f} | {c["shiftedControlF1"]:.3f} |')
        (output/'report.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
        print(json.dumps({'output':str(output),'build':replay.header.client_version,'chunks':len(chunks),'records':sum(stream_counts.values()),'referenceDeaths':len(deaths),'gameplayDecoder':summary['gameplayDecoding'],'rawWindowRows':raw_count,'timingCandidates':hypotheses},indent=2))

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('capabilities')
    d=sub.add_parser('doctor',help='Inspect an executable for static decoder-builder blockers; does not enable gameplay decoding.')
    d.add_argument('--client-exe',required=True,type=Path)
    d.add_argument('--replay',type=Path)
    d.add_argument('--out',type=Path,help='Write a new diagnostic JSON file; existing files are preserved.')
    p=sub.add_parser('analyze')
    p.add_argument('replay',type=Path);p.add_argument('--out',required=True,type=Path)
    p.add_argument('--match',type=Path);p.add_argument('--timeline',type=Path);p.add_argument('--riot-id')
    p.add_argument('--window',nargs=2,type=float,metavar=('START_SECONDS','END_SECONDS'))
    p.add_argument('--tolerance',type=float,default=0.15)
    p.add_argument('--experimental-deaths',action='store_true',help='Enable the narrow, empirically validated death-marker profile.')
    p.add_argument('--experimental-movement',action='store_true',help='Decode experimental 16.21 waypoint paths; requires map 11 from --map-id or API match.')
    p.add_argument('--experimental-health',action='store_true',help='Decode sparse 16.21 champion health updates after validating champion entity allocation and metadata death totals.')
    p.add_argument('--experimental-items',action='store_true',help='Decode partial 16.21 item-update prefixes, without classifying purchases or assigning identity.')
    p.add_argument('--map-id',type=int,help='Explicit map assertion for movement decoding without API match data; only 11 is supported.')
    args=parser.parse_args(argv)
    if args.command=='doctor':
        from decoder_doctor import doctor
        try:
            return doctor(args)
        except (ValueError,OSError,RoflParseError,struct.error) as e:
            print(json.dumps({'error':str(e),'status':'failed'}),file=sys.stderr)
            return 1
    if args.command=='capabilities':
        print(json.dumps({'version':VERSION,'containerBuilds':list(LAYOUTS),'verifiedGameplayDecoders':[],
            'experimentalProfiles':{v:{'kind':'champion_death_marker','scope':'timestamp and victim entity; metadata order mapping checked against death totals'} for v in DEATH_PROFILES},
            'experimentalMovement':{'build':'16.21.829.8620','mapId':11,'kind':'waypoint_paths','continuousPositions':False,'participantIdentityAssigned':False},
            'experimentalHealth':{'build':'16.21.829.8620','kind':'sparse_champion_health','teamVisibility':'unknown','continuousHealth':False},
            'experimentalItems':{'build':'16.21.829.8620','kind':'item_update_prefix','transactionsClassified':False,'payloadFullyDecoded':False},'offline':True},indent=2));return 0
    if not math.isfinite(args.tolerance) or not 0<args.tolerance<=1:
        parser.error('--tolerance must be greater than zero and at most one second.')
    if args.window and (not all(math.isfinite(x) for x in args.window) or args.window[0]<0 or args.window[1]<args.window[0]):
        parser.error('--window requires a nonnegative, increasing time range.')
    try:
        analyze(args);return 0
    except (ValueError,KeyError,OSError,RoflParseError,struct.error) as e:
        print(json.dumps({'error':str(e),'status':'failed'},ensure_ascii=False),file=sys.stderr);return 1

if __name__=='__main__':
    raise SystemExit(main())
