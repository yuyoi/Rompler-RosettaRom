"""FULL fake banks for BOTH PCM chips: every byte is generated, none of Roland's data remains.
IC8 = synth drum kit (slots) ; IC7 = sine tone ladder (slots). Everything outside the slots = encoded silence.
Writes test_card/full_fake/{ic8,ic7}_fake_full.bin + audition WAVs + key. Names/IC12 untouched."""
import os, importlib.machinery, importlib.util
import numpy as np

sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw'))
rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
rom = rs.Rom(); R = rs.RATE
src = open('gen_test_card.py', encoding='utf8').read().split("swaps, names = {}, {}")[0]
ns = {}; exec(src.replace("OUT = 'test_card'; os.makedirs(OUT + '/wavs', exist_ok=True)", ''), ns)   # reuse make() = synth drum voices
make = ns['make']
OUT = 'test_card/full_fake'; os.makedirs(OUT, exist_ok=True)
FULL = rs.FULL

# whole wave space as silence (log value 0 = smallest magnitude), then slots on top
space = np.zeros(2 * 262144)                       # IC8 samples then IC7 samples (linear floats, 0 -> m=0)
slots = {}
ic7_ids = [i for i in range(rs.NW) if rom.chip(i) == 'IC7' and i not in rom.parent]
for i in range(rs.NW):
    if i in rom.parent: continue
    a, n, loop = rom.ent[i]
    if rom.chip(i) == 'IC8':
        x = make(rom.names[i], n, loop)
    else:
        k = ic7_ids.index(i); f = 110 * (3520 / 110) ** (k / max(1, len(ic7_ids) - 1))      # 110 Hz .. 3.5 kHz, equal ratio
        cyc = max(1, round(f * n / R)); t = np.arange(n); x = np.sin(2 * np.pi * cyc * t / n)
        if not loop: x *= np.minimum(1, t / 64) * np.clip((n - t) / (n * 0.35), 0, 1)
        x = x * 0.9
    slots[i] = (a, n, loop, x)
for i, (a, n, loop, x) in sorted(slots.items(), key=lambda kv: -kv[1][1]):
    space[a:a + n] = rs.fit(x, n, True)

imgs = {}
for name, lo in (('ic8', 0), ('ic7', 262144)):
    log = rs.lin_to_log(space[lo:lo + 262144] * FULL)
    img = rs.log_to_rom(log); imgs[name] = img
    img.tofile('%s/%s_fake_full.bin' % (OUT, name))

# verify: decode back, every slot must match its source; compare with the real Roland dumps
orig = {'ic8': rom.ic8, 'ic7': rom.ic7}; worst = {'ic8': 1.0, 'ic7': 1.0}; aud = {'ic8': [], 'ic7': []}
dec = {k: rs.log_to_lin(rs.rom_to_log(v)) for k, v in imgs.items()}
for i, (a, n, loop, x) in slots.items():
    k = 'ic8' if a < 262144 else 'ic7'; base = 0 if k == 'ic8' else 262144; d = dec[k][a - base:a - base + n]
    worst[k] = min(worst[k], np.corrcoef(d, rs.fit(x, n, True))[0, 1]); aud[k] += [np.tile(d, 3) if loop else d, np.zeros(R // 6)]
for k in imgs:
    same = float((imgs[k] == orig[k]).mean()) * 100
    print('%s: slots %d, worst corr %.4f, bytes equal to the real Roland chip: %.2f%% (chance level ~0.4%%), 0x00 bytes %.1f%%'
          % (k.upper(), sum(1 for s in slots.values() if (s[0] < 262144) == (k == 'ic8')), worst[k], same, 100 * float((imgs[k] == 0).mean())))
    rs.write_wav('%s/audition_%s_fake.wav' % (OUT, k), np.concatenate([a_ / (np.abs(a_).max() + 1e-9) if len(a_) > R // 6 else a_ for a_ in aud[k]]))
import hashlib
for k in imgs: print(k, 'MD5', hashlib.md5(imgs[k].tobytes()).hexdigest())
with open(OUT + '/README.txt', 'w') as f:
    f.write('Full fake PCM banks (generated; contain none of Roland\'s data).\n'
            'ic8_fake_full.bin -> burn to the DRUM chip (data MD5 of the real one: 61ad8efa5e78c19be691b2b2e2ddda4b)\n'
            'ic7_fake_full.bin -> burn to the INSTRUMENT chip (real one: ba6fa6a8f9892dacd6009f52225ac2a2)\n'
            'IC8: synth drum kit in every drum slot. IC7: pure sine ladder 110 Hz..3.5 kHz across the instrument slots, in slot order.\n'
            'Everything outside the slots is encoded silence. Control ROM / names untouched. Hardware-untested.\n')
