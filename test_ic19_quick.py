"""Runs the Quick screen (ic19_quick.py) on your own patched IC19 in mcs96_sim: draw, then every key, and checks the
timbre bytes and the LCD text. Needs ctrl/ic19_patched.bin built with patch_ic19.py --quick."""
import sys
from mcs96_sim import Sim

rom = open(sys.argv[1] if len(sys.argv) > 1 else 'ctrl/ic19_patched.bin', 'rb').read()
s = Sim(rom); lcd = []
s.stubs[0x208a] = lambda s: lcd.append(bytes(s.ld(s.ld(0x78, 2) + 1 + i, 1) for i in range(32)).decode('latin-1'))
s.stubs[0x208c] = lambda s: None
BASE, PART = 0xe1e4 + 2 * 0xf6, 2                      # test on part 3
OFF = {'cut': 0x17, 'res': 0x18, 'atk': 0x31, 'rel': 0x35}
start = {'cut': [50, 99, 0, 100], 'res': [10, 30, 0, 29], 'atk': [20, 0, 100, 1], 'rel': [60, 60, 60, 60]}
for k, vals in start.items():
    for p, v in enumerate(vals): s.st(BASE + 0x0e + p * 0x3a + OFF[k], v, 1)
for part in range(9): s.st(0xf310 + part * 16, 0xe1e4 + part * 0xf6, 2)
s.st(0xf6cd, PART, 1); s.st(0xb4, 0x503d, 2); s.st(0xb6, 1, 1)
val = lambda k: [s.ld(BASE + 0x0e + p * 0x3a + OFF[k], 1) for p in range(4)]
# live update setup: part 3 holds one note (index 5) with three LA32 partials:
#   p=0x06: synth, timbre partial block 0     p=0x0a: PCM, block 0 (must stay untouched)     p=0x10: synth, block 1
for r in range(0x40): s.st(0xee40 + r, 0xff, 1)
s.st(0xf285 + PART * 16, 5, 1); s.st(0xf3c0 + 5, 0xff, 1); s.st(0xf440 + 5, 0x06, 1)
s.st(0xee40 + 0x06, 0x0a, 1); s.st(0xee40 + 0x0a, 0x10, 1); s.st(0xee40 + 0x10, 0xff, 1)
for p_, blk, pcm in ((0x06, 0, 0), (0x0a, 0, 1), (0x10, 1, 0)):
    s.st(0xee80 + p_, BASE + 0x0e + blk * 0x3a, 2); s.st(0xef80 + p_, 0x80 if pcm else 0x24, 1)
    s.st(0xf1c0 + p_, 0x80, 1); s.st(0xef81 + p_, 0x55, 1); s.st(0x0c41 + p_, 0x80, 1); s.st(0x0d01 + p_, 0x55, 1)
s.st(0x08, 0xff, 1)                                                   # int_mask
s.st(0x70, 0xff, 1); s.call(0x503d)
fails = 0
def check(name, ok):
    global fails
    fails += not ok
    print('%-40s %s' % (name, 'ok' if ok else 'FAIL'))
check('draw: %r' % lcd[-1], lcd[-1] == 'Cut 050 Res 10P3Atk 020 Rel 060 ')
for key, k, want in [(0x05, 'cut', [51, 100, 1, 100]), (0x0d, 'cut', [50, 99, 0, 99]), (0x0d, 'cut', [49, 98, 0, 98]),
                     (0x06, 'res', [11, 30, 1, 30]), (0x0e, 'res', [10, 29, 0, 29]),
                     (0x07, 'atk', [21, 1, 100, 2]), (0x0f, 'atk', [20, 0, 99, 1]),
                     (0x04, 'rel', [61, 61, 61, 61]), (0x0c, 'rel', [60, 60, 60, 60])]:
    s.st(0x70, key, 1); s.call(0x503d)
    check('key %02x %s %s' % (key, k, val(k)), val(k) == want)
check('redraw after keys: %r' % lcd[-1], lcd[-1] == 'Cut 049 Res 10P3Atk 020 Rel 060 ')
# after the key sequence: cutoff +1 -1 -1 on block 0 (50->51->50->49) and block 1 (99->100->99->98); reso +1 -1
lv = lambda base, p_: s.ld(base + p_, 1)
check('live cutoff synth p06: 0x%02x' % lv(0x0c41, 0x06), lv(0x0c41, 0x06) == 0x7f and lv(0xf1c0, 0x06) == 0x7f)
check('live cutoff synth p10: 0x%02x' % lv(0x0c41, 0x10), lv(0x0c41, 0x10) == 0x7f and lv(0xf1c0, 0x10) == 0x7f)
r = 10 + 1; want = r | (r << 3 & 0xe0)
check('live reso p06 = 0x%02x (want 0x%02x)' % (lv(0x0d01, 0x06), want), lv(0x0d01, 0x06) == want == lv(0xef81, 0x06))
r = 29 + 1; want = r | (r << 3 & 0xe0)
check('live reso p10 = 0x%02x (want 0x%02x)' % (lv(0x0d01, 0x10), want), lv(0x0d01, 0x10) == want == lv(0xef81, 0x10))
check('reso writes 0x0D00 pair from 0xEF80 shadow', s.ld(0x0d00 + 0x06, 1) == 0x24 and s.ld(0x0d00 + 0x10, 1) == 0x24)
check('PCM partial p0a untouched', (lv(0x0c41, 0x0a), lv(0xf1c0, 0x0a), lv(0x0d01, 0x0a), lv(0xef81, 0x0a), lv(0x0d00, 0x0a)) == (0x80, 0x80, 0x55, 0x55, 0))
check('int_mask restored', s.ld(0x08, 1) == 0xff)
for want in (3, 4, 5, 6, 7, 0, 1, 2):
    s.st(0x70, 0x0a, 1); s.call(0x503d)
    if s.ld(0xf6cd, 1) != want: break
check('Part button cycles P3 -> P8 -> P1 -> P3', s.ld(0xf6cd, 1) == 2 and lcd[-1][15] == '3')
s.st(0xf6cd, 8, 1); s.st(0x70, 0x0a, 1); s.call(0x503d)
check('Part button from rhythm part -> P1', s.ld(0xf6cd, 1) == 0)
s.st(0xf6cd, 8, 1); before = bytes(s.m[0xe1e4:0xe1e4 + 9 * 0xf6]); s.st(0x70, 0x05, 1); s.call(0x503d)
check('rhythm part untouched', bytes(s.m[0xe1e4:0xe1e4 + 9 * 0xf6]) == before)
s.st(0xf4e2, 0x7ff0, 2); s.stubs[0x7ff0] = s.stubs[0x5b36] = lambda s: None     # previous screen = stub
s.st(0xf6cd, PART, 1); s.st(0x70, 0x01, 1); s.call(0x503d)
check('Exit pops state (rb6 1 -> 0)', s.ld(0xb6, 1) == 0)
# MIDI CC (patch_ic19.py --cc): call the stock CC dispatch 0x3BBA as the per-part loop does
if s.ld(0x3bce + 2 * 74, 2):
    def cc(n, v, part=PART, mask=0xff):
        s.st(0x08, mask, 1); s.st(0x42, 0x1234, 2); s.st(0x44, 5, 1); s.st(0x45, n, 1); s.st(0x46, v, 1)
        s.st(0x50, part * 16, 2); s.st(0xc7, 0, 1); s.call(0x3bba)
        return (s.ld(0x42, 2), s.ld(0x44, 1), s.ld(0x45, 1), s.ld(0x46, 1), s.ld(0x50, 2)) == (0x1234, 5, n, v, part * 16)
    ok = cc(74, 127)
    check('CC74 127: cut %s, regs kept' % val('cut'), ok and val('cut') == [100] * 4 and s.ld(0xc7, 1) == 8)
    check('CC74 live p06 0x%02x p10 0x%02x' % (lv(0xf1c0, 0x06), lv(0xf1c0, 0x10)),
          lv(0xf1c0, 0x06) == 0x7f + 51 == lv(0x0c41, 0x06) and lv(0xf1c0, 0x10) == 0x7f + 2 == lv(0x0c41, 0x10))
    cc(74, 0, mask=0x7f)
    check('CC74 0: cut %s, live p06 0x%02x' % (val('cut'), lv(0x0c41, 0x06)),
          val('cut') == [0] * 4 and lv(0x0c41, 0x06) == 0x7f + 51 - 100 and lv(0x0c41, 0x10) == 0x7f + 2 - 100)
    check('CC: int_mask kept when bit 7 was off', s.ld(0x08, 1) == 0x7f)
    s.st(0xf1c0 + 0x06, 0xf0, 1); cc(74, 127); s.st(0xf1c0 + 0x10, 0x10, 1); cc(74, 0)
    check('CC74 live clamps 0xff (+100) and 0x00 (-100)', lv(0x0c41, 0x06) == 0xff - 100 and lv(0x0c41, 0x10) == 0)
    cc(71, 64); r = 15 + 1
    check('CC71 64: res %s, live 0x%02x' % (val('res'), lv(0x0d01, 0x06)),
          val('res') == [15] * 4 and lv(0x0d01, 0x06) == r | (r << 3 & 0xe0) == lv(0x0d01, 0x10))
    cc(73, 127); cc(72, 1)
    check('CC73 127 atk %s, CC72 1 rel %s' % (val('atk'), val('rel')), val('atk') == [100] * 4 and val('rel') == [1] * 4)
    check('CC: PCM partial p0a untouched', (lv(0x0c41, 0x0a), lv(0xf1c0, 0x0a), lv(0x0d01, 0x0a)) == (0x80, 0x80, 0x55))
    before = bytes(s.m[0xe1e4:0xe1e4 + 9 * 0xf6]); cc(74, 77, part=8)
    check('CC on rhythm part: nothing', bytes(s.m[0xe1e4:0xe1e4 + 9 * 0xf6]) == before)
    s.st(0x45, 7, 1); s.st(0x46, 100, 1); s.st(0x50, PART * 16, 2); s.call(0x3bba)
    check('CC7 volume still stock', s.ld(0xf288 + PART * 16, 1) == rom[0x12f1 + 100])
sys.exit(1 if fails else 0)
