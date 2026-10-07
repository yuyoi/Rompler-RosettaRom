"""Rosetta ROM baker: puts the Rosetta OS into YOUR OWN D-110 dumps and writes ready-to-burn files.

No Roland data is in this repo or in this tool: you read your own chips, drop the dumps in the folders, run it.

  roms/IC19 (main OS EPROM)/                 your IC19 dump (32 KB, v1.10; the original, not a patched one)
  roms/IC15 (bin from Rosetta Studio here)/  the IC15 file Rosetta Studio wrote (your samples' names / wave table),
                                             or your plain IC15 dump; 128 KB or the 512 KB x4 SST39SF040 file
  (any folder name that starts with IC19 / IC15 works; only the .bin file in it is used)

  python bake_rosetta.py                      -> baked/ (burn files + BURN.txt with MD5s and what goes where)
  python bake_rosetta.py --test               also runs the Rosetta checks in the simulator first
  python bake_rosetta.py --banner " D-110  ROSETTA " "  mod by JSW    "    (IC19 banner, shown without IC15)

Writes:
  D110_IC19_Rosetta-vN_27C256.bin            IC19 for a 27C256 / M27C256B / W27E257 (32 KB)
  D110_IC19_Rosetta-vN_27C512-doubled.bin    IC19 for a W27C512 / 27C512 in the 27C256 socket (image twice)
  D110_IC15_Rosetta-vN_SST39SF040-x4.bin     IC15 for an SST39SF040 (512 KB, 4 copies)
  D110_IC15_Rosetta-vN_128K.bin              IC15 for an SST39SF010A (128 KB)
Don't share the .bin files (they hold Roland's code): share this repo, people bake their own.
"""
import argparse, glob, hashlib, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
IC19_ARGS = ['--quick', '--cc', '--rosetta', '--plain-words', '--boot-banner', '--banner-time', '15', '--ic15-hook']
IC19_BANNER = (' D-110  ROSETTA ', '  mod by JSW    ')


def one_dump(roms, chip, sizes):
    dirs = sorted(d for d in glob.glob(os.path.join(roms, '*')) if os.path.isdir(d) and
                  os.path.basename(d).lower().replace(' ', '').startswith(chip.lower()))
    if len(dirs) != 1: sys.exit('%s: need one folder whose name starts with %s (found %d)' % (roms, chip, len(dirs)))
    folder = dirs[0]
    files = sorted(f for f in glob.glob(os.path.join(folder, '*.bin')) if os.path.isfile(f))
    if not files: sys.exit('%s: put your .bin there (one file)' % folder)
    if len(files) > 1: sys.exit('%s: one dump only, found %s' % (folder, ', '.join(os.path.basename(f) for f in files)))
    if os.path.getsize(files[0]) not in sizes:
        sys.exit('%s: %d bytes, expected %s' % (files[0], os.path.getsize(files[0]), ' or '.join(map(str, sizes))))
    return files[0]


def run(args):
    r = subprocess.run([sys.executable, os.path.join(HERE, args[0])] + args[1:], cwd=HERE, capture_output=True,
                       text=True)
    if r.returncode:
        sys.exit((r.stdout + r.stderr).strip())
    return r.stdout


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--roms', default=os.path.join(HERE, 'roms'), help='folder with the IC19 and IC15 folders (default roms/)')
    ap.add_argument('-o', '--out', default=os.path.join(HERE, 'baked'), help='output folder (default baked/)')
    ap.add_argument('--banner', nargs=2, metavar=('LINE1', 'LINE2'), default=IC19_BANNER,
                    help='IC19 banner, 16 chars per line (the IC15 banner replaces it when IC15 is found)')
    ap.add_argument('--test', action='store_true', help='run test_rosetta.py on the baked files first')
    a = ap.parse_args()
    sys.path.insert(0, HERE)
    import rosetta
    v = rosetta.VERSION
    ic19 = one_dump(a.roms, 'IC19', (0x8000,))
    ic15 = one_dump(a.roms, 'IC15', (0x20000, 0x80000))
    os.makedirs(a.out, exist_ok=True)
    name = lambda chip, kind: os.path.join(a.out, 'D110_%s_Rosetta-v%d_%s.bin' % (chip, v, kind))
    with tempfile.TemporaryDirectory() as tmp:
        t19, t15 = os.path.join(tmp, 'ic19.bin'), os.path.join(tmp, 'ic15.bin')
        run(['patch_ic19.py', ic19, '-o', t19] + IC19_ARGS + ['--banner'] + list(a.banner))
        run(['patch_ic15.py', ic15, '-o', t15, '--rosetta'])
        b19, b15 = open(t19, 'rb').read(), open(t15, 'rb').read()
        if a.test:
            print(run(['test_rosetta.py', t19, t15]).strip().splitlines()[-1])
    if len(b15) == 0x80000: b15 = b15[:0x20000]          # the 4 copies are the same
    files = [(name('IC19', '27C256'), b19, 'IC19 (OS, socketed): 27C256 / M27C256B / W27E257, 32 KB'),
             (name('IC19', '27C512-doubled'), b19 * 2, 'IC19 on a W27C512 / 27C512 (64 KB, the 32 KB image twice)'),
             (name('IC15', 'SST39SF040-x4'), b15 * 4, 'IC15 (control ROM, adapter): SST39SF040, 512 KB = 4 copies'),
             (name('IC15', '128K'), b15, 'IC15 on an SST39SF010A (128 KB)')]
    lines = ['Rosetta OS v%d, baked from your own dumps:' % v,
             '  IC19 in: %s' % os.path.basename(ic19), '  IC15 in: %s' % os.path.basename(ic15), '']
    for path, data, what in files:
        open(path, 'wb').write(data)
        lines.append('%s\n  %s\n  MD5 %s' % (os.path.basename(path), what, hashlib.md5(data).hexdigest()))
    lines += ['', 'Burn: one IC19 file and one IC15 file (T48: write, then verify / read back and compare MD5).',
              'Power off and unplug before swapping chips. Keep your original chips.',
              'Do not share these .bin files (they contain Roland code): share the repo, people bake their own.']
    open(os.path.join(a.out, 'BURN.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
