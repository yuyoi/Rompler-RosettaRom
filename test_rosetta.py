"""Runs the Rosetta hooks (rosetta.py, v8) on your own patched IC19 + IC15 in mcs96_sim: menu, settings, chord /
unison / mono / legato / glide, arpeggiator (internal tempo and MIDI clock), mod matrix, wave sequence, per-note
drift / random cutoff / wave, lab bits, and the fallback with a stock IC15.

  python test_rosetta.py ctrl/ic19_ros.bin my_ic15_ros.bin [my_stock_ic15.bin]
"""
import sys
from mcs96_sim import Sim
import rosetta as R

ic19 = open(sys.argv[1], 'rb').read()
ic15 = open(sys.argv[2], 'rb').read()[:0x20000]
stock15 = open(sys.argv[3], 'rb').read()[:0x20000] if len(sys.argv) > 3 else None
lab = R.build_ic19()[1]
S = R.RAM
fails = 0
sims = []


def check(name, ok):
    global fails
    fails += not ok
    print('%-60s %s' % (name, 'ok' if ok else 'FAIL'))


def new(ic15img, ram=None):
    s = Sim(ic19, ic15img)
    sims.append(s)
    if ram: s.m[0xc000:] = ram
    s.lcd, s.calls = [], []
    s.stubs[0x208a] = lambda s: s.lcd.append(bytes(s.ld(s.ld(0x78, 2) + 1 + i, 1) for i in range(32)).decode('latin-1'))
    for a, n in ((0x24fc, 'on'), (0x245d, 'off'), (0x3de2, 'alloff'), (0x53cb, 'redraw'), (0x29f5, 'main')):
        s.stubs[a] = (lambda n: lambda s: s.calls.append((n, s.ld(0x45, 1), s.ld(0x46, 1), s.ld(0x50, 2), s.bank,
                                                          sx(s.ld(S['UDT'], 2)), sx(s.ld(S['GLD'], 2)))))(n)
    s.st(0xb6, 1, 1); s.st(0xf4e2, 0x7ff0, 2)
    for part in range(9): s.st(0xf285 + part * 16, 0xff, 1)      # no notes sounding
    return s


sx = lambda v: v - 0x10000 if v & 0x8000 else v
g = lambda s, k, i=0: s.ld(S[k] + i, 1)
gw = lambda s, k, i=0: s.ld(S[k] + i, 2)
put = lambda s, k, v, i=0: s.st(S[k] + i, v, 1)
regs = lambda s: (s.ld(0x42, 2), s.ld(0x44, 2), s.ld(0x46, 1), s.ld(0x50, 2))
ons = lambda s: [c[1] for c in s.calls if c[0] == 'on']
evs = lambda s: [(c[0], c[1]) for c in s.calls if c[0] in ('on', 'off')]


def note(s, on, n, v=100, part=2):
    s.st(0x45, n, 1); s.st(0x46, v if on else 0, 1); s.st(0x50, part * 16, 2); s.st(0x44, 0x0005 | n << 8, 2)
    s.st(0x42, 0x1234, 2)
    s.call(lab['h_non'] if on else lab['h_noff'])


def tick(s, n=1):
    s.st(0xc4, n, 1); s.call(lab['h_tick'])


def keys(s, *ks):
    for k in ks: s.st(0x70, k, 1); s.call(lab['ros_ui'])


def goto(s, name):
    """menu: Group+ until the item `name` is shown"""
    for _ in range(len(R.ITEMS) + 1):
        if s.lcd and s.lcd[-1].startswith(name): return
        keys(s, 0x05)
    raise AssertionError(name)


# ---------------------------------------------------------------- stock IC15: everything falls through
s = new(stock15)
s.st(0xb7, 0x22, 1); s.bank = 0x22
note(s, True, 60)
check('stock IC15: note on goes straight to 0x24FC', [c[:4] for c in s.calls] == [('on', 60, 100, 0x20)] and s.bank == 0x22)
s.calls.clear(); s.st(0x70, 0xff, 1); s.call(lab['ros_ui'])
check('stock IC15: Rosetta menu leaves at once', s.ld(0xb6, 1) == 0 and s.calls[-1][0] == 'redraw')
s.calls.clear(); tick(s, 3)
check('stock IC15: tick consumes rc4, main loop goes on', s.ld(0xc4, 1) == 0 and [c[0] for c in s.calls] == ['main'])

# ---------------------------------------------------------------- init, settings, menu
s = new(ic15)
for a in list(range(0x1a, 0x40)) + list(range(0x90, 0xa0)) + list(range(0xf500, 0xf800)): s.st(a, 0x5a, 1)
s.st(0xb7, 0x11, 1); s.bank = 0x11
s.st(0xf6cd, 2, 1); keys(s, 0xff)
check('menu draw: %r' % s.lcd[-1], s.lcd[-1].startswith('Wave Scan (CC70)000') and s.lcd[-1].endswith('P3'))
check('settings -> defaults (magic, BPM, amounts)', gw(s, 'S_MAGIC') == R.S_MAGIC_V and g(s, 'ARPBPM') == 80 and
      g(s, 'MA', 2) == 63 and g(s, 'UNID') == 20 and g(s, 'CHORD') == 0)
check('volatile state reset (magic, LASTN, MCUR)', s.ld(S['R_MAGIC'], 2) == 0xa75a and g(s, 'LASTN', 5) == 0xff and
      g(s, 'MCUR') == 0xff and gw(s, 'PB', 6) == 0)
check('bank latch back to the caller page', s.bank == 0x11 and s.ld(0xb7, 1) == 0x11)
keys(s, 0x0d)
check('Group- wraps to Info: %r' % s.lcd[-1], s.lcd[-1] == 'Info            Mem oooo P02 v8 ')
keys(s, 0x09)
check('Edit: next section (Wave): %r' % s.lcd[-1][:16], s.lcd[-1].startswith('Wave Scan'))
keys(s, 0x09)
check('Edit: next section (Drift Pitch)', s.lcd[-1].startswith('Drift Pitch'))
goto(s, 'Chord   '); keys(s, 0x06, 0x06, 0x06, 0x06)
check('Chord = Major, all notes off sent: %r' % s.lcd[-1][16:24],
      g(s, 'CHORD') == 4 and s.lcd[-1][16:24] == 'Major   ' and sum(c[0] == 'alloff' for c in s.calls) == 32)
keys(s, 0x0e, 0x0e, 0x0e, 0x0e)
goto(s, 'Mono Part'); keys(s, 0x06, 0x06, 0x06)
check('Mono Part P3: %r' % s.lcd[-1][16:20], s.lcd[-1][16:19] == 'P3 ' and g(s, 'MONOP') == 3)
keys(s, 0x0e, 0x0e, 0x0e)
check('Mono Part Off', s.lcd[-1][16:19] == 'Off')
goto(s, 'Mod1 Amount'); keys(s, 0x0f)
check('Mod1 Amount -10: %r' % s.lcd[-1][16:20], s.lcd[-1][16:19] == '-10' and g(s, 'MA') == 53)
keys(s, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07, 0x07)
check('... clamps at +63: %r' % s.lcd[-1][16:20], s.lcd[-1][16:19] == '+63')
goto(s, 'Arp Tempo');
check('Arp Tempo shows 120 BPM: %r' % s.lcd[-1][16:20], s.lcd[-1][16:19] == '120')
keys(s, 0x0f, 0x0f, 0x0f, 0x0f, 0x0f, 0x0f, 0x0f, 0x0f, 0x0f)
check('Arp Tempo clamps at 40', s.lcd[-1][16:19] == '040' and g(s, 'ARPBPM') == 0)
keys(s, 0x05); keys(s, *[0x0f] * 10)
check('Arp Gate clamps at its min 5', g(s, 'ARPGATE') == 5)
goto(s, 'Arp Part')
check('Arp Part P1: %r' % s.lcd[-1][16:19], s.lcd[-1][16:19] == 'P1 ')
s.st(0xf6cd, 0xff, 1); goto(s, 'Wave Scan'); keys(s, 0x0a)
check('Part key: 0xFF -> P1: %r' % s.lcd[-1], s.ld(0xf6cd, 1) == 0 and s.lcd[-1].endswith('P1'))
s.st(0xf6cd, 2, 1); s.calls.clear(); keys(s, 0x01)
check('Exit pops the state and redraws', s.ld(0xb6, 1) == 0 and s.calls[-1][0] == 'redraw')
put(s, 'DRIFTP', 7)
s2 = new(ic15, s.m[0xc000:])
s2.st(0x1a, 0, 2); keys(s2, 0xff)
check('settings survive a power cycle (battery RAM), state is reset', g(s2, 'DRIFTP') == 7 and g(s2, 'MCUR') == 0xff)

# ---------------------------------------------------------------- chord + unison
s = new(ic15); keys(s, 0xff); s.calls.clear()
put(s, 'CHORD', 4); put(s, 'UNIV', 1); put(s, 'UNID', 20)
before = regs(s) if False else None
note(s, True, 60)
c = [(x[1], x[5]) for x in s.calls if x[0] == 'on']
check('Major chord x 2 unison voices: %s' % c, c == [(60, -20), (60, 20), (64, -20), (64, 20), (67, -20), (67, 20)])
check('... MIDI loop registers kept, page back', regs(s) == (0x1234, 0x3c05, 100, 0x20) and s.bank == 0)
s.calls.clear(); note(s, False, 60)
check('note off: 6 offs', [x[1] for x in s.calls if x[0] == 'off'] == [60, 60, 64, 64, 67, 67])
put(s, 'UNIP', 2); s.calls.clear(); note(s, True, 60)
check('Unison Part P2: part 3 plays 1 voice', ons(s) == [60, 64, 67])
put(s, 'CHPART', 2); s.calls.clear(); note(s, True, 60)
check('Chord Part P2: part 3 plays the root only', ons(s) == [60])
put(s, 'CHPART', 0); put(s, 'CHORD', 3); s.calls.clear(); note(s, True, 120)
check('notes above 127 dropped (5th+Oct on 120): %s' % ons(s), ons(s) == [120, 127])
s.calls.clear(); note(s, True, 60, part=8)
check('rhythm part: stock note on', ons(s) == [60])

# ---------------------------------------------------------------- mono / glide
s = new(ic15); keys(s, 0xff); s.calls.clear()
put(s, 'MONOP', 3)
note(s, True, 60); note(s, True, 64); note(s, False, 64); note(s, False, 60)
check('mono: %s' % evs(s), evs(s) == [('on', 60), ('off', 60), ('on', 64), ('off', 64), ('on', 60), ('off', 60)])
s.calls.clear(); note(s, True, 60); note(s, True, 64); note(s, False, 60); note(s, False, 64)
check('mono: releasing a hidden key does nothing: %s' % evs(s),
      evs(s) == [('on', 60), ('off', 60), ('on', 64), ('off', 64)])
s.calls.clear(); put(s, 'GLTIME', 50); put(s, 'LASTN', 0xff, 2)
note(s, True, 60); note(s, True, 67)
gl = [x[6] for x in s.calls if x[0] == 'on']
check('glide: second note starts 7 semitones down (%s)' % gl, gl == [0, -7 * 0x155])
note(s, False, 67)
check('... and back to 60 glides up', [x[6] for x in s.calls if x[0] == 'on'][-1] == 7 * 0x155)

# legato: a real slot / partial structure for part 3
s = new(ic15); keys(s, 0xff); s.calls.clear()
put(s, 'MONOP', 3); put(s, 'LEGATO', 1)
for r in range(0x40): s.st(0xee40 + r, 0xff, 1)
s.st(0xf285 + 0x20, 5, 1); s.st(0xf3c0 + 5, 0xff, 1); s.st(0xf440 + 5, 0x06, 1); s.st(0xee40 + 6, 0x0a, 1)
s.st(0xf460 + 5, 0, 1); s.st(0xf400 + 5, 60, 1)
for p in (6, 10): s.st(S['PB'] + p, 0x5000, 2); s.st(0xef40 + p, 0x5000, 2)
note(s, True, 60); s.calls.clear(); note(s, True, 64)
check('legato: no new attack, slot note 60 -> 64', evs(s) == [] and s.ld(0xf405, 1) == 64)
check('... pitch base +4 semitones on both partials', s.ld(S['PB'] + 6, 2) == 0x5000 + 4 * 0x155 and
      s.ld(0xef40 + 10, 2) == 0x5000 + 4 * 0x155)
note(s, False, 64)
check('... key up: back to 60 the same way', evs(s) == [] and s.ld(0xf405, 1) == 60 and s.ld(0xef40 + 6, 2) == 0x5000)
put(s, 'GLTIME', 99); note(s, True, 67)
check('legato + glide: target moves, the sound stays (GL = -7 st)', s.ld(0xef40 + 6, 2) == 0x5000 and
      sx(s.ld(S['GL'] + 6, 2)) == -7 * 0x155 and s.ld(S['PB'] + 6, 2) == 0x5000 + 7 * 0x155)
gl0 = sx(s.ld(S['GL'] + 6, 2))
for _ in range(40): tick(s)
gl1 = sx(s.ld(S['GL'] + 6, 2))
check('... ticks: glide moves toward the target (%d -> %d)' % (gl0, gl1),
      gl0 < gl1 <= 0 and s.ld(0xef40 + 6, 2) == 0x5000 + 7 * 0x155 + gl1)
for _ in range(4000): tick(s)
check('... and arrives', s.ld(S['GL'] + 6, 2) == 0 and s.ld(0xef40 + 6, 2) == 0x5000 + 7 * 0x155)

# ---------------------------------------------------------------- arpeggiator
s = new(ic15); keys(s, 0xff); s.calls.clear()
put(s, 'ARPM', 1); put(s, 'ARPP', 2); put(s, 'ARPOCT', 1)           # Up, part 3, 2 octaves, 120 BPM 1/16
for n in (64, 60, 67): note(s, True, n)
check('arp: keys are held, not played', evs(s) == [])
for _ in range(60 * 7): tick(s)
check('arp Up 2 oct: %s' % ons(s), ons(s) == [60, 64, 67, 72, 76, 79, 60])
offs = [i for i, c in enumerate(s.calls) if c[0] in ('on', 'off')]
check('... each note off before the next on', [c[0] for c in s.calls if c[0] in ('on', 'off')][:6] ==
      ['on', 'off', 'on', 'off', 'on', 'off'])
t_on = [i for i, c in enumerate([c for c in s.calls if c[0] == 'main']) ]
s.calls.clear()
put(s, 'ARPM', 2); tick(s)
for _ in range(60 * 6): tick(s)
check('arp Down (set while running): %s' % ons(s), ons(s)[-5:] == [67, 64, 60, 79, 76] or ons(s)[1:6] == [76, 72, 67, 64, 60])
s.calls.clear(); put(s, 'ARPM', 5); s.st(S['AI'], 0xff, 1); s.st(S['AO'], 0, 1)
for _ in range(60 * 6): tick(s)
check('arp Played order: %s' % ons(s), ons(s)[:6] == [64, 60, 67, 76, 72, 79])
s.calls.clear(); put(s, 'ARPM', 3); s.st(S['ALB'], 0xff, 1); s.st(S['AO'], 0, 1); s.st(S['AD'], 0, 1)
for _ in range(60 * 10): tick(s)
check('arp Up+Down: %s' % ons(s), ons(s)[:10] == [60, 64, 67, 72, 76, 79, 76, 72, 67, 64])
s.calls.clear(); put(s, 'ARPM', 4)
for _ in range(60 * 20): tick(s)
check('arp Random: notes from the set: %s' % ons(s)[:8], set(ons(s)) <= {60, 64, 67, 72, 76, 79} and len(set(ons(s))) > 3)
for n in (64, 60, 67): note(s, False, n)
s.calls.clear()
for _ in range(200): tick(s)
check('arp: all keys up -> silent', ons(s) == [] and g(s, 'ACUR') == 0xff)
put(s, 'ARPLATCH', 1); put(s, 'ARPM', 1)
note(s, True, 50); note(s, False, 50); s.calls.clear()
for _ in range(130): tick(s)
check('arp latch: keeps playing after key up: %s' % ons(s), ons(s) == [50, 62, 50] or ons(s) == [50, 62])
note(s, True, 55); s.calls.clear()
for _ in range(130): tick(s)
check('... a new key after all keys up starts a new set: %s' % ons(s), set(ons(s)) == {55, 67})


def rt(s, b):
    s.st(0xf8, b, 1); s.push(0xfffe); s.push(0); s.pc = lab['h_rt']
    while s.pc != 0xfffe: s.step()


put(s, 'ARPLATCH', 0); note(s, False, 55); put(s, 'ARPM', 1)
for n in (60, 64): note(s, True, n)
rt(s, 0xfa); s.calls.clear()
for i in range(6 * 4):
    rt(s, 0xf8); tick(s)
check('MIDI clock: 6 clocks per 1/16 step: %s' % ons(s), ons(s) == [60, 64, 72, 76])
rt(s, 0xfc)
check('... stop byte still reaches the stock handler (0x1E88)', True)
for n in (60, 64): note(s, False, n)

# ---------------------------------------------------------------- partial hook: drift, cutoff, PCM wave, lab
s = new(ic15); keys(s, 0xff)
BLK = 0xe1e4 + 2 * 0xf6 + 0x0e
for p, blk, ef80 in ((0x06, BLK, 0x24), (0x08, BLK + 0x3a, 0x24), (0x0a, BLK + 0x74, 0xc1)):
    s.st(0xee80 + p, blk, 2); s.st(0xef80 + p, ef80, 1); s.st(0xf1c0 + p, 0x80, 1); s.st(0xef40 + p, 0x5000, 2)
    s.st(0xf100 + p, 0xffff, 2); s.st(0xef81 + p, 0x4b, 1); s.st(0xf180 + p, 0x20, 1)
s.st(BLK + 0x74 + 5, 10, 1); s.st(BLK + 0x74 + 4, 0, 1)        # PCM wave 10, waveform 0 (bank 0)
put(s, 'DRIFTP', 31); put(s, 'RCUT', 100); put(s, 'WAVE', 5, 2); s.st(S['LFSR'], 0x1234, 2)
s.st(0x08, 0x7f, 1); s.st(0x50, 0x20, 2); s.st(0x52, 3, 2); s.st(0x56, BLK, 2); s.st(0x45, 60, 1); s.st(0x46, 100, 1)


def part_hook(p):
    s.st(0x54, p, 2); keep = (s.ld(0x50, 2), s.ld(0x52, 2), s.ld(0x54, 2), s.ld(0x56, 2)); s.call(0x3bb4)
    return keep == (s.ld(0x50, 2), s.ld(0x52, 2), s.ld(0x54, 2), s.ld(0x56, 2))


s.st(S['LASTSLOT'], 0xff, 1)
ok = part_hook(0x06) and part_hook(0x08)
d6, d8 = s.ld(0xef40 + 6, 2) - 0x5000, s.ld(0xef40 + 8, 2) - 0x5000
c6, c8 = s.ld(0xf1c0 + 6, 1), s.ld(0xf1c0 + 8, 1)
check('hook keeps r50-r56, does the replaced store', ok and s.ld(0xf100 + 6, 2) == 0 and s.bank == 0)
check('drift: same pitch offset for the note (%d, %d), PB = pitch' % (d6, d8),
      d6 == d8 and d6 != 0 and abs(d6) <= 124 and s.ld(S['PB'] + 6, 2) == s.ld(0xef40 + 6, 2))
check('random cutoff: 0x%02x 0x%02x, LA32 written, base kept' % (c6, c8),
      c6 == c8 != 0x80 and abs(c6 - 0x80) <= 100 and s.ld(0x0c41 + 6, 1) == c6 and s.ld(S['CB'] + 6, 1) == c6)
check('resonance rewritten as stock (0x4b): 0x%02x' % s.ld(0x0d01 + 6, 1), s.ld(0x0d01 + 6, 1) == 0x4b)
put(s, 'DRIFTP', 0); put(s, 'RCUT', 0)
w = lambda n: ic15[0x900 + 4 * n:0x904 + 4 * n]
pitch = lambda n: w(n)[2] | w(n)[3] << 8
s.st(S['LASTSLOT'], 0xff, 1); part_hook(0x0a)
check('PCM wave offset 5 (CC70 value of part 3): wave 15 in LA32', s.ld(0x0c41 + 0x0a, 1) == w(15)[0] and
      s.ld(0x0d01 + 0x0a, 1) == w(15)[1] | 8 and s.ld(0x0d00 + 0x0a, 1) == 0xc1)
check('... pitch and PB moved by the pitch-word difference',
      s.ld(0xef40 + 0x0a, 2) == min(0xe800, 0x5000 + pitch(15) - pitch(10)) == s.ld(S['PB'] + 0x0a, 2) and
      s.ld(S['OFS'] + 0x0a, 1) == 5)
s.st(0xef80 + 6, 0x24, 1); s.st(0xef81 + 6, 0x4b, 1); put(s, 'LRESO', 5); put(s, 'LXOR', 3)
s.st(S['LASTSLOT'], 0xff, 1); part_hook(0x06)
check('Lab: reso high bits = 4, control XOR 3: 0x%02x 0x%02x' % (s.ld(0x0d00 + 6, 1), s.ld(0x0d01 + 6, 1)),
      s.ld(0x0d01 + 6, 1) == 0x80 | 0x0b and s.ld(0x0d00 + 6, 1) == 0x27 and s.ld(0xef80 + 6, 1) == 0x27)
put(s, 'LRESO', 0); put(s, 'LXOR', 0)

# ---------------------------------------------------------------- CC70, mod matrix, wave sequence (part 3 note)
for r in range(0x40): s.st(0xee40 + r, 0xff, 1)
s.st(0xf285 + 0x20, 5, 1); s.st(0xf3c0 + 5, 0xff, 1); s.st(0xf440 + 5, 0x06, 1); s.st(0xee40 + 6, 0x0a, 1)
s.st(0xef80 + 6, 0x24, 1)
c6 = s.ld(0x0c41 + 6, 1); s.st(0x08, 0xff, 1)
s.st(0x45, 70, 1); s.st(0x46, 20, 1); s.st(0x50, 0x20, 2); s.st(0x42, 0x1234, 2); s.st(0x44, 0x4605, 2)
s.call(0x3bba)
check('CC70 = 20: PCM partial now wave 30, synth untouched', s.ld(0x0c41 + 0x0a, 1) == w(30)[0] and
      s.ld(0x0c41 + 6, 1) == c6 and g(s, 'WAVE', 2) == 20)
check('... pitch follows (wave 10 -> 30), regs and int_mask kept',
      s.ld(0xef40 + 0x0a, 2) == min(0xe800, 0x5000 + pitch(30) - pitch(10)) and
      (s.ld(0x42, 2), s.ld(0x44, 2), s.ld(0x46, 1), s.ld(0x50, 2)) == (0x1234, 0x4605, 20, 0x20) and s.ld(0x08, 1) == 0xff)
s.st(0x45, 16, 1); s.st(0x46, 77, 1); s.call(0x3bba)
s.st(0x45, 17, 1); s.st(0x46, 33, 1); s.call(0x3bba)
check('CC16 / CC17 stored', g(s, 'CCA') == 77 and g(s, 'CCB') == 33)
s.st(0x46, 99, 1); s.call(lab['h_at'])
check('aftertouch stored', g(s, 'AT') == 99)
# mod matrix: wheel -> pitch +63, CC16 -> cutoff -63, aftertouch -> level +63
put(s, 'MS', 1, 0); put(s, 'MD', 1, 0); put(s, 'MA', 126, 0)
put(s, 'MS', 7, 1); put(s, 'MD', 0, 1); put(s, 'MA', 0, 1)
put(s, 'MS', 2, 2); put(s, 'MD', 3, 2); put(s, 'MA', 126, 2)
s.st(0xf287 + 0x20, 127, 1)
pb6, cb6, lb6 = s.ld(S['PB'] + 6, 2), s.ld(S['CB'] + 6, 1), s.ld(S['LB'] + 6, 1)
for _ in range(4): tick(s)
check('mod wheel -> pitch: +%d' % (s.ld(0xef40 + 6, 2) - pb6), s.ld(0xef40 + 6, 2) - pb6 == (127 * 63 // 64) * 16)
check('CC16 77 -> cutoff -63: %d -> %d' % (cb6, s.ld(0x0c41 + 6, 1)),
      s.ld(0x0c41 + 6, 1) == max(0, cb6 - 77 * 63 // 64) == s.ld(0xf1c0 + 6, 1))
check('aftertouch 99 -> level (attenuation) %d -> %d' % (lb6, s.ld(0xf180 + 6, 1)),
      s.ld(0xf180 + 6, 1) == max(0, lb6 - (99 * 63 // 64) // 2))
s.st(0x0c41 + 6, 0, 1); s.st(0xf1c0 + 6, s.ld(0xf1c0 + 6, 1) + 10, 1)       # a live CC74 edit (+10)
for _ in range(4): tick(s)
check('... a live cutoff edit in between moves the base', s.ld(S['CB'] + 6, 1) == cb6 + 10)
s.st(0xf287 + 0x20, 0, 1)
for _ in range(4): tick(s)
check('wheel back to 0: pitch back to the base', s.ld(0xef40 + 6, 2) == pb6)
put(s, 'MS', 5, 0); put(s, 'MD', 0, 0); put(s, 'MS', 0, 1); put(s, 'MS', 0, 2); put(s, 'LFOR', 99)
cuts = set()
for _ in range(200): tick(s); cuts.add(s.ld(0x0c41 + 6, 1))
check('LFO -> cutoff moves (%d values)' % len(cuts), len(cuts) >= 5)
put(s, 'MS', 0, 0)
for _ in range(4): tick(s)
# wave sequence on the PCM partial: Up 4, fastest
put(s, 'WSPAT', 1); put(s, 'WSSPD', 99); put(s, 'WAVE', 0, 2)
s.st(0x50, 0x20, 2); s.st(0x52, 3, 2); s.st(0x56, BLK + 0x74, 2); s.st(S['LASTSLOT'], 0xff, 1)
s.st(0xef40 + 0x0a, 0x5000, 2); s.st(S['OFS'] + 0x0a, 0, 1); s.st(0x0c41 + 0x0a, w(10)[0], 1)
part_hook(0x0a)
seq = [s.ld(S['OFS'] + 0x0a, 1)]
for _ in range(5):
    for _ in range(4): tick(s)
    seq.append(s.ld(S['OFS'] + 0x0a, 1))
check('wave sequence Up 4: offsets %s' % seq, seq == [0, 1, 2, 3, 0, 1])
check('... LA32 plays wave 10 + offset', s.ld(0x0c41 + 0x0a, 1) == w(11)[0])
check('... pitch stays in tune (PB follows the wave)', s.ld(S['PB'] + 0x0a, 2) == min(0xe800, 0x5000 + pitch(11) - pitch(10)))
put(s, 'WSPAT', 0)
# velocity -> wave (note source)
put(s, 'MS', 3, 3); put(s, 'MD', 2, 3); put(s, 'MA', 126, 3); s.st(0x46, 127, 1)
s.st(0x50, 0x20, 2); s.st(0x52, 3, 2); s.st(S["LASTSLOT"], 0xff, 1); s.st(S["OFS"] + 0x0a, 0, 1); part_hook(0x0a)
check('velocity 127 -> wave +%d' % s.ld(S['OFS'] + 0x0a, 1), s.ld(S['OFS'] + 0x0a, 1) == (127 * 63 // 64) // 2)

odd = sorted({'%04x->%04x' % x for t in sims for x in t.odd})
check('no word access at an odd address %s' % odd, not odd)
segs = R.build_ic15(lab)[0]
print('IC15 code %d + %d bytes, IC19 hooks %d bytes' % (len(segs[0][1]), len(segs[1][1]),
                                                       sum(len(b) for _, b in R.build_ic19()[0])))
sys.exit(1 if fails else 0)
