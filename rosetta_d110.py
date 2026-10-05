"""D-110 PCM codec: ROM bytes <-> linear float.  16-bit log sample = 2 ROM bytes (s,c), munt bit order.
mag = 2^(m/2048), m = low 15 bits, sign = bit 15.  Wave space = IC8 (0x00000) + IC7 (0x80000)."""
import numpy as np
ORDER=[0,9,1,2,3,4,5,6,7,10,11,12,13,14,15,8]
def rom_to_log(rom):
    s=rom[0::2].astype(np.uint32); c=rom[1::2].astype(np.uint32); out=np.zeros(len(s),np.uint32)
    for u,o in enumerate(ORDER):
        bit=((s>>(7-o))&1) if o<8 else ((c>>(7-(o-8)))&1); out|=bit<<(15-u)
    return out
def log_to_rom(l):
    l=np.asarray(l,np.uint32); s=np.zeros(len(l),np.uint32); c=np.zeros(len(l),np.uint32)
    for u,o in enumerate(ORDER):
        bit=(l>>(15-u))&1
        if o<8: s|=bit<<(7-o)
        else: c|=bit<<(7-(o-8))
    out=np.empty(len(l)*2,np.uint8); out[0::2]=s; out[1::2]=c; return out
def log_to_lin(l):
    return np.where(l&0x8000,-1.0,1.0)*2.0**((l&0x7fff)/2048.0)
def lin_to_log(x):
    x=np.asarray(x,np.float64); mag=np.abs(x)
    m=np.where(mag>=1,np.round(2048*np.log2(np.maximum(mag,1))),0).clip(0,32767).astype(np.uint32)
    return m|np.where(x<0,0x8000,0).astype(np.uint32)

def read_wav(fn):
    """16/24/32-bit or 8-bit PCM WAV -> mono float -1..1 at 32 kHz"""
    import wave
    w = wave.open(fn); n = w.getnchannels(); sr = w.getframerate(); sw = w.getsampwidth()
    if sw == 3:
        raw = np.frombuffer(w.readframes(w.getnframes()), np.uint8).reshape(-1, 3)
        d = ((raw[:, 0].astype(np.int32) | raw[:, 1].astype(np.int32) << 8 | raw[:, 2].astype(np.int32) << 16) << 8 >> 8).astype(np.float64)
        d = np.where(d >= 2**23, d - 2**24, d) / 2.0**23
        d = d.reshape(-1, n).mean(1)
    else:
        d = np.frombuffer(w.readframes(w.getnframes()), {1: np.uint8, 2: np.int16, 4: np.int32}[sw]).astype(np.float64).reshape(-1, n).mean(1)
        d = (d - 128) / 128 if sw == 1 else d / float(2 ** (8 * sw - 1))
    if sr != 32000:
        t = np.arange(int(len(d) * 32000 / sr)) * sr / 32000; d = np.interp(t, np.arange(len(d)), d)
    return d
