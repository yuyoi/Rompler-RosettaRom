#!/usr/bin/env python3
"""MCS-96 (Intel 8096/8097BH) disassembler with flow tracing, set up for the Roland D-110 OS ROM (IC19).

  python mcs96_dis.py ctrl/ic19.bin > ctrl/ic19.lst        full listing (traced code + data)
  python mcs96_dis.py ctrl/ic19.bin --summary              entry points, code/data map, I/O + RAM references
  python mcs96_dis.py ctrl/ic19.bin --at 2080 20           decode 20 instructions linearly from 0x2080

Decoding follows the 8x9x opcode map (no 80C196 extensions); test_mcs96_dis.py checks every decode against
MAME's i8x9x disassembler. Code is found by tracing from the reset address (0x2080) and the interrupt vectors
(0x2000-0x2011), then following jump tables (word or byte-pair, dense or sparse), code pointers held in registers
that 'br' jumps through, the UI menu descriptors (UI_MENU) and ROM code the OS copies into RAM. Anything not
reached is listed as data. See IC19_MAP.md for what the traced code does.

D-110 memory map (MAME roland_d10.cpp, CPU N8097BH @ 12 MHz, 8-bit bus):
  0x0000-0x00FF  CPU registers / SFRs        0x0100 bank latch, 0x0200 system out, 0x021A/0x021C buttons,
                                             0x0300/0x0380 LCD data/ctrl
  0x1000-0x7FFF  IC19 (file offset == CPU address)
  0x8000-0xBFFF  16 KB bank window: page n = n*0x4000 in bank space (0x00000 IC19, 0x40000 RAM,
                 0x80000 IC12 presets, 0xC0000 memory card)
  0xC000-0xFFFF  fixed RAM (= bank space 0x40000)
The output is derived from Roland's code: keep it out of git (ctrl/ is ignored).
"""
import sys, argparse

# ---- SFR names (8x9x): read name, write name ----
SFR8_R = {0x00: 'zero', 0x01: 'zero_hi', 0x02: 'ad_result_lo', 0x03: 'ad_result_hi', 0x04: 'hsi_time_lo',
          0x05: 'hsi_time_hi', 0x06: 'hsi_status', 0x07: 'sbuf', 0x08: 'int_mask', 0x09: 'int_pending',
          0x0a: 'timer1_lo', 0x0b: 'timer1_hi', 0x0c: 'timer2_lo', 0x0d: 'timer2_hi', 0x0e: 'port0',
          0x0f: 'port1', 0x10: 'port2', 0x11: 'sp_stat', 0x15: 'ios0', 0x16: 'ios1', 0x18: 'sp_lo', 0x19: 'sp_hi'}
SFR8_W = {**SFR8_R, 0x02: 'ad_command', 0x03: 'hsi_mode', 0x04: 'hso_time_lo', 0x05: 'hso_time_hi',
          0x06: 'hso_command', 0x0a: 'watchdog', 0x0e: 'baud_rate', 0x11: 'sp_con', 0x15: 'ioc0',
          0x16: 'ioc1', 0x17: 'pwm_control'}
SFR16_R = {0x00: 'zero', 0x04: 'hsi_time', 0x0a: 'timer1', 0x0c: 'timer2', 0x18: 'sp'}
SFR16_W = {0x00: 'zero', 0x04: 'hso_time', 0x18: 'sp'}

VECTORS = [(0x2000, 'int_timer_ovf'), (0x2002, 'int_ad_done'), (0x2004, 'int_hsi_data'), (0x2006, 'int_hso'),
           (0x2008, 'int_hsi0'), (0x200a, 'int_sw_timer'), (0x200c, 'int_serial'), (0x200e, 'int_extint'),
           (0x2010, 'trap')]
RESET = 0x2080

D110_IO = {0x0100: 'BANK', 0x0200: 'SYS_OUT', 0x021a: 'BTN_SC0', 0x021b: 'BTN_SC0+1', 0x021c: 'BTN_SC1',
           0x021d: 'BTN_SC1+1', 0x0280: 'LCD_AUX', 0x0300: 'LCD_DATA', 0x0380: 'LCD_CTRL', 0x0400: 'REV_LATCH_A',
           0x0800: 'REV_LATCH_B'}           # 0x021a written = output latch; 0x0c00-0x0dff = LA32 (see IC19_MAP.md)

# UI menu interpreter (v1.10). A state handler does 'ld r78, #menu' + jump to UI_MENU. Menu: dw init routine,
# then entries until 0x00: 'FE lo hi' includes another entry list; otherwise key, type, dw operand, and when
# type bit 7 is set a further dw routine run after the action. type & 0x7f is a letter from UI_TYPES; its stub
# in UI_ACTIONS calls the operand (always code) and then acts on what it returns (r78 = variable, r75 = max).
UI_MENU, UI_MENU_SIG, UI_TYPES, UI_ACTIONS, UI_ACTIONS_BR = 0x53a3, bytes.fromhex('99ff70df'), 0x5475, 0x5485, 0x5472
# key codes: 0x01-0x08 = BTN_SC0 bits 7..0, 0x09-0x10 = BTN_SC1 bits 7..0 (scan at 0x1a95); names from MAME
UI_KEYS = {0x01: 'Exit', 0x02: 'Patch', 0x03: 'Timbre', 0x04: 'Part+', 0x05: 'Group+', 0x06: 'Bank+', 0x07: 'Number+',
           0x08: 'Write', 0x09: 'Edit', 0x0a: 'Part', 0x0b: 'System', 0x0c: 'Part-', 0x0d: 'Group-', 0x0e: 'Bank-',
           0x0f: 'Number-', 0x10: 'Enter'}
UI_ACTION_NAMES = {'!': 'call', '>': 'push state', '=': 'set state', '+': '+1 (max r75)', '-': '-1 (min 0)',
                   'i': '+10 (max r75)', 'd': '-10 (min 0)', 'I': '+1 bits 0-2', 'J': '+1 bits 3-5',
                   'K': 'set bit 6', 'D': '-1 bits 0-2', 'E': '-1 bits 3-5', 'F': 'clear bit 6'}


def region(a):
    """D-110 address space class of a CPU address."""
    if a < 0x100: return 'reg'
    if a < 0x1000: return 'io'
    if a < 0x8000: return 'rom'
    if a < 0xc000: return 'win'
    return 'ram'


def regname(n, size, write):
    if size == 2 or size == 4:
        t = SFR16_W if write else SFR16_R
        if n in t: return t[n]
    t = SFR8_W if write else SFR8_R
    return t.get(n, 'r%02x' % n)


# ---- opcode table: op -> (mnemonic, form, args) ----
# forms: none, skip, r1 (one register), r2 (xch), sh (shift), norml, rel8, rel11, rel16, djnz, jb, br,
#        a2 (dst <- aop), a3 (dst <- src1 op aop), st (aop <- reg), push, pop
OPT = {}
FE = {}            # signed multiply/divide behind the 0xFE prefix
BAD = 'bad'


def _grp(tab, base, mn, form, *args):
    for aa in range(4):
        tab[base + aa] = (mn, form, args)


OPT[0x00] = ('skip', 'skip', ())
for _op, _mn, _s in ((0x01, 'clr', 2), (0x02, 'not', 2), (0x03, 'neg', 2), (0x05, 'dec', 2), (0x06, 'ext', 4),
                     (0x07, 'inc', 2), (0x11, 'clrb', 1), (0x12, 'notb', 1), (0x13, 'negb', 1), (0x15, 'decb', 1),
                     (0x16, 'extb', 2), (0x17, 'incb', 1)):
    OPT[_op] = (_mn, 'r1', (_s,))
OPT[0x04] = ('xch', 'r2', (2,))       # 80C196 opcodes; MAME decodes them for 8x9x too, flagged in the summary
OPT[0x14] = ('xchb', 'r2', (1,))
for _op, _mn, _s in ((0x08, 'shr', 2), (0x09, 'shl', 2), (0x0a, 'shra', 2), (0x0c, 'shrl', 4), (0x0d, 'shll', 4),
                     (0x0e, 'shral', 4), (0x18, 'shrb', 1), (0x19, 'shlb', 1), (0x1a, 'shrab', 1)):
    OPT[_op] = (_mn, 'sh', (_s,))
OPT[0x0f] = ('norml', 'norml', ())
for _op in range(8):
    OPT[0x20 + _op] = ('sjmp', 'rel11', ())
    OPT[0x28 + _op] = ('scall', 'rel11', ())
    OPT[0x30 + _op] = ('jbc', 'jb', ())
    OPT[0x38 + _op] = ('jbs', 'jb', ())
# 3-operand: dst size, src1 size, aop size
for _b, _mn, _d, _s in ((0x40, 'and', 2, 2), (0x44, 'add', 2, 2), (0x48, 'sub', 2, 2), (0x4c, 'mulu', 4, 2),
                        (0x50, 'andb', 1, 1), (0x54, 'addb', 1, 1), (0x58, 'subb', 1, 1), (0x5c, 'mulub', 2, 1)):
    _grp(OPT, _b, _mn, 'a3', _d, _s, _s)
_grp(FE, 0x4c, 'mul', 'a3', 4, 2, 2)
_grp(FE, 0x5c, 'mulb', 'a3', 2, 1, 1)
# 2-operand: dst size, aop size, dst is read too (False = pure load)
for _b, _mn, _d, _s, _rd in ((0x60, 'and', 2, 2, 1), (0x64, 'add', 2, 2, 1), (0x68, 'sub', 2, 2, 1),
                             (0x6c, 'mulu', 4, 2, 1), (0x70, 'andb', 1, 1, 1), (0x74, 'addb', 1, 1, 1),
                             (0x78, 'subb', 1, 1, 1), (0x7c, 'mulub', 2, 1, 1), (0x80, 'or', 2, 2, 1),
                             (0x84, 'xor', 2, 2, 1), (0x88, 'cmp', 2, 2, 2), (0x8c, 'divu', 4, 2, 1),
                             (0x90, 'orb', 1, 1, 1), (0x94, 'xorb', 1, 1, 1), (0x98, 'cmpb', 1, 1, 2),
                             (0x9c, 'divub', 2, 1, 1), (0xa0, 'ld', 2, 2, 0), (0xa4, 'addc', 2, 2, 1),
                             (0xa8, 'subc', 2, 2, 1), (0xac, 'ldbze', 2, 1, 0), (0xb0, 'ldb', 1, 1, 0),
                             (0xb4, 'addcb', 1, 1, 1), (0xb8, 'subcb', 1, 1, 1), (0xbc, 'ldbse', 2, 1, 0)):
    _grp(OPT, _b, _mn, 'a2', _d, _s, _rd)      # _rd: 0 load, 1 read-modify-write, 2 compare (no write)
_grp(FE, 0x6c, 'mul', 'a2', 4, 2, 1)
_grp(FE, 0x7c, 'mulb', 'a2', 2, 1, 1)
_grp(FE, 0x8c, 'div', 'a2', 4, 2, 1)
_grp(FE, 0x9c, 'divb', 'a2', 2, 1, 1)
for _op in (0xc0, 0xc2, 0xc3):                  # no immediate form (0xc1 is 80C196 bmov)
    OPT[_op] = ('st', 'st', (2,))
for _op in (0xc4, 0xc6, 0xc7):
    OPT[_op] = ('stb', 'st', (1,))
_grp(OPT, 0xc8, 'push', 'push')
for _op in (0xcc, 0xce, 0xcf):
    OPT[_op] = ('pop', 'pop', ())
for _i, _mn in enumerate(('jnst', 'jnh', 'jgt', 'jnc', 'jnvt', 'jnv', 'jge', 'jne',
                          'jst', 'jh', 'jle', 'jc', 'jvt', 'jv', 'jlt', 'je')):
    OPT[0xd0 + _i] = (_mn, 'rel8', ())
OPT[0xe0] = ('djnz', 'djnz', ())
OPT[0xe3] = ('br', 'br', ())
OPT[0xe7] = ('ljmp', 'rel16', ())
OPT[0xef] = ('lcall', 'rel16', ())
for _op, _mn in ((0xf0, 'ret'), (0xf2, 'pushf'), (0xf3, 'popf'), (0xf7, 'trap'), (0xf8, 'clrc'), (0xf9, 'setc'),
                 (0xfa, 'di'), (0xfb, 'ei'), (0xfc, 'clrvt'), (0xfd, 'nop'), (0xff, 'rst')):
    OPT[_op] = (_mn, 'none', ())

# control flow class per mnemonic
FLOW = {'sjmp': 'jmp', 'ljmp': 'jmp', 'scall': 'call', 'lcall': 'call', 'ret': 'ret', 'br': 'br', 'rst': 'stop',
        'trap': 'trap', 'djnz': 'jcc', 'jbc': 'jcc', 'jbs': 'jcc'}
for _i in range(16):
    FLOW[OPT[0xd0 + _i][0]] = 'jcc'


class Ins:
    """One decoded instruction. ops: tuples
       ('r', reg, size, write)      register direct
       ('#', value, nbytes)         immediate (nbytes 0 = shift count)
       ('[]', reg, autoinc, write)  indirect
       ('ix', disp, reg, long, write)  indexed; reg 0 = absolute address
       ('a', target)                code address     ('bit', n)"""
    __slots__ = ('a', 'raw', 'mn', 'ops', 'flow', 'tgt')

    def __init__(self, a, raw, mn, ops, flow=None, tgt=None):
        self.a, self.raw, self.mn, self.ops, self.flow, self.tgt = a, raw, mn, ops, flow, tgt

    @property
    def n(self): return len(self.raw)

    def mem_refs(self):
        """Absolute memory addresses this instruction names: (addr, write, how)."""
        out = []
        for o in self.ops:
            if o[0] == 'ix':
                d, r, lng = o[1], o[2], o[3]
                if r == 0:
                    out.append(((d if lng else d & 0xffff) & 0xffff, o[4], 'abs'))
                elif lng:
                    out.append((d, o[4], 'base'))
            elif o[0] == '#' and o[2] == 2:
                out.append((o[1], False, 'imm'))
        return out


def decode(mem, a):
    """Decode the instruction at CPU address a. mem(addr) -> byte."""
    op = mem(a)
    p, tab = a + 1, OPT
    if op == 0xfe:
        nx = mem(a + 1)
        if nx not in FE:
            return Ins(a, bytes([op]), BAD, [], 'bad')
        op, p, tab = nx, a + 2, FE
    if op not in tab:
        return Ins(a, bytes([op]), BAD, [], 'bad')
    mn, form, args = tab[op]
    aa = op & 3
    m = lambda k: mem(p + k)
    ops, tgt, n = [], None, 0

    def aop(k, size, write):
        """operand from addressing mode aa at p+k: (operand, nbytes)"""
        b = m(k)
        if aa == 0: return ('r', b, size, write), 1
        if aa == 1:
            if size == 1: return ('#', b, 1), 1
            return ('#', b | m(k + 1) << 8, 2), 2
        if aa == 2: return ('[]', b & 0xfe, b & 1, write), 1
        if b & 1: return ('ix', m(k + 1) | m(k + 2) << 8, b & 0xfe, True, write), 3
        d = m(k + 1)
        return ('ix', d - 256 if d >= 128 else d, b, False, write), 2

    if form == 'none':
        pass
    elif form == 'skip':
        ops, n = [('#', m(0), 1)], 1
    elif form == 'r1':
        ops, n = [('r', m(0), args[0], True)], 1
    elif form == 'r2':                                   # xch reg, reg: both written
        ops, n = [('r', m(1), args[0], True), ('r', m(0), args[0], True)], 2
    elif form == 'sh':
        c = m(0)
        cnt = ('#', c, 0) if c < 0x10 else ('r', c, 1, False)
        ops, n = [('r', m(1), args[0], True), cnt], 2
    elif form == 'norml':
        ops, n = [('r', m(1), 4, True), ('r', m(0), 1, True)], 2
    elif form == 'rel8':
        d = m(0); tgt = (p + 1 + (d - 256 if d >= 128 else d)) & 0xffff
        ops, n = [('a', tgt)], 1
    elif form == 'rel11':
        d = (op & 7) << 8 | m(0)
        if d & 0x400: d -= 0x800
        tgt = (p + 1 + d) & 0xffff
        ops, n = [('a', tgt)], 1
    elif form == 'rel16':
        tgt = (p + 2 + (m(0) | m(1) << 8)) & 0xffff
        ops, n = [('a', tgt)], 2
    elif form == 'djnz':
        d = m(1); tgt = (p + 2 + (d - 256 if d >= 128 else d)) & 0xffff
        ops, n = [('r', m(0), 1, True), ('a', tgt)], 2
    elif form == 'jb':
        d = m(1); tgt = (p + 2 + (d - 256 if d >= 128 else d)) & 0xffff
        ops, n = [('r', m(0), 1, False), ('bit', op & 7), ('a', tgt)], 2
    elif form == 'br':
        ops, n = [('[]', m(0) & 0xfe, 0, False)], 1
    elif form == 'a2':
        dsz, ssz, rd = args
        src, k = aop(0, ssz, False)
        ops, n = [('r', m(k), dsz, rd != 2), src], k + 1
    elif form == 'a3':
        dsz, s1, ssz = args
        src, k = aop(0, ssz, False)
        ops, n = [('r', m(k + 1), dsz, True), ('r', m(k), s1, False), src], k + 2
    elif form == 'st':
        dst, k = aop(0, args[0], True)
        ops, n = [('r', m(k), args[0], False), dst], k + 1
    elif form == 'push':
        src, k = aop(0, 2, False)
        ops, n = [src], k
    elif form == 'pop':
        dst, k = aop(0, 2, True)
        ops, n = [dst], k
    raw = bytes(mem(i) for i in range(a, p + n))
    return Ins(a, raw, mn, ops, FLOW.get(mn), tgt)


def fmt_op(o, label=None):
    k = o[0]
    if k == 'r': return regname(o[1], o[2], o[3])
    if k == '#': return '#%d' % o[1] if o[2] == 0 else ('#0x%02x' % o[1] if o[2] == 1 else '#0x%04x' % o[1])
    if k == '[]': return '[%s]%s' % (regname(o[1], 2, False), '+' if o[2] else '')
    if k == 'ix':
        d, r, lng = o[1], o[2], o[3]
        if r == 0: return '0x%04x' % (d & 0xffff)
        if lng: return '0x%04x[%s]' % (d, regname(r, 2, False))
        return '%s0x%02x[%s]' % ('-' if d < 0 else '', abs(d), regname(r, 2, False))
    if k == 'a': return (label(o[1]) if label else None) or '0x%04x' % o[1]
    if k == 'bit': return str(o[1])
    return '?'


def fmt_ins(i, label=None):
    if i.mn == BAD: return 'db      0x%02x ; invalid opcode' % i.raw[0]
    return ('%-7s %s' % (i.mn, ', '.join(fmt_op(o, label) for o in i.ops))).rstrip()


class Rom:
    def __init__(self, data, base=0):
        self.d, self.base = data, base

    def __call__(self, a):
        o = a - self.base
        return self.d[o] if 0 <= o < len(self.d) else 0xff

    def has(self, a): return 0 <= a - self.base < len(self.d)

    def word(self, a): return self(a) | self(a + 1) << 8


class D110(Rom):
    """IC19 as the CPU sees it: 0x1000-0x7fff direct, 0x8000-0xbfff through the bank window assumed on page 0
    (IC19 0x0000-0x3fff). The OS selects page 0 to run code in IC19's low 4 KB (stb #0 -> 0x0100; lcall 0x8a00)."""
    def __init__(self, data):
        super().__init__(data)
        self.copies = []            # (cpu dst, cpu src, length): ROM code the OS copies into RAM and runs there

    @property
    def ranges(self):               # listing order: IC19 file order, then RAM copies
        return ((0x8000, 0x9000), (0x1000, 0x8000)) + tuple((d, d + n) for d, s, n in self.copies)

    def off(self, a):
        for d, s, n in self.copies:
            if d <= a < d + n: return self.off(s + a - d)
        if 0x1000 <= a < 0x8000: return a
        if 0x8000 <= a < 0xc000: return a - 0x8000
        return None

    def __call__(self, a):
        o = self.off(a)
        return self.d[o] if o is not None and o < len(self.d) else 0xff

    def has(self, a):
        o = self.off(a)
        return o is not None and o < len(self.d)


# ---- flow tracing ----
class Trace:
    def __init__(self, rom):
        self.rom = rom
        self.ins = {}          # addr -> Ins
        self.owner = {}        # byte addr -> start of the instruction covering it
        self.labels = {}       # addr -> name
        self.kind = {}         # addr -> 'vec' | 'sub' | 'loc' | 'dat'
        self.xref = {}         # target -> set of source addrs
        self.problems = []     # (addr, text)
        self.jtabs = {}        # table addr -> (n entries, br site)
        self.data_refs = {}    # addr -> set of source addrs (absolute data refs into the ROM)
        self.outside = set()   # flow targets outside known code space (retried after RAM copies are found)
        self.ptr_imm = {}      # instruction addr -> code address its immediate operand points to
        self.menu_rows = {}    # addr -> (length, text, label targets, note): decoded UI menu descriptors
        self.menu_bad = set()  # menus that failed to decode (reported once)
        self.menu_imm = {}     # instruction addr -> menu its 'ld r78, #imm' passes to the interpreter
        self.menu_bytes = set()

    def in_code(self, a):
        if 0x9000 <= a < 0xc000: return False                  # window aliases of 0x1000-0x3fff: not code
        return a >= 0x1000 and self.rom.has(a)

    def add_label(self, a, kind, name=None):
        rank = {'vec': 3, 'sub': 2, 'loc': 1, 'dat': 0}
        if a not in self.kind or rank[kind] > rank[self.kind[a]]:
            self.kind[a] = kind
            self.labels[a] = name or {'sub': 'sub_%04x', 'loc': 'L%04x', 'dat': 'd_%04x'}[kind] % a

    def run(self, entries):
        work = list(entries)
        while work:
            a = work.pop()
            while True:
                if a in self.ins: break
                if not self.in_code(a):
                    self.outside.add(a)
                    break
                if a in self.owner:
                    self.problems.append((a, 'jump into the middle of the instruction at 0x%04x' % self.owner[a]))
                    break
                i = decode(self.rom, a)
                clash = [b for b in range(a, a + i.n)
                         if b in self.owner or b in self.jtab_bytes() or b in self.menu_bytes]
                if clash:
                    self.problems.append((a, 'instruction overlaps code/table at 0x%04x' % clash[0]))
                    break
                if i.flow == 'bad':
                    self.problems.append((a, 'invalid opcode 0x%02x' % i.raw[0]))
                    break
                self.ins[a] = i
                for b in range(a, a + i.n): self.owner[b] = a
                for addr, w, how in i.mem_refs():
                    if how != 'imm' and 0x1000 <= addr < 0x8000 and self.rom.has(addr):
                        self.data_refs.setdefault(addr, set()).add(a)
                f = i.flow
                if f in ('jmp', 'jcc', 'call'):
                    self.xref.setdefault(i.tgt, set()).add(a)
                    self.add_label(i.tgt, 'sub' if f == 'call' else 'loc')
                    work.append(i.tgt)
                if f in ('jmp', 'ret', 'br', 'stop', 'trap'):
                    break                               # trap: the D-110 handler reports and never returns
                a += i.n

    _jb = None

    def jtab_bytes(self):
        if self._jb is None:
            self._jb = {t + k for t, (n, _) in self.jtabs.items() for k in range(2 * n)}
        return self._jb

    def closure_ok(self, v, maxins=3000):
        """Speculative trace from v (all paths, nothing recorded): (ok, instructions). ok means no invalid
        opcode, no overlap with known code or tables, no jump into an instruction and no flow outside code."""
        seen, own, work = set(), set(), [v]
        jb = self.jtab_bytes()
        while work:
            a = work.pop()
            while a not in seen and a not in self.ins:
                if not self.in_code(a) or a in self.owner or a in own: return False, len(seen)
                i = decode(self.rom, a)
                if i.flow == 'bad' or any(b in self.owner or b in own or b in jb or b in self.menu_bytes
                                          for b in range(a, a + i.n)):
                    return False, len(seen)
                seen.add(a)
                own.update(range(a, a + i.n))
                if len(seen) > maxins: return False, len(seen)
                if i.flow in ('jmp', 'jcc', 'call'): work.append(i.tgt)
                if i.flow in ('jmp', 'ret', 'br', 'stop', 'trap'): break
                a += i.n
        return True, len(seen)

    def find_code_pointers(self):
        """Immediates that are code addresses: (1) loaded into / compared with a register that a 'br [r]'
        jumps through, when every ROM-range immediate seen for that register validates (rb4, the UI state
        handler in the D-110 OS); (2) 'cmp rX, #addr' where addr starts a clean closure of >= 16 instructions
        (handler identity checks)."""
        br_regs = {i.ops[0][1] for i in self.ins.values() if i.mn == 'br'}
        by_reg = {}
        for i in self.ins.values():
            if i.mn in ('ld', 'cmp') and i.ops[0][0] == 'r' and i.ops[1][0] == '#' and i.ops[1][2] == 2:
                by_reg.setdefault(i.ops[0][1], []).append(i)
        new, check = [], {}
        ok = lambda v: check.setdefault(v, (True, 99) if v in self.ins else self.closure_ok(v))
        for r, lst in by_reg.items():
            rom_vals = [i for i in lst if 0x1000 <= i.ops[1][1] < 0x8000]
            reg_ptr = (r in br_regs and len(rom_vals) >= 2 and len(rom_vals) >= 0.8 * len(lst)
                       and all(ok(i.ops[1][1])[0] for i in rom_vals))
            for i in rom_vals:
                v = i.ops[1][1]
                if not (reg_ptr or (i.mn == 'cmp' and ok(v)[0] and ok(v)[1] >= 16)): continue
                self.ptr_imm[i.a] = v
                self.xref.setdefault(v, set()).add(i.a)
                self.add_label(v, 'sub')
                if v not in self.ins: new.append(v)
        return new

    def find_ram_copies(self):
        """'ld rS, #src / ld rD, #dst / ldb rT, [rS]+ / stb rT, [rD]+ / cmp rS, #end': ROM code copied to RAM."""
        found = []
        for a, i in sorted(self.ins.items()):
            if not (i.mn == 'ldb' and i.ops[1][0] == '[]' and i.ops[1][2]): continue
            rt, rs = i.ops[0][1], i.ops[1][1]
            nxt = self.ins.get(a + i.n)
            if not (nxt and nxt.mn == 'stb' and nxt.ops[0][1] == rt and nxt.ops[1][0] == '[]' and nxt.ops[1][2]): continue
            rd = nxt.ops[1][1]
            cmp = self.ins.get(nxt.a + nxt.n)
            if not (cmp and cmp.mn == 'cmp' and cmp.ops[0][1] == rs and cmp.ops[1][0] == '#'): continue
            src = dst = None
            p = a
            for _ in range(4):
                q = self.owner.get(p - 1)
                if q is None or q not in self.ins: break
                qi = self.ins[q]
                if qi.mn == 'ld' and qi.ops[1][0] == '#':
                    if qi.ops[0][1] == rs and src is None: src = qi.ops[1][1]
                    if qi.ops[0][1] == rd and dst is None: dst = qi.ops[1][1]
                p = q
            if src is None or dst is None or dst < 0xc000 or not self.rom.has(src): continue
            n = cmp.ops[1][1] - src
            if 0 < n <= 0x1000 and (dst, src, n) not in self.rom.copies:
                self.rom.copies.append((dst, src, n))
                found.append((dst, src, n, a))
        return found

    def find_jump_tables(self):
        """Code pointer tables: 'ld rX, TABLE[rY]' (or the pair 'ldb rX, TABLE[rY]' + 'ldb rX+1, TABLE+1[rY]')
        with TABLE in fixed ROM (or in the window just before a 'br [rX]' in the same block) and rX a register
        some 'br [rX]' jumps through. Entries are read until one does not point to code, reaches the table's own
        targets, or passes a 'cmp rY, #N' bound. When the load is followed by 'cmp rX, #0' the table is sparse:
        zero entries mean 'no handler' (the MIDI controller table at 0x3bce)."""
        br_regs = {i.ops[0][1] for i in self.ins.values() if i.mn == 'br'}
        new = []
        for a, i in sorted(self.ins.items()):
            if not (i.mn in ('ld', 'ldb') and i.ops[1][0] == 'ix' and i.ops[1][3] and i.ops[1][2] != 0): continue
            rx, base, last = i.ops[0][1], i.ops[1][1], i
            if i.mn == 'ldb':
                hi = self.ins.get(a + i.n)
                if not (rx % 2 == 0 and hi and hi.mn == 'ldb' and hi.ops[0][1] == rx + 1 and hi.ops[1][0] == 'ix'
                        and hi.ops[1][1:3] == (base + 1, i.ops[1][2])): continue
                last = hi
            nx = self.ins.get(last.a + last.n)
            holes = bool(nx and nx.mn == 'cmp' and nx.ops[0][:2] == ('r', rx) and nx.ops[1][:2] == ('#', 0))
            if rx not in br_regs or base in self.jtabs or not self.in_code(base): continue
            if not 0x1000 <= base < 0x8000 and not self._br_follows(a, rx): continue
            limit, p = 256, a
            for _ in range(10):                         # index range check shortly before the load
                q = self.owner.get(p - 1)
                if q is None or q not in self.ins: break
                qi = self.ins[q]
                if qi.flow in ('jmp', 'ret', 'br', 'stop'): break
                if qi.mn in ('cmp', 'cmpb') and qi.ops[1][0] == '#':
                    limit = qi.ops[1][1] + 1
                    break
                p = q
            n, tgts = 0, set()
            while n < limit:
                e = base + 2 * n
                if e in self.owner or e + 1 in self.owner or (n and e in self.labels) or e in tgts: break
                if e in self.menu_bytes: break
                if tgts and base < min(tgts) <= e: break
                tgt = self.rom.word(e)
                if tgt == 0 and holes:
                    n += 1
                    continue
                if not self.in_code(tgt) or decode(self.rom, tgt).flow == 'bad': break
                if (tgt < 0x8000) != (base < 0x8000): break             # fixed tables -> fixed code etc.
                if tgt in self.owner and tgt not in self.ins: break      # middle of a known instruction
                tgts.add(tgt)
                n += 1
            while n and holes and self.rom.word(base + 2 * (n - 1)) == 0: n -= 1
            if len(tgts) >= 2:
                self.jtabs[base] = (n, a)
                self._jb = None
                self.add_label(base, 'loc', 'jtab_%04x' % base)
                for k in range(n):
                    tgt = self.rom.word(base + 2 * k)
                    if tgt == 0: continue
                    self.xref.setdefault(tgt, set()).add(base + 2 * k)
                    self.add_label(tgt, 'loc')
                    new.append(tgt)
        return new

    def _br_follows(self, a, rx):
        p = a
        for _ in range(8):
            i = self.ins.get(p)
            if i is None: return False
            if i.mn == 'br': return i.ops[0][1] == rx
            if i.flow in ('jmp', 'ret', 'stop'): return False
            p += i.n
        return False

    def find_menus(self):
        """UI menu descriptors (see UI_MENU): 'ld r78, #menu' followed within 3 instructions by a jump or call to
        the interpreter. Decodes each menu and returns the code it points to (init, operands, after-routines)."""
        rom = self.rom
        if bytes(rom(UI_MENU + k) for k in range(len(UI_MENU_SIG))) != UI_MENU_SIG: return []
        letters = ''
        while rom(UI_TYPES + len(letters)) and len(letters) < 32: letters += chr(rom(UI_TYPES + len(letters)))
        new = []
        if UI_ACTIONS not in self.jtabs:
            self.jtabs[UI_ACTIONS] = (len(letters), UI_ACTIONS_BR)
            self._jb = None
        for x, kind, name in [(UI_ACTIONS, 'loc', 'ui_actions'), (UI_TYPES, 'dat', 'ui_types')] + \
                [(rom.word(UI_ACTIONS + 2 * k), 'loc', 'ui_act_%02x' % ord(c)) for k, c in enumerate(letters)]:
            if self.labels.get(x) == name: continue
            self.kind[x], self.labels[x] = kind, name
            if kind == 'loc' and x != UI_ACTIONS: new.append(x)
        for a, i in sorted(self.ins.items()):
            if not (i.mn == 'ld' and i.ops[0][:2] == ('r', 0x78) and i.ops[1][0] == '#'): continue
            p, j = a + i.n, None
            for _ in range(3):
                j = self.ins.get(p)
                if j is None or j.flow: break
                p += j.n
            if j is None or j.flow not in ('jmp', 'call'): continue
            m = i.ops[1][1]
            if j.tgt != UI_MENU:
                handler = m in self.ins or (self.in_code(m) and m < 0x8000 and self.closure_ok(m)[0])
                if handler and self._state_setter(j.tgt):
                    if a not in self.ptr_imm:
                        self.ptr_imm[a] = m
                        self.xref.setdefault(m, set()).add(a)
                        self.add_label(m, 'sub')
                        new.append(m)
                continue
            self.menu_imm[a] = m
            if m not in self.menu_rows and m not in self.menu_bad: new += self._menu(m, letters, a)
        return [x for x in new if x not in self.ins]

    def _state_setter(self, x):
        """True if the straight-line code at x (calls stepped over) copies r78 into a register that a 'br [r]'
        jumps through: the r78 passed in is then a UI state handler (0x57d1: push state, rb4 = r78)."""
        br_regs = {i.ops[0][1] for i in self.ins.values() if i.mn == 'br'}
        for _ in range(6):
            i = self.ins.get(x)
            if i is None: return False
            if i.mn == 'ld' and i.ops[1][:2] == ('r', 0x78) and i.ops[0][1] in br_regs: return True
            if i.flow in ('jmp', 'ret', 'br', 'stop', 'trap'): return False
            x += i.n
        return False

    def _menu(self, m, letters, site):
        """Decode one menu (with its includes) and commit it only if every byte and pointer checks out."""
        rom, rows, tgts = self.rom, {}, []
        busy = lambda x, n: any(b in self.owner or b in self.menu_bytes or b in rows for b in range(x, x + n))

        def code(x, src):
            if (not self.in_code(x) or x >= 0x8000 or decode(rom, x).flow == 'bad'
                    or (x in self.owner and x not in self.ins)):
                raise ValueError('0x%04x (at 0x%04x) is not code' % (x, src))
            tgts.append((x, src))
            return x

        def entries(a, depth):
            if depth > 4: raise ValueError('includes nest too deep at 0x%04x' % a)
            for _ in range(64):
                if a in self.menu_rows or a in rows: return         # tail shared with a list already decoded
                k = rom(a)
                if k == 0:
                    rows[a] = (1, 'menu    end', (), '')
                    return
                if k == 0xfe:
                    inc = rom.word(a + 1)
                    rows[a] = (3, 'menu    include %s', (inc,), '')
                    if inc not in self.menu_rows and inc not in rows: entries(inc, depth + 1)
                    a += 3
                    continue
                t = rom(a + 1)
                c = chr(t & 0x7f)
                if c not in letters: raise ValueError('unknown action 0x%02x at 0x%04x' % (t, a))
                n = 6 if t & 0x80 else 4
                if busy(a, n): raise ValueError('entry at 0x%04x overlaps code or another menu' % a)
                op = code(rom.word(a + 2), a)
                txt = 'key %02x %-7s %r %%s' % (k, UI_KEYS.get(k, ''), c)
                ops = (op,)
                if n == 6:
                    txt += ', then %s'
                    ops += (code(rom.word(a + 4), a),)
                rows[a] = (n, txt, ops, UI_ACTION_NAMES.get(c, 'action %r' % c))
                a += n
            raise ValueError('no end marker within 64 entries')

        try:
            if busy(m, 2): raise ValueError('menu overlaps code')
            rows[m] = (2, 'menu    init %s', (code(rom.word(m), m),), 'run on entry and refresh')
            entries(m + 2, 0)
        except ValueError as e:
            self.problems.append((site, 'menu 0x%04x not decoded: %s' % (m, e)))
            self.menu_bad.add(m)
            return []
        self.add_label(m, 'dat', 'menu_%04x' % m)
        for a, row in rows.items():
            n, txt, ops, _ = self.menu_rows[a] = row
            self.menu_bytes.update(range(a, a + n))
            if txt.startswith('menu    include'): self.add_label(ops[0], 'dat', 'menu_%04x' % ops[0])
        for x, src in tgts:
            self.xref.setdefault(x, set()).add(src)
            self.add_label(x, 'sub')
        return [x for x, _ in tgts]


def build(rom, extra_entries=()):
    t = Trace(rom)
    entries = []
    for v, name in VECTORS:
        tgt = rom.word(v)
        if tgt != 0xffff and t.in_code(tgt):
            t.add_label(tgt, 'vec', name)
            entries.append(tgt)
    t.add_label(RESET, 'vec', 'reset')
    entries.append(RESET)
    p = RESET + decode(rom, RESET).n                    # D-110: sjmp/ljmp vector run after the reset jump,
    while decode(rom, p).mn in ('sjmp', 'ljmp'):        # called by the bank-window code as an API
        t.add_label(p, 'vec', 'api_%04x' % p)
        entries.append(p)
        p += decode(rom, p).n
    for e in extra_entries:
        t.add_label(e, 'sub')
        entries.append(e)
    t.run(entries)
    while True:
        new = t.find_jump_tables() + t.find_menus()
        if hasattr(rom, 'copies'):
            for dst, src, n, site in t.find_ram_copies():
                t.add_label(dst, 'sub', 'ram_%04x' % dst)
                t.problems.append((site, 'note: copies 0x%04x-0x%04x to RAM 0x%04x, traced there' % (src, src + n - 1, dst)))
        if not new: new = t.find_code_pointers()
        new += [a for a in t.outside if t.in_code(a)]
        t.outside -= set(new)
        if not new: break
        t.run(new)
    for a in sorted(t.outside):
        src = sorted(s for s, i in t.ins.items() if i.tgt == a)
        t.problems.append((a, 'flow leaves code space (from %s)' % ' '.join('%04x' % x for x in src)))
    for a in t.data_refs:
        if a not in t.ins: t.add_label(a, 'dat')
    return t


# ---- output ----
def comment_for(t, i):
    notes = []
    for addr, w, how in i.mem_refs():
        if how == 'imm':
            if 0x100 <= addr < 0x1000 and addr in D110_IO: notes.append('#%s' % D110_IO[addr])
            continue
        r = region(addr)
        if r == 'reg': continue
        name = D110_IO.get(addr) or ('LA32' if 0x0c00 <= addr < 0x0e00 else '') or t.labels.get(addr) or ''
        notes.append(('%s %s' % (r, name)).strip() if how == 'abs' else 'table %s %s' % (r, name))
    if i.a in t.ptr_imm:
        notes.append('code ptr -> %s' % t.labels.get(t.ptr_imm[i.a], '0x%04x' % t.ptr_imm[i.a]))
    if i.a in t.menu_imm:
        notes.append('menu -> %s' % t.labels.get(t.menu_imm[i.a], '0x%04x' % t.menu_imm[i.a]))
    if i.a in t.ins and i.flow in ('call', 'jmp') and i.tgt in t.labels and t.labels[i.tgt].startswith(('int_', 'trap', 'reset')):
        notes.append(t.labels[i.tgt])
    return '; ' + ', '.join(notes) if notes else ''


def listing(t, out):
    rom = t.rom
    w = out.write
    w('; MCS-96 listing, %d instructions traced, %d jump tables, %d problems\n' %
      (len(t.ins), len(t.jtabs), len(t.problems)))
    for a, msg in t.problems: w(';   problem at 0x%04x: %s\n' % (a, msg))
    w('; vectors:\n')
    for v, name in VECTORS: w(';   0x%04x %-14s -> 0x%04x\n' % (v, name, rom.word(v)))
    lab = lambda x: t.labels.get(x)
    jb = t.jtab_bytes()
    ranges = getattr(rom, 'ranges', ((rom.base, rom.base + len(rom.d)),))
    alias = sorted(a for a in t.ins if 0x9000 <= a < 0xc000)
    for lo, end in ranges + (((alias[0], alias[-1] + 8),) if alias else ()):
        if lo >= 0x8000:
            w('\n; ======== 0x%04x-0x%04x: bank window, page 0 assumed (IC19 offset 0x%04x-) ========\n' %
              (lo, end - 1, lo - 0x8000))
        else:
            w('\n; ======== 0x%04x-0x%04x: IC19, fixed ========\n' % (lo, end - 1))
        a = lo
        while a < end:
            if a in t.labels:
                refs = sorted(t.xref.get(a, ())) or sorted(t.data_refs.get(a, ()))
                more = ' ...' if len(refs) > 6 else ''
                w('\n%s:%s\n' % (t.labels[a], ('    ; from ' + ' '.join('%04x' % r for r in refs[:6]) + more) if refs else ''))
            if a in t.ins:
                i = t.ins[a]
                w('  %04x  %-20s  %-38s %s\n' % (a, i.raw.hex(' '), fmt_ins(i, lab), comment_for(t, i)))
                a += i.n
                continue
            if a >= 0x9000:                                     # alias section: code only
                a += 1
                continue
            if a in t.menu_rows:
                n, txt, ops, note = t.menu_rows[a]
                body = txt % tuple(lab(x) or '0x%04x' % x for x in ops)
                w(('  %04x  %-20s  %-38s %s' % (a, ' '.join('%02x' % rom(x) for x in range(a, a + n)), body,
                                                 '; ' + note if note else '')).rstrip() + '\n')
                a += n
                continue
            if a in t.jtabs:
                n, site = t.jtabs[a]
                for k in range(n):
                    e = a + 2 * k
                    tgt = rom.word(e)
                    w('  %04x  %02x %02x                 dw      %-30s ; [%d] for br at %04x\n' %
                      (e, rom(e), rom(e + 1), lab(tgt) or '0x%04x' % tgt, k, site))
                a += 2 * n
                continue
            # data run up to the next code / table / label, 16 bytes per line
            b = a + 1
            while (b < end and b - a < 16 and b not in t.ins and b not in t.labels and b not in jb
                   and b not in t.menu_rows):
                b += 1
            chunk = bytes(rom(x) for x in range(a, b))
            if all(x == 0xff for x in chunk):
                c = b
                while (c < end and rom(c) == 0xff and c not in t.ins and c not in t.labels and c not in jb
                       and c not in t.menu_rows): c += 1
                w('  %04x  ff x %d\n' % (a, c - a))
                a = c
                continue
            txt = ''.join(chr(x) if 32 <= x < 127 else '.' for x in chunk)
            w('  %04x  %-48s  db  |%s|\n' % (a, chunk.hex(' '), txt))
            a = b


def summary(t, out):
    rom, w = t.rom, out.write
    code = len(t.owner)
    jt = sum(2 * n for n, _ in t.jtabs.values())
    w('IC19 summary: %d bytes, %d instructions (%d code bytes), %d jump tables (%d bytes), %d UI menus (%d bytes)\n' %
      (len(rom.d), len(t.ins), code, len(t.jtabs), jt, len(set(t.menu_imm.values())), len(t.menu_bytes)))
    w('subroutines %d, local labels %d\n' % (sum(1 for k in t.kind.values() if k == 'sub'),
                                             sum(1 for k in t.kind.values() if k == 'loc')))
    w('\nentry points:\n  0x%04x reset\n' % RESET)
    for v, name in VECTORS:
        x = rom.word(v)
        w('  0x%04x %-14s %s\n' % (x, name, '(unused)' if x == 0xffff else ''))
    w('\nproblems (%d):\n' % len(t.problems))
    for a, msg in t.problems[:40]: w('  0x%04x %s\n' % (a, msg))
    # code / data map in 256-byte rows
    w('\nmap, one char per 64 bytes: C code, c some code, T jump table, M UI menus, . data, - FF fill\n')
    jb = t.jtab_bytes()
    for row in list(range(0x8000, 0x9000, 0x1000)) + list(range(0x1000, 0x8000, 0x1000)):
        s = ''
        for blk in range(row, row + 0x1000, 64):
            cb = sum(1 for b in range(blk, blk + 64) if b in t.owner)
            tb = sum(1 for b in range(blk, blk + 64) if b in jb)
            mb = sum(1 for b in range(blk, blk + 64) if b in t.menu_bytes)
            ff = all(rom(b) == 0xff for b in range(blk, blk + 64))
            s += 'C' if cb >= 32 else 'T' if tb >= 32 else 'M' if mb >= 32 else '-' if ff else 'c' if cb else '.'
        w('  %04x %s%s\n' % (row, s, '  (window page 0 = IC19 0x0000)' if row >= 0x8000 else ''))
    # references by address class
    io, ram, win, rdat = {}, {}, {}, {}
    used = {}
    for a, i in t.ins.items():
        used[i.mn] = used.get(i.mn, 0) + 1
        for addr, wr, how in i.mem_refs():
            r = region(addr)
            d = {'io': io, 'ram': ram, 'win': win, 'rom': rdat}.get(r)
            if d is None: continue
            if how == 'imm' and r != 'io': continue
            e = d.setdefault(addr, [0, 0, 0, set()])
            e[0 if how == 'imm' else 1 if not wr else 2] += 1
            e[3].add(a)
    for title, d in (('I/O (0x0100-0x0fff): imm / read / write', io), ('bank window (0x8000-0xbfff)', win),
                     ('fixed RAM (0xc000-0xffff)', ram), ('ROM data (0x1000-0x7fff)', rdat)):
        w('\n%s: %d addresses\n' % (title, len(d)))
        lim = 60 if d is io else 20
        for addr in sorted(d)[:lim]:
            e = d[addr]
            w('  0x%04x %-10s %3d %3d %3d   e.g. %s\n' % (addr, D110_IO.get(addr, ''), e[0], e[1], e[2],
                                                      ' '.join('%04x' % x for x in sorted(e[3])[:4])))
        if len(d) > lim: w('  ... %d more\n' % (len(d) - lim))
    rare = [m for m in ('xch', 'xchb', 'rst', 'trap', 'br', 'norml', 'mul', 'mulb', 'div', 'divb') if m in used]
    w('\nnotable instructions: %s\n' % ', '.join('%s x%d' % (m, used[m]) for m in rare))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('rom')
    ap.add_argument('--summary', action='store_true')
    ap.add_argument('--at', nargs=2, metavar=('ADDR', 'COUNT'), help='linear decode (hex address, count)')
    ap.add_argument('--entry', action='append', default=[], help='extra code entry point (hex)')
    ap.add_argument('-o', '--out')
    a = ap.parse_args(argv)
    rom = D110(open(a.rom, 'rb').read())
    out = open(a.out, 'w') if a.out else sys.stdout
    if a.at:
        p = int(a.at[0], 16)
        for _ in range(int(a.at[1])):
            i = decode(rom, p)
            out.write('%04x  %-20s  %s\n' % (p, i.raw.hex(' '), fmt_ins(i)))
            p += i.n
        return
    t = build(rom, [int(x, 16) for x in a.entry])
    (summary if a.summary else listing)(t, out)


if __name__ == '__main__':
    main()
