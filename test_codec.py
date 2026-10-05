import numpy as np
from rosetta_d110 import *
for f in ['dumps/r15179880.ic8.bin','dumps/r15179878.ic7.bin']:
    r=np.fromfile(f,np.uint8); l=rom_to_log(r)
    print(f,'bytes round trip:',np.array_equal(log_to_rom(l),r),
          '| via float:',np.array_equal(log_to_rom(lin_to_log(log_to_lin(l))),r))
    m=l&0x7fff; print('  m percentiles 1/50/99/max:',np.percentile(m,[1,50,99]),m.max(),'  unused-sign-zero m=0 count',int((m==0).sum()))
