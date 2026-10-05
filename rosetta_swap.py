"""rosetta_swap.py  index wav [new_name] [--out dir]
Replace D-110 wave #index (0-127, from the IC12 table at 0x900) with a WAV, same slot position/length.
Writes patched IC8 (idx pos<0x80) or IC7 (pos>=0x80), and IC12 if a new 8-char name is given.
Names: IC12 0x100 + 8*index (8 ASCII chars). Wave space = IC8 then IC7."""
import sys, glob, os, numpy as np
from rosetta_d110 import *
from swap_ic8 import read_wav
CTRL=glob.glob('ctrl/Roland D110 (v1.06*/r15179873*.bin')[0]
def entry(c,i): pos,ln=int(c[0x900+4*i]),int(c[0x901+4*i]); return pos*0x800,0x800<<((ln>>4)&7),bool(ln&0x80)
def run(i,wav,name=None,out='patched'):
    c=np.fromfile(CTRL,np.uint8); ic8=np.fromfile('dumps/r15179880.ic8.bin',np.uint8); ic7=np.fromfile('dumps/r15179878.ic7.bin',np.uint8)
    addr,n,loop=entry(c,i); half=len(ic8)//2
    rom,base,fn=(ic8,0,'IC8_r15179880') if addr<half else (ic7,half,'IC7_r15179878')
    assert addr+n<=base+half, 'slot crosses chip boundary'
    x=read_wav(wav)[:n]; x=np.concatenate([x,np.zeros(n-len(x))]); x=x/(np.abs(x).max()+1e-9)*0.98
    o=rom.copy(); a=(addr-base)*2; o[a:a+2*n]=log_to_rom(lin_to_log(x*2.0**(32766/2048)))
    os.makedirs(out,exist_ok=True); o.tofile(f'{out}/{fn}_patched.bin'); res=[fn]
    if name:
        nm=name.encode('ascii')[:8].ljust(8); c2=c.copy(); c2[0x100+8*i:0x108+8*i]=list(nm); c2.tofile(f'{out}/IC12_r15179873_patched.bin'); res.append('IC12 name -> %r'%nm)
    return res,(i,hex(addr),n,loop)
if __name__=='__main__':
    a=sys.argv[1:]; print(run(int(a[0]),a[1],a[2] if len(a)>2 else None))
