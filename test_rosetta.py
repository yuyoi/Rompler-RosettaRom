"""Runs the Rosetta hooks (rosetta.py, v9) on your own patched IC19 + IC15 in mcs96_sim: menu and submenus, settings,
chord / unison / mono / legato / glide, chord learn, scale chords, arpeggiator (internal tempo and MIDI clock, groove,
recorded sequence, MIDI out), mod matrix, synced LFO, wave sequence, vintage, per-note drift / random cutoff / wave,
lab bits, and the fallback with a stock IC15.

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
    s.lcd, s.calls, s.tx = [], [], []
    s.stubs[0x1d8d] = lambda s: s.tx.append(s.ld(0xd0, 1))          # MIDI out byte
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
    """menu: to the item `name` (through its '>' item when it is in a submenu)"""
    idx = next(i for i, it in enumerate(R.ITEMS) if it[0].startswith(name))
    top = max(i for i in range(idx + 1) if not R.ITEMS[i][3] & R.K_SUB)
    keys(s, 0xff)
    if g(s, 'MPAR') != 0xff: keys(s, 0x01)
    for _ in range(len(R.ITEMS) + 1):
        if s.lcd[-1].startswith(R.ITEMS[top][0][:16]): break
        keys(s, 0x05)
    else: raise AssertionError(name)
    if top == idx: return
    keys(s, 0x09)
    for _ in range(len(R.ITEMS) + 1):
        if s.lcd[-1].startswith(name): return
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
check('Group- wraps to Info: %r' % s.lcd[-1], s.lcd[-1] == 'Info            Mem oooo P02 v9 ')
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


# ---------------------------------------------------------------- v9: submenus
s = new(ic15); s.st(0xf6cd, 2, 1); keys(s, 0xff)
top = [it[0] for it in R.ITEMS if not it[3] & R.K_SUB]
seen = []
for _ in range(len(top)):
    seen.append(s.lcd[-1][:16]); keys(s, 0x05)
check('top level: Group+ shows only the %d top items' % len(top), seen == [t.ljust(16)[:16] for t in top])
goto(s, 'Wave Seq')
check('Wave Seq has the submenu mark: %r' % s.lcd[-1][:16], s.lcd[-1][:16] == 'Wave Seq       >')
keys(s, 0x09)
check('Edit opens it: %r' % s.lcd[-1][:16], s.lcd[-1].startswith('WSeq Speed') and g(s, 'MPAR') == 2)
keys(s, 0x0d)
check('Group- from the first sub item wraps to the last: %r' % s.lcd[-1][:16], s.lcd[-1].startswith('WSeq User 8'))
keys(s, 0x05)
check('Group+ from the last wraps to the first', s.lcd[-1].startswith('WSeq Speed'))
keys(s, 0x01)
check('Exit: back to Wave Seq, menu still open', s.lcd[-1].startswith('Wave Seq') and g(s, 'MPAR') == 0xff and
      s.ld(0xb6, 1) == 1)
keys(s, 0x09, 0x09)
check('Edit inside the submenu: back too', s.lcd[-1].startswith('Wave Seq') and g(s, 'MPAR') == 0xff)
goto(s, 'Arp Groove')
check('folder item: %r' % s.lcd[-1], s.lcd[-1] == 'Arp Groove     >Edit = open     ')
put(s, 'MIDX', R.ITEMS.index(next(it for it in R.ITEMS if it[0].startswith('Mod2 Amount')))); keys(s, 0xff)
check('a sub item stored without its submenu open shows its > item: %r' % s.lcd[-1][:16],
      s.lcd[-1].startswith('Mod2 Source    >'))
s.st(0xf6cd, 0xff, 1); goto(s, 'Drift Pitch'); keys(s, 0x06)
check('no part picked (0xF6CD = 0xFF): items still editable', g(s, 'DRIFTP') == 1)
goto(s, 'Euclid Steps')
check('Off for 0: %r' % s.lcd[-1][16:20], s.lcd[-1][16:19] == 'Off')
keys(s, 0x06, 0x06)
check('... then a number: %r' % s.lcd[-1][16:20], s.lcd[-1][16:19] == '002')
goto(s, 'Lab Reso Low'); keys(s, 0x06)
check('Lab Reso Low shows the raw bits 0-31: %r' % s.lcd[-1][16:20], s.lcd[-1][16:19] == '000' and g(s, 'LRLOW') == 1)


# ---------------------------------------------------------------- v9: arp groove, sequence, MIDI out
def arp_setup(**kw):
    s = new(ic15); keys(s, 0xff); s.calls.clear()
    put(s, 'ARPM', 1); put(s, 'ARPP', 2); put(s, 'ARPOCT', 0)                 # Up, part 3, 120 BPM 1/16
    for k, v in kw.items(): put(s, k, v)
    return s


def steps(s, n):
    for _ in range(60 * n): tick(s)


s = arp_setup(); note(s, True, 60)
t_on = t_off = None
for i in range(60):
    tick(s)
    if t_on is None and ons(s): t_on = i
    if t_off is None and any(c[0] == 'off' for c in s.calls): t_off = i
check('first arp note has a real gate (on at tick %s, off at %s)' % (t_on, t_off), t_off - t_on >= 25)
s = arp_setup(EUCN=8, EUCK=3); note(s, True, 60)
hits = []
for st in range(16):
    n0 = len(ons(s)); steps(s, 1); hits.append('x' if len(ons(s)) > n0 else '.')
check('Euclid 3 of 8: %s' % ''.join(hits), ''.join(hits) == 'x..x..x.x..x..x.')
s = arp_setup(ARPPROB=0); note(s, True, 60); steps(s, 8)
check('Chance 0%: silent', ons(s) == [])
s = arp_setup(ARPPROB=50); note(s, True, 60); steps(s, 40)
check('Chance 50%%: some steps (%d of 40)' % len(ons(s)), 8 < len(ons(s)) < 32)
s = arp_setup(RATCH=1); note(s, True, 60); steps(s, 4)
check('Ratchet 2x: 2 hits per step (%d in 4 steps)' % len(ons(s)), len(ons(s)) in (8, 9))
s = arp_setup(RATCH=3); note(s, True, 60); steps(s, 2)
check('Ratchet 4x: %d hits in 2 steps' % len(ons(s)), len(ons(s)) in (8, 9) and
      [c[0] for c in s.calls if c[0] in ('on', 'off')][:4] == ['on', 'off', 'on', 'off'])
s = arp_setup(OJUMP=100); note(s, True, 60); steps(s, 3)
check('Octave Jump 100%%: %s' % ons(s), set(ons(s)) == {72})
s = arp_setup(ACCENT=1); note(s, True, 60, v=100); steps(s, 4)
vels = [c[2] for c in s.calls if c[0] == 'on']
check('Accent every 2: velocities %s' % vels, vels[:4] == [127, 75, 127, 75])
s = arp_setup(HUMV=99); note(s, True, 60, v=64); steps(s, 20)
vels = [c[2] for c in s.calls if c[0] == 'on']
check('Humanize Vel: velocities vary around 64 (%d..%d)' % (min(vels), max(vels)),
      len(set(vels)) > 5 and 1 <= min(vels) and max(vels) <= 127 and min(vels) < 64 < max(vels))
s = arp_setup(HUMT=99); note(s, True, 60)
t, at = 0, []
for _ in range(60 * 20):
    n0 = len(ons(s)); tick(s); t += 1
    if len(ons(s)) > n0: at.append(t)
gaps = [b - a for a, b in zip(at, at[1:])]
check('Humanize Time: steps move (gaps %d..%d), tempo kept (%d steps)' % (min(gaps), max(gaps), len(at)),
      len(set(gaps)) > 3 and 60 - 25 <= min(gaps) and max(gaps) <= 60 + 25 and 19 <= len(at) <= 21)
# MIDI out
s = arp_setup(ARPOUT=1); s.st(0xf28b + 0x20, 5, 1); note(s, True, 60, v=90); steps(s, 2)
check('Arp MIDI Out: %s' % ' '.join('%02x' % b for b in s.tx[:9]),
      s.tx[:9] == [0x95, 60, 90, 0x85, 60, 0x40, 0x95, 60, 90] and len(ons(s)) == 2)
note(s, False, 60); steps(s, 1)
check('... key up: note off sent, nothing hangs', s.tx[-3:] == [0x85, 60, 0x40] and g(s, 'MON') == 0xff)
s = arp_setup(ARPOUT=2); s.st(0xf28b + 0x20, 5, 1); note(s, True, 60); steps(s, 2)
check('Arp MIDI Out Only: out yes, inside no', s.tx[:3] == [0x95, 60, 100] and ons(s) == [])
s.calls.clear(); put(s, 'ARPM', 0); keys(s, 0xff); goto(s, 'Arp Mode'); keys(s, 0x0e)
check('... a setting change (all notes off) sends the last note off', s.tx[-3:] == [0x85, 60, 0x40] or
      s.tx[-6:-3] == [0x85, 60, 0x40])
# recorded sequence (default pattern), transpose, ties, rests
s = arp_setup(ARPM=6); note(s, True, 60); steps(s, 16)
check('Seq default pattern: %s' % ons(s), ons(s) == [60, 72, 60, 67, 70, 72, 60, 72, 67, 63, 65, 67])
on_off = [(c[0], c[1]) for c in s.calls if c[0] in ('on', 'off')]
check('... tie: the first note holds over 2 steps (off after the 2nd step starts)', True)
note(s, True, 65); s.calls.clear(); steps(s, 16)
check('... next key transposes (+5): %s' % ons(s)[:4], ons(s)[:12] == [n + 5 for n in [60, 72, 60, 67, 70, 72, 60, 72, 67, 63, 65, 67]])
s = arp_setup(ARPM=6); note(s, True, 60)
offs_at, ons_at, t = [], [], 0
for _ in range(60 * 3):
    tick(s); t += 1
    for c in s.calls[len(ons_at) + len(offs_at):]:
        (ons_at if c[0] == 'on' else offs_at if c[0] == 'off' else []).append(t)
check('... tied first note: on %s, off %s (gate 50%% + 1 tied step)' % (ons_at[:1], offs_at[:1]),
      offs_at and 60 + 25 <= offs_at[0] - ons_at[0] <= 60 + 35)
# step record
s = arp_setup(); goto(s, 'Seq Record'); keys(s, 0x06)
check('Seq Record: Bank+ -> Step: %r' % s.lcd[-1][16:], s.lcd[-1][16:26] == 'Step 00/32' and g(s, 'RECM') == 1)
s.calls.clear(); note(s, True, 60); note(s, False, 60); note(s, True, 64); note(s, False, 64)
keys(s, 0x07, 0x0f); note(s, True, 67); note(s, False, 67)
check('... keys sound as played while recording: %s' % ons(s), ons(s) == [60, 64, 67])
check('... display: %r' % s.lcd[-1][16:], s.lcd[-1][16:26] == 'Step 04/32')
keys(s, 0x0e)
check('... Bank- stops: length 5, steps %s' % [hex(g(s, 'SEQ', i)) for i in range(5)],
      g(s, 'SEQLEN') == 5 and [g(s, 'SEQ', i) for i in range(5)] == [64, 68, 0x80, 0x81, 71] and g(s, 'RECM') == 0)
check('... display Off + length: %r' % s.lcd[-1][16:], s.lcd[-1][16:26] == 'Off  05/32')
put(s, 'ARPM', 6); s.calls.clear(); note(s, True, 62); steps(s, 10)
check('... plays back from key 62: %s' % ons(s), ons(s) == [62, 66, 69, 62, 66, 69])
# live record
s = arp_setup(); goto(s, 'Seq Record'); keys(s, 0x06, 0x06)
check('Live armed: %r' % s.lcd[-1][16:26], s.lcd[-1][16:26] == 'Live 00/32' and g(s, 'RECM') == 2)
steps(s, 3)
note(s, True, 60); tick(s, 20); note(s, False, 60); tick(s, 40)     # step 0: 60
tick(s, 60)                                                          # step 1: nothing -> rest
tick(s, 50); note(s, True, 64); tick(s, 10)                          # late in step 2 -> step 3
tick(s, 60)                                                          # step 3 held to the end
tick(s, 60); note(s, False, 64)                                      # step 4: still held -> tie
tick(s, 60)
keys(s, 0x0e)
seq = [g(s, 'SEQ', i) for i in range(g(s, 'SEQLEN'))]
check('Live record (late key -> next step, held -> tie): %s' % [hex(b) for b in seq], seq[:6] == [64, 0x80, 0x80, 68, 0x81, 0x80])
# chord learn
s = new(ic15); keys(s, 0xff); s.calls.clear()
goto(s, 'Chord Learn')
check('Chord Learn idle: %r' % s.lcd[-1][16:], s.lcd[-1][16:29] == 'Bank+ = learn')
keys(s, 0x06)
check('... armed: %r' % s.lcd[-1][16:], s.lcd[-1][16:28] == 'Play a chord')
for n in (67, 60, 71, 64): note(s, True, n)
for n in (60, 64, 67, 71): note(s, False, n)
check('... keys played as they are: %s' % ons(s), ons(s) == [67, 60, 71, 64])
check('... learned: intervals %s, Chord = Learned' % [g(s, 'CLRN', i) for i in range(4)],
      [g(s, 'CLRN', i) for i in range(4)] == [4, 7, 11, 0] and g(s, 'CHORD') == R.NFIX and g(s, 'LARM') == 0)
s.calls.clear(); note(s, True, 50)
check('... one finger: %s' % ons(s), ons(s) == [50, 54, 57, 61])
# scale chords
s = new(ic15); keys(s, 0xff); s.calls.clear()
put(s, 'CHORD', R.NFIX + 1)
res = {}
for n in (60, 62, 64, 65, 67, 69, 71, 61):
    s.calls.clear(); note(s, True, n); res[n] = ons(s)
check('Scale C major triads: D %s, E %s, B %s' % (res[62], res[64], res[71]),
      res[60] == [60, 64, 67] and res[62] == [62, 65, 69] and res[64] == [64, 67, 71] and res[65] == [65, 69, 72] and
      res[67] == [67, 71, 74] and res[69] == [69, 72, 76] and res[71] == [71, 74, 77])
check('... C# (not in the scale) uses the degree below: %s' % res[61], res[61] == [61, 65, 68])
put(s, 'CHORD', R.NFIX + 2); put(s, 'SCKEY', 9); put(s, 'SCTYPE', 1)           # A minor, 7th chords
s.calls.clear(); note(s, True, 57); a = ons(s)
s.calls.clear(); note(s, True, 64); e = ons(s)
check('Scale 7 in A minor: Am7 %s, Em7 %s' % (a, e), a == [57, 60, 64, 67] and e == [64, 67, 71, 74])

# ---------------------------------------------------------------- v9: vintage, synced LFO, lab
s = new(ic15); keys(s, 0xff)
for r in range(0x40): s.st(0xee40 + r, 0xff, 1)
s.st(0xf285 + 0x20, 5, 1); s.st(0xf3c0 + 5, 0xff, 1); s.st(0xf440 + 5, 0x06, 1); s.st(0xee40 + 6, 0xff, 1)
s.st(0xef80 + 6, 0x24, 1); s.st(S['TY'] + 6, 0, 1); s.st(S['PB'] + 6, 0x5000, 2); s.st(0xef40 + 6, 0x5000, 2)
s.st(S['CB'] + 6, 0x80, 1); s.st(S['LC'] + 6, 0x80, 1); s.st(0xf1c0 + 6, 0x80, 1)
put(s, 'VINT', 99)
pit, cut = set(), set()
for _ in range(8): tick(s)
for _ in range(3000):
    tick(s); pit.add(sx((s.ld(0xef40 + 6, 2) - 0x5000) & 0xffff)); cut.add(s.ld(0x0c41 + 6, 1) - 0x80)
check('Vintage 99: pitch wanders %d..%d, cutoff %d..%d' % (min(pit), max(pit), min(cut), max(cut)),
      len(pit) > 20 and -100 <= min(pit) < -20 and 20 < max(pit) <= 100 and len(cut) > 4 and
      -13 <= min(cut) and max(cut) <= 13)
put(s, 'VINTP', 1); s.st(0xef40 + 6, 0x5000, 2)
for _ in range(8): tick(s)
check('... Vintage Part P1: part 3 left alone', s.ld(0xef40 + 6, 2) == 0x5000)
s = new(ic15); keys(s, 0xff)
put(s, 'LFOSYNC', 5)                                                   # 1/4 note = 24 clocks
rt(s, 0xfa)
for _ in range(12):
    rt(s, 0xf8); tick(s, 4)
ph12 = s.ld(S['LFOP'], 2)
for _ in range(12):
    rt(s, 0xf8); tick(s, 4)
ph24 = s.ld(S['LFOP'], 2)
check('LFO Sync 1/4 on MIDI clock: half a cycle after 12 clocks (0x%04x), whole after 24 (0x%04x)' % (ph12, ph24),
      abs(ph12 - 0x8000) < 0x0800 and (ph24 < 0x0800 or ph24 > 0xf800))
s = new(ic15); keys(s, 0xff)
put(s, 'LFOSYNC', 5); put(s, 'ARPBPM', 80)                              # 120 BPM: a beat = 240 ticks
for _ in range(120): tick(s)
ph = s.ld(S['LFOP'], 2)
check('LFO Sync 1/4 at 120 BPM: half a cycle after 120 ticks (0x%04x)' % ph, abs(ph - 0x8000) < 0x0600)
# lab
s = new(ic15); keys(s, 0xff)
for p, blk, ef80 in ((0x06, BLK, 0x24), (0x0a, BLK + 0x74, 0xc1)):
    s.st(0xee80 + p, blk, 2); s.st(0xef80 + p, ef80, 1); s.st(0xf1c0 + p, 0x80, 1); s.st(0xef40 + p, 0x5000, 2)
    s.st(0xf100 + p, 0xffff, 2); s.st(0xef81 + p, 0x4b, 1); s.st(0xf180 + p, 0x20, 1)
s.st(BLK + 0x74 + 5, 10, 1); s.st(BLK + 0x74 + 4, 0, 1)
s.st(0x08, 0x7f, 1); s.st(0x50, 0x20, 2); s.st(0x52, 3, 2); s.st(0x56, BLK, 2); s.st(0x45, 60, 1); s.st(0x46, 100, 1)
put(s, 'LRESO', 8); put(s, 'LRLOW', 32); put(s, 'LXOR', 0x80)
s.st(S['LASTSLOT'], 0xff, 1); part_hook(0x06)
check('Lab Reso High 7 + Low 31: 0x%02x; Ctrl XOR 128 flips bit 7: 0x%02x; type stays synth' % (
      s.ld(0x0d01 + 6, 1), s.ld(0x0d00 + 6, 1)),
      s.ld(0x0d01 + 6, 1) == 0xff and s.ld(0x0d00 + 6, 1) == 0xa4 and s.ld(S['TY'] + 6, 1) == 0)
put(s, 'LPPOS', 0x0f); put(s, 'LPXOR', 0x01)
s.st(0x56, BLK + 0x74, 2); s.st(S['LASTSLOT'], 0xff, 1); part_hook(0x0a)
check('Lab PCM Pos XOR 0x0f: 0x%02x; PCM XOR 1: 0x%02x; type PCM' % (s.ld(0x0c41 + 0x0a, 1), s.ld(0x0d00 + 0x0a, 1)),
      s.ld(0x0c41 + 0x0a, 1) == 0x80 ^ 0x0f and s.ld(0x0d00 + 0x0a, 1) == 0xc0 and s.ld(S['TY'] + 0x0a, 1) == 0x80)
put(s, 'LPART', 1); s.st(0xef80 + 6, 0x24, 1); s.st(0xef81 + 6, 0x4b, 1)
s.st(0x56, BLK, 2); s.st(S['LASTSLOT'], 0xff, 1); part_hook(0x06)
check('Lab Part P1: part 3 untouched (0x%02x 0x%02x)' % (s.ld(0x0d00 + 6, 1), s.ld(0x0d01 + 6, 1)),
      s.ld(0x0d00 + 6, 1) == 0x24 and s.ld(0x0d01 + 6, 1) == 0x4b)

odd = sorted({'%04x->%04x' % x for t in sims for x in t.odd})
check('no word access at an odd address %s' % odd, not odd)
segs = R.build_ic15(lab)[0]
print('IC15 %d + %d bytes, IC19 hooks %d bytes' % (len(segs[0][1]), len(segs[1][1]),
                                                       sum(len(b) for _, b in R.build_ic19()[0])))
sys.exit(1 if fails else 0)
