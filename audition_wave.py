"""Audition one PCM wave on a D-110 over MIDI: writes a timbre with a single PCM partial into part 1's temp area (SysEx), then plays a note.
usage: py -3.10 audition_wave.py <wave index 0-255 (panel number minus 1)> [seconds] [note]"""
import sys, time, glob, mido
sys.path.insert(0, 'ctrl')
import importlib.util
sp = importlib.util.spec_from_file_location('ic12', 'ctrl/ic12_dump.py'); ic = importlib.util.module_from_spec(sp)
sys.argv_save = sys.argv; sys.argv = ['x']; sp.loader.exec_module(ic); sys.argv = sys.argv_save
PORT = 'MIDI (OCTA-CAPTURE) 1'; DEV = 0x14; CH = 1            # part 1 -> MIDI channel 2
idx = int(sys.argv[1]); dur = float(sys.argv[2]) if len(sys.argv) > 2 else 1.5; note = int(sys.argv[3]) if len(sys.argv) > 3 else 60
tmpl = None
for i in range(128):                                           # first preset whose partial 1 is a PCM wave
    t = ic.timbre(i)
    if (t['mute'] & 1) and (ic.PS[t['s12']] >> 1) & 1: tmpl = t; break
p = bytearray(tmpl['parts'][0]); p[0] = 36; p[1] = 50       # neutral pitch: coarse 36 (C4 = key 60), fine 50
if idx >= 0: p[5] = idx & 127; p[4] = (p[4] & 1) | (2 if idx >= 128 else 0)
common = bytes(b'WaveTest  ') + bytes([tmpl['s12'], tmpl['s34'], 0x01, tmpl['nosus']])
def a7(lin): return [(lin >> 14) & 0x7F, (lin >> 7) & 0x7F, lin & 0x7F]
def dt1(lin, data):
    a = a7(lin); s = sum(a) + sum(data); return mido.Message('sysex', data=[0x41, DEV, 0x16, 0x12] + a + list(data) + [(128 - s % 128) % 128])
base = (0x04 << 14)                                            # timbre temp area, part 1
msgs = [dt1(base, common)] + [dt1(base + 14 + 58 * k, bytes(p) if k == 0 else bytes(tmpl['parts'][0]) ) for k in range(4)]
o = mido.open_output(PORT)
for m in msgs: o.send(m); time.sleep(0.2)
time.sleep(0.2)
print('template', tmpl['name'], 'wave', idx, flush=True)
o.send(mido.Message('note_on', channel=CH, note=note, velocity=100)); time.sleep(dur)
o.send(mido.Message('note_off', channel=CH, note=note)); time.sleep(0.5); o.close()
