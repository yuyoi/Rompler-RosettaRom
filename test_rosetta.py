"""Runs the Rosetta hooks (rosetta.py) on your own patched IC19 + IC15 in mcs96_sim: menu, chord memory, per-note
drift / random cutoff, wave offset and CC70 wave scan, and the fallback with a stock IC15.

  python test_rosetta.py ctrl/ic19_ros.bin my_ic15_ros.bin [my_stock_ic15.bin]
"""
import sys
from mcs96_sim import Sim
import rosetta as R

ic19 = open(sys.argv[1], 'rb').read()
ic15 = open(sys.argv[2], 'rb').read()[:0x20000]
stock15 = open(sys.argv[3], 'rb').read()[:0x20000] if len(sys.argv) > 3 else None
lab = R.build_ic19()[1]
fails = 0


def check(name, ok):
    global fails
    fails += not ok
    print('%-52s %s' % (name, 'ok' if ok else 'FAIL'))


def new(ic15img):
    s = Sim(ic19, ic15img)
    s.lcd, s.calls = [], []
    s.stubs[0x208a] = lambda s: s.lcd.append(bytes(s.ld(s.ld(0x78, 2) + 1 + i, 1) for i in range(32)).decode('latin-1'))
    for a, n in ((0x24fc, 'on'), (0x245d, 'off'), (0x3de2, 'alloff'), (0x53cb, 'redraw')):
        s.stubs[a] = (lambda n: lambda s: s.calls.append((n, s.ld(0x45, 1), s.ld(0x46, 1), s.ld(0x50, 2), s.bank)))(n)
    s.st(0xb6, 1, 1); s.st(0xf4e2, 0x7ff0, 2)
    return s


ram = lambda s, k: s.ld(R.RAM[k], 1)
regs = lambda s: (s.ld(0x42, 2), s.ld(0x44, 2), s.ld(0x46, 1), s.ld(0x50, 2))

# --- stock IC15 (or none): everything falls through to the stock routines
s = new(stock15)
s.st(0xb7, 0x22, 1); s.bank = 0x22
s.st(0x45, 60, 1); s.st(0x46, 100, 1); s.st(0x50, 0x20, 2); s.call(lab['h_non'])
check('stock IC15: note on goes straight to 0x24FC', [c[:4] for c in s.calls] == [('on', 60, 100, 0x20)] and s.bank == 0x22)
s.calls.clear(); s.st(0x70, 0xff, 1); s.call(lab['ros_ui'])
check('stock IC15: Rosetta menu leaves at once', s.ld(0xb6, 1) == 0 and s.calls[-1][0] == 'redraw')

# --- Rosetta IC15
s = new(ic15)
for a in range(R.RB, R.RB + R.RAM_INIT_LEN): s.st(a, 0x5a, 1)     # battery RAM garbage
s.st(0xb7, 0x11, 1); s.bank = 0x11
s.st(0xf6cd, 2, 1); s.st(0x70, 0xff, 1); s.call(lab['ros_ui'])
check('menu draw: %r' % s.lcd[-1], s.lcd[-1].startswith('Wave Scan (CC70)000') and s.lcd[-1].endswith('P3'))
check('settings zeroed once (magic set)', s.ld(R.RAM['R_MAGIC'], 2) == 0xa75a and ram(s, 'CHORD') == 0 and ram(s, 'DRIFTP') == 0)
check('bank latch back to the caller page', s.bank == 0x11 and s.ld(0xb7, 1) == 0x11)
keys = lambda *ks: [(s.st(0x70, k, 1), s.call(lab['ros_ui'])) for k in ks]
keys(0x05, 0x05)                                    # -> Drift Pitch
keys(0x07, 0x07, 0x07, 0x07, 0x06)                  # +10 x4 (clamp 31), +1
check('Drift Pitch clamps at 31: %r' % s.lcd[-1], ram(s, 'DRIFTP') == 31 and s.lcd[-1].startswith('Drift Pitch'))
keys(0x0f, 0x0f, 0x0f, 0x0f, 0x0e)
check('... and at 0', ram(s, 'DRIFTP') == 0)
keys(0x0d, 0x0d, 0x0d)                              # back past item 0 -> wraps to the last item (Info)
check('Group- wraps to Info: %r' % s.lcd[-1], s.lcd[-1] == 'Info            Mem ok/ok P02   ')
keys(0x06)
check('Bank+ on Info changes nothing', ram(s, 'MIDX') == 6)
keys(0x0d)
check('Chord Part: %r' % s.lcd[-1][:19], s.lcd[-1].startswith('Chord Part') and s.lcd[-1][16:19] == 'All')
keys(0x0d, 0x06, 0x06, 0x06, 0x06)                  # Chord: Major
check('Chord = Major (and all notes off sent): %r' % s.lcd[-1][16:24],
      ram(s, 'CHORD') == 4 and s.lcd[-1][16:24] == 'Major   ' and sum(c[0] == 'alloff' for c in s.calls) == 32)
s.calls.clear(); keys(0x01)
check('Exit pops the state and redraws', s.ld(0xb6, 1) == 0 and s.calls[-1][0] == 'redraw')

# chord memory on note on / off
s.calls.clear(); s.st(0x42, 0x24fc, 2); s.st(0x44, 0x3c05, 2); s.st(0x46, 100, 1); s.st(0x50, 0x20, 2)
before = regs(s); s.call(lab['h_non'])
check('chord note on: %s' % [c[1] for c in s.calls], [c[1:4] for c in s.calls] == [(60, 100, 0x20), (64, 100, 0x20), (67, 100, 0x20)])
check('... MIDI loop registers kept, page back', regs(s) == before and s.bank == 0x11)
s.calls.clear(); s.call(lab['h_noff'])
check('chord note off: %s' % [c[1] for c in s.calls], [c[:2] for c in s.calls] == [('off', 60), ('off', 64), ('off', 67)])
s.st(R.RAM['CHPART'], 2, 1); s.calls.clear(); s.call(lab['h_non'])
check('Chord Part = P2: part 3 plays the root only', [c[1] for c in s.calls] == [60])
s.st(R.RAM['CHPART'], 0, 1); s.st(0x50, 0x80, 2); s.calls.clear(); s.call(lab['h_non'])
check('rhythm part: root only', [c[1] for c in s.calls] == [60])
s.st(0x44, 0x7a05, 2); s.st(0x50, 0x20, 2); s.calls.clear(); s.call(lab['h_non'])
check('notes above 127 dropped: %s' % [c[1] for c in s.calls], [c[1] for c in s.calls] == [122, 126])

# per-partial note-on hook: synth partial p06 + p08 of one note, PCM partial p0a with a wave offset
BLK = 0xe1e4 + 2 * 0xf6 + 0x0e
for p, blk, ef80 in ((0x06, BLK, 0x24), (0x08, BLK + 0x3a, 0x24), (0x0a, BLK + 0x74, 0xc1)):
    s.st(0xee80 + p, blk, 2); s.st(0xef80 + p, ef80, 1); s.st(0xf1c0 + p, 0x80, 1); s.st(0xef40 + p, 0x5000, 2)
    s.st(0xf100 + p, 0xffff, 2)
s.st(BLK + 0x74 + 5, 10, 1); s.st(BLK + 0x74 + 4, 0, 1)        # PCM wave 10, waveform 0 (bank 0)
s.st(R.RAM['DRIFTP'], 31, 1); s.st(R.RAM['RCUT'], 100, 1); s.st(R.RAM['WAVE'] + 2, 5, 1); s.st(R.RAM['LFSR'], 0x1234, 2)
s.st(0x08, 0x7f, 1); s.st(0x50, 0x20, 2); s.st(0x52, 3, 2); s.st(0x56, BLK, 2)


def part_hook(p):
    s.st(0x54, p, 2); keep = (s.ld(0x50, 2), s.ld(0x52, 2), s.ld(0x54, 2), s.ld(0x56, 2)); s.call(0x3bb4)
    return keep == (s.ld(0x50, 2), s.ld(0x52, 2), s.ld(0x54, 2), s.ld(0x56, 2))


s.st(R.RAM['LASTSLOT'], 0xff, 1)
ok = part_hook(0x06) and part_hook(0x08)
d6, d8 = s.ld(0xef40 + 6, 2) - 0x5000, s.ld(0xef40 + 8, 2) - 0x5000
c6, c8 = s.ld(0xf1c0 + 6, 1), s.ld(0xf1c0 + 8, 1)
check('hook keeps r50-r56, does the replaced store', ok and s.ld(0xf100 + 6, 2) == 0 and s.bank == 0x11)
check('drift: same pitch offset for the note (%d, %d)' % (d6, d8), d6 == d8 and d6 != 0 and abs(d6) <= 124)
check('random cutoff: 0x%02x 0x%02x, LA32 written' % (c6, c8),
      c6 == c8 != 0x80 and abs(c6 - 0x80) <= 100 and s.ld(0x0c41 + 6, 1) == c6)
s.st(R.RAM['LASTSLOT'], 0xff, 1); part_hook(0x06)
check('next note: new random values', (s.ld(0xef40 + 6, 2) - 0x5000 - d6) or (s.ld(0xf1c0 + 6, 1) - c6))
s.st(R.RAM['DRIFTP'], 0, 1); s.st(R.RAM['RCUT'], 0, 1)
w = lambda n: ic15[0x900 + 4 * n:0x904 + 4 * n]
s.st(R.RAM['LASTSLOT'], 0xff, 1); part_hook(0x0a)
pitch = lambda n: w(n)[2] | w(n)[3] << 8
check('PCM wave offset 5: wave 15 address in LA32', s.ld(0x0c41 + 0x0a, 1) == w(15)[0] and
      s.ld(0x0d01 + 0x0a, 1) == w(15)[1] | 8 and s.ld(0x0d00 + 0x0a, 1) == 0xc1)
check('... pitch base moved by the pitch-word difference',
      s.ld(0xef40 + 0x0a, 2) == min(0xe800, 0x5000 + pitch(15) - pitch(10)) and s.ld(R.RAM['OFS'] + 0x0a, 1) == 5)

# CC70 live, via the stock CC dispatch: part 3 holds note slot 5 = p06 (synth), p0a (PCM)
for r in range(0x40): s.st(0xee40 + r, 0xff, 1)
s.st(0xf285 + 0x20, 5, 1); s.st(0xf3c0 + 5, 0xff, 1); s.st(0xf440 + 5, 0x06, 1); s.st(0xee40 + 6, 0x0a, 1)
c6 = s.ld(0x0c41 + 6, 1); s.st(0x08, 0xff, 1)
s.st(0x45, 70, 1); s.st(0x46, 20, 1); s.st(0x50, 0x20, 2); s.st(0x42, 0x1234, 2); s.st(0x44, 0x4605, 2)
s.call(0x3bba)
check('CC70 = 20: PCM partial now wave 30, synth untouched', s.ld(0x0c41 + 0x0a, 1) == w(30)[0] and
      s.ld(0x0c41 + 6, 1) == c6 and ram(s, 'WAVE') == 0 and s.ld(R.RAM['WAVE'] + 2, 1) == 20)
check('... pitch follows (wave 10 -> 30), regs and int_mask kept',
      s.ld(0xef40 + 0x0a, 2) == min(0xe800, 0x5000 + pitch(30) - pitch(10)) and
      (s.ld(0x42, 2), s.ld(0x44, 2), s.ld(0x46, 1), s.ld(0x50, 2)) == (0x1234, 0x4605, 20, 0x20) and s.ld(0x08, 1) == 0xff)
s.st(0x50, 0x80, 2); s.call(0x3bba)
check('CC70 on the rhythm part: nothing', s.ld(R.RAM['WAVE'] + 8, 1) == 0)
print("IC15 code %d bytes" % len(R.build_ic15(lab)[0]))
sys.exit(1 if fails else 0)
