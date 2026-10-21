from argparse import Namespace
from contextlib import redirect_stdout
import io
import struct
from pathlib import Path
import tempfile
import unittest

import decoder_doctor as doctor


def image(text=None, riot=True, names=b''):
    text = text if text is not None else bytes(range(256))*256
    sections = [('.text',text),('.rdata',names or b'\0'*32)]
    if riot:
        sections.append(('.riot0',b'\0'*32))
    data=bytearray(512)
    data[:2]=b'MZ'
    struct.pack_into('<I',data,0x3c,64)
    data[64:68]=b'PE\0\0'
    struct.pack_into('<HH',data,68,0x8664,len(sections))
    struct.pack_into('<H',data,84,112)
    struct.pack_into('<H',data,88,0x20b)
    for index,(name,body) in enumerate(sections):
        offset=200+index*40
        data[offset:offset+8]=name.encode().ljust(8,b'\0')
        struct.pack_into('<IIII',data,offset+8,len(body),4096+index*0x20000,len(body),len(data))
        data.extend(body)
    return bytes(data)


class DecoderDoctorTests(unittest.TestCase):
    def inspect(self,data):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'client.exe'
            path.write_bytes(data)
            report=doctor.inspect_client(path)
            self.assertEqual(path.read_bytes(),data)
            return report

    def test_combined_signals_block_static_builder_without_claiming_a_cipher(self):
        report=self.inspect(image())
        self.assertEqual(report['status'],'static_analysis_blocked')
        self.assertFalse(report['clientExecuted'])
        self.assertFalse(any(report['gameplayDecoding'].values()))

    def test_entropy_alone_does_not_label_encryption(self):
        self.assertEqual(self.inspect(image(riot=False))['status'],'inspection_complete_decoder_unverified')

    def test_packet_names_prevent_the_no_rtti_classification(self):
        report=self.inspect(image(names=b'.?AVPKT_Test_Spell@@\0'))
        self.assertEqual(report['evidence']['packetTypeNameCount'],1)
        self.assertEqual(report['status'],'inspection_complete_decoder_unverified')
        self.assertFalse(report['gameplayDecoding']['spellCasts'])

    def test_low_entropy_does_not_label_encryption(self):
        self.assertEqual(self.inspect(image(text=b'\x90\xc3'*1000))['status'],'inspection_complete_decoder_unverified')

    def test_bad_headers_and_section_boundaries_are_rejected(self):
        bad_range=bytearray(image())
        struct.pack_into('<I',bad_range,200+20,len(bad_range)+1)
        overlap=bytearray(image())
        struct.pack_into('<I',overlap,240+20,512)
        for data in [b'not PE',image()[:100],image()[:-1],bytes(bad_range),bytes(overlap)]:
            with self.subTest(length=len(data)):
                with self.assertRaises(ValueError):
                    doctor.pe_sections(data)

    def test_output_cannot_replace_input_or_prior_report(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'client.exe'
            original=image()
            path.write_bytes(original)
            args=Namespace(client_exe=path,replay=None,out=path)
            with self.assertRaises(FileExistsError):
                doctor.doctor(args)
            self.assertEqual(path.read_bytes(),original)

    def test_blocked_cli_returns_distinct_status_and_saves_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'client.exe'
            path.write_bytes(image())
            out=Path(directory)/'report.json'
            with redirect_stdout(io.StringIO()):
                result=doctor.doctor(Namespace(client_exe=path,replay=None,out=out))
            self.assertEqual(result,2)
            self.assertIn('static_analysis_blocked',out.read_text())


if __name__=='__main__':
    unittest.main()
