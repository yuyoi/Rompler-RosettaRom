# D-110 IC12 (control ROM, LH5310-97 `r15179873`, 128 KB) - structure map

Validated 2026-10-05 against munt's `ControlROMMap`/`Structures.h` (MT-32/CM-32L family). Dump script: `ctrl/ic12_dump.py pcm | timbres | rhythm`.
"Verified" = parsed output is self-consistent (pointer chains contiguous, names match waves, pitch values land on exact semitones).

## Map

| Offset | Size | What | Status |
|---|---|---|---|
| `0x0000` | 128 x u16 | **Preset timbre map** (A = 0-63, B = 64-127). Pointers are plain ROM offsets (no bias). | verified |
| `0x0100` | 256 x 8 B | **Wave names** (ASCII, space padded). Same index as the PCM table. | verified |
| `0x0900` | 256 x 4 B | **PCM table**: `pos, len, pitchLo, pitchHi`. See below. | verified |
| `0x0D00` | 64 x u16 | **Rhythm timbre map**. Pointer **minus 0x8000** = ROM offset (CPU sees the ROM at 0x8000). | verified |
| `0x0D80-0x0FFF` | ~0x280 | not identified (looks like event/sequence data: `92 xx yy`, `b6 07 ..`) | open |
| `0x1000-0x11FF` | 64 x 8 B? | records `00 nn 18 32 0c 00 01 00` (nn counts up). Probably per-key rhythm settings (timbre, level, pan, reverb in munt = 4 B x 85). Not decoded. | open |
| `0x1200-0x28C2` | 64 timbres | **Rhythm timbres** (R1-R64), compressed format. 1-3 partials each. | verified |
| `0x28C2-0x2FFF` | | more timbre-like records (`Marimba`, `Drop Hit`, `AcouBass 1`, `Bell Swing`...), not referenced by the rhythm map. Possibly the "Memory" bank defaults. | open |
| `0x3000` | ~64 x u16 | pointer table (`0x3100, 0x3160, 0x3190, ...`) into `0x3100-0x3BFF` | open |
| `0x3100-0x3BFF` | | **drum pattern data**: header `03 17 00 00`, then 3-byte events `[note, velocity, tick]` (note 0x23=35 kick, 0x2A=42 hat, 0x26=38 snare, ticks step by 6), end marker `ff 80 00`. | mostly decoded |
| `0x3C00-0x3FFF` | | FF fill | |
| `0x4000-0x96FF` | 128 timbres | **Preset timbres** (`AcouPiano1` ... `JungleTune`), compressed. A bank `0x4000-0x68A7`, B bank `0x68B0-0x96FD`; gaps at the bank boundary only (`0x68A8`, `0x7FCA`). | verified |
| `0x9800-0xAFFF` | | FF fill | |
| `0xB000-0x1EE7A` | ~82 KB | **Three demo songs**: `Macho Memory` 0xB000, `Sugar Plum` 0x10000, `Bumble Dee` 0x15C10 (event data runs to 0x1EE7A, FF after). Sequencer data, not decoded. Rosetta v8 puts code at 0x1C000-0x1EFFF (demo unreachable with the Quick mod). | identified |
| `0x1F000-0x1FFFF` | | FF fill | |

IC19 (32 KB) is the 8095 OS, IC6 (32 KB) is not identified. Nothing in IC12 is code.

## PCM table entry (4 bytes, munt `ControlROMPCMStruct`)
- `pos` : start = `pos * 0x800` **samples** = `pos * 0x1000` bytes of the 1 MB wave space (IC8 = 0x00000-0x7FFFF, IC7 = 0x80000-0xFFFFF).
- `len` byte: bits 6-4 = size exponent, length = `0x800 << exp` samples; bit 7 = loop; **bit 0 = 1 on the 30 bank-2 (index 128+) drum entries**, 0 on all others (munt: "unaffected by master tune" is bit 0 == 0).
- `pitch` u16 (LE), **4096 per octave**. `0x5000` = the wave plays at its stored 32 kHz rate when the note is middle C with coarse 36. Other values are exact semitone offsets: `AcPianoH 0x52AB = +2.00 st`, `AcPianoL 0x3D4B = -14.03 st`, `Pf Thump 0x4000 = -12.00 st`, `Snare 4 0x46A5 = -7.02 st`.
  Playback rate = `32000 * 2^(pitch/4096 - 5)` Hz at middle C. **This is the answer to "what is the pitch field"** for the Rosetta swap: a replacement wave recorded at rate R with root note n needs `pitch = 4096 * (5 + log2(R / 32000)) - (n - 60) * 4096/12`.
- 256 entries, but only 128 distinct start addresses: index 128-255 re-use bank-1 waves (drum set `*` names, loop slices `Loop n`/`JamLp n` with different lengths).
- Wave index used by a PCM partial = `pcmWave + (128 if waveform > 1 else 0)`.

## Timbre record (compressed, munt `initCompressedTimbre`)
`name[10], partialStructure12, partialStructure34, partialMute, noSustain` (14 B) followed by one 58-byte partial per **un-muted** partial (bit k of `partialMute`; muted partials are not stored, the previous partial is reused). So record lengths are 14 + 58n (72/130/188/246).
- A partial is PCM when `PS[structure] & 2` (1st of a pair) or `& 1` (2nd), with `PS = [0,0,2,2,1,3,3,0,3,0,2,1,3]`; otherwise it is a synth (square/saw) partial. `waveform` bit 0 = square/saw, bit 1 = PCM bank (0 -> waves 0-127, 1 -> waves 128-255).
- Partial fields (58 B): wg(8: coarse, fine, keyfollow, bender, waveform, pcmWave, pulseWidth, pwVelo), pitchEnv(12), pitchLFO(3), tvf(17), tva(18).

## Checks that passed
- Preset chain: 126 of 127 neighbouring records are exactly contiguous (`end == next start`); the 2 breaks are bank/page alignment.
- Rhythm chain: all 64 contiguous. Rhythm names vs waves agree (HiHat -> `HiHat *`, Rim Shot -> `RimShot*`, Mt HiConga -> `MtHCnga*`).
- Timbres built from PCM partials refer to sensible waves (`Orche Hit` = JamLp + Violin 2 + Clarinet + Pizzicato).

## Open items (to finish the reverse engineering)
1. `0x1000-0x11FF` table and `0x0D80-0x0FFF` blob (rhythm key settings? sequence data?).
2. Where the 8095 OS (IC19) reads rhythm key -> timbre (needs 8095 disassembly), and the system tables munt calls reserve/pan/program/max/soundgroup/startup message (none located yet in IC12; they may live in IC19). Lead (IC19_MAP.md): the OS reads the rhythm map at `0x25F2`/`0x4DD0` and a word table at IC12 `0x0F00` at `0x2573`/`0x4D8B`.
3. ~~Whether the OS assumes fixed addresses for the 0x0000/0x0900/0x0D00 tables~~ **Yes**: IC19 reads them with absolute operands (`0x8000`, `0x8900`/`0x8902`, `0x8D00`, plus `0x8F00`) after selecting bank page `0x20` (IC19_MAP.md). Moving a table = patching those operands.
4. Demo song format (0xB000+), only needed if the area is reused.
5. ~~IC6 `r15179879` contents.~~ The BOSS reverb chip's program ROM (MAME `roland_d10.cpp`, region "boss"); not CPU code.

## Hardware: replacing IC12 (LH5310, "TONE ROM") - from the D-110 service notes p.12 "IC DATA" (read 2026-10-05)
LH5310-DJ, 28-pin DIP, top view (the board footprint is 28-pin, NOT 32):
```
 A15  1 +-v-+ 28 Vcc
 A12  2 |   | 27 A14
 A7   3 |   | 26 A13
 A6   4 |   | 25 A8
 A5   5 |   | 24 A9
 A4   6 |   | 23 A11
 A3   7 |   | 22 A16      <- A16 sits where a 27C256 has OE#
 A2   8 |   | 21 A10
 A1   9 |   | 20 /OE      <- one active-low enable (where a 27C256 has CE#)
 A0  10 |   | 19 D7
 D0  11 |   | 18 D6
 D1  12 |   | 17 D5
 D2  13 |   | 16 D4
 GND 14 +---+ 15 D3
```
Same page also lists: EP ROM uPD27C256AD-20 (28-pin, 32 KB, the OS), REVERB MASK ROM HN623257PZ20 (28-pin), S RAM HM62256LP-15, PCM ROMs HN62304B (32-pin, see CONTEXT.md).

**SST39SF040 (DIP-32) as IC12, 128 KB used (A17 = A18 = 0):** seat the DIP-32 so its pins 3-30 line up with the 28-pin footprint (chip pin k+2 = board pin k; pins 1, 2, 31, 32 overhang the notch end). Everything lines up (A15..A0, D0..D7, GND, A10/A11/A9/A8/A13/A14, chip CE# <- board /OE) EXCEPT:
- chip pin 24 (OE#) sits on board pin 22 (A16): lift pin 24, tie it to GND (always output-enabled; chip CE# is the real enable).
- board pin 22 (A16) -> wire to chip pin 2 (A16).
- chip pin 30 (A17 on SF040) sits on board pin 28 (Vcc): lift it and tie to GND.
- chip pin 1 (A18) -> GND.
- chip pins 32 (VDD) and 31 (WE#) -> board Vcc (pin 28 net).
SF010 variant (128 KB part): same, pins 1 and 30 are NC (still lift 30). Check with a meter before power: board pin 20 should swing low during reads (active-low enable); if it is high-enabled on your board the polarity differs from the manual.

## Designator corrections (D-110 service notes p.4 parts list + p.14 change info, read 2026-10-05)
- The dump files are named "ic12" (romset naming), but on the D-110 main board the LH5310 tone ROM is **IC15** ("15179904 LH5310-DJ, 1M mask ROM"; the dump `r15179873 lh5310-97` is the later revision from the p.14 change note). **IC12 on the board is a TC74HC27P** (triple 3-input AND). Use IC15 when talking about the physical chip.
- CPU = **8097BH (IC18)**, not an 8095. OS = IC19 (uPD27C256AD-20, 32 KB). **IC6 = HN623257PZ20 "reverb mask ROM" (32 KB)** - so the dump `r15179879.ic6` is reverb data, not control data. IC7 = HN62304BPC99, IC8 = HN62304BPD10 (4 Mbit PCM). Reverb chip = IC5 HG61H20R36F, LA chip = IC9 MB87136APF, DRAM IC1-4 MN4264-12, SRAM IC17 HM62256LP-15, gate arrays IC21 (uPD65005G-062) and IC16 (HG61H15B-72F).
- C23 = 0.1 uF decoupling on the 8097BH Vcc pin (pin 1), next to C26 10 uF/16 V electrolytic.

## IC15 in the schematic (service notes p.7, main board; symbol labelled LH531097 = the "-97" part)
- Plain 28-pin symbol, nothing drawn for extra pads. Pins: 22 A16, 1 A15, 27 A14 ... 10 A0 all on the shared ADDRESS bus; 19..11 D7..D0 on the shared DATA bus; 28 Vcc, 14 GND.
- **Pin 20 /CE is private to IC15**: driven by inverter 10f (out pin 12) <- NAND/NOR-style gate 14d (inputs /RD and AUXB2). The same /RD also feeds IC19's /OE (22); IC19's /CE (20) comes from BANK0.
- So the only net you could cut without upsetting other chips is pin 20; every address/data/power pin is shared. No trace cuts are needed for the SST: lift SST pins 24 and 30, wire A16 pad -> SST pin 2, tie SST pin 1 low, pins 31/32 to Vcc, SST CE# (pin 22) lands on board pin 20.
