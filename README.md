<p align="center"><img src="assets/logo.png" width="360" alt="Rosetta ROM"></p>

# Rosetta ROM

> **Works on real hardware.** Custom samples play on a real Roland D-110 from SST39SF040 flash chips in IC7, IC8 and
> IC15. See [Status](#status-working-prototype-2026-10-06) for the setup and the wiring lessons.

Goal: make any rompler a sampler by replacing its PCM mask ROMs with flash chips (e.g. SST39SF040) programmed by an
ESP32, so your own samples play where the factory waves were. First target: **Roland D-110** (LA synthesis).

This is the next step after [U110 RomHex Studio](https://github.com/yuyoi/u110-romhex-studio) and the
[ESP32 maskrom programmer](https://github.com/yuyoi/esp32-maskrom-programmer) (U110 HexWizard).

## What works

- **Decode the D-110 wave ROMs** (IC8 = drums, IC7 = instruments): 16-bit log samples, two ROM bytes each. Round trip
  ROM -> audio -> ROM is bit-exact on the dumps used here. Decoded audio was checked by ear.
- **Read the sample table + names** from the control ROM (IC12): 4-byte entries `{pos, len/loop, pitch}`, wave names
  8 ASCII chars at `0x100 + 8*index`. Wave space is 1 MB: IC8 first, then IC7.
- **Swap a wave** with a WAV (same slot position and length, no table edits) and **rename** it.
- **Rosetta ROM Studio** (`rosetta_studio.pyw`): U110-Studio-style GUI. Wave list, waveform (original vs replacement),
  load WAV, rename, save/open projects, import ROM dumps, import a folder of WAVs, export all originals, BUILD patched images.

## Open questions

- The pitch field of the table entries (tuning of a swapped wave is a guess; drums are fine, pitched waves may be off).
- Table entries beyond the first 128 (`0xB00+` block), timbre names (10 chars from `0x1200`), what IC6 (32 KB) holds.
- The log-to-linear scale is matched to munt's description. Banks built with it play correctly on a D-110.

## Use

You must supply your **own ROM dumps** (they are Roland's copyrighted data and are not in this repo):

```
dumps/r15179880.ic8.bin   512 KB drum PCM ROM
dumps/r15179878.ic7.bin   512 KB instrument PCM ROM
ctrl/<anything>/r15179873*.bin   128 KB control ROM (IC12)   (or File > Import ROM dumps in the Studio)
```

```
pip install numpy
python rosetta_studio.pyw            # GUI (Python 3.10, Windows; tkinter)
python rosetta_studio.pyw --selftest # headless build check
python rosetta_swap.py 3 kick.wav [NEWNAME]   # CLI swap of wave #3
```

BUILD writes `r15179880.ic8_patched.bin`, `r15179878.ic7_patched.bin` and (if you renamed) `r15179873.ic12_patched.bin`
plus `report.txt`. Images are in chip byte order, as dumped. Renaming needs IC12 reprogrammed too.

## Files

| File | |
|---|---|
| `rosetta_d110.py` | ROM <-> log <-> linear codec |
| `rosetta_studio.pyw` | GUI |
| `rosetta_swap.py`, `swap_ic8.py` | CLI swap tools |
| `probe_pcm.py`, `table_test.py`, `split_table.py`, `test_*.py` | analysis and tests used to work the format out |
| `CONTEXT.md` | working notes, findings and open questions |
| `mcs96_dis.py`, `test_mcs96_dis.py`, `mame_ref/` | MCS-96 disassembler + flow tracer for the D-110 OS ROM (IC19); test against MAME's disassembler |
| `IC12_MAP.md`, `IC19_MAP.md` | control ROM and OS ROM structure maps |
| `patch_ic19.py` | patches your own IC19 dump (v1.10): `--banner` sets the version screen text, `--boot-banner` shows it at every power-on, `--plain-words` swaps TVA/TVF/WG... for plain labels |
| `ic19_quick.py` | Quick screen (Enter + Edit): cutoff/reso/attack/release for all partials, used by `patch_ic19.py --quick` |
| `mcs96_sim.py`, `test_ic19_quick.py` | small MCS-96 simulator (no I/O); runs the Quick screen on your patched dump |
| `patch_ic15.py` | puts new OS code into your own IC15 image (free area 0x1F000), called via `patch_ic19.py --ic15-hook` |

## Credits and legal

- **Made by JunkSmithWizard (JSW) together with Claude (Anthropic's AI).**
- Sample format, bit order and table structure follow the [munt](https://github.com/munt/munt) MT-32 emulator source (LGPL)
  and were then checked against D-110 dumps. No munt code is included.
- Roland, D-110, MT-32 and LA synthesis are trademarks of their owners. This project is not affiliated with Roland.
  No ROM data or decoded audio is distributed here.
- MIT licensed (see `LICENSE`).

logo: runic ring spells ROSETTA (Elder Futhark) round a cross pattee; the purple rosette is the "little rose" of the name, and the Rosetta Stone, the key between scripts. `python make_logo.py` regenerates `assets/`.

## Status: working prototype (2026-10-06)
Custom samples play on a real Roland D-110 from SST39SF040 flash in IC7, IC8 and IC15 (x4 image on IC15). Verified with a synthetic glitch bank,
organic/drum banks and a bank made from the author's own voice recordings (intelligible on the hardware).

Wiring lessons: lift SST pin 24 (OE#) clear of any pad and ground it separately; check every net with a continuity beeper; do not use two sets of
pin labels on one picture. Always read a chip first, write, read back and compare MD5.

Record-your-own workflow:
1. `rosetta_recorder.pyw`: hold SPACE to record a snip (mic -> 32 kHz mono, trimmed, normalised) into `recordings/NNN_label.wav`.
2. `py -3.10 gen_recorded_bank.py`: fills every wave slot with a take (or a reversed/crushed/sped-up variant), names each wave by what it
   sounds like, stretches long takes into small slots (S=2/4 with the pitch field lowered), writes IC8/IC7/IC15 burn files + `key.txt`.
3. Burn IC15, IC8, IC7 (`minipro -p SST39SF040 -w file`, verify by read-back), RAM-reset the D-110 so the new names load.
Needs your own ROM dumps (not included). Known limits: slots are 0.06-0.5 s so long takes are stretched (8 kHz bandwidth at S=4);
length codes 4-7 untested; PN-D10-01 card shows "No Data" in the modded unit (cause unknown).

Demo: `demo/d110_recorded_bank_all_waves.m4a` is a real D-110 playing waves 1-128 of the recorded bank in order, loops at the end.

## TODO
- [ ] **Patch workflow (no Roland data in the repo):** pack builder writes a `.rpatch` (new wave audio, PCM-table entries, names only); a small separate injector script applies it to the user's OWN IC15/IC7/IC8 dumps, checks the dump revision (MD5), tiles IC15 4x for the SST39SF040 and writes the three burn files. Studio gets File > "Apply Noise Pack" calling the injector; the program must still launch and work with no dumps loaded.
- [ ] Built-in noise pack preset (pink/white noise, buzz loops, noise drums; from `gen_glitch_bank.py`) as one of those patches.
- [ ] PN-D10-01 ROM card shows "No Data" in the modded unit: test the card in a GR-50.
- [ ] Length codes 4-7 (samples longer than 0.51 s without the stretch trick) untested.
- [ ] Rebuild `dist/Rosetta ROM D110.exe` (current exe is v0.1).

## D-110 OS mod: one EPROM swap (IC19 only)
Works on a real D-110 (OS v1.10). It only changes IC19, the socketed OS EPROM, and works with a stock IC15/IC7/IC8.
- **Quick screen:** hold **Enter** + press **Edit** (this used to start the demo). Group +/- = filter cutoff,
  Bank +/- = resonance, Number +/- = attack, Part +/- = release. Each step moves all 4 partials of the current part.
  Part (plain button) = next part P1..P8. Exit = back. Cutoff and resonance change held notes live; attack/release
  apply from the next note. Cutoff/resonance only affect synth partials (SQU/SAW), not PCM.
- **MIDI CC knobs** (`--cc`, not yet tested on hardware): CC74 cutoff, CC71 resonance, CC73 attack, CC72 release,
  per part on its MIDI channel. Cutoff/resonance move held notes live, like the Quick screen. Other numbers:
  `--cc 74,71,73,72` order cutoff,reso,attack,release (only CCs the stock OS ignores).
- **Plain words:** WG/P-ENV/P-LFO/TVF/TVA... become OS/Pitch/Vibr./Flt/Amp...
- **Boot banner:** your own 2 x 16 characters at power-on.

**Legal:** this repo contains no Roland code. You read **your own** IC19 and the tool adds the new bytes to your dump.
Please don't share the patched .bin: share this repo instead.

1. Read your IC19 (27C256-type EPROM, e.g. M5M27C256K) on a programmer such as a T48 (27C256 profile) and save it
   as `ctrl/ic19.bin`. Keep the original chip.
2. Patch it (the tool refuses anything that is not the v1.10 dump, SHA-1 `28635510...`):
   ```
   python patch_ic19.py ctrl/ic19.bin -o ctrl/ic19_mod.bin --quick --cc --plain-words --boot-banner --banner-time 15 --banner " D-110  ROSETTA " "  your text     "
   ```
   Any option can be left out. `python test_ic19_quick.py ctrl/ic19_mod.bin` runs the Quick screen in a simulator
   first.
3. Burn `ic19_mod.bin` to a blank 27C256 (UV EPROM such as M27C256B; erase it under UV first), read it back and
   compare, then fit it in IC19 (notch the same way).
4. If anything looks wrong, put the original chip back.

Details: `IC19_MAP.md` ("Stage 3", "Quick screen"). Code: `patch_ic19.py`, `ic19_quick.py`.

## Disassembling the OS ROM (IC19)
IC19 (32 KB, socketed) holds the 8097 program. With your own dump in `ctrl/ic19.bin` (gitignored):
```
python mcs96_dis.py ctrl/ic19.bin -o ctrl/ic19.lst     # listing: traced code, jump tables, data
python mcs96_dis.py ctrl/ic19.bin --summary            # vectors, code/data map, I/O and RAM references
sh mame_ref/build.sh && python test_mcs96_dis.py       # optional: check the decoder against MAME
```
The listing is derived from Roland's code: keep it private. Findings so far: `IC19_MAP.md`.

## Reading your own IC15 (the LH5310 control ROM)
IC15 is a 28-pin DIP LH5310-DJ mask ROM (128 KB, board designator IC15; the dump set calls it "ic12"). Pinout, top view: A15 1, A12 2, A7 3, A6 4, A5 5, A4 6, A3 7, A2 8, A1 9, A0 10, D0 11, D1 12, D2 13, GND 14, D3 15, D4 16, D5 17, D6 18, D7 19, /OE 20, A10 21, A16 22, A11 23, A9 24, A8 25, A13 26, A14 27, Vcc 28. Note A16 sits on pin 22, where a 27C256 has OE#, and /OE on pin 20, where a 27C256 has CE#, so a plain 27C256 profile does not work without an adapter or jumper.
- Read on a T48 with `minipro -p <profile> -x -r ic15.bin` (`-x` skips the chip-ID check, mask ROMs have none) and compare against the known revision before patching.
- TODO (author to fill in): exact socket/adapter and jumper wiring used to read it, and which T48 profile.
