"""Patch your own D-110 OS ROM dump (IC19, v1.10). No Roland data is stored here: the input is checked by SHA-1 and
only the new bytes are written. See IC19_MAP.md, "Stage 3".

  python patch_ic19.py ctrl/ic19.bin -o ctrl/ic19_patched.bin --banner " D-110  ROSETTA " "  mod by JSW    "

--banner replaces the two 16-character LCD lines shown when the version combo is held at power-on (boot code 0x2264
compares the SC1 button row with 0xEA, then prints the string at 0x2205: one LCD position byte, 32 chars, 00).
No ROM checksum routine was found in v1.10 (the only byte-summing loops are the SysEx checksums at 0x4518 and 0x4c27),
so nothing has to be fixed up after a patch.
"""
import argparse, hashlib, sys

V110_SHA1 = '28635510f30d6c1fb88e00da03e5b4e045c380cb'   # 32 KB IC19 dump, "ver1.10 Aug. 30, 1988"
BANNER = 0x2206                                             # 2 x 16 chars, then 0x00 at 0x2226


def banner_patch(line1, line2):
    text = line1.ljust(16)[:16] + line2.ljust(16)[:16]
    if any(not 0x20 <= ord(c) < 0x7f for c in text):
        sys.exit('banner: plain ASCII only')
    return [(BANNER, text.encode('ascii'))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('-o', '--out', default='ctrl/ic19_patched.bin')
    ap.add_argument('--banner', nargs=2, metavar=('LINE1', 'LINE2'), help='version screen text, 16 chars per line')
    ap.add_argument('--any-version', action='store_true', help='skip the v1.10 SHA-1 check (addresses may be wrong)')
    a = ap.parse_args()

    rom = bytearray(open(a.rom, 'rb').read())
    sha = hashlib.sha1(rom).hexdigest()
    if sha != V110_SHA1 and not a.any_version:
        sys.exit('%s: SHA-1 %s is not the v1.10 dump this tool knows (use --any-version to force)' % (a.rom, sha))
    patches = banner_patch(*a.banner) if a.banner else []
    if not patches:
        sys.exit('nothing to patch (try --banner)')
    for addr, new in patches:
        old = bytes(rom[addr:addr + len(new)])
        rom[addr:addr + len(new)] = new
        print('0x%04x  %r -> %r' % (addr, old.decode('latin-1'), new.decode('latin-1')))
    open(a.out, 'wb').write(rom)
    print('wrote %s (%d bytes, SHA-1 %s)' % (a.out, len(rom), hashlib.sha1(rom).hexdigest()))


if __name__ == '__main__':
    main()
