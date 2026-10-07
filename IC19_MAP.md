# D-110 IC19 (OS ROM, 32 KB, MCS-96 code) - structure map

Dump checked 2026-10-06: SHA1 `28635510f30d6c1fb88e00da03e5b4e045c380cb`, CRC32 `3ae68187` = MAME's
`d-110.v1.10.ic19.bin` ("D-110 ver1.10 Aug. 30, 1988", string at `0x2206`). Tools: `mcs96_dis.py` (disassembler +
flow tracer), `test_mcs96_dis.py` (decoder vs MAME's i8x9x disassembler on every byte offset: 0 mismatches).
"Verified" = read from the traced code. "Hypothesis" = plausible, not yet confirmed.

## Resume here: stage 3 (pick the first patch)
- **Repo `yuyoi/Rompler-RosettaRom`, branch `claude/chat-session-0e24rd`** (not `yuyoi/u110-romhex-studio`).
- The ROM is not in git. Put your own IC19 dump at `ctrl/ic19.bin` and check `sha1sum` = the SHA1 above (v1.10;
  other versions decode fine but every address in this file is for v1.10). Then regenerate the private listing:
  `python mcs96_dis.py ctrl/ic19.bin -o ctrl/ic19.lst` and `python mcs96_dis.py ctrl/ic19.bin --summary`.
  `python test_mcs96_dis.py` checks the tracer against this ROM; `sh mame_ref/build.sh` first adds the MAME decoder check.
- Stage 2 is done (2026-10-07): UI menus decoded (below), MIDI input traced from the serial interrupt to the SysEx
  address map, I/O devices identified. Traced code went from 15.3 KB to 23.9 KB; what is left untraced in
  `0x2000-0x7FFF` is ~1.5 KB, almost all strings and tables.
- Next: pick the first small patch and test it in an emulator before burning an EPROM. Candidates, smallest first:
  1. A text change (version string `0x2206`, a menu string through the window table at IC19 `0x0000`) to prove the
     build/checksum/burn path. **Works on hardware (2026-10-07):** `patch_ic19.py --banner` (see "Stage 3: first patch").
  2. A UI tweak through a menu entry: every key binding is one 4/6-byte entry (see "UI menus").
  3. A SysEx tweak: the address map is one 10-entry table (`0x470C`/`0x4718`, see "MIDI input").
  The emulator: MAME's `d110` driver runs this ROM (no sound: MAME has no LA32), enough to check UI and SysEx.

## CPU and memory map
CPU N8097BH (MCS-96) at 12 MHz, BUSWIDTH tied low (8-bit external bus). Map from MAME `roland_d10.cpp`, confirmed by the code:

| CPU address | What | Status |
|---|---|---|
| `0x0000-0x00FF` | 8097 registers/SFRs. SP starts at `0xF9D0` (in RAM). | verified |
| `0x0100` | bank latch: page n maps bank-space `n * 0x4000` into the window | verified |
| `0x0200` | system out (LED, reverb program A13/A14, ...) | MAME |
| `0x021A`, `0x021C` | button matrix inputs SC0/SC1 | verified (read) |
| `0x0300`, `0x0380` | LCD data / control (busy flag read from `0x0380`) | verified |
| `0x021A` (write) | output latch (shadow `rc8`): bit 0 = OR of the per-part bytes `0xF283` and flags `rc6`/`rc7` (`0x5B0D`; activity LED?), bits 1-3 = reverb mode bits 1-3 | verified (writes), bit 0 use hypothesis |
| `0x0280` | LCD-side latch: `0x2C` while the LCD module is initialised (`0x1C8C`), `0x0C` otherwise | verified (writes), use unknown |
| `0x0400`, `0x0800` | reverb parameter latches (see "I/O devices") | verified |
| `0x0C00-0x0DFF` | LA32 sound generator: per-partial register banks, interrupt source register | verified access pattern, register meaning partly hypothesis |
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

## UI menus (verified)
- `rb4` holds the current UI state handler; `br [rb4]` at `0x4F1A`/`0x6F31` runs it. A handler is `ld r78, #menu` +
  `ljmp 0x53A3`. The interpreter gets the event in `r70`: `0xFF` = enter/refresh (runs the menu's init routine),
  `0xF0` = refresh only if `0xF6E6` bit 6 is clear, anything else = a key code looked up in the entry list.
- Menu format: `dw init`, then entries until `0x00`:
  - `FE lo hi`: include another entry list (lists share tails, e.g. `0x5775` = include `0x5229` + the list at `0x5778`).
  - `key, type, dw operand` (4 bytes) or, when type bit 7 is set, `key, type, dw operand, dw after` (6 bytes); `after`
    runs once the action is done (usually a redraw).
- `type & 0x7F` is a letter from `"!+-=>ASidIJKDEF"` (`0x5475`); stubs in the word table `0x5485`. The operand is
  always code. For value actions it is an accessor that returns `r78` = the variable, `r75` = its maximum.

| type | stub | action |
|---|---|---|
| `!` | `0x54F1` | call the operand |
| `>` | `0x54C1` | push state: current `rb4` to the stack at `0xF4E2[rb6*2]` (`rb6` = depth), `rb4` = operand |
| `=` | `0x54CF` | set state: `rb4` = operand, no push |
| `+` `-` | `0x54F3` `0x5504` | variable +1 (max `r75`) / -1 (min 0) |
| `i` `d` | `0x5511` `0x5519` | +10 / -10, clamped the same way |
| `I` `J` `K` | `0x5521` `0x5540` `0x5561` | +1 in bits 0-2 / +1 in bits 3-5 / set bit 6 |
| `D` `E` `F` | `0x5532` `0x5552` `0x556D` | -1 in bits 0-2 / -1 in bits 3-5 / clear bit 6 |
| `A` `S` | `0x7539` `0x754D` | not read yet (used for the Bank keys on the part screens) |

- Exit (key `0x01`) in the shared list `0x5229` calls `0x5391`: pop state (`rb6--`, `rb4` = saved). When the depth
  `rb6` reaches 0 the interpreter clears `0xF4CE` and jumps to `0x5B36` (top level).
- `0x57D1` = push state with `rb4 = r78` (no menu): `ld r78, #handler` + `ljmp 0x57D1` passes a state handler.
- Key codes (scan at `0x1A95`: code k = `BTN_SC0` bit 8-k for 1-8, `BTN_SC1` bit 16-k for 9-16; names from MAME):

| code | key | code | key | code | key | code | key |
|---|---|---|---|---|---|---|---|
| `01` | Exit | `05` | Group + | `09` | Edit | `0D` | Group - |
| `02` | Patch | `06` | Bank + | `0A` | Part | `0E` | Bank - |
| `03` | Timbre | `07` | Number + | `0B` | System | `0F` | Number - |
| `04` | Part + | `08` | Write/Copy | `0C` | Part - | `10` | Enter |

  Codes `0x19`, `0x81`, `0x82` are internal events (screens load them into `r70`; `0x81`/`0x82` also go to `0xF6E6`).
- Top-level menu `0x4F8E` (state `0x4F66`): Part/System/Timbre/Patch push their screens (`0x6BA6`, `0x735B`, `0x5BDC`,
  `0x6E7B`), Write calls `0x590C`, Part +/- comes from the included list `0x5778`.
- The listing prints every menu as `menu`/`key` rows with key names and actions; 34 menus, 1224 bytes.

## MIDI input (verified)
- **Serial interrupt `0x1DAC`** (also transmits from the ring `0xFE00-0xFEFF`, pointers `re8`/`rea`). Received byte
  in `rf8`, running status in `rfa`, data count in `rfb`. Channel messages become 3-byte events
  `status, data1, data2` (1-data-byte messages repeat data1) in the ring `0xF9FB-0xFCE2`, write pointer `rec`,
  read pointer `ree` (`rf2` = consumer's copy). Real-time: `0xFE` active sensing reloads the timeout `rc5 = 0x1E`
  (on timeout the software timer injects `0xFF` = reset); `0xFC` stop is queued; clock/start/continue are ignored;
  `0xF1-0xF6` cancel running status.
- **SysEx**: `F0 41 ...` (Roland) is stored inline: an `F0` event whose data bytes become the end pointer after `F7`,
  body (from `0x41`) right after it, up to `0xFDF3`; overflow queues `F0 00 F7`, a full queue queues `0xFE`
  ("Exclusive BufferOverflow Error"). `F0 00 ...` goes to a separate byte ring `0xFF00-0xFFFF` (`rf4`/`rf6`) read
  by the serial debug monitor (`0x1D78`, from `0x183C`): hypothesis, the monitor talks over MIDI. Other IDs are ignored.
- **Reader** `0x1D35` (API vector `0x2098`): `r70` = status, `r75` = data1, `r74` = data2, or for SysEx `r74` =
  pointer to the body.
- **Main-loop dispatch `0x22A8`**: channel messages index `jtab_241C` by `(status & 0x70) >> 3`:
  `8n` note off `0x245D`, `9n` note on `0x24FC`, `An`/`Dn` ignored (`0x244E`), `Bn` control change `0x3BBA`,
  `Cn` program change `0x244F`, `En` pitch bend `0x242C`. The handler runs once per part (9 parts, 16-byte records at
  `0xF283`, receive channel at `+8` = `0xF28B`) whose channel matches; `r50` = part * 16. Program change on the
  control channel (`0xEDB6`) goes to `0x6F01` instead (hypothesis: patch change). `0xEDB5` bit 0 set = echo channel messages to
  MIDI out. `0xFF` resets controllers (`0x234A`); `0xF0`/`0xFE` go to the SysEx parser `0x41AA`.
- **Control change table `0x3BCE`**: 128 words, 0 = ignored. Handled: 1 modulation (`0x3CCE`, `0xF287[part]`),
  6 data entry (`0x3CD7`), 7 volume (`0x3CFF`), 10 pan (`0x3D10`), 11 expression (`0x3D22`), 64 hold (`0x3D33`,
  `0xF286[part]`), 98/99 (`0x3D94`), 100 (`0x3D9D`), 101 (`0x3DAB`) = RPN/NRPN select, 121 reset controllers
  (`0x3DB9`), 123 all notes off (`0x3DE2`), 124-127 (`0x3DDD`).
- **SysEx parser `0x42C5`**: body `41, dev, model, cmd, ...`; model must be `0x16`. Commands (`0x47F0` + `jtab_47C6`):
  `42` DAT `0x43AD`, `40` WSD `0x4346`, `41` RQD `0x4366`, `12` DT1 `0x43CE`, `11` RQ1 `0x44A7`, `43` ACK / `4E` ERR /
  `4F` RJC `0x46AB`, `45` EOD `0x469C` (full Roland handshake). Address `aa bb cc` is copied to `0xF6A5-0xF6A7`, device
  ID to `0xF6A4`. DT1 data starts at body + 7.
- **Address map** (`0x46B1`: MSB looked up in `0x470C`, `size, RAM base` words at `0x4718`; offset = `bb << 7 | cc`,
  must be below size; device ID check at `0x48B5`):

| MSB | RAM | size | device ID | likely contents |
|---|---|---|---|---|
| `00` | `0xE000` + 16 * part | 16 / part | a part's receive channel (`0x4740`) | patch temporary |
| `01` | `0xE090` | 340 = 85 * 4 | rhythm part channel (`0xF30B`) | rhythm setup |
| `02` | `0xE1E4` + 246 * part | 246 / part | channel of part 1-8 | timbre temporary |
| `03` | `0xE000` | 484 | unit ID (`0xEDB7`) | `00` + `01` as one block |
| `04` | `0xE1E4` | 1968 = 8 * 246 | unit ID | all timbre temporaries |
| `05` | `0xE994` | 1024 = 128 * 8 | unit ID | patch memory |
| `06` | `0xC000` | 8 KB | unit ID | timbre memory (first half) |
| `08` | `0x8000` window (RAM page `0x11`) | 16 KB | unit ID | timbre memory (banked) |
| `10` | `0xED94` | 33 | unit ID | system area (`+1..+3` reverb, see below) |
| `20` | `0xF6AC` | 129 | unit ID | LCD text (MT-32 "display" area) |

  "Likely contents" follows the MT-32-family MIDI implementation; the RAM ranges and sizes are read from the table.

## I/O devices (stage 2 step 3)
- **`0x0400` / `0x0800`: reverb latches (verified)**, write-only, shadows `0xF4A3` / `0xF4A2`, set from the system
  area (SysEx `10 00 01-03`) by `0x4C93`, `0x4CC6`, `0x4D04`:
  - mode `0xED95`: bit 0 -> `0x0800` bit 2, bits 1-3 -> `0x021A` bits 1-3 (MAME's MT-32 driver: reverb program A13/A14
    on the system output);
  - time `0xED96`: bits 0-2 -> `0x0400` bits 0-2;
  - level `0xED97`: bit 0 -> `0x0400` bit 3, bits 1-2 -> `0x0800` bits 0-1.
  Reset (`0x2106-0x214A`) writes zero to both, waits, and writes zero again.
- **`0x0280`**: written only around LCD set-up (see memory map). Hypothesis: LCD module reset/contrast line.
- **`0x0C00-0x0DFF`: LA32 (verified as the sound chip, register meaning partly hypothesis)**. Evidence: 32-entry
  register banks indexed by partial * 2, and `int_extint` (`0x3138`) reads `0x0C00` to get the number of the partial
  that raised the interrupt, then reloads that partial's registers (munt: the LA32 interrupts when a ramp completes).
  Banks (32 words each, RAM shadows in brackets):
  - `0x0C00`/`0x0C01` and `0x0C80`/`0x0C81`: ramp pairs `rate|direction (bit 7), target`; which bank is used depends on
    `0xEF80[p]` bit 7 (`0x2CD3`, `0x3073`). [`0xEEC1`]
  - `0x0C40`/`0x0C41`: written at `0x36FF`, `0x38AB` (`0xFF` or a computed value), `0x3939`. [`0xF1C0` = `0x0C41`]
  - `0x0CC0`: `0xFFFF` at reset and in the interrupt handler (`0x316E`).
  - `0x0D00`/`0x0D01`: flags / resonance-related byte (timbre partial byte `0x18`, `0x3781`). [`0xEF80`/`0xEF81`]
  - `0x0D40-0x0D7F`: 4 groups of 16 bytes, words at `+0/+2/+4` reset to `0`, `0x8000`, `0xFFFF` (`0x3026`).
  - `0x0DC0` = `0xC000`, `0x0DC2` = 0 at reset: global control.
  Partial byte offsets match munt's MT-32 partial parameter layout (`0x18` TVF resonance, `0x19` TVF keyfollow, ...):
  hypothesis until checked against a capture or munt.

## Coverage (mcs96_dis.py, 2026-10-07)
7842 instructions / 23.9 KB of code, 16 jump tables (incl. sparse and byte-pair tables), 34 UI menus, 1 RAM copy,
0 decode conflicts. Untraced in `0x2000-0x7FFF`: ~1.5 KB, mostly strings and data tables (`0x41B8` SysEx error
messages, `0x5724` LCD character set, `0x66EB` tuning labels, `0x7804` "Roland D-10" ID strings). Possibly code still
untraced: `0x65B0-0x662D`, `0x7469-0x7489`.

## Other open items
1. What IC12 `0x0F00` holds (word table, indexed like the rhythm map).
2. Where the system tables munt calls reserve/pan/program/max/soundgroup live (IC12 or IC19).
3. Menu actions `A`/`S` (`0x7539`/`0x754D`), and what produces the internal key codes `0x19`/`0x81`/`0x82`.
4. LA32 register meanings (per bank) and the `0x0D40` groups; `0x0280`.
5. Whether `F0 00 ...` really feeds the debug monitor over MIDI.
6. Whether the OS checksums IC19 (matters for the first patch).

## Stage 3: first patch (2026-10-07)
- **No ROM checksum.** The only loops that add up bytes read through a pointer are the SysEx checksums: `0x4518`
  (address bytes from `0xF6A5`) and `0x4C27` (outgoing Roland message up to `F7`, `negb`/`and 0x7F`). Nothing sums
  `0x1000-0x7FFF`, and test mode (`0x8A00`) has no ROM test. So a patched IC19 needs no checksum fix-up.
- **Version screen.** Boot code `0x2264` reads the SC1 button row (`0x021C`). On `0xEA` it prints the string at
  `0x2205` (api_208a -> `0x1C02`) then `0x228D` runs a delay loop and waits until api_208e returns 0; on `0xFC` it enters test mode (`0x8A00`).
  Combo confirmed on the unit: hold **Enter + Part - + Bank -** at power-on (`0xEA` = SC1 bits 4, 2, 0 low; keys read active-low). String format for `0x1C02`: one LCD DDRAM address
  byte (`0x00` = line 1), then characters to column 16, then line 2 (`0x40`) until a `00` byte. v1.10 has 32 characters
  at `0x2206-0x2225` and `00` at `0x2226`.
- `patch_ic19.py ctrl/ic19.bin --banner "LINE1" "LINE2"` checks the v1.10 SHA-1, writes the two 16-character lines
  and saves `ctrl/ic19_patched.bin`. Checked: 20 bytes differ, all within `0x2206-0x2225`, and the regenerated listing
  differs only in that string.
- **Hardware test passed (2026-10-07).** Burned on a T48 to an ST M27C256B (UV EPROM) in place of the stock Mitsubishi
  M5M27C256K. The unit boots normally, and the combo shows the new text. So the dump -> patch -> burn path works.
- `0xFC` (Number - + Enter held) enters test mode instead.
- **Boot banner (built 2026-10-07, not yet burned):** `--boot-banner` changes `0x2269` from `cmpb r70,#0xEA; jne` to
  `cmpb r70,#0xFC; je`, so the version screen shows on every power-on and only the test-mode combo skips it.
  After the banner, `r70` = 0 (left by `0x228D`), so the `0xFC` test at `0x2278` does not fire. `--banner-time N` sets
  the delay count at `0x228E` (v1.10: 30). Each step is 256*256 `djnz` loops, about 0.15 s at 12 MHz (estimate, not timed).

