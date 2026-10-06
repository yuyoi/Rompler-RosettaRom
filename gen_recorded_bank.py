"""Wave bank from the user's own recordings (recordings/*.wav, made with rosetta_recorder).  Every wave slot gets a recording (or a reversed / crushed /
sped-up variant of one), named by what it sounds like.  Long takes use the stretch trick (S=2/4).  Output: private_banks/recorded/ (IC8, IC7, IC15 x4).
usage: py -3.10 gen_recorded_bank.py [recordings_dir]"""
import os, sys, glob, hashlib, importlib.machinery, importlib.util
import numpy as np, soundfile as sf
from scipy.signal import resample_poly
from analyze_rec import feat
sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw'))
rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
rom = rs.Rom(); R = rs.RATE; C4 = 261.6256
SRC = sys.argv[1] if len(sys.argv) > 1 else 'recordings'; OUT = 'private_banks/recorded'; os.makedirs(OUT, exist_ok=True)

def norm(x, p=0.95): return x / (np.abs(x).max() + 1e-9) * p
def S_pitch(S): return 0x5000 - int(round(4096 * np.log2(S)))
def pitch_field(f):
    while f > 4000: f /= 2
    while f < 40: f *= 2
    return int(round(0x5000 + 4096 * np.log2(C4 / f)))
def xloop(x, m):
    f = max(64, m // 8); x = np.pad(x, (0, max(0, m + f - len(x))), mode='reflect'); y = x[:m].copy(); w = np.linspace(0, np.pi / 2, f)
    y[:f] = x[:f] * np.sin(w) + x[m:m + f] * np.cos(w); return y

recs = []
for fn in sorted(glob.glob(os.path.join(SRC, '*.wav'))):
    x, sr = sf.read(fn); x = x if x.ndim == 1 else x.mean(1)
    if sr != R: x = resample_poly(x, R, sr)
    d = feat(x); n = int(os.path.basename(fn)[:3])
    if d['flat'] > 0.4: w = 'Hiss' if d['cen'] > 3300 else 'Shh'
    elif d['dur'] < 0.15: w = 'Pop' if d['cen'] < 2000 else 'Tick'
    elif d['ac'] >= 0.75: w = 'Hum' if d['cen'] < 1500 else ('Vox' if d['cen'] < 2700 else 'Ahh')
    elif d['pk'] > 0.35 and d['dur'] < 0.6: w = 'Pluck'
    else: w = 'Buzz' if d['cen'] > 2800 else 'Moan'
    recs.append(dict(x=x, d=d, name='%s%02d' % (w, n), what=w, num=n))
recs.sort(key=lambda r: -r['d']['dur'])

def variant(r, k):
    x, nm = r['x'], r['name']
    if k == 0: return x, nm
    if k == 1: return x[::-1].copy() * np.minimum(1, np.arange(len(x)) / 150), ('r' + nm)[:8]
    if k == 2: q = 8; return np.repeat(np.round(norm(x, 1) * q) / q, 2)[:len(x)], ('c' + nm)[:8]
    return resample_poly(x, 2, 3), ('u' + nm)[:8]                        # k=3: x1.5 faster/higher

ids = [i for i in range(rs.NW) if i not in rom.parent]
ones = sorted([i for i in ids if not rom.ent[i][2]], key=lambda i: -rom.ent[i][1]); loops = [i for i in ids if rom.ent[i][2]]
swaps, names, pitches, key = {}, {}, {}, {}; seen = {}
for j, i in enumerate(ones):                                              # biggest slots <- longest takes
    a, n, lp = rom.ent[i]; q = int(j * len(recs) / len(ones)); r = recs[q]; vk = seen.get(q, 0); seen[q] = vk + 1; x, nm = variant(r, vk); dur = len(x)
    S = 1
    while S < 4 and n * S < dur: S *= 2
    y = x[:n * S].copy(); f = min(len(y), 400); y[-f:] *= np.linspace(1, 0, f)
    y = norm(np.pad(y, (0, n * S - len(y))))
    swaps[i] = norm(np.pad(resample_poly(y, 1, S) if S > 1 else y, (0, n))[:n]); pitches[i] = S_pitch(S); names[i] = nm
    key[i] = (nm, 'take %03d%s' % (r['num'], '' if vk == 0 else ' variant'), n, lp, S)
voiced = [r for r in recs if r['d']['dur'] > 0.3]
for j, i in enumerate(loops):                                             # loops: a steady middle chunk of a take
    a, n, lp = rom.ent[i]; r = voiced[j % len(voiced)]; x = r['x']; c = len(x) // 2 + (j // len(voiced)) * n // 3
    c = min(max(c, n), len(x) - n) if len(x) > 2 * n else len(x) // 2; seg = x[max(0, c - n):max(0, c - n) + 2 * n]
    z = norm(xloop(seg, n)); swaps[i] = z; pitches[i] = 0x5000 if r['d']['flat'] > .3 else pitch_field(r['d']['f0'] if 70 < r['d']['f0'] < 600 else 261.6)
    names[i] = ('L' + r['name'])[:8]; key[i] = (names[i], 'loop of take %03d' % r['num'], n, lp, 1)

files, lines = rs.build(rom, swaps, names, OUT, False, {}, {}, set(), pitches)
c = np.fromfile(OUT + '/' + files[2], np.uint8); np.tile(c, 4).tofile(OUT + '/ic15_SST39SF040_x4_512K_burn_this.bin')
with open(OUT + '/key.txt', 'w') as f:
    f.write('wave idx (0-based, panel shows idx+1), name, content, slot, stretch\n')
    for i in sorted(key): nm, what, n, lp, S = key[i]; f.write('%3d  %-8s  %s  (slot %.2f s%s, S=%d)\n' % (i, nm, what, n / R, ', loop' if lp else '', S))
print(len(swaps), 'waves from', len(recs), 'takes')
for fn in (files[0], files[1], 'ic15_SST39SF040_x4_512K_burn_this.bin'): print(fn, hashlib.md5(open(OUT + '/' + fn, 'rb').read()).hexdigest()[:8])
