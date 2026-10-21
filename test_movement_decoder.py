import json
import struct
import unittest
from movement_decoder import load_profile, decode_vector, decode_movement, parse_paths, read_varuint

class MovementTests(unittest.TestCase):
    def setUp(self):
        self.p=load_profile('16.21.829.8620','20e09df23c66b85e')

    def test_fixed_encoded_path(self):
        # Synthetic packet: one point, signed coordinates and a 325-unit speed.
        packet=bytes.fromhex('08250bccccb3a07acc98cc12dbfbcc36')
        self.assertEqual(decode_movement(packet,self.p),[
            {'entityId':0x40000001,'speed':325.,'waypoints':[{'x':7158.,'y':7812.}],'recordFlags':2}])

    def test_every_truncation_and_trailing_byte_refused(self):
        packet=bytes.fromhex('08250bccccb3a07acc98cc12dbfbcc36')
        for size in range(len(packet)):
            with self.subTest(size=size),self.assertRaises(ValueError):decode_movement(packet[:size],self.p)
        with self.assertRaises(ValueError):decode_movement(packet+b'\0',self.p)

    def test_exact_profile_scope(self):
        for args in [('16.20.824.8524',self.p['protocolDigest'],11),
                     (self.p['clientVersion'],'wrong',11),
                     (self.p['clientVersion'],self.p['protocolDigest'],12),
                     (self.p['clientVersion'],self.p['protocolDigest'],None)]:
            with self.assertRaises(ValueError):load_profile(*args)

    def test_header_selectors_and_vector_order(self):
        def inv(key):return {v:i for i,v in enumerate(self.p[key])}
        v=inv('vectorByteMap');a=inv('prefix32ByteMap');b=inv('prefix16ByteMap')
        for hi in range(8):
            for lo in range(8):
                for size in (0,1,2,3,255,256,257):
                    plain=bytes(i%256 for i in range(size));header=8|lo|(hi<<4)
                    prefix=bytes([a[17]]) if lo not in (0,1,2,5) else b''
                    prefix+=bytes([b[19]]) if hi not in (0,2,5,7) else b''
                    length=bytes([v[size]]) if size<128 else bytes([v[(size&127)|128],v[size>>7]])
                    body=bytes(v[plain[i//2 if i%2==0 else size-1-i//2]] for i in range(size))
                    self.assertEqual(decode_vector(bytes([header])+prefix+length+body,self.p),plain)

    def test_absent_vector(self):
        self.assertEqual(decode_movement(b'\0',self.p),[])
        with self.assertRaises(ValueError):decode_vector(b'\0\0',self.p)

    def test_varint_overflow_and_unterminated(self):
        table=list(range(256))
        for payload,bits in [(b'\x80',32),(b'\xff\xff\xff\xff\x1f',32),(b'\xff\xff\x04',16)]:
            with self.assertRaises(ValueError):read_varuint(payload,0,table,bits)

    def test_multiple_records_delta_and_wrap(self):
        # Two waypoints: x wraps uint16; y switches from absolute to byte delta.
        record=struct.pack('<HIfBHHBB',4,7,340.,3,65535,65534,2,3)
        second=struct.pack('<HIfHH',2,8,0.,0,0)
        paths=parse_paths(record+second)
        self.assertEqual(paths[0]['waypoints'],[{'x':7356.,'y':7408.},{'x':7360.,'y':7414.}])
        self.assertEqual(paths[1]['entityId'],8)

    def test_malformed_inner_records(self):
        for payload in (b'x',struct.pack('<HIf',0,1,300.),struct.pack('<HIfHH',2,1,float('nan'),0,0),
                        struct.pack('<HIf',3,1,300.)):
            with self.assertRaises(ValueError):parse_paths(payload)

    def test_negative_deltas_are_signed(self):
        record=struct.pack('<HIfBHHbb',4,7,340.,3,0,2,-1,-3)
        self.assertEqual(parse_paths(record)[0]['waypoints'],[
            {'x':7358.,'y':7416.},{'x':7356.,'y':7410.}])

    def test_high_flags_preserved_without_changing_count(self):
        record=struct.pack('<HIfHH',0x202,7,340.,0,0)
        path=parse_paths(record)[0]
        self.assertEqual(path['recordFlags'],0x202)
        self.assertEqual(len(path['waypoints']),1)

if __name__=='__main__':unittest.main()
