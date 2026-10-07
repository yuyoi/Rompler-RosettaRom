"""Put new OS code into your own IC15 (control ROM, LH5310 / "ic12" in the dump set) image. The D-110 maps IC15 in
128 KB, bank pages 0x20-0x27 at CPU 0x8000-0xBFFF; 0x1F000-0x1FFFF (page 0x27, CPU 0xB000) is FF fill in the stock
ROM. Use with patch_ic19.py --ic15-hook --boot-banner. See IC19_MAP.md, "Code in IC15".

  python patch_ic15.py my_ic15.bin -o ic15_patched.bin --hello "Hello from IC15!" "new OS code runs"
  python patch_ic15.py my_ic15.bin -o ic15_ros.bin --rosetta        (Rosetta features, see rosetta.py)

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
        blob = rosetta.build_ic15(rosetta.build_ic19()[1])[0]
    else:
        blob = hello(*a.hello)
    if len(blob) > 0x1000: sys.exit('blob too big')
    for copy in range(0, len(rom), 0x20000):
        at = copy + BASE
        if rom[at:at + 2] != MAGIC and set(rom[at:at + 0x1000]) != {0xff}:
            sys.exit('0x%05x is not free (FF) in this image' % at)
        rom[at:at + 0x1000] = blob + b'\xff' * (0x1000 - len(blob))     # (re)patching clears an older blob
    open(a.out, 'wb').write(rom)
    print('wrote %s: %d bytes at 0x%05x in %d cop%s' % (a.out, len(blob), BASE, len(rom) // 0x20000,
                                                       'y' if len(rom) == 0x20000 else 'ies'))


if __name__ == '__main__':
    main()
