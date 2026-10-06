"""Acoustic/vocal IC7 test bank for the D-110: real instrument notes (Univ. of Iowa MIS recordings, downloaded to a
scratch dir) + offline Windows TTS speech, cut/looped to fit every IC7 slot.  Nothing synthetic, no Roland data.
Everything outside the slots is encoded silence.  Output goes to private_banks/acoustic/ (gitignored: third-party audio).
usage: py -3.10 gen_acoustic_bank.py <iowa_dir> <tts_dir> [stretch]
stretch S (1,2,4): one-shots are stored S times too fast; play them log2(S)*12 semitones lower to get real speed back
and S times the slot length (a 512 ms slot at S=4 holds 2 s)"""
import os, sys, aifc, hashlib, importlib.machinery, importlib.util
import numpy as np
from scipy.signal import resample_poly

sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw'))
rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
from rosetta_d110 import read_wav
rom = rs.Rom(); R = rs.RATE; FULL = rs.FULL
IOWA, TTS = sys.argv[1], sys.argv[2]
S = int(sys.argv[3]) if len(sys.argv) > 3 else 1
OUT = 'private_banks/acoustic' + ('_x%d' % S if S > 1 else ''); os.makedirs(OUT, exist_ok=True)


def read_aiff(fn):
    a = aifc.open(fn, 'rb'); n, sw, sr, nf = a.getnchannels(), a.getsampwidth(), a.getframerate(), a.getnframes()
    raw = a.readframes(nf); a.close()
    if sw == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        d = ((b[:, 0] << 16) | (b[:, 1] << 8) | b[:, 2]); d = np.where(d >= 2 ** 23, d - 2 ** 24, d).astype(np.float64) / 2 ** 23
    elif sw == 2:
        d = np.frombuffer(raw, '>i2').astype(np.float64) / 32768
    else:
        d = np.frombuffer(raw, '>i4').astype(np.float64) / 2 ** 31
    d = d.reshape(-1, n).mean(1)
    g = np.gcd(sr, R); return resample_poly(d, R // g, sr // g)


def notes(x, min_gap=0.12, thr=0.06, max_len=3.0):
    """split a multi-note recording into [(start, end)] by envelope"""
    h = int(R * 0.01); e = np.sqrt(np.convolve(x ** 2, np.ones(h) / h, 'same')); e = e[::h]; pk = e.max()
    on = e > thr * pk; out = []; i = 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and (on[j] or on[j:j + int(min_gap / 0.01)].any()): j += 1
            if (j - i) * 0.01 > 0.08: out.append((i * h, min(j * h, i * h + int(max_len * R))))
            i = j
        else: i += 1
    return out


def fade(x, ms_in=1.0, frac_out=0.12):
    x = x.copy(); a = max(1, int(R * ms_in / 1000)); x[:a] *= np.linspace(0, 1, a)
    b = max(8, int(len(x) * frac_out)); x[-b:] *= np.linspace(1, 0, b); return x


def oneshot(seg, n):
    m = n * S; y = fade(seg[:m] if len(seg) >= m else np.concatenate([seg, np.zeros(m - len(seg))]))
    if S > 1: y = resample_poly(y, 1, S); y = np.concatenate([y, np.zeros(n)])[:n]    # S times too fast
    return y


def loop(seg, n):
    """pitch-synchronous loop: pick a stable stretch, find its period, resample k cycles into n samples"""
    s = min(int(0.22 * R), max(0, len(seg) - int(0.35 * R))); y = seg[s:s + int(0.3 * R)]
    y = y - y.mean(); lags = np.arange(int(R / 1000), int(R / 55)); ac = np.array([np.dot(y[:-l], y[l:]) for l in lags])
    P = lags[np.argmax(ac[:len(lags)])]
    for l in range(1, len(lags) - 1):                    # first strong peak = fundamental period (avoid sub-octave pick)
        if ac[l] > ac[l - 1] and ac[l] >= ac[l + 1] and ac[l] > 0.8 * ac.max(): P = lags[l]; break
    k = max(1, int(round(n / P))); L = int(round(k * P)); a = len(y) // 2 - L // 2; cyc = y[a:a + L]
    z = np.interp(np.linspace(0, L, n, endpoint=False), np.arange(L + 1), np.append(cyc, cyc[0])); return z


def wsola(x, ratio, fl=640):
    hs = fl // 2; ha = int(hs * ratio); out = np.zeros(int(len(x) / ratio) + fl); w = np.hanning(fl); pos = 0; o = 0; prev = None
    while pos + fl + 200 < len(x) and o + fl < len(out):
        if prev is None: s = pos
        else:
            lo, hi = max(0, pos - 160), min(len(x) - fl, pos + 160); best, s = -1e18, pos
            tgt = x[prev:prev + fl]
            for c in range(lo, hi, 8):
                v = np.dot(x[c:c + hs], tgt[hs:hs + hs] if len(tgt) >= fl else tgt[:hs])
                if v > best: best, s = v, c
        out[o:o + fl] += x[s:s + fl] * w; prev = s + hs; pos += ha; o += hs
    return out[:o + hs]


def speech(fn, n):
    x = read_wav(fn); thr = 0.03 * np.abs(x).max(); idx = np.where(np.abs(x) > thr)[0]; x = x[idx[0]:idx[-1] + 1]
    m = n * S
    if len(x) > m:
        r = len(x) / m
        x = wsola(x, r) if r < 4 else np.interp(np.linspace(0, len(x), m), np.arange(len(x)), x)
    return oneshot(x, n)


def load(name):
    x = read_aiff(os.path.join(IOWA, name)); x = x / (np.abs(x).max() + 1e-9); return x, notes(x)


SRC = {k: load(f) for k, f in {
    'flute1': 'Flute.vib.mf.C5B5.aiff', 'flute2': 'Flute.vib.pp.B3B4.aiff', 'violin': 'Violin.arco.mf.sulD.D4A4.aiff',
    'cello1': 'Cello.arco.pp.sulC.C2Gb2.aiff', 'cello2': 'Cello.arco.mf.sulG.G2Bb2.aiff', 'vibe': 'Vibraphone.sustain.pp.C3B3.aif',
    'pizzv': 'Violin.pizz.ff.sulE.E5A5.aiff', 'pizzv2': 'Violin.pizz.pp.sulG.G3B3.aiff', 'pizzc': 'Cello.pizz.ff.sulD.D3B3.aiff',
    'guitar': 'Guitar.mf.sulA.C4E4.mono.aif', 'marimba': 'Marimba.cord.mf.C5B5.aif', 'vibed': 'Vibraphone.dampen.mf.C4B4.aif',
    'piano1': 'Piano.mf.G4.aiff', 'piano2': 'Piano.ff.D5.aiff', 'piano3': 'Piano.pp.A7.aiff', 'piano4': 'Piano.pp.C1.aiff'}.items()}
for k, (x, nt) in SRC.items(): print('%-8s %3d notes' % (k, len(nt)))


def note(key, i):
    x, nt = SRC[key]; a, b = nt[i % len(nt)]; return x[a:b]


ids = sorted([i for i in range(rs.NW) if rom.chip(i) == 'IC7' and i not in rom.parent], key=lambda i: rom.ent[i][0])
cls = {}
for i in ids: cls.setdefault((rom.ent[i][1], bool(rom.ent[i][2])), []).append(i)
print({k: len(v) for k, v in cls.items()})
slots = {}; key = {}
# --- 37 sustained loops (64 ms, pitch-synchronous) : flute / violin / cello / vibraphone, rotating notes
sus = [('flute1', 0), ('violin', 0), ('cello1', 0), ('flute2', 0), ('vibe', 0), ('cello2', 0)]
for j, i in enumerate(cls[(2048, True)]):
    s, _ = sus[j % len(sus)]; ni = 1 + (j // len(sus)) * 2
    a, n, lp = rom.ent[i]; slots[i] = (a, n, lp, loop(note(s, ni), n)); key[i] = '%s note %d, sustained loop' % (s, ni)
# --- 9 short one-shots (64 ms): plucks
plk = [('pizzv', 2), ('pizzc', 3), ('guitar', 4), ('marimba', 5), ('vibed', 6), ('piano2', 1), ('pizzv2', 5), ('guitar', 8), ('marimba', 2)]
for (s, ni), i in zip(plk, cls[(2048, False)]):
    a, n, lp = rom.ent[i]; slots[i] = (a, n, lp, oneshot(note(s, ni), n)); key[i] = '%s note %d, attack' % (s, ni)
# --- 29 x 128 ms: 12 spoken syllables then plucked/struck instrument notes
words = ['hi', 'hey', 'yo', 'go', 'wow', 'hmm', 'ah', 'oh', 'boom', 'bang', 'pop', 'yay']
ins = [('piano1', 0), ('piano2', 0), ('piano3', 0), ('piano4', 0), ('piano1', 1), ('guitar', 1), ('guitar', 2), ('guitar', 5),
       ('marimba', 0), ('marimba', 3), ('marimba', 7), ('vibed', 1), ('vibed', 4), ('pizzv', 6), ('pizzc', 1), ('pizzv2', 1), ('piano2', 4)]
for j, i in enumerate(cls[(4096, False)]):
    a, n, lp = rom.ent[i]
    if j < len(words): slots[i] = (a, n, lp, speech(os.path.join(TTS, words[j] + '.wav'), n)); key[i] = 'speech "%s"' % words[j]
    else: s, ni = ins[j - len(words)]; slots[i] = (a, n, lp, oneshot(note(s, ni), n)); key[i] = '%s note %d, attack' % (s, ni)
# --- 256 ms / 512 ms: words
for w, i in zip(['yes', 'no'], cls[(8192, False)]):
    a, n, lp = rom.ent[i]; slots[i] = (a, n, lp, speech(os.path.join(TTS, w + '.wav'), n)); key[i] = 'speech "%s"' % w
for w, i in zip(['hello', 'roland'], cls[(16384, False)]):
    a, n, lp = rom.ent[i]; slots[i] = (a, n, lp, speech(os.path.join(TTS, w + '.wav'), n)); key[i] = 'speech "%s"' % w

space = np.zeros(262144)                              # IC7 only, silence everywhere else
for i, (a, n, lp, x) in sorted(slots.items(), key=lambda kv: -kv[1][1]):
    space[a - 262144:a - 262144 + n] = rs.fit(x, n, True)
img = rs.log_to_rom(rs.lin_to_log(space * FULL)); img.tofile(OUT + '/ic7_acoustic.bin')

dec = rs.log_to_lin(rs.rom_to_log(img)); worst = 1.0; aud = []
for i, (a, n, lp, x) in slots.items():
    d = dec[a - 262144:a - 262144 + n]; worst = min(worst, np.corrcoef(d, rs.fit(x, n, True))[0, 1])
    aud += [np.tile(d, 4) if lp else d, np.zeros(R // 8)]
rs.write_wav(OUT + '/audition_ic7_acoustic.wav', np.concatenate(aud))
with open(OUT + '/key.txt', 'w') as f:
    f.write('IC7 acoustic bank: wave idx (0-based; panel shows idx+1), original name, content\n')
    for i in sorted(slots): f.write('%3d  %-8s  %s\n' % (i, rom.names[i].strip(), key[i]))
print('slots %d, worst decode corr %.4f' % (len(slots), worst), 'MD5', hashlib.md5(img.tobytes()).hexdigest())
