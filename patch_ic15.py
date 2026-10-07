"""Put new OS code into your own IC15 (control ROM, LH5310 / "ic12" in the dump set) image. The D-110 maps IC15 in
128 KB, bank pages 0x20-0x27 at CPU 0x8000-0xBFFF; 0x1F000-0x1FFFF (page 0x27, CPU 0xB000) is FF fill in the stock
ROM. Use with patch_ic19.py --ic15-hook --boot-banner. See IC19_MAP.md, "Code in IC15".

  python patch_ic15.py my_ic15.bin -o ic15_patched.bin --hello "Hello from IC15!" "new OS code runs"
  python patch_ic15.py my_ic15.bin -o ic15_ros.bin --rosetta        (Rosetta features, see rosetta.py; also writes
                                                                     0x1C000-0x1EFFF, the end of the demo songs)

Accepts a 128 KB image or a 512 KB SST39SF040 burn file (4 copies); every copy gets the same bytes.
"""
import argparse, sys

BASE = 0x1F000              # IC15 offset of CPU 0xB000 in page 0x27
MAGIC = b'\x1c\x5a'         # checked by the IC19 trampoline before it calls 0xB002


def hello(line1, line2):
    text = (line1.ljust(16)[:16] + line2.ljust(16)[:16]).encode('ascii')
    return (MAGIC +
            bytes.fromhex('a10ab078'     # ld    r78, #0xb00a
                          'ef8170'       # lcall api_208a (prints LCD addr byte + text up to 00)
                          'f0') +        # ret
            b'\x00' + text + b'\x00')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('-o', '--out', required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument('--hello', nargs=2, metavar=('LINE1', 'LINE2'), help='16 chars per line')
    g.add_argument('--rosetta', action='store_true', help='Rosetta features (use with patch_ic19.py --rosetta)')
    a = ap.parse_args()
    rom = bytearray(open(a.rom, 'rb').read())
    if len(rom) not in (0x20000, 0x80000):
        sys.exit('expected a 128 KB image or a 512 KB burn file, got %d bytes' % len(rom))
    if a.rosetta:
        import rosetta
        segs = rosetta.build_ic15(rosetta.build_ic19()[1])[0]       # [(cpu address in page 0x27, bytes)]
        # the code area 0x1C000-0x1EFFF is the end of the demo song data (unused once IC19 has the Quick mod)
        areas = [(0x1c000, 0x3000, segs[0][1]), (BASE, 0x1000, segs[1][1])]
        assert segs[0][0] == 0x8000 and segs[1][0] == 0xb000
    else:
        areas = [(BASE, 0x1000, hello(*a.hello))]
    for copy in range(0, len(rom), 0x20000):
        at = copy + BASE
        if rom[at:at + 2] != MAGIC and set(rom[at:at + 0x1000]) != {0xff}:
            sys.exit('0x%05x is not free (FF) in this image' % at)
        for off, size, blob in areas:
            if len(blob) > size: sys.exit('blob too big for 0x%05x' % off)
            rom[copy + off:copy + off + size] = blob + b'\xff' * (size - len(blob))   # (re)patching clears older code
    open(a.out, 'wb').write(rom)
    for off, size, blob in areas:
        print('%d bytes at 0x%05x' % (len(blob), off))
    print('wrote %s, %d cop%s' % (a.out, len(rom) // 0x20000, 'y' if len(rom) == 0x20000 else 'ies'))


if __name__ == '__main__':
    main()
