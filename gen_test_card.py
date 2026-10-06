"""Synthesise a test drum kit (no samples downloaded) for the D-110 IC8 slots, write WAVs, a .rcard card,
patched ROM images, and an audition WAV decoded back from the patched IC8 (proves the round trip)."""
import os, io, json, wave, zipfile, importlib.machinery, importlib.util
import numpy as np

sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw'))
rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
rom = rs.Rom(); R = rs.RATE; rng = np.random.default_rng(110)
OUT = 'test_card'; os.makedirs(OUT + '/wavs', exist_ok=True)


def t_(n): return np.arange(n) / R
def env(n, k): return np.exp(-t_(n) * k)
def sweep(n, f0, f1, k): t = t_(n); f = f1 + (f0 - f1) * np.exp(-t * k); return np.sin(2 * np.pi * np.cumsum(f) / R)
def noise(n): return rng.standard_normal(n)
def hp(x, a=0.9):
    y = np.zeros_like(x); p = q = 0.0
    for i, v in enumerate(x): y[i] = a * (p + v - q); p = y[i]; q = v
    return y
def square(n, f): return np.sign(np.sin(2 * np.pi * f * t_(n)))
def loopify(x, xf=512):
    x = x.copy(); n = len(x); w = np.linspace(0, 1, xf)
    x[:xf] = x[:xf] * w + x[n - xf:] * (1 - w); return x[:n - xf]  # tail folded in -> seam-free when tiled
def make(name, n, loop):
    nm = name.strip().lower()
    if nm.startswith('bsdrum1'): x = sweep(n, 160, 48, 30) * env(n, 22)
    elif nm.startswith('bsdrum2'): x = sweep(n, 220, 70, 60) * env(n, 60) + 0.2 * noise(n) * env(n, 400)
    elif nm.startswith('bsdrum3'): x = sweep(n, 120, 38, 12) * env(n, 7)
    elif nm.startswith('snare'): x = 0.55 * sweep(n, 230, 170, 25) * env(n, 28) + 0.8 * hp(noise(n), 0.7) * env(n, 18 + 4 * int(nm[-1]))
    elif nm.startswith('tomtom'): x = sweep(n, 230 - 50 * int(nm[-1]), 110 - 25 * int(nm[-1]), 9) * env(n, 7)
    elif 'hihat' in nm or nm == 'cabasa': x = hp(noise(n), 0.97) * env(n, 55 if loop is False else 1e-9)
    elif nm.startswith('crash') or nm.startswith('china') or nm.startswith('ride') or nm == 'cup':
        x = sum(square(n, f) for f in (330, 442, 563, 691, 877, 1213)) * 0.15 + hp(noise(n), 0.95) * 0.5; x = x * env(n, 4 if 'crash' in nm else 7)
    elif nm == 'rimshot': x = 0.6 * sweep(n, 1700, 900, 150) * env(n, 180) + 0.5 * hp(noise(n), .8) * env(n, 300)
    elif nm == 'clap': x = sum(hp(noise(n), .8) * np.roll(env(n, 70), k) * (np.arange(n) >= k) for k in (0, 300, 620)) + 0.6 * hp(noise(n), .8) * np.roll(env(n, 25), 900) * (np.arange(n) >= 900)
    elif nm in ('conga', 'mthcnga'): x = sweep(n, 330, 240, 40) * env(n, 22)
    elif nm == 'bongo': x = sweep(n, 480, 360, 50) * env(n, 35)
    elif nm == 'cowbell': x = (square(n, 540) + square(n, 800)) * 0.3 * env(n, 14)
    elif nm == 'tambrin': x = hp(noise(n), .96) * (env(n, 20) + 0.4 * np.roll(env(n, 35), 1200))
    elif nm == 'agogo': x = (np.sin(2 * np.pi * 900 * t_(n)) + 0.6 * np.sin(2 * np.pi * 1350 * t_(n))) * env(n, 12)
    elif nm == 'claves': x = np.sin(2 * np.pi * 2300 * t_(n)) * env(n, 70)
    elif 'timbl' in nm: x = sweep(n, 520 - 130 * ('lo' in nm), 400 - 100 * ('lo' in nm), 15) * env(n, 12) + 0.2 * hp(noise(n), .9) * env(n, 40)
    elif nm == 'timpatak': x = hp(noise(n), 0.8) * env(n, 200) + sweep(n, 160, 100, 20) * env(n, 10)
    elif nm == 'timpani': x = sweep(n, 110, 80, 10) * env(n, 4)
    else: x = sweep(n, 200, 120, 15) * env(n, 8)
    if loop:
        x = hp(noise(n), .97) * 0.6 + 0.4 * np.sin(2 * np.pi * 440 * t_(n)); x = np.tile(loopify(x), 2)[:n]
        k = 2 * np.pi * np.round(220 * n / R) / n * np.arange(n); x = 0.5 * np.sin(k) + 0.3 * np.sin(3 * k) + 0.15 * hp(np.roll(noise(n), 0), .9) * 0   # periodic: seam-free
    x = np.tanh(1.4 * x)
    return x / (np.abs(x).max() + 1e-9) * 0.9


swaps, names = {}, {}
for i in range(rs.NW):
    if rom.chip(i) != 'IC8':
        continue
    if i in rom.parent:
        continue     # tail half of another drum: shares its data
    a, n, loop = rom.ent[i]; nm = rom.names[i]
    x = make(nm, n, loop); swaps[i] = x; b = nm.strip(); names[i] = (('Sy' + b[:-1])[:7] + b[-1]) if b[-1].isdigit() else ('Sy' + b)[:8]
    with wave.open('%s/wavs/%03d_%s.wav' % (OUT, i, nm.strip().replace(' ', '')), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(R); w.writeframes(np.round(np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
meta = {'format': 'rosetta-card', 'version': 1, 'machine': 'D-110', 'name': 'synth_drums_test',
        'waves': {str(i): {'file': 'w%03d.wav' % i, 'src': 'synth'} for i in swaps}, 'names': {str(i): n for i, n in names.items()}}
with zipfile.ZipFile(OUT + '/synth_drums_test.rcard', 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('card.json', json.dumps(meta, indent=1))
    for i, x in swaps.items():
        z.writestr('w%03d.wav' % i, rs.pcm16(x))
files = rs.build(rom, swaps, names, OUT + '/patched'); print('built', files, 'slots', len(swaps))
# verify: decode the patched IC8 slots and compare with what we wrote; make an audition WAV from it
p8 = np.fromfile(OUT + '/patched/r15179880.ic8_patched.bin', np.uint8)
dec = rs.log_to_lin(rs.rom_to_log(p8)); aud = []; worst = 1.0
for i, x in swaps.items():
    a, n, loop = rom.ent[i]; d = dec[a:a + n]; c = np.corrcoef(d / (np.abs(d).max() + 1e-9), rs.fit(x, n, True))[0, 1]; worst = min(worst, c)
    if c < 0.99: print('  low corr slot', i, rom.names[i], n, loop, '%.3f' % c, 'peak %.3f rms %.4f' % (np.abs(x).max(), np.sqrt((x ** 2).mean())))
    aud += [np.tile(d, 3) if loop else d, np.zeros(R // 4)]
print('worst decode-vs-source correlation %.4f' % worst)
rs.write_wav(OUT + '/audition_synth_drums.wav', np.concatenate([a_ / (np.abs(a_).max() + 1e-9) if len(a_) > R // 4 else a_ for a_ in aud]))
print(open(OUT + '/patched/report.txt').read()[:400])
