import numpy as np, itertools
a=np.fromfile('dumps/r15179878.ic7.bin',np.uint8); b=np.fromfile('dumps/r15179880.ic8.bin',np.uint8)
order=[0,9,1,2,3,4,5,6,7,10,11,12,13,14,15,8]
def descr(s,c,use=True):
    s=s.astype(np.uint32); c=c.astype(np.uint32); out=np.zeros(len(s),np.uint32)
    o=order if use else list(range(16))
    for u in range(16):
        bit=((s>>(7-o[u]))&1) if o[u]<8 else ((c>>(7-(o[u]-8)))&1)
        out|=bit<<(15-u)
    return out
def lin(l):
    sign=np.where(l&0x8000,-1.0,1.0); mag=2.0**(((l&0x7fff).astype(np.float64))/2048.0)
    return sign*mag
def score(x):  # lag-1 autocorr over windows
    x=x[:200000]; x=x-x.mean(); 
    return float((x[1:]*x[:-1]).sum()/((x*x).sum()+1e-9))
cands={
 'ic7 pairs':(a[0::2],a[1::2]),'ic7 pairs swapped':(a[1::2],a[0::2]),
 'ic8 pairs':(b[0::2],b[1::2]),'ic8 pairs swapped':(b[1::2],b[0::2]),
 'ic7|ic8 interleave a,b':(a,b),'ic8,ic7':(b,a),
 'ic7 first half/second':(a[:len(a)//2],a[len(a)//2:]),
 'ic8 first half/second':(b[:len(b)//2],b[len(b)//2:]),
}
for n,(s,c) in cands.items():
    for use in (True,False):
        l=descr(s,c,use); print('%-24s order=%-5s lag1=%.3f'%(n,use,score(lin(l))))

import wave
def dump(name,arr,swap=False):
    s,c=(arr[1::2],arr[0::2]) if swap else (arr[0::2],arr[1::2])
    x=lin(descr(s,c,True)); x=x/np.abs(x).max()*0.9
    pcm=(x*32767).astype(np.int16)
    w=wave.open(name,'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(32000); w.writeframes(pcm.tobytes()); w.close()
dump('ic7_decoded_32k.wav',a); dump('ic8_decoded_32k.wav',b)
