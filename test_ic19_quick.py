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
sys.exit(1 if fails else 0)
