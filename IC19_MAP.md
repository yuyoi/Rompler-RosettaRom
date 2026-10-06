# D-110 IC19 (OS ROM, 32 KB, MCS-96 code) - structure map

Dump checked 2026-10-06: SHA1 `28635510f30d6c1fb88e00da03e5b4e045c380cb`, CRC32 `3ae68187` = MAME's
`d-110.v1.10.ic19.bin` ("D-110 ver1.10 Aug. 30, 1988", string at `0x2206`). Tools: `mcs96_dis.py` (disassembler +
flow tracer), `test_mcs96_dis.py` (decoder vs MAME's i8x9x disassembler on every byte offset: 0 mismatches).
"Verified" = read from the traced code. "Hypothesis" = plausible, not yet confirmed.

## CPU and memory map
CPU N8097BH (MCS-96) at 12 MHz, BUSWIDTH tied low (8-bit external bus). Map from MAME `roland_d10.cpp`, confirmed by the code:

| CPU address | What | Status |
|---|---|---|
| `0x0000-0x00FF` | 8097 registers/SFRs. SP starts at `0xF9D0` (in RAM). | verified |
| `0x0100` | bank latch: page n maps bank-space `n * 0x4000` into the window | verified |
| `0x0200` | system out (LED, reverb program A13/A14, ...) | MAME |
| `0x021A`, `0x021C` | button matrix inputs SC0/SC1 | verified (read) |
| `0x0300`, `0x0380` | LCD data / control (busy flag read from `0x0380`) | verified |
| `0x0280`, `0x0400`, `0x0800` | written at reset (`0x0280 = 0x0C`, zero to `0x0400`/`0x0800`) | unknown device |
| `0x0C00-0x0DC2` | heavy writes; reset fills `0x0CC0-0x0CFF` with 32 words `0xFFFF` | hypothesis: LA32 (32 partials) |
| `0x1000-0x7FFF` | IC19, file offset = CPU address | verified |
| `0x8000-0xBFFF` | 16 KB bank window | verified |
| `0xC000-0xFFFF` | fixed RAM (bank space `0x40000`) | verified |

Bank pages seen in the code: `0x00` IC19 `0x0000-0x3FFF` (strings, window code), `0x11` RAM, `0x20` IC12 `0x0000-0x3FFF`,
`0x30`/`0x31` memory card. IC6 (`r15179879`) is the BOSS reverb chip's program ROM (MAME: region "boss"), not CPU code.

## IC19 layout

| Offset | What | Status |
|---|---|---|
| `0x0000-0x08CC` | only reachable through the window (page 0, CPU `0x8000+`). Word table of pointers (`0x8146`, `0x8167`, ...) to the UI strings ("Patch Select/", "TIMB_E/Part", ...), read by `ld r78, 0x8000[r76]` at `0x7D78` after `clrb rb7` -> bank 0 | verified |
| `0x0A00-0x0FB3` | **factory TEST MODE, run from the window** (`stb #0 -> 0x0100; lcall 0x8A00` at `0x2280`): switch, D/A, MIDI loop-back, RAM and RAM-card tests; own jump table at `0x8A8A` (33 entries) | verified |
| `0x0F22-0x0F6C` | 75-byte routine copied to RAM `0xF000` (copy loop at `0x8E0B`). Called with the page in `rb7`: switches the bank while running from RAM, so card/RAM pages can be read from window code | verified |
| `0x1000-0x1805` | data tables (curves, constants) | data |
| `0x1820-0x1FA8` | serial debug monitor ("load ok", "sum err", "hex err", "#break at:"), LCD driver (`0x1C54-0x1CF8`), TRAP handler `0x19D5` (prints `#break at:` + address, then `ljmp 0x182D` into the monitor) | verified |
| `0x2000-0x2011` | interrupt vectors (below) | verified |
| `0x2018` | chip configuration byte `0xBD` | verified |
| `0x2080` | reset: `sjmp 0x20EF` (init: SP, I/O devices, serial port, ...) | verified |
| `0x2082-0x20A3` | 16 `sjmp`/`ljmp` entry vectors, called by the window code (`lcall 0x2086/0x208A/0x208E`) | verified |
| `0x2200-0x2240` | version string + credits | verified |
| `0x2240-0x7FEC` | main OS code and data (UI, MIDI, LA32/sound control) | partly traced |

Vectors: timer overflow `0x22A3`, software timer `0x1A08` (HSO scheduling), serial (MIDI) `0x1DAC`, EXTINT `0x3138`,
TRAP `0x19D5`; A/D, HSI data, HSO and HSI.0 unused (`0xFFFF`).

## The OS reads IC12 at fixed addresses (answers IC12_MAP open item 3)
All with bank page `0x20` selected just before (IC12 offset = CPU address - `0x8000`):

| Code | Access | IC12 table |
|---|---|---|
| `0x4E51` | `ld r78, 0x8000[r70]` | preset timbre map `0x0000` |
| `0x36E3`, `0x383F` | `ld r70, 0x8900[r74]`, `add r70, 0x8902[r76]` | PCM table `0x0900` (`pos/len`, `pitch`) |
| `0x25F2`, `0x4DD0` | `ld r70, 0x8D00[r70]` | rhythm timbre map `0x0D00` |
| `0x2573`, `0x4D8B` | `ld r70, 0x8F00[r70]` | **word table at `0x0F00`**, inside the unidentified `0x0D80-0x0FFF` blob |

So those table addresses are hard-coded in IC19: moving a table means patching these operands (and any others found later).

## UI dispatch (why part of the code is still untraced)
- `rb4` holds the current UI state handler (`ld rb4, #0x4F66`, `cmp rb4, #0x5036`); `br [rb4]` at `0x4F1A` and `0x6F31`.
- Handlers start `ld r78, #descriptor` + `ljmp 0x53A3`, and `0x53A3` interprets the descriptor. Hypothesis from a few
  examples: a leading routine pointer, then entries keyed by button codes with a type byte (`0x21`, `0x3E`, `0xBE`, ...)
  and handler pointers. Not decoded yet.
- Those pointers lead to most of the code still listed as data (`0x5000-0x7FFF`).

## Coverage (mcs96_dis.py, 2026-10-06)
~5000 instructions / 15.3 KB of code traced from the vectors, 6 jump tables, 1 RAM copy, 0 decode conflicts.
Untraced but decoding cleanly as code: roughly 10 KB, mostly UI handlers behind the descriptors.

## Open items
1. Decode the `0x53A3` descriptor format and feed its handler pointers to the tracer.
2. Identify the devices at `0x0280`, `0x0400`, `0x0800`, `0x0C00-0x0DC2` (LA32 register layout, reverb control).
3. MIDI input path from the serial interrupt `0x1DAC` (SysEx parser, part/channel mapping).
4. What IC12 `0x0F00` holds (word table, indexed like the rhythm map).
5. Where the system tables munt calls reserve/pan/program/max/soundgroup live (IC12 or IC19).
