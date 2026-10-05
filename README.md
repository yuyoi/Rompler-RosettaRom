# Rosetta ROM

> **UNTESTED PROTOTYPE.** The software round-trips in simulation, but **nothing has been burned or run in a synth yet.**
> Expect rough edges, wrong assumptions and changes. Do not desolder anything on the strength of this repo alone.

Goal: make any rompler a sampler by replacing its PCM mask ROMs with flash chips (e.g. SST39SF040) programmed by an
ESP32, so your own samples play where the factory waves were. First target: **Roland D-110** (LA synthesis).

This is the next step after [U110 RomHex Studio](https://github.com/yuyoi/u110-romhex-studio) and the
[ESP32 maskrom programmer](https://github.com/yuyoi/esp32-maskrom-programmer) (U110 HexWizard).

## What works (in software only)

- **Decode the D-110 wave ROMs** (IC8 = drums, IC7 = instruments): 16-bit log samples, two ROM bytes each. Round trip
  ROM -> audio -> ROM is bit-exact on the dumps used here. Decoded audio was checked by ear.
- **Read the sample table + names** from the control ROM (IC12): 4-byte entries `{pos, len/loop, pitch}`, wave names
  8 ASCII chars at `0x100 + 8*index`. Wave space is 1 MB: IC8 first, then IC7.
- **Swap a wave** with a WAV (same slot position and length, no table edits) and **rename** it.
- **Rosetta ROM Studio** (`rosetta_studio.pyw`): U110-Studio-style GUI. Wave list, waveform (original vs replacement),
  load WAV, rename, save/open projects, import ROM dumps, import a folder of WAVs, export all originals, BUILD patched images.

## What is NOT verified

- Anything on real hardware: chip pinouts/packages of IC7/IC8/IC12 vs the flash adapter, timing, burning, playback in a D-110.
- The pitch field of the table entries (tuning of a swapped wave is a guess; drums are fine, pitched waves may be off).
- Table entries beyond the first 128 (`0xB00+` block), timbre names (10 chars from `0x1200`), what IC6 (32 KB) holds.
- The log-to-linear scale is matched to munt's description and sounds right, but is not hardware-confirmed.

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

## Credits and legal

- **Made by JunkSmithWizard (JSW) together with Claude (Anthropic's AI).**
- Sample format, bit order and table structure follow the [munt](https://github.com/munt/munt) MT-32 emulator source (LGPL)
  and were then checked against D-110 dumps. No munt code is included.
- Roland, D-110, MT-32 and LA synthesis are trademarks of their owners. This project is not affiliated with Roland.
  No ROM data or decoded audio is distributed here.
- MIT licensed (see `LICENSE`).
