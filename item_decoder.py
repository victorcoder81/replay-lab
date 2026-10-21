"""Exact-build item-update prefixes, with unknown suffixes kept explicit."""
import json
import math
from pathlib import Path
import struct
from movement_decoder import read_varuint

def load_item_profile(version, protocol):
    profile=json.loads(Path(__file__).with_name('item-16.21.json').read_text(encoding='utf8'))
    if (version,protocol)!=(profile['clientVersion'],profile['protocolDigest']):
        raise ValueError('Item profile requires exact 16.21 build and protocol.')
    for key in ('itemIdByteMap','numericFieldByteMap','goldByteMap'):
        if sorted(profile[key])!=list(range(256)):
            raise ValueError('Invalid item byte map.')
    return profile

def decode_item_prefix(payload, profile):
    if not payload:
        raise ValueError('Missing item update header.')
    header=payload[0];cursor=1
    gold_selector=(header>>1)&7
    gold_defaults={2:2.,5:1.,6:-1.,7:0.}
    if gold_selector in gold_defaults:
        gold=gold_defaults[gold_selector]
    else:
        if cursor+4>len(payload):
            raise ValueError('Truncated item gold field.')
        raw=bytes(profile['goldByteMap'][x] for x in payload[cursor:cursor+4]);cursor+=4
        if profile['goldByteOrder']=='reverse':raw=raw[::-1]
        gold=struct.unpack('<f',raw)[0]
        if not math.isfinite(gold):
            raise ValueError('Nonfinite item gold field.')
    if cursor>len(payload):
        raise ValueError('Truncated item outer prefix.')
    if not header&1:
        raise ValueError('Default nested item structure is unsupported.')
    if cursor+3>len(payload):
        raise ValueError('Truncated nested item header.')
    nested=int.from_bytes(payload[cursor:cursor+3],'little');cursor+=3
    if (nested>>5)&3:
        raise ValueError('Nonempty item string variant is unsupported.')
    selector=(nested>>17)&7
    defaults={0:0xffffffff,2:0,5:1,7:2}
    if selector in defaults:
        item=defaults[selector]
    else:
        item,cursor=read_varuint(payload,cursor,profile['itemIdByteMap'],32)
    numeric_selector=(nested>>14)&7
    numeric_defaults={0:-1.,4:0.,6:2.,3:1.}
    if numeric_selector in numeric_defaults:
        numeric=numeric_defaults[numeric_selector]
    else:
        if cursor+4>len(payload):
            raise ValueError('Truncated item numeric field.')
        raw=bytes(profile['numericFieldByteMap'][x] for x in payload[cursor:cursor+4]);cursor+=4
        if profile['numericFieldByteOrder']=='reverse':raw=raw[::-1]
        numeric=struct.unpack('<f',raw)[0]
        if not math.isfinite(numeric):
            raise ValueError('Nonfinite item numeric field.')
    return {'itemId':item,'goldBalance':gold,'goldScope':'at_item_update_only',
        'rawHeaderFlag5':bool(header&32),'rawHeaderFlag4':bool(header&16),
        'itemNumericValue':numeric,'itemNumericMeaning':'unverified',
        'decodedPrefixBytes':cursor,'undecodedSuffixBytes':len(payload)-cursor,
        'payloadFullyDecoded':False,'transactionType':'unknown'}
