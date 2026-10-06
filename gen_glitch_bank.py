"""'Glitch' test set for the Roland D-110: loud, unmistakable, nothing like the stock cheese.  Pink/white noise, bitcrushed buzz loops, stutters,
reversed/crushed speech, chirps, clicks and noisy drums fill EVERY IC7/IC8 wave in the stock slots (stretch S=2 on the 0.26 s+ slots for length).
Speech = offline Windows TTS, no third-party audio otherwise.  Output: private_banks/glitch/ (IC8, IC7, IC15 x4 512 KB).
usage: py -3.10 gen_glitch_bank.py <tts_dir>"""
import os, sys, hashlib, importlib.machinery, importlib.util
import numpy as np
from scipy.signal import resample_poly, lfilter

sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw'))
rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
from rosetta_d110 import read_wav
rom = rs.Rom(); R = rs.RATE; rng = np.random.default_rng(1988)
TTS = sys.argv[1]; OUT = 'private_banks/glitch'; os.makedirs(OUT, exist_ok=True); C4 = 261.6256


def tts(w):
    x = read_wav(os.path.join(TTS, w + '.wav')); i = np.where(np.abs(x) > 0.03 * np.abs(x).max())[0]; return x[i[0]:i[-1] + 1]


def norm(x, peak=0.97): return x / (np.abs(x).max() + 1e-9) * peak
def loud(x, g=3.0): return norm(np.tanh(g * norm(x, 1.0)))                       # clipped, pushed
def white(m): return rng.standard_normal(m)


def pink(m):
    f = np.fft.rfft(rng.standard_normal(m)); k = np.arange(len(f)); k[0] = 1; return np.fft.irfft(f / np.sqrt(k), m)


def crush(x, bits=4, ds=1):
    q = 2 ** (bits - 1); y = np.round(norm(x, 1.0) * q) / q
    return np.repeat(y[::ds], ds)[:len(y)] if ds > 1 else y


def env(m, k): return np.exp(-np.arange(m) / R * k)
def chirp(m, f0, f1): f = np.geomspace(f0, f1, m); return np.sin(2 * np.pi * np.cumsum(f) / R)
def rev(x): return x[::-1]


def stutter(x, sl, reps):
    out = np.zeros(len(x)); i = 0
    while i < len(x):
        s = x[i:i + sl]; blk = np.tile(s, reps)[:len(x) - i]; out[i:i + len(blk)] = blk; i += sl * reps
    return out


def fit_to(x, m): return np.pad(x[:m], (0, max(0, m - len(x))))


def xloop(x, m):                                     # seamless: cross-fade tail into head
    f = max(64, m // 8); x = np.pad(x, (0, max(0, m + f - len(x))), mode='reflect'); y = x[:m].copy(); w = np.linspace(0, np.pi / 2, f)
    y[:f] = x[:f] * np.sin(w) + x[m:m + f] * np.cos(w); return y


def cyc(m, k, fn):                                   # k whole cycles of fn(phase) in m samples -> loop at k*R/m Hz
    ph = np.arange(m) / m * k; return fn(ph % 1.0), k * R / m


def pitch_field(f):
    while f > 4000: f /= 2
    while f < 40: f *= 2
    return int(round(0x5000 + 4096 * np.log2(C4 / f)))


def S_pitch(S): return 0x5000 - int(round(4096 * np.log2(S)))


def deci(y, S, n): return norm(np.pad(resample_poly(y, 1, S) if S > 1 else y, (0, n))[:n])


def deci_loop(z, S, n): return norm(resample_poly(np.tile(z, 3), 1, S)[n:2 * n] if S > 1 else z)


# ---- looped recipes (periodic or noise), n samples, variation v -> (audio, pitch)
def L_pink(n, v): return norm(xloop(pink(n * 2), n)), 0x5000
def L_white(n, v): return norm(xloop(white(n * 2), n)), 0x5000
def L_crushpink(n, v): return norm(crush(xloop(pink(n * 2), n), 3 + v % 2, 1 + v % 3)), 0x5000


def L_buzz(n, v):
    k = 6 + 3 * (v % 4); z, f = cyc(n, k, lambda p: 2 * p - 1); return loud(crush(z, 5, 1), 2.0), pitch_field(f)


def L_pulse(n, v):
    k = 10 + 2 * (v % 5); z, f = cyc(n, k, lambda p: np.where(p < 0.08 + 0.05 * (v % 3), 1.0, -1.0)); return norm(z), pitch_field(f)


def L_fmmetal(n, v):
    k = 5 + (v % 4); z, f = cyc(n, k, lambda p: np.sin(2 * np.pi * p + 6 * np.sin(2 * np.pi * (2.76 + v % 3) * p))); return norm(z), pitch_field(f)


def L_ring(n, v):
    k = 4 + v % 5; z, f = cyc(n, k, lambda p: np.sin(2 * np.pi * p) * np.sign(np.sin(2 * np.pi * (7 + v % 3) * p))); return loud(z, 2.5), pitch_field(f)


def L_gate(n, v): g = (np.arange(n) // (n // (8 + 4 * (v % 3))) % 2).astype(float); return norm(xloop(white(n * 2), n) * g), 0x5000


def L_vowel(w):
    def f_(n, v):
        x = tts(w); a = len(x) // 2 - n // 2; seg = x[max(0, a):max(0, a) + n * 2]; z = xloop(seg, n)
        return loud(crush(z, 6, 1), 2.0), 0x5000
    return f_


LOOPS = [L_pink, L_white, L_crushpink, L_buzz, L_pulse, L_fmmetal, L_ring, L_gate, L_vowel('ahh'), L_vowel('eee'), L_vowel('ooh'), L_vowel('mmm')]


# ---- one-shot recipes: return audio of length m (=n*S)
def O_click(m, v): x = np.zeros(m); x[:3] = 1; x += 0.6 * white(m) * env(m, 900); return loud(x, 4)
def O_zap(m, v): return loud(chirp(m, 6000, 80 + 40 * (v % 4)) * env(m, 5 + v % 4), 3)
def O_rise(m, v): return loud(chirp(m, 80, 5000 + 800 * (v % 3)) * np.linspace(0.1, 1, m) ** 2, 2)
def O_noiseburst(m, v): return loud(pink(m) * env(m, 18 + 8 * (v % 4)), 3)
def O_crushburst(m, v): return norm(crush(white(m) * env(m, 12 + 5 * (v % 3)), 2 + v % 3, 2 + v % 4))
def O_imp(m, v): x = np.zeros(m); x[::int(R / (40 + 25 * (v % 5)))] = 1; return loud(np.convolve(x, env(300, 120), 'same'), 3)
def O_fmbell(m, v): t = np.arange(m) / R; return loud(np.sin(2 * np.pi * (400 + 90 * v) * t + 9 * np.sin(2 * np.pi * 1.4 * (400 + 90 * v) * t) * env(m, 6)) * env(m, 3 + v % 3), 2)
def O_stut(w): return lambda m, v: loud(stutter(fit_to(tts(w), m), 700 + 300 * (v % 4), 3 + v % 3), 2.5)
def O_revw(w): return lambda m, v: norm(rev(fit_to(tts(w), m)) * np.minimum(1, np.arange(m) / 200))
def O_crushw(w): return lambda m, v: loud(crush(fit_to(tts(w), m), 4, 3), 2.5)
ONES = [O_click, O_zap, O_rise, O_noiseburst, O_crushburst, O_imp, O_fmbell]
WORDS = ['hi', 'hey', 'yo', 'go', 'wow', 'hmm', 'ah', 'oh', 'boom', 'bang', 'pop', 'yay', 'yes', 'no', 'hello', 'roland']


def build_one(fn, n, S): return deci(fn(n * S, 0), S, n), S_pitch(S)


ids = [i for i in range(rs.NW) if i not in rom.parent]
swaps, names, pitches, key = {}, {}, {}, {}
# ---------------- IC8 : glitch drums
D = {'BsDrum': lambda m, v: loud(chirp(m, 260 - 40 * v, 30) * env(m, 5.5), 4) + 0.5 * O_click(m, v),
     'Snare': lambda m, v: loud(0.7 * pink(m) * env(m, 16 + 4 * v) + 0.5 * crush(chirp(m, 400, 150) * env(m, 25), 3, 2 + v), 3),
     'TomTom': lambda m, v: loud(chirp(m, 520 + 90 * v, 70) * env(m, 4), 3), 'HiHat': lambda m, v: loud(np.diff(white(m + 1)) * env(m, 40), 3),
     'Crash': lambda m, v: loud(pink(m) * env(m, 2.2) + 0.4 * np.diff(white(m + 1)) * env(m, 3.5), 3), 'Ride': lambda m, v: loud(O_fmbell(m, v + 2) * env(m, 1.2), 3),
     'Cup': O_fmbell, 'China': lambda m, v: loud(crush(pink(m) * env(m, 3), 3, 2), 3), 'RimShot': O_click, 'Clap': lambda m, v: loud(stutter(pink(m) * env(m, 30), 400, 4), 3),
     'MtHCnga': O_zap, 'Conga': lambda m, v: loud(chirp(m, 380, 160) * env(m, 7), 3), 'Bongo': O_zap, 'Cowbell': O_fmbell, 'Tambrin': O_crushburst,
     'Agogo': O_fmbell, 'HiTimbl': O_zap, 'LoTimbl': lambda m, v: loud(chirp(m, 300, 90) * env(m, 5), 3), 'Cabasa': O_crushburst,
     'TimpAtak': O_noiseburst, 'Timpani': lambda m, v: loud(chirp(m, 130, 55) * env(m, 2.2), 3)}
for i in ids:
    if rom.chip(i) != 'IC8': continue
    a, n, lp = rom.ent[i]; nm = rom.names[i].strip(); S = 2 if n >= 8192 else 1
    if lp:
        z = (L_pink, L_gate, L_crushpink)[len(swaps) % 3](n * S, 1)[0]; swaps[i] = deci_loop(z, S, n); pitches[i] = S_pitch(S) if S > 1 else 0x5000
    else:
        fn = next(v for k, v in D.items() if nm.startswith(k)); v = int(nm[-1]) if nm[-1].isdigit() else 0
        swaps[i] = deci(fn(n * S, v), S, n); pitches[i] = S_pitch(S)
    names[i] = ('G' + nm.replace(' ', ''))[:8]; key[i] = (names[i], 'glitch drum' + (' loop' if lp else ''), n, lp)
# ---------------- IC7
cls = {}
for i in ids:
    if rom.chip(i) == 'IC7': cls.setdefault((rom.ent[i][1], bool(rom.ent[i][2])), []).append(i)
for j, i in enumerate(cls[(2048, True)]):
    fn = LOOPS[j % len(LOOPS)]; a, n, lp = rom.ent[i]; swaps[i], pitches[i] = fn(n, j // len(LOOPS)); names[i] = ('%s%02d' % (fn.__name__[2:7], i % 100))[:8]; key[i] = (names[i], 'loop ' + fn.__name__, n, lp)
for j, i in enumerate(cls[(2048, False)]):
    fn = ONES[j % len(ONES)]; a, n, lp = rom.ent[i]; swaps[i], pitches[i] = build_one(fn, n, 1); names[i] = ('%s%02d' % (fn.__name__[2:7], i % 100))[:8]; key[i] = (names[i], 'one-shot ' + fn.__name__, n, lp)
rec = [O_stut, O_revw, O_crushw]
for j, i in enumerate(cls[(4096, False)]):
    a, n, lp = rom.ent[i]
    if j < 12: w = WORDS[j]; fn = rec[j % 3](w); nm = ('%s%s' % ('SRC'[j % 3], w))[:8]; what = '%s word "%s"' % (('stutter', 'reversed', 'crushed')[j % 3], w)
    else: fn = ONES[j % len(ONES)]; nm = ('%s%02d' % (fn.__name__[2:7], i % 100))[:8]; what = 'one-shot ' + fn.__name__
    swaps[i], pitches[i] = build_one(fn, n, 2); names[i] = nm; key[i] = (nm, what, n, lp)
for w, i, f in zip(['yes', 'no'], cls[(8192, False)], [O_stut, O_crushw]):
    a, n, lp = rom.ent[i]; swaps[i], pitches[i] = build_one(f(w), n, 2); names[i] = ('Gl' + w)[:8]; key[i] = (names[i], 'glitched "%s"' % w, n, lp)
for i, f, nm in zip(cls[(16384, False)], [lambda m, v: loud(pink(m) * np.linspace(0.05, 1, m) ** 2, 3), O_revw('hello')], ['PinkRise', 'RevHello']):
    a, n, lp = rom.ent[i]; swaps[i], pitches[i] = build_one(f, n, 2); names[i] = nm; key[i] = (nm, 'long glitch', n, lp)

files, lines = rs.build(rom, swaps, names, OUT, False, {}, {}, set(), pitches)
c = np.fromfile(OUT + '/' + files[2], np.uint8); i8 = np.fromfile(OUT + '/' + files[0], np.uint8); i7 = np.fromfile(OUT + '/' + files[1], np.uint8)
worst = 1.0
for i, x in swaps.items():
    pos, e = int(c[0x900 + 4 * i]), (int(c[0x901 + 4 * i]) >> 4) & 7; a, n = pos * 0x800, 0x800 << e
    r, base = (i8, 0) if a < 0x40000 else (i7, 0x40000)
    d = rs.log_to_lin(rs.rom_to_log(r[(a - base) * 2:(a - base + n) * 2])); ref = rs.fit(x, n, False)
    worst = min(worst, np.corrcoef(d, ref)[0, 1] if d.std() > 0 and ref.std() > 0 else 0.0)
np.tile(c, 4).tofile(OUT + '/ic15_SST39SF040_x4_512K_burn_this.bin')
with open(OUT + '/key.txt', 'w') as f:
    f.write('wave idx (0-based, panel shows idx+1), name, content, slot\n')
    for i in sorted(key): nm, what, n, lp = key[i]; f.write('%3d  %-8s  %s  (slot %.2f s%s)\n' % (i, nm, what, n / R, ', loop' if lp else ''))
print('waves %d (of %d visible), worst decode corr %.4f' % (len(swaps), len(ids), worst))
for fn in (files[0], files[1], 'ic15_SST39SF040_x4_512K_burn_this.bin'): print(fn, hashlib.md5(open(OUT + '/' + fn, 'rb').read()).hexdigest()[:8])
