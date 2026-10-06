"""ID-ladder test card: every IC8 slot = a pure sine, chromatic ladder from A3 upward (slot order). Unmistakable on the synth,
and the pitch tells you which slot you are hearing. Loop slots get whole cycles (seamless)."""
import os, json, zipfile, importlib.machinery, importlib.util
import numpy as np
sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw')); rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
rom = rs.Rom(); R = rs.RATE; OUT = 'test_card'; os.makedirs(OUT, exist_ok=True)
NOTE = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
swaps, names, rows = {}, {}, []
k = 0
for i in range(rs.NW):
    if rom.chip(i) != 'IC8' or i in rom.parent:
        continue
    a, n, loop = rom.ent[i]; midi = 57 + k; f = 440 * 2 ** ((midi - 69) / 12); k += 1
    cyc = max(1, round(f * n / R)); t = np.arange(n); x = np.sin(2 * np.pi * cyc * t / n)           # whole cycles: seamless when looped
    if not loop:
        x *= np.minimum(1, t / 64) * np.clip((n - t) / (n * 0.35), 0, 1)                            # short attack, fade the last 35%
    swaps[i] = x * 0.9; nm = '%s%d' % (NOTE[midi % 12], midi // 12 - 1); names[i] = ('T%02d %s' % (k - 1, nm))[:8]
    rows.append((i, rom.names[i].strip(), names[i], round(R * cyc / n, 1), loop))
meta = {'format': 'rosetta-card', 'version': 1, 'machine': 'D-110', 'name': 'id_ladder',
        'waves': {str(i): {'file': 'w%03d.wav' % i, 'src': 'sine'} for i in swaps}, 'names': {str(i): n for i, n in names.items()}}
with zipfile.ZipFile(OUT + '/id_ladder.rcard', 'w', zipfile.ZIP_DEFLATED) as z:
    z.writestr('card.json', json.dumps(meta, indent=1))
    for i, x in swaps.items(): z.writestr('w%03d.wav' % i, rs.pcm16(x))
files = rs.build(rom, swaps, names, OUT + '/patched_id', norm=False); print(files)
with open(OUT + '/id_ladder_key.txt', 'w') as f:
    f.write('slot  original   new name  tone(Hz)  loop\n'); [f.write('%4d  %-9s  %-8s  %7.1f  %s\n' % (r[0], r[1], r[2], r[3], 'LOOP' if r[4] else '')) for r in rows]
p8 = np.fromfile(OUT + '/patched_id/r15179880.ic8_patched.bin', np.uint8); dec = rs.log_to_lin(rs.rom_to_log(p8)); aud = []; worst = 1
for i, x in swaps.items():
    a, n, loop = rom.ent[i]; d = dec[a:a + n]; worst = min(worst, np.corrcoef(d, x)[0, 1]); d = d / np.abs(d).max(); aud += [np.tile(d, 3) if loop else d, np.zeros(R // 6)]
print('worst corr %.4f' % worst); rs.write_wav(OUT + '/audition_id_ladder.wav', np.concatenate(aud))
print(open(OUT + '/id_ladder_key.txt').read()[:600])
