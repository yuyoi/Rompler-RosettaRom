"""Play a list of PCM waves in a row on the D-110 (parts 2+3 = MIDI ch 3+4): per wave a temp-timbre SysEx (device 0x14, 0.2 s gaps), then a note.
usage: py -3.10 audition_seq.py idx[:seconds] ...   (idx 0-based, panel number minus 1)"""
import sys, time, importlib.util, mido
sp = importlib.util.spec_from_file_location('ic12', 'ctrl/ic12_dump.py'); ic = importlib.util.module_from_spec(sp)
args = sys.argv[1:]; sys.argv = ['x']; sp.loader.exec_module(ic)
tmpl = next(t for t in (ic.timbre(i) for i in range(128)) if (t['mute'] & 1) and (ic.PS[t['s12']] >> 1) & 1)
o = mido.open_output('MIDI (OCTA-CAPTURE) 1'); DEV = 0x14
def a7(l): return [(l >> 14) & 0x7F, (l >> 7) & 0x7F, l & 0x7F]
def dt1(l, d):
    a = a7(l); s = sum(a) + sum(d); return mido.Message('sysex', data=[0x41, DEV, 0x16, 0x12] + a + list(d) + [(128 - s % 128) % 128])
o.send(dt1((0x10 << 14) + 4, bytes([16, 4, 4, 2, 2, 2, 1, 0, 1]))); time.sleep(0.3)   # partial reserve, as in the whale session
for k_, a in enumerate(args):
    slot = 62 + (k_ % 2)                                          # alternate memory slots so the patch value changes -> part reloads
    idx, _, sec = a.partition(':'); idx = int(idx); sec = float(sec or 1.5)
    p = bytearray(tmpl['parts'][0]); p[0] = 36; p[1] = 50; p[5] = idx & 127; p[4] = (p[4] & 1) | (2 if idx >= 128 else 0)
    common = b'WaveTest  ' + bytes([2, 2, 0x01, tmpl['nosus']])
    quiet = bytearray(tmpl['parts'][0]); quiet[44] = 0          # TVA level 0: partials 2-4 stay silent
    mem = (0x08 << 14) + 256 * slot                                # timbre MEMORY slot 64
    for m in [dt1(mem, common)] + [dt1(mem + 14 + 58 * k, bytes(p) if k == 0 else bytes(quiet)) for k in range(4)]: o.send(m); time.sleep(0.2)
    for n in (0, 1, 2):                                          # parts 1-3: patch -> group Memory (2), number 63
        o.send(dt1((0x03 << 14) + 16 * n, bytes([2, slot, 24, 50, 12, 0, 1, 0]))); time.sleep(0.3)
    time.sleep(0.2); print('wave idx', idx, flush=True)
    o.send(mido.Message('note_on', channel=0, note=60, velocity=110)); time.sleep(sec)
    o.send(mido.Message('note_off', channel=0, note=60)); time.sleep(0.8)
o.close(); print('done')
