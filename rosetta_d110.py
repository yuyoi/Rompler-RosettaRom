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
