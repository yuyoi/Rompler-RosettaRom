"""Audition PCM waves like the whale-song session: part 1 = a stock timbre, then live single-parameter writes into the timbre TEMP area (04 00 00 + offset).
usage: py -3.10 audition_seq2.py idx[:seconds] ...   (idx 0-based = panel wave number - 1)"""
import sys, time, mido
args = sys.argv[1:]
o = mido.open_output('MIDI (OCTA-CAPTURE) 1'); DEV = 0x14
def a7(l): return [(l >> 14) & 0x7F, (l >> 7) & 0x7F, l & 0x7F]
def dt1(l, d):
    a = a7(l); s = sum(a) + sum(d); return mido.Message('sysex', data=[0x41, DEV, 0x16, 0x12] + a + list(d) + [(128 - s % 128) % 128])
def send(m, gap=0.12): o.send(m); time.sleep(gap)
def P(off, v): send(dt1((0x04 << 14) + off, bytes([v])))
send(dt1((0x10 << 14) + 4, bytes([16, 4, 4, 2, 2, 2, 1, 0, 1])), 0.3)         # partial reserve (whale session)
send(dt1((0x03 << 14) + 0, bytes([0, 0, 24, 50, 12, 0, 1, 0])), 0.5)           # part 1 = preset A 01
P(10, 2); P(11, 2); P(12, 0x01)                                                  # structure 2, only partial 1 on
for k in (1, 2, 3): P(14 + 58 * k + 41, 0)                                       # partials 2-4 TVA level 0 (offset 41)
for a in args:
    idx, _, sec = a.partition(':'); idx = int(idx); sec = float(sec or 1.5)
    P(14 + 0, 36); P(14 + 1, 50)                                                 # neutral pitch
    P(14 + 4, 2 if idx >= 128 else 0); P(14 + 5, idx & 127)                      # waveform bank, wave number
    time.sleep(0.15); print('wave idx', idx, flush=True)
    o.send(mido.Message('note_on', channel=0, note=60, velocity=110)); time.sleep(sec)
    o.send(mido.Message('note_off', channel=0, note=60)); time.sleep(0.8)
o.close(); print('done')
