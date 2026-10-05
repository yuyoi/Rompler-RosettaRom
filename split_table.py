import numpy as np, glob, wave, os
src=open('probe_pcm.py').read().split("cands=")[0]; exec(src)
ctrl=np.fromfile(glob.glob('ctrl/Roland D110 (v1.06*/r15179873*.bin')[0],np.uint8)
S=np.concatenate([lin(descr(b[0::2],b[1::2],True)),lin(descr(a[0::2],a[1::2],True))])  # IC8 then IC7
os.makedirs('samples',exist_ok=True)
def wr(fn,x):
    x=x/(np.abs(x).max()+1e-9)*0.9; w=wave.open(fn,'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(32000); w.writeframes((x*32767).astype(np.int16).tobytes()); w.close()
aud=[]; gap=np.zeros(8000)
for i in range(128):
    pos,ln,plo,phi=ctrl[0x900+4*i:0x900+4*i+4]
    n=0x800<<((ln>>4)&7); loop=ln>>7
    x=S[pos*0x800:pos*0x800+n]
    wr('samples/w%03d_pos%02x_len%x%s.wav'%(i,pos,n,'_loop' if loop else ''),np.tile(x,4) if loop else x)
    aud+= [np.tile(x,4)/ (np.abs(x).max()+1e-9) if loop else x/(np.abs(x).max()+1e-9), gap]
wr('audition_first128.wav',np.concatenate(aud))
print(len(np.concatenate(aud))/32000,'s')
