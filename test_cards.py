import importlib.util, sys, os, wave, numpy as np, tempfile
from tkinter import messagebox
messagebox.showinfo = messagebox.showerror = messagebox.showwarning = lambda *a, **k: None
messagebox.askyesnocancel = lambda *a, **k: False
sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw')); rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
a = rs.Studio(); a.withdraw()
t = np.sin(np.arange(7000) / 15.0) * 0.5
tmp = tempfile.mkdtemp(); wp = os.path.join(tmp, '003_kick.wav')
open(wp, 'wb').write(rs.pcm16(t))
a.on_drop([wp.encode()]); a.tv.selection_set('3'); a.on_drop([wp.encode()])       # drop with a selection
print('dropped -> swaps', sorted(a.swaps), 'dirty', a.dirty)
a.renames[3] = 'MyKick'; a.path = os.path.join(tmp, 't.rcard'); a.save(); print('saved dirty', a.dirty, os.path.getsize(a.path), 'bytes')
b = rs.Studio(); b.withdraw(); b.dirty = False; b.open(a.path)
print('reopened swaps', sorted(b.swaps), 'names', b.renames, 'src', b.src[3])
print('audio match', np.allclose(np.clip(a.swaps[3], -1, 1), b.swaps[3], atol=1/32768*2))
ra = rs.build(a.rom, a.swaps, a.renames, tmp + '/a'); rb = rs.build(b.rom, b.swaps, b.renames, tmp + '/b')
print('same ROM image from card:', open(tmp + '/a/r15179880.ic8_patched.bin', 'rb').read() == open(tmp + '/b/r15179880.ic8_patched.bin', 'rb').read())
a.destroy(); b.destroy()
