"""Audition PCM waves on ALL 8 parts at once (channel mapping unknown): every part = preset A 01, then live single-byte writes into each part's timbre temp area.
usage: py -3.10 audition_seq3.py idx[:seconds] ...   (idx 0-based = panel wave number - 1)"""
import sys, time, mido
args = sys.argv[1:]
o = mido.open_output('MIDI (OCTA-CAPTURE) 1'); DEV = 0x14; STR = 246
def a7(l): return [(l >> 14) & 0x7F, (l >> 7) & 0x7F, l & 0x7F]
def dt1(l, d):
    a = a7(l); s = sum(a) + sum(d); return mido.Message('sysex', data=[0x41, DEV, 0x16, 0x12] + a + list(d) + [(128 - s % 128) % 128])
def send(m, gap=0.1): o.send(m); time.sleep(gap)
def P(n, off, v): send(dt1((0x04 << 14) + STR * n + off, bytes([v])))
send(dt1((0x10 << 14) + 4, bytes([16, 4, 4, 2, 2, 2, 1, 0, 1])), 0.3)
for n in range(8): send(dt1((0x03 << 14) + 16 * n, bytes([0, 0, 24, 50, 12, 0, 1, 0])), 0.3)     # every part = preset A 01
time.sleep(0.5)
for n in range(8):
    P(n, 10, 2); P(n, 11, 2); P(n, 12, 0x01)
    for k in (1, 2, 3): P(n, 14 + 58 * k + 41, 0)
    P(n, 14, 36); P(n, 15, 50)
for a in args:
    idx, _, sec = a.partition(':'); idx = int(idx); sec = float(sec or 1.5)
    for n in range(8): P(n, 14 + 4, 2 if idx >= 128 else 0); P(n, 14 + 5, idx & 127)
    time.sleep(0.2); print('wave idx', idx, flush=True)
    for ch in range(8): o.send(mido.Message('note_on', channel=ch, note=60, velocity=110))
    time.sleep(sec)
    for ch in range(8): o.send(mido.Message('note_off', channel=ch, note=60))
    time.sleep(0.8)
o.close(); print('done')
