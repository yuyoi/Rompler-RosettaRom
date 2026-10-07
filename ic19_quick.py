"""Quick screen for the D-110 (IC19 v1.10): hold Enter + press Edit (the old demo combo, key code 0x19) to open it.

    Cut --- Res --P1      Group +/-  : filter cutoff  (all 4 partials, 0-100)
    Atk --- Rel ---       Bank +/-   : resonance      (0-30)
                          Part       : next part (P1..P8)
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
    def jbs(s, r, bit, tgt): s.raw('%02x%02x00' % (0x38 + bit, r)); s.fix.append(('r8', len(s.b) - 1, tgt, s.pc))
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
            (0x07, 'atk_up'), (0x0f, 'atk_dn'), (0x04, 'rel_up'), (0x0c, 'rel_dn'), (0x0a, 'part_next')]
    for k, t in keys: D.raw('%02x21' % k); D.w(0)
    D.raw('00')
    D.L('tpl'); D.raw(b'\x00' + b'Cut --- Res --P-' + b'Atk --- Rel --- ' + b'\x00')

    # --- code at 0x503d (dead demo menu code) ---
    C = Asm(0x503d)
    C.L('handler'); C.raw('a1'); C.w(D.lab['menu']); C.raw('78'); C.ljmp(MENU_RUN)       # ld r78,#menu; ljmp 0x53a3
    for name, off, mx, kind in [('cut', CUT, 100, 1), ('res', RES, 30, 2), ('atk', ATK, 100, 0), ('rel', REL, 100, 0)]:
        C.L(name + '_up'); C.raw('b10176'); C.sjmp(name)                  # ldb r76,#1
        C.L(name + '_dn'); C.raw('b1ff76')                                 # ldb r76,#0xff
        C.L(name); C.raw('ad%02x74' % off)                                 # ldbze r74,#off
        C.raw('a1%02x%02x72' % (mx, kind)); C.sjmp('adj')                  # ld r72,#kind<<8|max: r72 = max, r73 = live kind
        # (max is in r72, not r75: r75 is the high byte of r74)
    C.L('adj')
    C.raw('af01cdf650')        # ldbze r50, 0xf6cd
    C.raw('990850'); C.jcc(0xdb, 'ret')                                    # cmpb r50,#8 ; jc ret (rhythm part: no edit)
    C.raw('090450')            # shl r50,#4
    C.raw('675110f374')        # add r74, 0xf310[r50]   (timbre temp of this part)
    C.raw('b10477')            # ldb r77,#4  (4 partials)
    C.L('loop')
    C.raw('b27471')            # ldb r71,[r74]          old value
    C.raw('54767170')          # addb r70,r71,r76
    C.raw('987270'); C.jcc(0xd1, 'ok')                                     # cmpb r70,r72 ; jnh ok
    C.raw('b07270')            # ldb r70,r72   (over max)
    C.jbc(0x76, 7, 'ok')       # delta +1: keep max
    C.raw('1170')              # clrb r70      (delta -1 wrapped below 0)
    C.L('ok')
    C.raw('c67470')            # stb r70,[r74]
    C.raw('987170'); C.jcc(0xdf, 'next')                                   # cmpb r70,r71 ; je next (clamped: no change)
    C.raw('987300'); C.jcc(0xdf, 'next')                                   # cmpb zero,r73 ; je next (no live kind)
    C.lcall('live')
    C.L('next')
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

    # --- X block at 0x3efa (dead demo-start code): Part button and live update ---
    X = Asm(0x3efa)
    X.L('part_next')           # Part button: current part 1..8 (rhythm part skipped), wraps
    X.raw('b301cdf670')        # ldb r70,0xf6cd
    X.raw('1770')              # incb r70
    X.raw('990870'); X.jcc(0xd3, 'pn_st')                                # cmpb r70,#8 ; jnc pn_st (r70 < 8)
    X.raw('1170')              # clrb r70
    X.L('pn_st'); X.raw('c701cdf670')                                  # stb r70,0xf6cd
    X.raw('f0')                # ret
    # live: r74 -> changed byte (cutoff 0x17 or reso 0x18 of a partial block), r76 = +1/-1, r73 = kind, r50 = part*16.
    # Walks the part's sounding notes and their LA32 partials like sub_30f0, and for each synth partial (0xEF80 bit 7
    # clear; PCM partials use these registers for the sample address) of this block rewrites the note-on result:
    #   cutoff: 0xF1C0[p] +/- 1 (0..255) -> LA32 0x0C41[p]
    #   reso:   (r+1) | ((r+1)<<3 & 0xE0) -> 0xEF81[p], LA32 0x0D01[p]   (same formula as sub_3615 at 0x3781)
    X.L('live')
    X.raw('a07478')            # ld r78,r74
    X.raw('69170078')          # sub r78,#0x17          block start (cutoff)
    X.jbc(0x73, 1, 'lv_go')
    X.raw('0578')              # dec r78                (reso byte is one further)
    X.L('lv_go')
    X.raw('717f08')            # andb int_mask,#0x7f    (as sub_30f0: no LA32 interrupt while walking)
    X.raw('af5185f252')        # ldbze r52,0xf285[r50]  first note of the part
    X.L('nl'); X.raw('99ff52'); X.jcc(0xdf, 'lv_done')                   # cmpb r52,#0xff ; je done
    X.raw('af5340f454')        # ldbze r54,0xf440[r52]  first partial of the note
    X.L('pl'); X.raw('99ff54'); X.jcc(0xdf, 'nn')                        # cmpb r54,#0xff ; je next note
    X.raw('8b5580ee78'); X.jcc(0xd7, 'pn')                               # cmp r78,0xee80[r54] ; jne (other block)
    X.raw('b35580ef7a'); X.jbs(0x7a, 7, 'pn')                            # ldb r7a,0xef80[r54] ; jbs PCM -> skip
    X.jbs(0x73, 1, 'reso')
    X.raw('b355c0f17a')        # ldb r7a,0xf1c0[r54]
    X.jbs(0x76, 7, 'cdn')
    X.raw('99ff7a'); X.jcc(0xdf, 'pn')                                   # at 0xff: stay
    X.raw('177a'); X.sjmp('cwr')                                         # incb r7a
    X.L('cdn'); X.raw('987a00'); X.jcc(0xdf, 'pn')                       # cmpb zero,r7a? at 0: stay
    X.raw('157a')              # decb r7a
    X.L('cwr'); X.raw('c755c0f17a'); X.raw('c755410c7a'); X.sjmp('pn')  # stb 0xf1c0[r54] ; stb LA32 0x0c41[r54]
    X.L('reso')
    X.raw('b378187a')          # ldb r7a,0x18[r78]      new resonance
    X.raw('177a')              # incb r7a
    X.raw('b07a7b')            # ldb r7b,r7a
    X.raw('19037b')            # shlb r7b,#3
    X.raw('71e07b')            # andb r7b,#0xe0
    X.raw('907b7a')            # orb r7a,r7b
    X.raw('c75581ef7a')        # stb r7a,0xef81[r54]
    # LA32 takes 0x0D00/0x0D01 as a pair (note-on writes 0x0D00 right before 0x0D01; writing 0x0D01 alone stopped the
    # voice on hardware, v4): rewrite 0x0D00 from its shadow 0xEF80 first, then the new 0x0D01
    X.raw('b35580ef7b'); X.raw('c755000d7b')                             # ldb r7b,0xef80[r54] ; stb LA32 0x0d00[r54]
    X.raw('c755010d7a')        # stb r7a,0x0d01[r54]
    X.L('pn'); X.raw('af5540ee54'); X.sjmp('pl')                         # ldbze r54,0xee40[r54]
    X.L('nn'); X.raw('af53c0f352'); X.sjmp('nl')                         # ldbze r52,0xf3c0[r52]
    X.L('lv_done'); X.raw('918008')                                      # orb int_mask,#0x80
    X.raw('f0')                # ret
    xcode = X.done(dict(D.lab))
    code = C.done(dict(D.lab, **X.lab))
    assert X.pc <= 0x3fa2, hex(X.pc)
    assert C.pc <= 0x5138, hex(C.pc)
    data = bytearray(D.done())
    # fill menu pointers
    def put(at, v): data[at - 0x2019:at - 0x2017] = v.to_bytes(2, 'little')
    put(D.lab['menu'], C.lab['draw'])
    for i, (k, t) in enumerate(keys):
        put(D.lab['menu'] + 2 + 4 * i + 2, t if isinstance(t, int) else dict(C.lab, **X.lab)[t])
    assert D.pc <= 0x2080, hex(D.pc)
    # top-menu entry at 0x4fa9: key 19 '>'(bit7) handler, after = ret
    entry = bytes([0x19, 0xbe]) + C.lab['handler'].to_bytes(2, 'little') + RET.to_bytes(2, 'little')
    return [(0x503d, code), (0x3efa, xcode), (0x2019, bytes(data)), (0x4fa9, entry),
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
