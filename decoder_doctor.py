"""Read-only preflight for executable-derived decoder research.

This inspects files. It does not unpack, launch or attach to the game, and a
successful inspection never means that gameplay decoding is available.
"""
from collections import Counter
import hashlib
import math
from pathlib import Path
import re
import struct

MAX_IMAGE_BYTES = 512 * 1024 * 1024


def pe_sections(data):
    """Validate PE32+ file boundaries before using section offsets."""
    if len(data) < 64 or data[:2] != b'MZ':
        raise ValueError('Expected a Windows PE executable (MZ header).')
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    if pe + 24 > len(data) or data[pe:pe+4] != b'PE\0\0':
        raise ValueError('Invalid or truncated PE header.')
    machine, count = struct.unpack_from('<HH', data, pe+4)
    optional_size = struct.unpack_from('<H', data, pe+20)[0]
    optional = pe+24
    table = optional+optional_size
    if machine != 0x8664 or optional_size < 112 or table > len(data):
        raise ValueError('Expected a complete Windows x64 optional header.')
    if struct.unpack_from('<H', data, optional)[0] != 0x20b:
        raise ValueError('Expected a PE32+ optional header.')
    if not 1 <= count <= 96 or table+count*40 > len(data):
        raise ValueError('Invalid or truncated PE section table.')
    entries = []
    spans = []
    for index in range(count):
        offset = table+index*40
        name = data[offset:offset+8].rstrip(b'\0').decode('ascii', 'replace')
        virtual_size, rva, size, raw_offset = struct.unpack_from('<IIII', data, offset+8)
        if size and (raw_offset < table+count*40 or raw_offset+size > len(data)):
            raise ValueError('PE section extends outside file data.')
        if size and any(raw_offset < end and start < raw_offset+size for start, end in spans):
            raise ValueError('PE section file ranges overlap.')
        if size:
            spans.append((raw_offset, raw_offset+size))
        entries.append({'name':name, 'rva':rva, 'virtualSize':virtual_size,
                        'rawOffset':raw_offset, 'rawSize':size})
    return entries


def entropy(data):
    if not data:
        return 0.0
    return -sum((n/len(data))*math.log2(n/len(data)) for n in Counter(data).values())


def inspect_client(path):
    path = Path(path)
    with path.open('rb') as source:
        data = source.read(MAX_IMAGE_BYTES+1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError('Executable exceeds the 512 MiB inspection limit.')
    sections = pe_sections(data)
    text_sections = [s for s in sections if s['name'] == '.text']
    if len(text_sections) != 1 or not text_sections[0]['rawSize']:
        raise ValueError('Expected one nonempty .text section.')
    text = text_sections[0]
    # Bounded samples from across .text, rather than only its first page.
    sample_size = min(65536, text['rawSize'])
    starts = sorted({0, (text['rawSize']-sample_size)//2, text['rawSize']-sample_size})
    samples = [entropy(data[text['rawOffset']+start:text['rawOffset']+start+sample_size]) for start in starts]
    packet_names = set(re.findall(rb'PKT_[A-Za-z0-9_]{3,160}', data))
    riot_sections = [s['name'] for s in sections if s['name'].startswith('.riot')]
    # This combination is evidence of packing/encryption, not a proof of the
    # cipher or a claim that entropy alone identifies a protected image.
    protected = bool(riot_sections and not packet_names and min(samples) > 7.8)
    return {
        'schema':'replay-lab-decoder-preflight/v1',
        'clientSha256':hashlib.sha256(data).hexdigest(), 'clientBytes':len(data),
        'inspectionOnly':True, 'clientExecuted':False,
        'status':'static_analysis_blocked' if protected else 'inspection_complete_decoder_unverified',
        'evidence':{'textEntropySamplesBitsPerByte':[round(v,6) for v in samples],
                    'packetTypeNameCount':len(packet_names), 'riotSections':riot_sections,
                    'sections':sections},
        'assessment':('Packed or encrypted code is suspected. The existing static packet-registration '
                      'builder cannot be assumed to work with this file.' if protected else
                      'No packing conclusion is made. Packet registrations and decoder functions '
                      'still require exact-build recovery and independent replay validation.'),
        'gameplayDecoding':{'movement':False, 'spellCasts':False, 'positions':False},
        'requiredEvidence':['An exact-build semantic decoder tied to this executable SHA-256 and replay protocol digest.',
                            'Recovered field layouts validated on multiple independent replays.'],
        'limits':['Entropy and absent packet names are diagnostic signals, not a verified unpacking method.',
                  'This command does not check an online decoder registry or verify the executable signature.',
                  'Transport parsing and the experimental death-marker profiles do not require this executable.'],
    }


def doctor(args):
    import json
    report = inspect_client(args.client_exe)
    if args.replay:
        from replay_lab import LabReader
        with LabReader.open(args.replay) as replay:
            report['replay'] = {'clientVersion':replay.header.client_version,
                                'protocolDigest':replay.header.protocol_digest}
        report['limits'].append('Executable version equality with the replay has not been established by this inspection.')
    if args.out:
        # Exclusive creation preserves both inputs and any prior diagnostic.
        with Path(args.out).open('x', encoding='utf8') as target:
            json.dump(report, target, indent=2, allow_nan=False)
            target.write('\n')
    print(json.dumps(report, indent=2, allow_nan=False))
    return 2 if report['status'] == 'static_analysis_blocked' else 0
