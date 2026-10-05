"""swap_ic8.py <slot#> <in.wav> [out.bin]  - replace one D-110 drum slot (table entry in IC12 first block) in IC8 with a WAV.
Keeps slot position+length (no table edits). WAV is resampled to 32 kHz, mono, truncated/padded to the slot."""
import sys, glob, wave, numpy as np
from rosetta_d110 import *
ctrl=np.fromfile(glob.glob('ctrl/Roland D110 (v1.06*/r15179873*.bin')[0],np.uint8)
def slot(i):
    pos,ln=ctrl[0x900+4*i],ctrl[0x900+4*i+1]; return int(pos)*0x800,0x800<<((ln>>4)&7),bool(ln&0x80)
def read_wav(fn):
    w=wave.open(fn); n=w.getnchannels(); sr=w.getframerate(); sw=w.getsampwidth()
    d=np.frombuffer(w.readframes(w.getnframes()),{1:np.uint8,2:np.int16,4:np.int32}[sw]).astype(np.float64)
    d=d.reshape(-1,n).mean(1)
    d=(d-128)/128 if sw==1 else d/float(2**(8*sw-1))
    if sr!=32000: t=np.arange(int(len(d)*32000/sr))*sr/32000; d=np.interp(t,np.arange(len(d)),d)
    return d
def swap(rom,i,x):
    addr,n,loop=slot(i); assert addr+n<=len(rom)//2, 'slot not in IC8 (pos>=0x80)'
    x=x[:n]; x=np.concatenate([x,np.zeros(n-len(x))]); x=x/ (np.abs(x).max()+1e-9)*0.98
    l=lin_to_log(x*2.0**(32766/2048)); out=rom.copy(); out[addr*2:(addr+n)*2]=log_to_rom(l); return out
if __name__=='__main__':
    rom=np.fromfile('dumps/r15179880.ic8.bin',np.uint8)
    out=swap(rom,int(sys.argv[1]),read_wav(sys.argv[2])); out.tofile(sys.argv[3] if len(sys.argv)>3 else 'IC8_patched.bin'); print('ok')
