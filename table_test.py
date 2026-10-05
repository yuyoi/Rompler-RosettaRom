import numpy as np, glob, importlib.util, sys
sys.argv=['x']; 
src=open('probe_pcm.py').read().split("cands=")[0]
exec(src)
ctrl=np.fromfile(glob.glob('ctrl/Roland D110 (v1.06*/r15179873*.bin')[0],np.uint8)
def lin_rom(rom):
    return lin(descr(rom[0::2],rom[1::2],True))
A=lin_rom(a); B=lin_rom(b)
orders={'IC7+IC8':np.concatenate([A,B]),'IC8+IC7':np.concatenate([B,A])}
# loop entries at 0xA24: pos 0xdb..0xff, 0x800 samples, assumed single cycles
for name,S in orders.items():
    sc=[]
    for k in range(37):
        pos=ctrl[0xA24+4*k]; seg=S[pos*0x800:(pos+1)*0x800]
        rng=np.abs(seg).max()+1e-9
        sc.append(abs(seg[-1]-seg[0])/rng)           # loop seam jump
        # smoothness: mean |diff| / amplitude
    sm=[np.abs(np.diff(S[ctrl[0xA24+4*k]*0x800:(ctrl[0xA24+4*k]+1)*0x800])).mean()/ (np.abs(S[ctrl[0xA24+4*k]*0x800:(ctrl[0xA24+4*k]+1)*0x800]).max()+1e-9) for k in range(37)]
    print(name,'seam jump med %.3f  roughness med %.3f'%(np.median(sc),np.median(sm)))
