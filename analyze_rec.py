import glob, os, numpy as np, soundfile as sf
R=32000
def feat(x):
    n=len(x); a=np.abs(x); p=a.max(); X=np.abs(np.fft.rfft(x*np.hanning(n))); f=np.fft.rfftfreq(n,1/R)
    cen=(X*f).sum()/(X.sum()+1e-9); flat=np.exp(np.log(X+1e-9).mean())/(X.mean()+1e-9)
    w=int(.01*R); e=np.array([np.sqrt((x[i:i+w]**2).mean()) for i in range(0,n-w,w//2)]) if n>2*w else np.array([1.0])
    pk=e.argmax()*(w//2)/R; ac=0.0; f0=0
    seg=x[n//2-min(n//2,1024):n//2+min(n//2,1024)]
    if len(seg)>600:
        c=np.correlate(seg,seg,'full')[len(seg)-1:]; c/=c[0]+1e-9; lo,hi=int(R/1000),int(R/70); k=lo+c[lo:hi].argmax(); ac=c[k]; f0=R/k
    return dict(dur=n/R,cen=cen,flat=flat,pk=pk,ac=ac,f0=f0)
if __name__=='__main__':
    for fn in sorted(glob.glob('recordings/*.wav')):
        x,_=sf.read(fn); d=feat(x); print(os.path.basename(fn),'%.2fs cen%5.0f flat%.2f pk%.2f ac%.2f f0%4.0f'%(d['dur'],d['cen'],d['flat'],d['pk'],d['ac'],d['f0']))
