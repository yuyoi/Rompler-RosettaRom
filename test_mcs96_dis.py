"""Checks mcs96_dis.py.
1. Hand-assembled cases from the 8096 opcode map (no ROM needed).
2. If mame_ref/mame_dasm exists (sh mame_ref/build.sh): every byte offset of a random 64 KB image, and of
   ctrl/ic19.bin if present, decoded by both; length and operands must match MAME's i8x9x disassembler.
"""
import os, re, random, subprocess, sys
from mcs96_dis import decode, fmt_ins, Rom


def at(hexbytes, a=0x2000):
    rom = Rom(bytes.fromhex(hexbytes), a)
    i = decode(rom, a)
    return i.n, fmt_ins(i)


CASES = [  # bytes, address, expected length, expected text
    ('a1 00 01 18', 0x2000, 4, 'ld      sp, #0x0100'),
    ('c3 01 e0 f9 d2', 0x2000, 5, 'st      rd2, 0xf9e0'),            # long indexed off r0 = absolute
    ('a3 18 02 d2', 0x2000, 4, 'ld      rd2, 0x02[sp]'),
    ('47 1c fe 20 30', 0x2000, 5, 'add     r30, r20, -0x02[r1c]'),
    ('47 31 34 12 20 30', 0x2000, 6, 'add     r30, r20, 0x1234[r30]'),
    ('fe 4f 31 34 12 20 30', 0x2000, 7, 'mul     r30, r20, 0x1234[r30]'),
    ('fe 6c 1c 20', 0x2000, 4, 'mul     r20, r1c'),
    ('4d 34 12 20 30', 0x2000, 5, 'mulu    r30, r20, #0x1234'),
    ('5d 05 20 30', 0x2000, 4, 'mulub   r30, r20, #0x05'),           # byte immediate
    ('9d 05 30', 0x2000, 3, 'divub   r30, #0x05'),
    ('8d 05 00 30', 0x2000, 4, 'divu    r30, #0x0005'),
    ('ad 05 30', 0x2000, 3, 'ldbze   r30, #0x05'),
    ('b2 31 20', 0x2000, 3, 'ldb     r20, [r30]+'),
    ('c9 34 12', 0x2000, 3, 'push    #0x1234'),
    ('cb 31 34 12', 0x2000, 4, 'push    0x1234[r30]'),
    ('cf 1c 04', 0x2000, 3, 'pop     0x04[r1c]'),
    ('c7 1c 04 20', 0x2000, 4, 'stb     r20, 0x04[r1c]'),
    ('09 04 1c', 0x2000, 3, 'shl     r1c, #4'),
    ('09 30 1c', 0x2000, 3, 'shl     r1c, r30'),                   # count >= 0x10 is a register
    ('0f 30 1c', 0x2000, 3, 'norml   r1c, r30'),
    ('e0 30 fe', 0x2000, 3, 'djnz    r30, 0x2001'),
    ('37 30 05', 0x2000, 3, 'jbc     r30, 7, 0x2008'),
    ('27 ff', 0x2000, 2, 'sjmp    0x2001'),                         # 11-bit displacement -1
    ('20 6d', 0x2080, 2, 'sjmp    0x20ef'),
    ('2f a8', 0x19e1, 2, 'scall   0x198b'),
    ('ef fd ff', 0x2000, 3, 'lcall   0x2000'),
    ('d7 80', 0x2000, 2, 'jne     0x1f82'),
    ('e3 31', 0x2000, 2, 'br      [r30]'),                          # the CPU ignores bit 0
    ('00 55', 0x2000, 2, 'skip    #0x55'),
    ('b1 19 06', 0x2000, 3, 'ldb     hso_command, #0x19'),
    ('90 16 e7', 0x2000, 3, 'orb     re7, ios1'),
    ('cd 00', 0x2000, 1, 'db      0xcd ; invalid opcode'),          # 80C196 only
    ('fe 00', 0x2000, 1, 'db      0xfe ; invalid opcode'),
]

fails = 0
for hx, a, n, txt in CASES:
    got = at(hx, a)
    if got != (n, txt):
        fails += 1
        print('FAIL %-22s want %d %-30r got %d %r' % (hx, n, txt, *got))
print('hand cases: %d/%d ok' % (len(CASES) - fails, len(CASES)))

# ---- MAME comparison ----
MAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mame_ref', 'mame_dasm')
NAMES = {'0': 0x00, 'int_mask': 0x08, 'int_pending': 0x09, 'sp': 0x18, 'al': 0x1c, 'ah': 0x1d, 'dl': 0x1e,
         'dh': 0x1f, 'bl': 0x20, 'bh': 0x21, 'cl': 0x22, 'ch': 0x23, 'ax': 0x1c, 'dx': 0x1e, 'bx': 0x20,
         'cx': 0x22, 'ad_command': 0x02, 'ad_result_lo': 0x02, 'hsi_mode': 0x03, 'ad_result_hi': 0x03,
         'hso_command': 0x06, 'hsi_status': 0x06, 'sbuf': 0x07, 'watchdog': 0x0a, 'baud_rate': 0x0e,
         'port0': 0x0e, 'port1': 0x0f, 'port2': 0x10, 'sp_con': 0x11, 'sp_stat': 0x11, 'ioc0': 0x15,
         'ios0': 0x15, 'ioc1': 0x16, 'ios1': 0x16, 'pwm_control': 0x17, 'hso_time': 0x04, 'hsi_time': 0x04,
         'timer1': 0x0a, 'timer2': 0x0c}
NAME_RE = re.compile(r'(?<![#\w])(%s)(?!\w)' % '|'.join(sorted(NAMES, key=len, reverse=True)))


def mame_norm(s):
    s = s.strip()
    sub = lambda t: NAME_RE.sub(lambda m: '%02x' % NAMES[m.group(1)], t)
    if s.startswith(('jbc ', 'jbs ')):                   # the bit number '0' is not register 0
        ops = s[4:].split(', ')
        return s[:4] + ', '.join([sub(ops[0])] + ops[1:])
    return sub(s)


def as_mame(i):
    """my decode printed in MAME's syntax, registers as plain hex"""
    if i.mn == 'bad': return '???'

    def op(o):
        k = o[0]
        if k == 'r': return '%02x' % o[1]
        if k == '#': return '#%04x' % o[1] if o[2] == 2 else '#%02x' % o[1]
        if k == '[]': return '[%02x]%s' % (o[1], '+' if o[2] else '')
        if k == 'ix':
            d, r, lng = o[1], o[2], o[3]
            if lng: return '%04x' % d if r == 0 else '%04x[%02x]' % (d, r)
            if r == 0: return '%04x' % (d & 0xff | 0xff00) if d < 0 else '%02x' % d
            return '-%02x[%02x]' % (-d, r) if d < 0 else '%02x[%02x]' % (d, r)
        if k == 'a': return '%04x' % o[1]
        return str(o[1])
    if i.mn == 'br': return 'br [%02x]' % i.raw[1]        # MAME prints the raw byte, bit 0 included
    return (i.mn + ' ' + ', '.join(op(o) for o in i.ops)).strip()


def compare(path, lo, hi):
    data = open(path, 'rb').read()
    rom = Rom(data)
    addrs = range(lo, hi)
    out = subprocess.run([MAME, path], input=''.join('%x\n' % a for a in addrs),
                         capture_output=True, text=True, check=True).stdout.splitlines()
    bad = 0
    for a, line in zip(addrs, out):
        _, n, txt = (line.split(' ', 2) + [''])[:3]
        i = decode(rom, a)
        mine, ref = (i.n, as_mame(i)), (int(n), mame_norm(txt))
        if ref[1] == '???': ref = (1, '???')            # MAME reports undefined opcodes as length 1 too
        if mine != ref:
            bad += 1
            if bad <= 10: print('  MISMATCH %04x %s: mine %r mame %r' % (a, data[a:a + 7].hex(' '), mine, ref))
    print('MAME check %s 0x%04x-0x%04x: %d offsets, %d mismatches' % (os.path.basename(path), lo, hi, len(addrs), bad))
    return bad


if os.path.exists(MAME):
    rnd = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mame_ref', 'random64k.bin')
    r = random.Random(96)
    open(rnd, 'wb').write(bytes(r.randrange(256) for _ in range(0x10000)))
    fails += compare(rnd, 0, 0xfff0)
    if os.path.exists('ctrl/ic19.bin'):
        fails += compare('ctrl/ic19.bin', 0x1000, 0x7ff8)
else:
    print('no mame_ref/mame_dasm: run  sh mame_ref/build.sh  for the MAME cross-check')
sys.exit(1 if fails else 0)
