"""Patch your own D-110 OS ROM dump (IC19, v1.10). No Roland data is stored here: the input is checked by SHA-1 and
only the new bytes are written. See IC19_MAP.md, "Stage 3".

  python patch_ic19.py ctrl/ic19.bin -o ctrl/ic19_patched.bin --banner " D-110  ROSETTA " "  mod by JSW    "

--banner replaces the two 16-character LCD lines shown when the version combo is held at power-on (boot code 0x2264
compares the SC1 button row with 0xEA, then prints the string at 0x2205: one LCD position byte, 32 chars, 00).
--boot-banner shows that screen on every power-on: the combo test `cmpb r70,#0xEA; jne 0x2278` at 0x2269 becomes
`cmpb r70,#0xFC; je 0x2278`, so only the test-mode combo (0xFC) skips it and test mode still works. --banner-time N
sets the delay loop count at 0x228E (v1.10: 30, about 4 s; each step is 256*256 djnz loops, ~0.15 s at 12 MHz).
--ic15-hook makes the banner call code in IC15 (see patch_ic15.py): a trampoline in the free FF area at 0x2191 saves
rb6/rb7, selects bank page 0x27 (IC15 0x1C000-0x1FFFF at 0x8000-0xBFFF; rb7 is the bank shadow every ISR restores),
checks the magic word 0x5A1C at 0xB000 (IC15 0x1F000) and calls 0xB002. With an unpatched IC15 it prints the normal
banner instead. The banner's `lcall api_208a` at 0x2272 is pointed at the trampoline.
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


# --plain-words: Roland jargon -> plain labels. In-place, same length (the strings are packed and 00-terminated in the
# window string area at file 0x0000-0x0FFF). (address, new text); the tool checks each ends at a 00 or at ' ='.
PLAIN_WORDS = [
    (0x0603, 'OS'),           # WG: wave generator = oscillator page
    (0x0606, 'Pitch'),        # P-ENV: pitch envelope page
    (0x060c, 'Vibr.'),        # P-LFO: pitch LFO = vibrato page
    (0x0612, 'Flt'),          # TVF: filter page
    (0x0616, 'Flt Env'),      # TVF-ENV
    (0x061e, 'Amp'),          # TVA: amplifier page
    (0x0622, 'Amp Env'),      # TVA-ENV
    (0x0497, 'Semitone '),    # PitchCors
    (0x04a1, 'Fine Tune'),    # PitchFine
    (0x04ab, 'KeyTrack='),    # Pitch KF=
    (0x034b, 'Voice Rsrv '),  # Ptl Reserve: inside "PART SET/ Part  Ptl Reserve =", followed by ' ='
]


def words_patch(rom):
    out = []
    for addr, new in PLAIN_WORDS:
        old = bytes(rom[addr:addr + len(new) + 2])
        if 0 in old[:len(new)] or not (old[len(new)] == 0 or old[len(new):] == b' ='):
            sys.exit('plain words: 0x%04x does not hold a %d-char label (dump not v1.10?)' % (addr, len(new)))
        out.append((addr, new.encode('ascii')))
    return out


IC15_TRAMP = 0x2191        # free FF area 0x2191-0x21FF (after the ljmp at 0x218e)
IC15_TRAMP_CODE = bytes.fromhex(
    'a0b670'        # ld   r70, rb6           ; r71 = rb7 = current bank
    'c870'          # push r70
    'b127b7'        # ldb  rb7, #0x27         ; IC15 page 7
    'c7010001b7'    # stb  rb7, 0x0100
    'a11c5a72'      # ld   r72, #0x5a1c       ; magic
    '8b0100b072'    # cmp  r72, 0xb000
    'd705'          # jne  0x21ae
    'ef568e'        # lcall 0xb002            ; code in IC15
    '2003'          # sjmp 0x21b1
    'efd9fe'        # lcall api_208a          ; fallback: normal banner (r78 = 0x2205)
    'cc70'          # pop  r70
    'b071b7'        # ldb  rb7, r71
    'c7010001b7'    # stb  rb7, 0x0100
    'f0')           # ret


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('rom')
    ap.add_argument('-o', '--out', default='ctrl/ic19_patched.bin')
    ap.add_argument('--banner', nargs=2, metavar=('LINE1', 'LINE2'), help='version screen text, 16 chars per line')
    ap.add_argument('--boot-banner', action='store_true', help='show the version screen on every power-on')
    ap.add_argument('--banner-time', type=int, metavar='N', help='banner delay, 1-255 steps of ~0.15 s (v1.10: 30)')
    ap.add_argument('--plain-words', action='store_true', help='replace TVA/TVF/WG/P-ENV/... with plain labels')
    ap.add_argument('--ic15-hook', action='store_true', help='banner runs code from IC15 0x1F000 (patch_ic15.py)')
    ap.add_argument('--any-version', action='store_true', help='skip the v1.10 SHA-1 check (addresses may be wrong)')
    a = ap.parse_args()

    rom = bytearray(open(a.rom, 'rb').read())
    sha = hashlib.sha1(rom).hexdigest()
    if sha != V110_SHA1 and not a.any_version:
        sys.exit('%s: SHA-1 %s is not the v1.10 dump this tool knows (use --any-version to force)' % (a.rom, sha))
    patches = banner_patch(*a.banner) if a.banner else []
    if a.plain_words:
        patches += words_patch(rom)
    if a.ic15_hook:
        if set(rom[IC15_TRAMP:IC15_TRAMP + len(IC15_TRAMP_CODE)]) != {0xff}: sys.exit('ic15 hook: 0x2191 is not free')
        patches += [(IC15_TRAMP, IC15_TRAMP_CODE), (0x2272, bytes.fromhex('ef1cff'))]   # lcall 0x2191
    if a.boot_banner:
        patches += [(0x226a, b'\xfc'), (0x226c, b'\xdf')]           # cmpb r70,#0xfc ; je 0x2278
    if a.banner_time is not None:
        if not 1 <= a.banner_time <= 255: sys.exit('--banner-time: 1-255')
        patches.append((0x228e, bytes([a.banner_time])))         # ldb r75,#N in the delay at 0x228d
    if not patches:
        sys.exit('nothing to patch (try --banner, --boot-banner, --plain-words, --ic15-hook)')
    for addr, new in patches:
        old = bytes(rom[addr:addr + len(new)])
        rom[addr:addr + len(new)] = new
        print('0x%04x  %s -> %s' % (addr, old.hex(' '), new.hex(' ')) if len(new) < 4 or 0xff in old else
              '0x%04x  %r -> %r' % (addr, old.decode('latin-1'), new.decode('latin-1')))
    open(a.out, 'wb').write(rom)
    print('wrote %s (%d bytes, SHA-1 %s)' % (a.out, len(rom), hashlib.sha1(rom).hexdigest()))


if __name__ == '__main__':
    main()
