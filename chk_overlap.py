import importlib.machinery, importlib.util
sp = importlib.util.spec_from_loader('rs', importlib.machinery.SourceFileLoader('rs', 'rosetta_studio.pyw')); rs = importlib.util.module_from_spec(sp); sp.loader.exec_module(rs)
rom = rs.Rom(); sl = [(i, rom.ent[i][0], rom.ent[i][0] + rom.ent[i][1]) for i in range(rs.NW) if rom.chip(i) == 'IC8']
for a in sl:
    for b in sl:
        if a[0] < b[0] and a[1] < b[2] and b[1] < a[2]:
            print('overlap', a[0], rom.names[a[0]], hex(a[1]), hex(a[2]), '<->', b[0], rom.names[b[0]], hex(b[1]), hex(b[2]))
print([i for i, _, _ in sl if i > 31], [rom.names[i] for i, _, _ in sl if i > 31])
