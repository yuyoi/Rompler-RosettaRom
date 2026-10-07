"""Quick screen for the D-110 (IC19 v1.10): hold Enter + press Edit (the old demo combo, key code 0x19) to open it.

    Cut --- Res --P1      Group +/-  : filter cutoff  (all 4 partials, 0-100)
    Atk --- Rel ---       Bank +/-   : resonance      (0-30)
                          Number +/- : amp env T1 (attack, 0-100)
                          Part +/-   : amp env T5 (release, 0-100)      Exit: back

Values are those of partial 1 of the current part (0xF6CD); each step moves all four partials of that part's timbre
edit copy (0xE1E4 + part*0xF6) by 1, clamped. The change applies from the next note (see IC19_MAP.md, "Live edits").
The rhythm part is not edited. Code goes in the dead demo-menu code (0x503D-0x5137), menu and LCD template in the free
FF area at 0x2019. The top-menu entry at 0x4FA9 (key 0x19 = demo) becomes '>' (push state) to this screen.
build() returns [(address, bytes)] for patch_ic19.py; run this file to print a disassembly.
"""
from mcs96_dis import decode, fmt_ins, Rom


class Asm:
    def __init__(s, org): s.org = org; s.b = bytearray(); s.fix = []; s.lab = {}
    @property
    def pc(s): return s.org + len(s.b)
    def L(s, n): s.lab[n] = s.pc
    def raw(s, h): s.b += bytes.fromhex(h) if isinstance(h, str) else h
    def w(s, v): s.b += (v & 0xffff).to_bytes(2, 'little')
    def jcc(s, op, tgt): s.raw('%02x00' % op); s.fix.append(('r8', len(s.b) - 1, tgt, s.pc))
    def sjmp(s, tgt): s.raw('2000'); s.fix.append(('sj', len(s.b) - 2, tgt, s.pc))
    def lcall(s, tgt): s.raw('ef'); s.w(0); s.fix.append(('r16', len(s.b) - 2, tgt, s.pc))
    def ljmp(s, tgt): s.raw('e7'); s.w(0); s.fix.append(('r16', len(s.b) - 2, tgt, s.pc))
    def djnz(s, r, tgt): s.raw('e0%02x00' % r); s.fix.append(('r8', len(s.b) - 1, tgt, s.pc))
    def jbc(s, r, bit, tgt): s.raw('%02x%02x00' % (0x30 + bit, r)); s.fix.append(('r8', len(s.b) - 1, tgt, s.pc))
    def done(s, ext={}):
        lab = dict(ext, **s.lab)
        for k, at, t, nxt in s.fix:
            t = lab[t] if isinstance(t, str) else t
            d = t - nxt
            if k == 'r8': assert -128 <= d < 128, (hex(t), d); s.b[at] = d & 0xff
            elif k == 'sj': assert -1024 <= d < 1024; s.b[at] = 0x20 | ((d >> 8) & 7); s.b[at + 1] = d & 0xff
            else: s.b[at:at + 2] = (d & 0xffff).to_bytes(2, 'little')
        return bytes(s.b)

def build():
    SUB_502B, SUB_525B, SUB_527D, SUB_5297, POP_STATE, MENU_RUN, RET = 0x502b, 0x525b, 0x527d, 0x5297, 0x5391, 0x53a3, 0x53e1
    PART = 0xf6cd                       # current part 0-8 (8 = rhythm)
    # param offsets from the timbre start (14 common bytes + partial block offset)
    CUT, RES, ATK, REL = 0x0e + 0x17, 0x0e + 0x18, 0x0e + 0x31, 0x0e + 0x35

    # --- data at 0x2019: menu + LCD template ---
    D = Asm(0x2019)
    D.L('menu'); D.w(0)                # init -> qdraw (fixed below)
    keys = [(0x01, POP_STATE), (0x05, 'cut_up'), (0x0d, 'cut_dn'), (0x06, 'res_up'), (0x0e, 'res_dn'),
            (0x07, 'atk_up'), (0x0f, 'atk_dn'), (0x04, 'rel_up'), (0x0c, 'rel_dn')]
    for k, t in keys: D.raw('%02x21' % k); D.w(0)
    D.raw('00')
    D.L('tpl'); D.raw(b'\x00' + b'Cut --- Res --P-' + b'Atk --- Rel --- ' + b'\x00')

    # --- code at 0x503d (dead demo menu code) ---
    C = Asm(0x503d)
    C.L('handler'); C.raw('a1'); C.w(D.lab['menu']); C.raw('78'); C.ljmp(MENU_RUN)       # ld r78,#menu; ljmp 0x53a3
    for name, off, mx in [('cut', CUT, 100), ('res', RES, 30), ('atk', ATK, 100), ('rel', REL, 100)]:
        C.L(name + '_up'); C.raw('b10176'); C.sjmp(name)                  # ldb r76,#1
        C.L(name + '_dn'); C.raw('b1ff76')                                 # ldb r76,#0xff
        C.L(name); C.raw('ad%02x74' % off); C.raw('b1%02x72' % mx); C.sjmp('adj')   # ldbze r74,#off ; ldb r72,#max (not r75: high byte of r74)
    C.L('adj')
    C.raw('af01cdf650')        # ldbze r50, 0xf6cd
    C.raw('990850'); C.jcc(0xdb, 'ret')                                    # cmpb r50,#8 ; jc ret (rhythm part: no edit)
    C.raw('090450')            # shl r50,#4
    C.raw('675110f374')        # add r74, 0xf310[r50]   (timbre temp of this part)
    C.raw('b10477')            # ldb r77,#4  (4 partials)
    C.L('loop')
    C.raw('b27470')            # ldb r70,[r74]
    C.raw('747670')            # addb r70,r76
    C.raw('987270'); C.jcc(0xd1, 'ok')                                     # cmpb r70,r72 ; jnh ok
    C.raw('b07270')            # ldb r70,r72   (over max)
    C.jbc(0x76, 7, 'ok')       # delta +1: keep max
    C.raw('1170')              # clrb r70      (delta -1 wrapped below 0)
    C.L('ok')
    C.raw('c67470')            # stb r70,[r74]
    C.raw('653a0074')          # add r74,#0x3a (next partial)
    C.djnz(0x77, 'loop')
    C.L('ret'); C.raw('f0')
    C.L('draw')
    C.raw('a1'); C.w(D.lab['tpl']); C.raw('78')                            # ld r78,#tpl
    C.raw('a1abf676')          # ld r76,#0xf6ab  (LCD line buffer: addr byte + 32 chars)
    C.raw('a1220074')          # ld r74,#34
    C.lcall(SUB_502B)          # copy
    C.raw('af01cdf650')        # ldbze r50,0xf6cd
    C.raw('990850'); C.jcc(0xdb, 'flush')
    C.raw('b05070'); C.raw('753170'); C.raw('c701bbf670')   # part digit at col 15
    C.raw('090450')            # shl r50,#4
    C.raw('a35110f372')        # ld r72,0xf310[r50]
    for off, pos, fn in [(CUT, 4, SUB_5297), (RES, 12, SUB_527D), (ATK, 20, SUB_5297), (REL, 28, SUB_5297)]:
        C.raw('b372%02x70' % off)                                          # ldb r70,off[r72]
        C.raw('a1'); C.w(0xf6ac + pos); C.raw('78')                        # ld r78,#buf+pos
        C.lcall(fn)
    C.L('flush'); C.ljmp(SUB_525B)
    code = C.done(D.lab)
    assert C.pc <= 0x5138, hex(C.pc)
    data = bytearray(D.done())
    # fill menu pointers
    def put(at, v): data[at - 0x2019:at - 0x2017] = v.to_bytes(2, 'little')
    put(D.lab['menu'], C.lab['draw'])
    for i, (k, t) in enumerate(keys):
        put(D.lab['menu'] + 2 + 4 * i + 2, t if isinstance(t, int) else C.lab[t])
    assert D.pc <= 0x2080, hex(D.pc)
    # top-menu entry at 0x4fa9: key 19 '>'(bit7) handler, after = ret
    entry = bytes([0x19, 0xbe]) + C.lab['handler'].to_bytes(2, 'little') + RET.to_bytes(2, 'little')
    return [(0x503d, code), (0x2019, bytes(data)), (0x4fa9, entry),
            (0x5037, D.lab['menu'].to_bytes(2, 'little'))]   # dead demo state 0x5036 now runs this menu too (safety)


OLD_SHA1 = 'cf84018246e2fac022720d6efdce7bdf42efcd47'   # SHA-1 of v1.10 bytes 0x4fa9-0x4fae + 0x5036-0x503c (the menu entry and demo handler)


def old_ok(rom):
    import hashlib
    return hashlib.sha1(bytes(rom[0x4fa9:0x4faf]) + bytes(rom[0x5036:0x503d])).hexdigest() == OLD_SHA1


if __name__ == '__main__':
    import sys
    for at, b in build():
        print('0x%04x  %d bytes  %s' % (at, len(b), b.hex()))
    code = build()[0][1]
    mem = bytearray(0x10000); mem[0x503d:0x503d + len(code)] = code; r = Rom(bytes(mem), 0); a = 0x503d
    while a < 0x503d + len(code):
        i = decode(r, a); print('  %04x %-15s %s' % (a, mem[a:a + i.n].hex(' '), fmt_ins(i))); a += i.n
