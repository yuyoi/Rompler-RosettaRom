"""'Way different' ROM set for the Roland D-110: EVERY wave in IC8 and IC7 is replaced by a synthesised sound
(no samples, no Roland audio), IC12 gets new wave names, the pitch of each tonal wave and, in the LONG set, a few
sounds that are much longer than the stock slots (table rewritten, freed waves play silence).

  py -3.10 gen_way_different.py            -> private_banks/way_different/safe/  and  /long/   (3 .bin each + key.txt)

safe = stock table layout, every sound fits its original slot (the length codes the chip is known to handle).
long = same sounds plus: 2.05 s crash, 2.05 s sub boom, 1.02 s 808 kick, 4.10 s evolving drone loop.
Burn:  r15179880.ic8_patched.bin -> IC8,  r15179878.ic7_patched.bin -> IC7,  r15179873.ic12_patched.bin -> IC12.
The IC12 image contains Roland's control data (your dump + edits): keep these files private."""
import os, sys, importlib.machinery, importlib.util
import numpy as np
from scipy.signal import resample_poly

sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw'))
rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
rom = rs.Rom(); R = rs.RATE; rng = np.random.default_rng(1996)
src = open('gen_test_card.py', encoding='utf8').read().split("swaps, names = {}, {}")[0]
ns = {}; exec(src.replace("OUT = 'test_card'; os.makedirs(OUT + '/wavs', exist_ok=True)", ''), ns)
make_drum = ns['make']                                   # synth drum voices (tested earlier on hardware)

C4 = 261.6256
OUTDIR = 'private_banks/way_different'


def pitch_for(f0):          # table pitch so that key 60 (C4) plays a wave whose content is f0 Hz at 32 kHz as C4
    return int(round(0x5000 + 4096 * np.log2(C4 / f0)))


def tt(n): return np.arange(n) / R
def norm(x, peak=0.8): return x / (np.abs(x).max() + 1e-9) * peak
def decay(n, k): return np.exp(-tt(n) * k)


def cycles(n, f=C4):
    k = max(1, int(round(f * n / R))); return k, k * R / n


def per(n, k, amp):                                      # periodic additive: amp[h-1] on harmonic h, k cycles in n samples
    t = np.arange(n) / n; x = np.zeros(n)
    for h, a in enumerate(amp, 1):
        if a and h * k < n / 2:
            x += a * np.sin(2 * np.pi * h * k * t)
    return x


# ---- looped (sustained) recipes: exact integer cycles per slot -> seamless
def r_saw(n, v):
    k, f = cycles(n); return norm(per(n, k, [1 / h ** (0.85 + 0.1 * v) for h in range(1, 80)])), f


def r_square(n, v):
    k, f = cycles(n); return norm(per(n, k, [(1 / h if h % 2 else 0) for h in range(1, 80)])), f


def r_pwm(n, v):
    k, f = cycles(n); t = np.arange(n) / n; w = 0.12 + 0.1 * (v % 4); x = np.zeros(n)
    for h in range(1, 80):
        if h * k < n / 2:
            x += (np.sin(2 * np.pi * h * k * t) - np.sin(2 * np.pi * h * k * t - 2 * np.pi * h * w)) / h
    return norm(x), f


def r_organ(n, v):
    k, f = cycles(n); d = [1, .85, .9, .6, 0, .5, 0, .35, 0, .25][:]; d = d + [0] * 6
    if v % 2: d[0] = 0.5; d[1] = 1
    return norm(per(n, k, d)), f


VOW = {'A': (800, 1150), 'E': (400, 2000), 'I': (300, 2500), 'O': (500, 900), 'U': (350, 700)}


def r_vowel(vw):
    def f_(n, v):
        k, f = cycles(n, C4 * (0.5 if v % 2 else 1)); F1, F2 = VOW[vw]; amp = []
        for h in range(1, 120):
            fh = h * f; amp.append((np.exp(-0.5 * ((fh - F1) / 110) ** 2) + 0.7 * np.exp(-0.5 * ((fh - F2) / 160) ** 2) + 0.03) / h ** 0.6)
        return norm(per(n, k, amp)), f
    return f_


def r_glass(n, v):
    k, f = cycles(n); t = np.arange(n) / n; x = np.zeros(n)
    for h in range(1, 14):
        if (h * k + 1) < n / 2:
            x += (np.sin(2 * np.pi * h * k * t) + 0.8 * np.sin(2 * np.pi * (h * k + 1 + v % 2) * t + h)) / h ** 1.3
    return norm(x), f


def r_reed(n, v):
    k, f = cycles(n); return norm(per(n, k, [(h ** -0.5 if h % 2 else 0) * (1 if h < 14 else 0.3) for h in range(1, 40)])), f


LOOPS = [('Saw', r_saw), ('Sqr', r_square), ('Pwm', r_pwm), ('Org', r_organ), ('VoxA', r_vowel('A')), ('VoxE', r_vowel('E')),
         ('VoxI', r_vowel('I')), ('VoxO', r_vowel('O')), ('VoxU', r_vowel('U')), ('Glass', r_glass), ('Reed', r_reed)]


# ---- one-shot recipes
def r_fmbell(n, v):
    t = tt(n); f = C4 * (1 if v % 2 else 2); idx = 5 * np.exp(-t * 3); x = np.sin(2 * np.pi * f * t + idx * np.sin(2 * np.pi * f * 3.5 * t)) * decay(n, 6 / (n / R) + 1.5)
    return norm(x), f


def r_fmep(n, v):
    t = tt(n); f = C4; x = np.sin(2 * np.pi * f * t + 2.2 * np.exp(-t * 6) * np.sin(2 * np.pi * f * t)) * decay(n, 3 + 3 / (n / R) * 0.4) \
        + 0.3 * np.sin(2 * np.pi * f * 14 * t) * decay(n, 40)
    return norm(x), f


def r_pluck(n, v):
    T = int(round(R / C4)) + (v % 3) * 0; buf = rng.uniform(-1, 1, T); out = np.zeros(n); damp = 0.996 - 0.002 * (v % 3)
    for i in range(n):
        out[i] = buf[i % T]; buf[i % T] = damp * 0.5 * (buf[i % T] + buf[(i + 1) % T])
    return norm(out), R / T


def r_metal(n, v):
    t = tt(n); f = C4 * 1.5; x = sum(np.sin(2 * np.pi * f * r * t) * np.exp(-t * (8 + 7 * j)) for j, r in enumerate((1, 2.76, 5.4, 8.93, 11.34)))
    return norm(x), f


def r_marimba(n, v):
    t = tt(n); f = C4; x = np.sin(2 * np.pi * f * t) * decay(n, 9) + 0.5 * np.sin(2 * np.pi * 4 * f * t) * decay(n, 25) + 0.25 * np.sin(2 * np.pi * 9.9 * f * t) * decay(n, 60)
    return norm(x), f


def r_swoosh(n, v):
    x = rng.standard_normal(n); y = np.zeros(n); s = 0.0; tn = np.arange(n) / n
    a = 0.02 + 0.5 * tn ** 2 if v % 2 else 0.5 * (1 - tn) ** 2 + 0.02
    for i in range(n):
        s += a[i] * (x[i] - s); y[i] = s
    return norm(y * np.sin(np.pi * tn) ** 0.7, 0.8), None


def r_zap(n, v):
    t = tt(n); f = 150 + 3000 * np.exp(-t * (14 + 6 * (v % 3))); x = np.tanh(2 * np.sin(2 * np.pi * np.cumsum(f) / R)) * decay(n, 10)
    return norm(x), None


def r_sub(n, v):
    t = tt(n); f = 65.41 * (1 + 0.5 * np.exp(-t * 30)); ph = 2 * np.pi * np.cumsum(f) / R
    x = (np.sin(ph) + 0.25 * np.sin(2 * ph)) * decay(n, 5 / max(0.05, n / R) + 2)
    return norm(x), 65.41


def r_voxhit(n, v):
    k, f = cycles(n); F = r_vowel('AEIOU'[v % 5])(n, 0)[0]; return norm(F * decay(n, 4 / max(0.05, n / R) + 3)), f


def r_clank(n, v):
    t = tt(n); x = (np.sign(np.sin(2 * np.pi * 180 * t)) + np.sign(np.sin(2 * np.pi * 267 * t)) + 0.5 * rng.standard_normal(n)) * decay(n, 25 + 10 * (v % 3))
    return norm(x), None


ONES = [('Bell', r_fmbell), ('EPno', r_fmep), ('Pluck', r_pluck), ('Metal', r_metal), ('Marimba', r_marimba), ('Swoosh', r_swoosh),
        ('Zap', r_zap), ('Sub', r_sub), ('VoxHit', r_voxhit), ('Clank', r_clank)]


# ---- long showpieces (LONG set)
def long_crash(n):
    x = np.zeros(n); t = tt(n)
    for f in (330, 442, 563, 691, 877, 1213, 1790, 2310):
        x += np.sign(np.sin(2 * np.pi * f * t)) * 0.12
    nz = rng.standard_normal(n); y = np.zeros(n); s = q = 0.0
    for i in range(n):
        s = 0.93 * (s + nz[i] - q); q = nz[i]; y[i] = s
    return norm((x + 0.4 * y) * (0.35 * decay(n, 2.2) + 0.65 * decay(n, 0.9)) * np.minimum(1, t * 400)), None


def long_boom(n):
    t = tt(n); f = 52 + 90 * np.exp(-t * 8); ph = 2 * np.pi * np.cumsum(f) / R
    x = (np.sin(ph) + 0.3 * np.sin(2 * ph + 0.5)) * decay(n, 1.6) + 0.15 * np.sin(2 * np.pi * 31 * t) * decay(n, 1.1)
    return norm(np.tanh(1.5 * x)), None


def long_kick(n):
    t = tt(n); f = 42 + 150 * np.exp(-t * 28); ph = 2 * np.pi * np.cumsum(f) / R
    return norm(np.tanh(1.8 * np.sin(ph) * decay(n, 3.2)) + 0.3 * rng.standard_normal(n) * decay(n, 500)), None


def long_drone(n):
    k, f = cycles(n, C4 / 2); t = np.arange(n) / n; x = np.zeros(n)
    for h in range(1, 30):
        if h * k * 1.02 < n / 2:
            d = 1 + (h % 3)                                  # integer cycle counts: every voice returns to its start -> seamless 4 s loop
            x += (np.sin(2 * np.pi * h * k * t) * (1 + 0.5 * np.sin(2 * np.pi * d * t + h)) + 0.7 * np.sin(2 * np.pi * (h * k + d) * t + 2 * h)) / h ** 1.1
    return norm(x), f


def slot_text(n): return '%.2f s' % (n / R)


# ---- LONGER set: same table as safe, but each slot holds S times more sound. The sound is synthesised at full length, decimated by S into the
# slot, and the table pitch is lowered by log2(S) octaves so the chip plays it back at real speed (bandwidth drops to 16 kHz / S).
STRETCH_DRUM = {'crash': 4, 'china': 4, 'ride': 4, 'timpani': 4, 'cup': 2, 'bsdrum1': 2, 'bsdrum3': 2, 'tomtom': 2}
STRETCH_LOOP = {'Saw': 4, 'Sqr': 2, 'Pwm': 2, 'Org': 4, 'VoxA': 4, 'VoxE': 4, 'VoxI': 4, 'VoxO': 4, 'VoxU': 4, 'Glass': 4, 'Reed': 4}
STRETCH_HIT = {'Bell': 8, 'EPno': 4, 'Pluck': 4, 'Metal': 8, 'Marimba': 4, 'Swoosh': 8, 'Zap': 2, 'Sub': 8, 'VoxHit': 4, 'Clank': 4}


def stretched(call, n, S, loop):
    """call(length) -> (audio, f0). Returns (audio of n samples holding S*n samples of real sound, f0 as the chip sees it)"""
    if S == 1:
        return call(n)
    x, f0 = call(n * S)
    y = resample_poly(np.tile(x, 3), 1, S)[n:2 * n] if loop else resample_poly(x, 1, S)[:n]
    y = np.concatenate([y, np.zeros(n - len(y))]) if len(y) < n else y
    return norm(y), (f0 * S if f0 else None)


def build_set(kind):
    out = '%s/%s' % (OUTDIR, kind); os.makedirs(out, exist_ok=True)
    vis = [i for i in range(rs.NW) if i not in rom.parent]
    swaps, names, pitches, loops, key = {}, {}, {}, {}, []
    li = oi = 0; longer = (kind == 'longer'); real = {}
    for i in vis:
        a, n, loop = rom.ent[i]; nm = rom.names[i]
        if rom.chip(i) == 'IC8':
            b = nm.strip(); S = next((v for k_, v in STRETCH_DRUM.items() if b.lower().startswith(k_)), 1) if longer else 1
            x, _ = stretched(lambda m: (make_drum(nm, m, loop), None), n, S, loop); real[i] = n * S
            if S > 1:
                pitches[i] = int(round(rom.pitch[i] - 4096 * np.log2(S)))
            swaps[i] = x; names[i] = (('Sy' + b[:-1])[:7] + b[-1]) if b[-1].isdigit() else ('Sy' + b)[:8]; key.append((i, names[i], 'drum voice', n, loop))
        elif loop:
            cn, fn = LOOPS[li % len(LOOPS)]; v = li // len(LOOPS); li += 1; S = STRETCH_LOOP[cn] if longer else 1
            x, f0 = stretched(lambda m: fn(m, v), n, S, True); real[i] = n * S
            swaps[i] = x; pitches[i] = pitch_for(f0); names[i] = ('%s%02d' % (cn, i % 100))[:8]; key.append((i, names[i], 'loop ' + cn, n, loop))
        else:
            cn, fn = ONES[oi % len(ONES)]; v = oi // len(ONES); oi += 1; S = STRETCH_HIT[cn] if longer else 1
            x, f0 = stretched(lambda m: fn(m, v), n, S, False); real[i] = n * S
            swaps[i] = x; names[i] = ('%s%02d' % (cn, i % 100))[:8]; key.append((i, names[i], 'hit ' + cn, n, loop))
            if f0:
                pitches[i] = pitch_for(f0)
            elif S > 1:
                pitches[i] = int(round(0x5000 - 4096 * np.log2(S)))
    free = set()
    if kind == 'long':
        byname = {rom.names[i].strip(): i for i in vis}
        looped_ic7 = [i for i in vis if rom.chip(i) == 'IC7' and rom.ent[i][2]]
        # (wave, length code, voice, name, loops, which chip half the block goes in: 0 = IC8 drums, 1 = IC7 instruments)
        targets = [(looped_ic7[0], 6, long_drone, 'DroneL', True, 1), (byname['Timpani'], 5, long_boom, 'SubBoom', False, 1),
                   (byname['Crash'], 4, long_crash, 'LongCrsh', False, 0), (byname['BsDrum1'], 4, long_kick, 'Kick808', False, 0)]
        tset = {t[0] for t in targets}; claimed = bytearray(256)
        span = lambda j: (rom.pos[j], rom.pos[j] + (1 << ((rom.lenb[j] >> 4) & 7)))
        for i, e, fn, nm, lp, half in targets:
            size = 1 << e; best = None
            for st in range(128 * half, 128 * half + 128, size):
                if any(claimed[st:st + size]):
                    continue
                cost = 0
                for j in vis:
                    if j in tset:
                        continue
                    a_, b_ = span(j)
                    if a_ < st + size and b_ > st:
                        cost += (b_ - a_) * (3 if rom.chip(j) == 'IC8' else 1)      # protect the drum kit
                if best is None or cost < best[0]:
                    best = (cost, st)
            claimed[best[1]:best[1] + size] = b'\x01' * size
            for j in vis:                                    # everything overlapping the block gets freed
                a_, b_ = span(j)
                if j not in tset and a_ < best[1] + size and b_ > best[1]:
                    free.add(j)
            n = 0x800 << e; x, f0 = fn(n)
            swaps[i] = x; names[i] = nm; loops[i] = lp
            if f0:
                pitches[i] = pitch_for(f0)
            key.append((i, nm, 'LONG %s' % slot_text(n), n, lp))
        # waves lying wholly inside freed space (or inside a long wave's old slot) go too
        fu = bytearray(256)
        for j in free | tset:
            for u in range(*span(j)):
                fu[u] = 1
        for j in range(rs.NW):
            if j not in tset and j not in free and all(fu[u] for u in range(*span(j))):
                free.add(j)
        def closure(f):                                      # waves lying wholly inside freed space (or a long wave's old slot) go too
            f = set(f)
            while True:
                fu = bytearray(256)
                for k in f | tset:
                    for u in range(*span(k)):
                        fu[u] = 1
                more = {k for k in range(rs.NW) if k not in tset and k not in f and all(fu[u] for u in range(*span(k)))}
                if not more:
                    return f
                f |= more
        free = closure(free)
        trial = {k: v for k, v in swaps.items() if k not in free}
        if rs.plan_layout(rom, trial, free)[1]:              # no unit left to park the freed waves on: free one more small wave
            for cand in sorted((k for k in vis if k not in tset and k not in free), key=lambda k: (rom.ent[k][1], -k)):
                f2 = closure(free | {cand}); trial = {k: v for k, v in swaps.items() if k not in f2}
                if not rs.plan_layout(rom, trial, f2)[1]:
                    free = f2; break
            else:
                raise SystemExit('could not find room to park the freed waves')
        for j in list(free):
            swaps.pop(j, None); names.pop(j, None); pitches.pop(j, None)
    files, lines = rs.build(rom, swaps, names, out, False, {}, loops, free, pitches)
    open(out + '/key.txt', 'w').write('index  name      what\n' + '\n'.join('%3d  %-8s  %s  (slot %s%s)%s' % (i, nm, w, slot_text(n), (', sounds for %s' % slot_text(real[i])) if real.get(i, n) != n else '', ' loop' if lp else '') for i, nm, w, n, lp in key)
                                      + ('\n\nFREED (silent): ' + ', '.join('%d %s' % (j, rom.names[j].strip()) for j in sorted(free)) if free else '') + '\n')
    import json                                           # real sound length of time-compressed waves, so the Studio can show it in the Time column
    st = {str(i): int(v) for i, v in real.items() if v > rom.ent[i][1]}
    if st:
        json.dump(st, open(out + '/sound_times.json', 'w'))
    # verify: decode every new wave back through the TABLE of the built IC12 (follows moves) and compare
    c = np.fromfile(out + '/' + files[2], np.uint8); i8 = np.fromfile(out + '/' + files[0], np.uint8); i7 = np.fromfile(out + '/' + files[1], np.uint8)
    worst = 1.0
    for i, x in swaps.items():
        pos, e = int(c[0x900 + 4 * i]), (int(c[0x901 + 4 * i]) >> 4) & 7; a, n = pos * 0x800, 0x800 << e
        r, base = (i8, 0) if a < 0x40000 else (i7, 0x40000)
        d = rs.log_to_lin(rs.rom_to_log(r[(a - base) * 2:(a - base + n) * 2])); ref = rs.fit(x, n, False)
        cc = np.corrcoef(d, ref)[0, 1] if d.std() > 0 and ref.std() > 0 else 0.0; worst = min(worst, cc)
    for j in range(256):
        pos, e = int(c[0x900 + 4 * j]), (int(c[0x901 + 4 * j]) >> 4) & 7
        assert pos + (1 << e) <= 256 and pos % (1 << e) == 0, ('illegal table entry', j)
    aud = []                                              # audition: every new wave decoded from the BUILT images via the built table, loops tiled twice
    for i in sorted(swaps):
        pos, e = int(c[0x900 + 4 * i]), (int(c[0x901 + 4 * i]) >> 4) & 7; a, n = pos * 0x800, 0x800 << e
        r, base = (i8, 0) if a < 0x40000 else (i7, 0x40000); d = rs.log_to_lin(rs.rom_to_log(r[(a - base) * 2:(a - base + n) * 2]))
        d = np.tile(d, 2) if (int(c[0x901 + 4 * i]) & 0x80) and n <= 0x4000 else d
        S = real.get(i, n) // n
        aud += [resample_poly(d, S, 1) if S > 1 else d, np.zeros(R // 5)]       # stretched waves: played at the speed the lowered pitch field gives on the chip
    rs.write_wav(out + '/audition_all_waves.wav', np.concatenate([a_ / (np.abs(a_).max() + 1e-9) if len(a_) > R // 5 else a_ for a_ in aud]))
    print('%s: %d waves written, %d freed, worst decode correlation %.4f, table legal -> %s' % (kind, len(swaps), len(free), worst, out))
    return out


if __name__ == '__main__':
    for k in (sys.argv[1:] or ['safe', 'long', 'longer']):
        build_set(k)
