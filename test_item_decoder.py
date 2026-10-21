import struct
import unittest
from item_decoder import load_item_profile,decode_item_prefix

class ItemTests(unittest.TestCase):
    def setUp(self):
        self.p=load_item_profile('16.21.829.8620','20e09df23c66b85e')
        self.inverse={v:i for i,v in enumerate(self.p['itemIdByteMap'])}
    def encoded(self,value):
        out=[]
        while value>=128:
            out.append(self.inverse[(value&127)|128]);value>>=7
        return bytes(out+[self.inverse[value]])
    def packet(self,item=12345,numeric_selector=4,suffix=b'\xaa'):
        header=(6<<17)|(numeric_selector<<14)
        return b'\x0f'+header.to_bytes(3,'little')+self.encoded(item)+suffix
    def test_synthetic_id_and_explicit_partial_status(self):
        r=decode_item_prefix(self.packet(),self.p)
        self.assertEqual(r['itemId'],12345)
        self.assertEqual(r['itemNumericValue'],0.)
        self.assertEqual(r['undecodedSuffixBytes'],1)
        self.assertFalse(r['payloadFullyDecoded'])
        self.assertEqual(r['transactionType'],'unknown')
    def test_all_item_selectors(self):
        for selector in range(8):
            expected={0:0xffffffff,2:0,5:1,7:2}.get(selector,4097)
            payload=b'\x0f'+((selector<<17)|(4<<14)).to_bytes(3,'little')
            if selector not in (0,2,5,7):payload+=self.encoded(4097)
            self.assertEqual(decode_item_prefix(payload,self.p)['itemId'],expected)
    def test_numeric_variants(self):
        inverse={v:i for i,v in enumerate(self.p['numericFieldByteMap'])}
        raw=struct.pack('<f',450.)
        if self.p['numericFieldByteOrder']=='reverse':raw=raw[::-1]
        for selector in range(8):
            p=self.packet(numeric_selector=selector,suffix=b'')
            defaults={0:-1.,4:0.,6:2.,3:1.}
            if selector not in defaults:p+=bytes(inverse[v] for v in raw)
            self.assertEqual(decode_item_prefix(p,self.p)['itemNumericValue'],defaults.get(selector,450.))
    def test_truncated_known_prefix(self):
        payload=self.packet(suffix=b'')
        for size in range(len(payload)):
            with self.subTest(size=size),self.assertRaises(ValueError):decode_item_prefix(payload[:size],self.p)
    def test_unsupported_variants_refused(self):
        for p in [b'\x0e',b'\x0f\x20\0\0',b'\x01']:
            with self.assertRaises(ValueError):decode_item_prefix(p,self.p)
    def test_scope_and_integer_overflow(self):
        with self.assertRaises(ValueError):load_item_profile('other',self.p['protocolDigest'])
        with self.assertRaises(ValueError):load_item_profile(self.p['clientVersion'],'other')
        payload=b'\x0f'+((6<<17)|(4<<14)).to_bytes(3,'little')
        with self.assertRaises(ValueError):decode_item_prefix(payload+bytes([self.inverse[255]])*5,self.p)
    def test_unknown_suffix_not_claimed_as_validated(self):
        for suffix in [b'',b'\0',bytes(range(256))]:
            r=decode_item_prefix(self.packet(suffix=suffix),self.p)
            self.assertEqual(r['undecodedSuffixBytes'],len(suffix))
            self.assertFalse(r['payloadFullyDecoded'])

    def test_gold_selectors_and_variable_balance(self):
        inverse={v:i for i,v in enumerate(self.p['goldByteMap'])}
        raw=struct.pack('<f',1234.5)
        if self.p['goldByteOrder']=='reverse':raw=raw[::-1]
        for selector in range(8):
            defaults={2:2.,5:1.,6:-1.,7:0.}
            payload=bytes([1|(selector<<1)])
            if selector not in defaults:payload+=bytes(inverse[v] for v in raw)
            payload+=self.packet()[1:]
            self.assertEqual(decode_item_prefix(payload,self.p)['goldBalance'],defaults.get(selector,1234.5))

    def test_nonfinite_gold_refused(self):
        inverse={v:i for i,v in enumerate(self.p['goldByteMap'])}
        raw=struct.pack('<f',float('inf'))
        if self.p['goldByteOrder']=='reverse':raw=raw[::-1]
        with self.assertRaises(ValueError):decode_item_prefix(b'\x01'+bytes(inverse[v] for v in raw)+self.packet()[1:],self.p)

if __name__=='__main__':unittest.main()
