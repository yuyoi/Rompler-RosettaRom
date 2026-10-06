"""'Organic longer' set for the Roland D-110: every IC7/IC8 wave is a recorded sound (Univ. of Iowa MIS instrument notes + offline Windows
speech/percussive voice sounds), stored S times too fast in the stock slots and played S times lower by the table pitch field (same trick as the
'longer' synth set, stock table layout, no untested length codes).  Writes IC8, IC7 and IC15 (x4 512 KB) images.  Third-party audio: private_banks/ only.
usage: py -3.10 gen_organic_longer.py <iowa_dir> <tts_dir>      -> private_banks/organic_longer/"""
import os, sys, hashlib, importlib.machinery, importlib.util, aifc
import numpy as np
from scipy.signal import resample_poly

sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw'))
rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
from rosetta_d110 import read_wav
rom = rs.Rom(); R = rs.RATE
IOWA, TTS = sys.argv[1], sys.argv[2]
KEEP = len(sys.argv) > 3 and sys.argv[3] == 'keepdrums'      # leave IC8 (stock drums) untouched
VC = sys.argv[4] if len(sys.argv) > 4 and sys.argv[3] == 'vcsl' else None   # dir of CC0 VCSL drum wavs -> real drums in IC8
OUT = 'private_banks/organic_longer' + ('_keepdrums' if KEEP else '_vcsl' if VC else ''); os.makedirs(OUT, exist_ok=True)
C4 = 261.6256


# ---------------------------------------------------------------- source handling
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
    d = d.reshape(-1, n).mean(1); g = np.gcd(sr, R); return resample_poly(d, R // g, sr // g)


def notes(x, min_gap=0.12, thr=0.06, max_len=3.0):
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


def norm(x, peak=0.85): return x / (np.abs(x).max() + 1e-9) * peak


def f0_of(seg):
    y = seg[int(0.04 * R):int(0.35 * R)]; y = y - y.mean()
    if len(y) < int(0.1 * R) or np.abs(y).max() < 1e-4: return None
    lags = np.arange(int(R / 2000), int(R / 50)); ac = np.array([np.dot(y[:-l], y[l:]) for l in lags]); P = None
    if ac.max() <= 0: return None
    for l in range(1, len(lags) - 1):
        if ac[l] > ac[l - 1] and ac[l] >= ac[l + 1] and ac[l] > 0.8 * ac.max(): P = lags[l]; break
    return R / P if P else None


def loop_cycles(seg, m):
    """pitch-synchronous loop: stable stretch, k whole cycles resampled into m samples -> (loop, k)"""
    s = min(int(0.22 * R), max(0, len(seg) - int(0.35 * R))); y = seg[s:s + int(0.3 * R)]
    y = y - y.mean(); lags = np.arange(int(R / 1000), int(R / 55)); ac = np.array([np.dot(y[:-l], y[l:]) for l in lags]); P = lags[np.argmax(ac)]
    for l in range(1, len(lags) - 1):
        if ac[l] > ac[l - 1] and ac[l] >= ac[l + 1] and ac[l] > 0.8 * ac.max(): P = lags[l]; break
    k = max(1, int(round(m / P))); L = int(round(k * P)); a = max(0, len(y) // 2 - L // 2); cyc = y[a:a + L]
    if len(cyc) < L: cyc = np.pad(cyc, (0, L - len(cyc)))
    return np.interp(np.linspace(0, L, m, endpoint=False), np.arange(L + 1), np.append(cyc, cyc[0])), k


def noise_loop(x, m):
    """seamless loop from noise-like audio: m samples, tail cross-faded into the head (equal power)"""
    f = max(64, m // 8)
    if len(x) < m + f: x = np.pad(x, (0, m + f - len(x)), mode='reflect')
    s = max(0, (len(x) - m - f) // 2); seg = x[s:s + m + f].copy(); y = seg[:m].copy(); w = np.linspace(0, np.pi / 2, f)
    y[:f] = seg[:f] * np.sin(w) + seg[m:m + f] * np.cos(w); return y


def wsola(x, ratio, fl=640):
    hs = fl // 2; ha = int(hs * ratio); out = np.zeros(int(len(x) / ratio) + fl); w = np.hanning(fl); pos = 0; o = 0; prev = None
    while pos + fl + 200 < len(x) and o + fl < len(out):
        if prev is None: s = pos
        else:
            lo, hi = max(0, pos - 160), min(len(x) - fl, pos + 160); best, s = -1e18, pos; tgt = x[prev:prev + fl]
            for c in range(lo, hi, 8):
                v = np.dot(x[c:c + hs], tgt[hs:hs + hs] if len(tgt) >= fl else tgt[:hs])
                if v > best: best, s = v, c
        out[o:o + fl] += x[s:s + fl] * w; prev = s + hs; pos += ha; o += hs
    return out[:o + hs]


def tts(word):
    x = read_wav(os.path.join(TTS, word + '.wav')); thr = 0.03 * np.abs(x).max(); idx = np.where(np.abs(x) > thr)[0]; return x[idx[0]:idx[-1] + 1]


FILES = {'flute1': 'Flute.vib.mf.C5B5.aiff', 'flute2': 'Flute.vib.pp.B3B4.aiff', 'violin': 'Violin.arco.mf.sulD.D4A4.aiff',
         'cello1': 'Cello.arco.pp.sulC.C2Gb2.aiff', 'cello2': 'Cello.arco.mf.sulG.G2Bb2.aiff', 'vibe': 'Vibraphone.sustain.pp.C3B3.aif',
         'pizzv': 'Violin.pizz.ff.sulE.E5A5.aiff', 'pizzv2': 'Violin.pizz.pp.sulG.G3B3.aiff', 'pizzc': 'Cello.pizz.ff.sulD.D3B3.aiff',
         'guitar': 'Guitar.mf.sulA.C4E4.mono.aif', 'marimba': 'Marimba.cord.mf.C5B5.aif', 'vibed': 'Vibraphone.dampen.mf.C4B4.aif',
         'piano1': 'Piano.mf.G4.aiff', 'piano2': 'Piano.ff.D5.aiff', 'piano3': 'Piano.pp.A7.aiff', 'piano4': 'Piano.pp.C1.aiff'}
SRC = {}
for k, f in FILES.items():
    x = read_aiff(os.path.join(IOWA, f)); x = x / (np.abs(x).max() + 1e-9); SRC[k] = (x, notes(x))


def note(key, i):
    x, nt = SRC[key]; a, b = nt[i % len(nt)]; return x[a:b]


# ---------------------------------------------------------------- building a wave
def pitch_field(f0s):
    """table pitch so a wave whose content is f0s Hz (as stored, S times too fast) plays as C4 on key 60"""
    while f0s > 4000: f0s /= 2
    while f0s < 40: f0s *= 2
    return int(round(0x5000 + 4096 * np.log2(C4 / f0s)))


def decimate(y, S, n):
    if S > 1: y = resample_poly(y, 1, S)
    return np.pad(y, (0, max(0, n - len(y))))[:n]


def one_note(seg, n, S, pitched=True):
    m = n * S; f0 = f0_of(seg) if pitched else None
    y = fade(seg[:m] if len(seg) >= m else np.pad(seg, (0, m - len(seg))))
    return norm(decimate(y, S, n)), (pitch_field(f0 * S) if f0 else 0x5000 - int(round(4096 * np.log2(S))))


def one_speech(x, n, S):
    m = n * S
    if len(x) > m:
        r = len(x) / m; x = wsola(x, r) if r < 4 else np.interp(np.linspace(0, len(x), m), np.arange(len(x)), x)
    y = fade(np.pad(x[:m], (0, max(0, m - len(x)))))
    return norm(decimate(y, S, n)), 0x5000 - int(round(4096 * np.log2(S)))


def loop_note(seg, n, S):
    m = n * S; z, k = loop_cycles(seg, m); y = resample_poly(np.tile(z, 3), 1, S)[n:2 * n] if S > 1 else z
    return norm(y), pitch_field(k * R / n)


def loop_noise(x, n, S):
    m = n * S; z = noise_loop(x, m); y = resample_poly(np.tile(z, 3), 1, S)[n:2 * n] if S > 1 else z
    return norm(y), 0x5000 - int(round(4096 * np.log2(S)))


def wavsrc(k):
    import soundfile as sf
    d, sr = sf.read(os.path.join(VC, k + '.wav')); d = d.mean(1) if d.ndim > 1 else d; g = np.gcd(sr, R); d = resample_poly(d, R // g, sr // g)
    d = d / (np.abs(d).max() + 1e-9); on = np.where(np.abs(d) > 0.02)[0]; return d[on[0]:] if len(on) else d


DRV = {'BsDrum1': ('wav', 'bd_a', 2), 'BsDrum2': ('wav', 'bd_b', 2), 'BsDrum3': ('wav', 'bd_c', 2),
       'Snare 1': ('wav', 'sn_1', 1), 'Snare 2': ('wav', 'sn_2', 1), 'Snare 3': ('wav', 'sn_3', 1), 'Snare 4': ('wav', 'sn_4', 1),
       'TomTom1': ('wav', 'tom_h', 2), 'TomTom2': ('wav', 'tom_l', 2), 'HiHat': ('wav', 'hat_c', 1), 'HiHatLp': ('wloop', 'hat_o', 1),
       'Crash': ('wav', 'crash1', 2), 'CrashLp': ('wloop', 'crash_long', 1), 'Ride': ('wav', 'ride', 2), 'Ride Lp': ('wloop', 'ride_long', 1),
       'Cup': ('wav', 'hat_oc', 1), 'China': ('wav', 'crash2', 2), 'ChinaLp': ('wloop', 'crash_long', 1), 'RimShot': ('wav', 'rim', 1),
       'Clap': ('wav', 'clap', 1), 'MtHCnga': ('wav', 'conga_a', 1), 'Conga': ('wav', 'conga_b', 2), 'Bongo': ('wav', 'bongo', 1),
       'Cowbell': ('wav', 'cowbell', 2), 'Tambrin': ('wav', 'tamb', 2), 'Agogo': ('wav', 'agogo', 2), 'HiTimbl': ('wav', 'darb_h', 1),
       'LoTimbl': ('wav', 'darb_l', 2), 'Cabasa': ('wav', 'cabasa', 2), 'TimpAtak': ('wav', 'timp', 1), 'Timpani': ('wav', 'timp', 4),
       'Noise': ('wloop', 'hat_o', 1)}

# ---------------------------------------------------------------- slot assignment
ids = [i for i in range(rs.NW) if i not in rom.parent]
swaps, names, pitches, key = {}, {}, {}, {}
# --- IC8: drums by name
DR = {  # name: (kind, source..., S)
    'BsDrum1': ('note', 'piano4', 0, 2), 'BsDrum2': ('tts', 'buh', 1), 'BsDrum3': ('tts', 'dun', 2),
    'Snare 1': ('tts', 'kuh', 2), 'Snare 2': ('tts', 'pah', 2), 'Snare 3': ('tts', 'chh', 2), 'Snare 4': ('tts', 'clap', 2),
    'TomTom1': ('tts', 'dum', 2), 'TomTom2': ('tts', 'tum', 2),
    'HiHat': ('tts', 'tss', 2), 'HiHatLp': ('nloop', 'sss', 2), 'Crash': ('tts', 'shh', 4), 'CrashLp': ('nloop', 'shh', 2),
    'Ride': ('note', 'vibe', 3, 4), 'Ride Lp': ('lnote', 'vibe', 5, 2), 'Cup': ('tts', 'ding', 2), 'China': ('tts', 'cha', 2),
    'ChinaLp': ('nloop', 'chh', 2), 'RimShot': ('tts', 'tick', 1), 'Clap': ('tts', 'clap', 2), 'MtHCnga': ('tts', 'tuh', 1),
    'Conga': ('note', 'pizzc', 2, 2), 'Bongo': ('tts', 'ta', 1), 'Cowbell': ('tts', 'tock', 2), 'Tambrin': ('tts', 'cha', 2),
    'Agogo': ('note', 'marimba', 5, 2), 'HiTimbl': ('note', 'marimba', 7, 2), 'LoTimbl': ('note', 'marimba', 0, 2),
    'Cabasa': ('tts', 'sss', 2), 'TimpAtak': ('tts', 'bong', 2), 'Timpani': ('note', 'piano4', 0, 4), 'Noise': ('nloop', 'sss', 2)}
for i in ids:
    if rom.chip(i) != 'IC8' or KEEP: continue
    a, n, lp = rom.ent[i]; nm = rom.names[i].strip(); spec = (DRV if VC else DR)[nm]; kind = spec[0]
    if kind == 'wav': x, p = one_note(wavsrc(spec[1]), n, spec[2], pitched=False); what = 'VCSL %s (CC0)' % spec[1]
    elif kind == 'wloop': x, p = loop_noise(wavsrc(spec[1]), n, spec[2]); what = 'VCSL %s noise loop (CC0)' % spec[1]
    elif kind == 'tts': x, p = one_speech(tts(spec[1]), n, spec[2]) if not lp else (None, None); what = 'voice "%s"' % spec[1]
    elif kind == 'note': x, p = one_note(note(spec[1], spec[2]), n, spec[3], pitched=False); what = '%s note %d' % (spec[1], spec[2])
    elif kind == 'lnote': x, p = loop_note(note(spec[1], spec[2]), n, spec[3]); what = '%s loop' % spec[1]
    else: x, p = loop_noise(tts(spec[1]) if len(tts(spec[1])) > n * spec[2] else np.tile(tts(spec[1]), 4), n, spec[2]); what = '"%s" noise loop' % spec[1]
    swaps[i] = x; pitches[i] = p; names[i] = ('O' + nm.replace(' ', ''))[:8]; key[i] = (names[i], what, n, lp)

# --- IC7: instruments / words
cls = {}
for i in ids:
    if rom.chip(i) == 'IC7': cls.setdefault((rom.ent[i][1], bool(rom.ent[i][2])), []).append(i)
sus = [('flute1', 0), ('violin', 0), ('cello1', 0), ('flute2', 0), ('vibe', 0), ('cello2', 0)]
for j, i in enumerate(cls[(2048, True)]):
    s, _ = sus[j % len(sus)]; ni = 1 + (j // len(sus)) * 2; a, n, lp = rom.ent[i]
    swaps[i], pitches[i] = loop_note(note(s, ni), n, 2); names[i] = ('%s%02d' % (s[:5].title(), i % 100))[:8]; key[i] = (names[i], '%s note %d, sustained loop' % (s, ni), n, lp)
plk = [('pizzv', 2), ('pizzc', 3), ('guitar', 4), ('marimba', 5), ('vibed', 6), ('piano2', 1), ('pizzv2', 5), ('guitar', 8), ('marimba', 2)]
for (s, ni), i in zip(plk, cls[(2048, False)]):
    a, n, lp = rom.ent[i]; swaps[i], pitches[i] = one_note(note(s, ni), n, 2); names[i] = ('%s%02d' % (s[:5].title(), i % 100))[:8]; key[i] = (names[i], '%s note %d' % (s, ni), n, lp)
words = ['hi', 'hey', 'yo', 'go', 'wow', 'hmm', 'ah', 'oh', 'boom', 'bang', 'pop', 'yay']
ins = [('piano1', 0), ('piano2', 0), ('piano3', 0), ('piano4', 0), ('piano1', 1), ('guitar', 1), ('guitar', 2), ('guitar', 5),
       ('marimba', 0), ('marimba', 3), ('marimba', 7), ('vibed', 1), ('vibed', 4), ('pizzv', 6), ('pizzc', 1), ('pizzv2', 1), ('piano2', 4)]
for j, i in enumerate(cls[(4096, False)]):
    a, n, lp = rom.ent[i]
    if j < len(words): swaps[i], pitches[i] = one_speech(tts(words[j]), n, 2); names[i] = ('V' + words[j])[:8]; key[i] = (names[i], 'speech "%s"' % words[j], n, lp)
    else:
        s, ni = ins[j - len(words)]; swaps[i], pitches[i] = one_note(note(s, ni), n, 4); names[i] = ('%s%02d' % (s[:5].title(), i % 100))[:8]; key[i] = (names[i], '%s note %d' % (s, ni), n, lp)
for w, i in zip(['yes', 'no'], cls[(8192, False)]):
    a, n, lp = rom.ent[i]; swaps[i], pitches[i] = one_speech(tts(w), n, 2); names[i] = ('V' + w)[:8]; key[i] = (names[i], 'speech "%s"' % w, n, lp)
for w, i in zip(['hello', 'roland'], cls[(16384, False)]):
    a, n, lp = rom.ent[i]; swaps[i], pitches[i] = one_speech(tts(w), n, 2); names[i] = ('V' + w)[:8]; key[i] = (names[i], 'speech "%s"' % w, n, lp)

# ---------------------------------------------------------------- build, verify, burn images
files, lines = rs.build(rom, swaps, names, OUT, False, {}, {}, set(), pitches)
c = np.fromfile(OUT + '/' + files[2], np.uint8); i8 = np.fromfile(OUT + '/' + files[0], np.uint8); i7 = np.fromfile(OUT + '/' + files[1], np.uint8)
worst = 1.0
for i, x in swaps.items():
    pos, e = int(c[0x900 + 4 * i]), (int(c[0x901 + 4 * i]) >> 4) & 7; a, n = pos * 0x800, 0x800 << e
    r, base = (i8, 0) if a < 0x40000 else (i7, 0x40000)
    d = rs.log_to_lin(rs.rom_to_log(r[(a - base) * 2:(a - base + n) * 2])); ref = rs.fit(x, n, False)
    cc = np.corrcoef(d, ref)[0, 1] if d.std() > 0 and ref.std() > 0 else 0.0; worst = min(worst, cc)
x4 = np.tile(c, 4); x4.tofile(OUT + '/ic15_SST39SF040_x4_512K_burn_this.bin')
with open(OUT + '/key.txt', 'w') as f:
    f.write('wave idx (0-based, panel shows idx+1), name, content, slot\n')
    for i in sorted(key):
        nm, what, n, lp = key[i]; f.write('%3d  %-8s  %s  (slot %.2f s%s)\n' % (i, nm, what, n / R, ', loop' if lp else ''))
print('waves %d, worst decode corr %.4f' % (len(swaps), worst))
for fn in (files[0], files[1], 'ic15_SST39SF040_x4_512K_burn_this.bin'):
    print(fn, hashlib.md5(open(OUT + '/' + fn, 'rb').read()).hexdigest()[:8])
