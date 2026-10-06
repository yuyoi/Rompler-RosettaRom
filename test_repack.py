"""Repack test: long WAVs move to bigger slots, the IC12 table is rewritten, nothing else is damaged.
py -3.10 test_repack.py"""
import sys, os, importlib.util
import numpy as np
spec = importlib.util.spec_from_file_location('rs', 'rosetta_studio.pyw'); rs = importlib.util.module_from_spec(spec)
sys.argv = ['x']; spec.loader.exec_module(rs)

rom = rs.Rom(); R = rs.RATE
sec = lambda s: np.sin(np.arange(int(s * R)) / 30.0) * 0.7

def run(swaps, free, out):
    return rs.build(rom, swaps, {}, out, True, {3: 60}, {}, free)

# 1) a 3.9 s wave on a drum slot, an 8.0 s wave on an instrument slot; free enough waves for the two blocks
moves, errs, txt, park = rs.plan_layout(rom, {3: sec(3.9), 32: sec(8.0)}, discard=set(range(128)) - {3, 32})
print('plan', moves, errs, txt)
assert not errs and moves[3][1] == 6 and moves[32][1] == 7, 'expected exp 6 and 7'
files, lines = run({3: sec(3.9), 32: sec(8.0)}, set(range(128)) - {3, 32}, 'repack_out')
print('\n'.join(lines))
c = np.fromfile('repack_out/r15179873.ic12_patched.bin', np.uint8)
ic8 = np.fromfile('repack_out/r15179880.ic8_patched.bin', np.uint8); ic7 = np.fromfile('repack_out/r15179878.ic7_patched.bin', np.uint8)

# 2) every table entry stays legal: inside the 1 MB space and aligned to its own length
for i in range(256):
    pos, lb = int(c[0x900 + 4 * i]), int(c[0x901 + 4 * i]); e = (lb >> 4) & 7
    assert pos + (1 << e) <= 256 and pos % (1 << e) == 0, ('illegal entry', i, pos, e)
print('all 256 table entries aligned and in range')

# 3) the new waves decode to the input
for i, x in ((3, sec(3.9)), (32, sec(8.0))):
    pos, e = int(c[0x900 + 4 * i]), (int(c[0x901 + 4 * i]) >> 4) & 7; a, n = pos * 0x800, 0x800 << e
    r, base = (ic8, 0) if a < 0x40000 else (ic7, 0x40000)
    d = rs.log_to_lin(rs.rom_to_log(r[(a - base) * 2:(a - base + n) * 2])); ref = rs.fit(x, n)
    print('wave %d -> pos 0x%05X slot %.2f s corr %.4f' % (i, a, n / R, np.corrcoef(d, ref)[0, 1]))
    assert np.corrcoef(d, ref)[0, 1] > 0.999

# 4) with nothing freed, a long wave must be refused cleanly (the ROM is 100% occupied)
m2, e2, t2, _ = rs.plan_layout(rom, {3: sec(3.9)}, discard=set())
print('no space free ->', e2[:1])
assert e2

# 5) same-size swap still works in place and leaves the table untouched
files, lines = rs.build(rom, {3: sec(0.2)}, {}, 'repack_out2')
c2 = np.fromfile('repack_out2/r15179873.ic12_patched.bin', np.uint8)
assert (c2 == rom.ctrl).all(); print('in-place swap leaves IC12 identical')
print('ALL OK')
