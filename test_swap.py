import numpy as np, wave
from swap_ic8 import *
i=next(k for k in range(128) if slot(k)[0]<0x80000//2 and slot(k)[1]>=0x1000 and not slot(k)[2])
addr,n,_=slot(i); print('slot',i,'addr',hex(addr),'len',n)
t=np.arange(n)/32000; tone=np.sin(2*np.pi*440*t)*np.exp(-t*6)
w=wave.open('test_tone.wav','wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(32000); w.writeframes((tone*30000).astype(np.int16).tobytes()); w.close()
rom=np.fromfile('dumps/r15179880.ic8.bin',np.uint8); out=swap(rom,i,read_wav('test_tone.wav'))
dec=log_to_lin(rom_to_log(out))[addr:addr+n]; dec=dec/np.abs(dec).max()
print('decoded-vs-input correlation %.4f'%np.corrcoef(dec,tone)[0,1])
diff=np.nonzero(rom!=out)[0]; print('bytes changed',len(diff),'range',hex(diff.min()),hex(diff.max()),'expected',hex(addr*2),hex((addr+n)*2-1))
