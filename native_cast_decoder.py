"""Optional bounded emulation of one locally supplied recovered client image.

No image or extracted game code is distributed. Nothing from the image runs
on the host CPU directly, and no Windows imports or live game memory are used.
"""
import hashlib
import math
from pathlib import Path
import struct

IMAGE_SHA256 = '046587872c6e0dc5aae9ac9414597f52025650671912ca2f5574ed2777018865'
IMAGE_BYTES = 44904448
OPCODE = 0x403
BUILD = '16.21.829.8620'
PROTOCOL = '20e09df23c66b85e'
SPELL_NAMES = {257534500: 'MissFortuneRicochetShot', 144071859: 'MissFortuneViciousStrikes',
               131194612: 'MissFortuneScattershot', 1911189: 'MissFortuneBulletTime',
               105475752: 'SummonerFlash', 214940034: 'SummonerBarrier'}


def read_validated_image(path, version, protocol):
    if (version, protocol) != (BUILD, PROTOCOL):
        raise ValueError('Native cast reader requires exact build and protocol.')
    path = Path(path)
    if path.stat().st_size != IMAGE_BYTES:
        raise ValueError('Recovered image size mismatch.')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != IMAGE_SHA256:
        raise ValueError('Recovered image fingerprint mismatch.')
    return data


class NativeCastDecoder:
    def __init__(self, path, version, protocol):
        data = read_validated_image(path, version, protocol)
        try:
            import unicorn as uc
            from unicorn import x86_const as regs
        except ImportError as exc:
            raise ValueError('Optional native cast reader requires requirements-native.txt.') from exc
        self.uc, self.regs = uc, regs
        self.base = 0x140000000
        self.io, self.heap, self.stack, self.stop = 0x10000000, 0x11000000, 0x20000000, 0x30000000
        self.u = uc.Uc(uc.UC_ARCH_X86, uc.UC_MODE_64)
        self.u.mem_map(self.base, (len(data) + 4095) & ~4095)
        self.u.mem_write(self.base, data)
        # ROFL already carries the base entity parameter in its transport.
        self.u.mem_write(self.base + 0xffbea0, bytes.fromhex('b801000000c3'))
        for address, size in ((self.io, 0x100000), (self.heap, 0x1000000),
                              (self.stack, 0x200000), (self.stop, 4096)):
            self.u.mem_map(address, size)
        self.initial = self.u.context_save()
        self.heap_used = 0
        self.fields = {}
        self.failed = False
        self.u.hook_add(uc.UC_HOOK_CODE, self._allocate,
                        begin=self.base + 0xf33c30, end=self.base + 0xf33c30)
        self.u.hook_add(uc.UC_HOOK_MEM_WRITE, self._write,
                        begin=self.io + 40, end=self.io + 335)

    def _allocate(self, machine, address, size, user):
        regs = self.regs
        count = machine.reg_read(regs.UC_X86_REG_RCX)
        if count > 0x800000 or self.heap_used + count + 32 >= 0x1000000:
            self.failed = True
            machine.emu_stop()
            return
        result = self.heap + self.heap_used
        self.heap_used = (self.heap_used + max(count, 16) + 31) & ~15
        sp = machine.reg_read(regs.UC_X86_REG_RSP)
        target = struct.unpack('<Q', machine.mem_read(sp, 8))[0]
        machine.reg_write(regs.UC_X86_REG_RAX, result)
        machine.reg_write(regs.UC_X86_REG_RSP, sp + 8)
        machine.reg_write(regs.UC_X86_REG_RIP, target)

    def _write(self, machine, access, address, size, value, user):
        if size in (2, 4):
            self.fields[(address - self.io, size)] = value & ((1 << (8 * size)) - 1)

    def _call(self, rva, arguments):
        sp = self.stack + 0x200000 - 0x108
        self.u.mem_write(sp, struct.pack('<Q', self.stop))
        self.u.reg_write(self.regs.UC_X86_REG_RSP, sp)
        for register, value in arguments:
            self.u.reg_write(register, value)
        self.u.emu_start(self.base + rva, self.stop, count=2000000)
        if self.failed or self.u.reg_read(self.regs.UC_X86_REG_RIP) != self.stop:
            raise ValueError('Native reader exceeded its bounds or instruction budget.')

    def decode(self, payload, header_entity):
        if not payload or len(payload) > 65536:
            raise ValueError('Invalid cast payload length.')
        u, regs = self.u, self.regs
        self.failed = False
        try:
            if self.heap_used:
                u.mem_write(self.heap, bytes(self.heap_used))
            self.heap_used = 0
            u.context_restore(self.initial)
            u.mem_write(self.io, bytes(0x2000))
            self._call(0xc38bb0, [(regs.UC_X86_REG_RCX, self.io)])
            self.fields = {}
            source, cursor = self.io + 0x10000, self.io + 0x800
            u.mem_write(source, payload)
            u.mem_write(cursor, struct.pack('<Q', source))
            u.mem_write(self.io + 12, struct.pack('<I', header_entity))
            self._call(0xe76a00, [(regs.UC_X86_REG_RCX, self.io),
                                  (regs.UC_X86_REG_RDX, cursor),
                                  (regs.UC_X86_REG_R8, source + len(payload))])
            if u.reg_read(regs.UC_X86_REG_RAX) & 255 != 1:
                raise ValueError('Native cast reader rejected payload.')
            if struct.unpack('<Q', u.mem_read(cursor, 8))[0] != source + len(payload):
                raise ValueError('Native cast reader did not consume full payload.')
            def field(offset, size=4):
                return self.fields[(offset, size)]
            def real(offset):
                value = struct.unpack('<f', field(offset).to_bytes(4, 'little'))[0]
                if not math.isfinite(value):
                    raise ValueError('Nonfinite cast field.')
                return value
            spell_hash = field(316)
            return {'casterEntityId': field(104), 'headerEntityId': header_entity,
                    'spellSlot': field(320, 2), 'spellHash': spell_hash,
                    'spellName': SPELL_NAMES.get(spell_hash),
                    'unverifiedWord196': field(196, 2), 'reportedManaCost': real(48),
                    'reportedCooldownSeconds': real(84), 'reportedCastTimeSeconds': real(160),
                    'rawCastToken': field(192), 'provenance': 'bounded_local_image_emulation',
                    'castCounterEquivalent': False, 'spellCastability': 'unknown',
                    'nativePayloadConsumedFully': True, 'semanticFieldsExtracted': 'selected_only'}
        except (self.uc.UcError, KeyError, struct.error) as exc:
            raise ValueError('Cast reader failed; no approximate record emitted.') from exc
