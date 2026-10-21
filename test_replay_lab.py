import json
from pathlib import Path
import struct
import tempfile
import unittest
import zstandard
import replay_lab as lab

def fixture(version='16.20.824.8524', extension=4, timestamp=12.5, declared_size=None, compressed=False):
    block=b'\x10'+struct.pack('<fBHIB',timestamp,1,123,456,99)
    body=zstandard.ZstdCompressor().compress(block) if compressed else block
    header=b'RIOT'+struct.pack('<H',2)+bytes(8)+bytes([len(version)])+version.encode()
    chunk=struct.pack('<IBIII',1,0,1<<24,declared_size if declared_size is not None else len(block),len(body) if compressed else 0)
    if version.startswith('16.21'):
        chunk+=bytes([extension])
    metadata=json.dumps({'gameLength':13000,'lastGameChunkId':1,'lastKeyFrameId':0,'statsJson':'[]'}).encode()
    return header+chunk+body+bytes(256)+metadata+struct.pack('<I',len(metadata))

class ReplayLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()
    def parse(self,data):
        p=self.root/'EUW1-1.rofl';p.write_bytes(data)
        with lab.LabReader.open(p) as replay:
            return list(replay.iter_blocks(include_payload=True))
    def test_both_layouts_produce_same_record(self):
        for build in lab.LAYOUTS:
            with self.subTest(build=build):
                b=self.parse(fixture(build))[0]
                self.assertEqual((b.timestamp,b.packet_id,b.param,b.payload),(12.5,123,456,b'c'))
    def test_compressed_layouts(self):
        for build in lab.LAYOUTS:
            self.assertEqual(len(self.parse(fixture(build,compressed=True))),1)
    def test_extension_change_rejected(self):
        with self.assertRaises(ValueError):self.parse(fixture('16.21.829.8620',extension=5))
    def test_unknown_build_rejected(self):
        with self.assertRaises(ValueError):self.parse(fixture('16.22.001.0001'))
    def test_chunk_overrun_rejected(self):
        with self.assertRaises(ValueError):self.parse(fixture(declared_size=10000000))
    def test_decompressed_size_mismatch_rejected(self):
        with self.assertRaises(lab.RoflParseError):self.parse(fixture(declared_size=50,compressed=True))
    def test_invalid_timestamp_rejected(self):
        with self.assertRaises(lab.RoflParseError):self.parse(fixture(timestamp=float('nan')))
    def test_truncated_file_rejected(self):
        with self.assertRaises((lab.RoflParseError,ValueError,struct.error)):self.parse(fixture()[:-9])
    def test_inputs_cannot_be_overwritten(self):
        source=self.root/'input.rofl';source.write_bytes(b'unchanged')
        with self.assertRaises(ValueError):lab.ensure_outputs_safe(source,self.root)
        self.assertEqual(source.read_bytes(),b'unchanged')
    def test_existing_outputs_preserved(self):
        source=self.root/'input.rofl';source.write_bytes(b'input')
        out=self.root/'out';out.mkdir();(out/'keep').write_text('keep')
        with self.assertRaises(ValueError):lab.ensure_outputs_safe(source,out)
        self.assertEqual((out/'keep').read_text(),'keep')
    def test_wrong_timeline_rejected(self):
        p=self.root/'EUW1-1.rofl';p.write_bytes(fixture())
        match=self.root/'match.json';timeline=self.root/'timeline.json'
        match.write_text(json.dumps({'metadata':{'matchId':'EUW1_1'}}))
        timeline.write_text(json.dumps({'metadata':{'matchId':'EUW1_2'}}))
        with lab.LabReader.open(p) as replay:
            with self.assertRaises(ValueError):lab.reference_data(replay,match,timeline,None)
    def test_timing_score_penalizes_frequent_noise(self):
        score=lab.temporal_score([1,2,3,4,5],[1,3],0.01)
        self.assertEqual(score['recall'],1)
        self.assertEqual(score['precision'],0.4)
        self.assertLess(score['f1'],1)
    def test_timing_score_handles_empty_and_edges(self):
        self.assertEqual(lab.temporal_score([],[],.1)['f1'],0)
        self.assertEqual(lab.temporal_score([1],[1.1],.11)['f1'],1)
    def test_death_profile_rejects_noncontiguous_entities(self):
        participants=[{'NUM_DEATHS':'0'} for _ in range(10)]
        with self.assertRaises(ValueError):lab.decode_death_markers([],set(range(10)),participants)
    def test_death_profile_refuses_metadata_count_mismatch(self):
        participants=[{'NUM_DEATHS':'0'} for _ in range(10)]
        entities=set(range(0x400000ae,0x400000b8))
        rows=[{'entity':0x400000ae,'payloadLength':5,'time':10,'opcode':0xa6}]
        with self.assertRaises(ValueError):lab.decode_death_markers(rows,entities,participants)
    def test_death_profile_refuses_wrong_api_victim(self):
        participants=[{'NUM_DEATHS':'1' if i==0 else '0','SKIN':'test','RIOT_ID_GAME_NAME':str(i)} for i in range(10)]
        entities=set(range(0x400000ae,0x400000b8))
        rows=[{'entity':0x400000ae,'payloadLength':5,'time':10,'opcode':0xa6}]
        reference={'metadataOrderMatches':True,'events':[{'timestampSeconds':10,'event':{'type':'CHAMPION_KILL','victimId':2}}]}
        with self.assertRaises(ValueError):lab.decode_death_markers(rows,entities,participants,reference)
    def test_respawn_generation_is_preserved_but_normalized_for_identity(self):
        participants=[{'NUM_DEATHS':'1' if i==0 else '0','SKIN':'test','RIOT_ID_GAME_NAME':str(i)} for i in range(10)]
        entities=set(range(0x400000ae,0x400000b8))|{0x400001ae}
        rows=[{'entity':0x400001ae,'payloadLength':5,'time':10,'opcode':0xa6}]
        decoded,checks=lab.decode_death_markers(rows,entities,participants)
        self.assertEqual(decoded[0]['victimParticipantId'],1)
        self.assertEqual(decoded[0]['victimEntityId'],0x400001ae)
        self.assertTrue(checks['metadataDeathCountsMatch'])

if __name__=='__main__':unittest.main()
