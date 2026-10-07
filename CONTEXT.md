# Rosetta ROM - context (grabbed 2026-10-05 from "u110-romhex studio and hexwizardv1")

Goal: ESP32 + RAM/flash stand-in for a rompler's mask-ROM PCM wave chip(s), so any rompler can play user samples (a sampler).
Generalises U110 HexWizard (one card format) -> per-machine "stones": address/data scramble + table format per synth.

## What already exists (reuse, don't rebuild)
- Desktop/U110_Card_Studio  : Studio app (src/u110build.py, u110card.py, u110wave.py, roland*.py, akai*.py). WAV -> card image, DPCM encode, loop/zone tables.
- Desktop/u110_card/FORMAT.md : solved U-110 card format (addr/data bit permutations raw<->proper, sample entry 10 B, tone list 0x50 B, 256 KB bank boundary).
- Desktop/esp32-maskrom-programmer : working ESP32-S3 -> SST39SF040 burner (GPIO direct, WiFi web UI, OLED). Verified 0 bad bytes / 512 KB. Write-only.
- Desktop/hexwizard_mk2 : KiCad cards. mk2_min routed (direct GPIO), mk2_fancy placed (74LVC595 addr + 74LVC245 data, slot-5V sense). Untested on hw.
- Desktop/U110_TODO.md : "U110 Hexacordia" = live ROM EMULATION (fast 5V SRAM <=55ns, ESP writes between synth reads, bit-mask/XOR data, address scramble as performance control). THIS is the seed of Rosetta ROM. Also Clock Tower, Korg M1/M3R card idea, Pro-E/D-50 wave swap idea.

## Hard-won facts
- Card slot: 34 pin, A0-A18, D0-D7, CS active HIGH, /OE active low, 5 V logic. ESP32 = 3.3 V (SST VIH only 2.0 V so ESP->chip OK; chip/synth->ESP 5 V NOT OK without 74LVC245 / FET switches).
- Flash can't serve reads while programming (status bits) -> live editing needs SRAM or dual-port; bus contention = THE design problem.
- Mask ROM swap (vs card) = chip is soldered in the synth: needs a socket/plug-in adapter in the DIP/SOP footprint, tri-state outputs, access time budget of the original (typ 150-250 ns mask ROMs; SRAM 55 ns is fine).
- ESP32-S3 GPIO count is tight (A0-A18 + D0-D7 + ctrl = ~30). Fancy card trick: shift registers for address OUT, but a ROM EMULATOR must READ the address bus fast -> shift regs don't work; needs 74LVC245 inputs, or CPLD/RP2040 PIO front, or ESP32 I2S/LCD-cam parallel capture.
- PCM data is often DPCM/scrambled/bank-split (U-110: 8-bit DPCM, bits permuted). Rompler tone/ROM tables must be reverse engineered per machine.

## Open design questions
1. Replace the wave ROM only (data swap, tables stay) vs also intercept the tone table region (new samples need new table entries).
2. Architecture: (A) SRAM + ESP loads it, synth reads SRAM directly (simple, static); (B) ESP/CPLD/PIO answers reads live (flexible, hard timing); (C) SRAM dual-port-ish with bus switches.
3. First target machine (U-110 is the only one fully solved; others: D-50/D-10, Korg M1/M3R PCM cards, JV/XP wave ROMs, Akai ... ).
4. Form factor: card (slot machines) vs DIP/SOP/QFP clip-in for soldered mask ROMs.

## Decisions (user, 2026-10-05)
- First target: Roland D-110 (not U-110). Needs: D-110 wave ROM chip pinout/size, dump (MAME has D-110/MT-32-family ROMs), PCM format. D-110 = LA synthesis + PCM ROM, so check which ROM(s) hold the PCM.
- Architecture: SST39SF040 (or similar) programmed by ESP32 at 3.3 V, using the user's existing working universal design (esp32-maskrom-programmer). NOT live emulation.
- Status: context only, no design doc yet.

## D-110 PCM DECODED (2026-10-05)
- IC7 (r15179878) and IC8 (r15179880): each an independent 512 KB MT-32-style PCM ROM. 16-bit log samples = 2 consecutive bytes (s,c), bit order {0,9,1,2,3,4,5,6,7,10,11,12,13,14,15,8} (munt Synth.cpp). No address scramble.
- Linear magnitude = 2^((v&0x7fff)/2048) (bigger = louder), sign = bit 15. Wrong way round gave glitchy audio.
- User HEARD it clear on the fixed render. Script: probe_pcm.py. Sample table lives in control ROM (pos*0x800, len 0x800<<exp, loop flag).
- Credit: user's own ear-first intuition that the first (glitchy) render sounded like it was playing "super fast" pointed straight at a decode/playback issue. Their call, recorded at their request.

## Control ROM table found (2026-10-05)
- Control ROM files unpacked to ctrl/. IC12 r15179873 (128 KB) holds the PCM table; IC19 (32 KB) = OS, IC6 (32 KB) unknown.
- Table in IC12 starts at 0x900: 4-byte entries {pos, len, pitchLo, pitchHi}, munt ControlROMPCMStruct format. addr = pos*0x800 SAMPLES (=pos*0x1000 bytes), length = 0x800<<((len>>4)&7), loop = len&0x80. First block = 128 entries (0x900-0xAFF), more blocks follow (0xB00.. variants with len low nibble 1, 0xC.. etc: not decoded).
- WAVE SPACE = 1 MB: IC8 first (bytes 0x00000-0x7FFFF), then IC7 (0x80000-0xFFFFF). Proof: single-cycle loop entries (0xA24+, pos 0xDB-0xFF) are smooth only in this order (seam jump 0.03 vs 0.26 swapped).
- Scripts: table_test.py, split_table.py -> samples/ (128 wavs) + audition_first128.wav.

- User: IC8 (r15179880) is DRUMS ONLY. Consistent with the order found (IC8 = wave pos 0x00-0x7F, IC7 = pos 0x80-0xFF incl. the looped waves at 0xDB-0xFF). So replacing IC8 alone = custom drum kit, needs only the 128-ish table entries pointing at pos 0-0x7F.

## Encoder + slot swap WORK in software (2026-10-05)
- rosetta_d110.py: ROM<->log<->linear codec, bit-exact round trip on both dumps. Full scale = m 32766 (mag 2^(m/2048)).
- swap_ic8.py <slot#> <in.wav> [out.bin]: replaces one drum slot in IC8, same position/length, no table edit. test_swap.py: decoded vs input correlation 1.0000.
- NOT yet: hardware test; slot names/key map; pitch field meaning (so rate/tuning of a swap is unverified); table blocks 0xB00+.

## Names + both chips (2026-10-05)
- Wave names: IC12 0x100 + 8*index, 8 ASCII chars, same index as the 0x900 table (validated: Rimshot/Bongo short, Crash/Ride/Timpani long, *Lp entries flagged loop). Idx 0-31 drums (IC8), 32+ = IC7 (AcPianoH, Trumpet, ...). First 128 table entries only; 128+ (0xB00 block) not understood.
- Timbre names are 10 chars at the start of each timbre record in IC12 (from 0x1200, e.g. ClsdHiHat1); not touched yet.
- rosetta_swap.py <index> <wav> [name]: patches IC8 or IC7 (by position) and IC12 name -> patched/. Tested both chips: decode corr 1.0000.
- UNVERIFIED: pitch field/tuning, hardware (IC7/IC8/IC12 package + pinout vs SST39SF040/SST39SF010; IC12 is a LH5310 128 KB mask ROM so IC12 also needs replacing for name edits).

## Rosetta ROM Studio v0.1 (2026-10-05)
- rosetta_studio.pyw (run: py -3.10 rosetta_studio.pyw). U110-Studio look (theme/LCD/LED meter copied). Wave list (128, filter IC8/IC7/Changed), waveform original vs replacement, load WAV, rename (8 chars), normalize, play. File: save/open project (.rosetta json), import ROM dumps (remembered in rosetta_config.json), import WAV folder (003_x.wav or by name), export all original waves, BUILD -> patched IC8/IC7/IC12 + report.txt.
- --selftest builds headless. Launches OK; GUI not yet clicked through by me. Hardware untested.

## HN62304B pinout - FROM THE D-110 SERVICE NOTES p.12 "IC DATA" (2026-10-05) - standard JEDEC, = 27C040 layout
"PCM ROM A/B  HN62304BPC99 / HN62304BPD10" (A = IC7 r15179878 = C99, B = IC8 r15179880 = D10 presumably), top view, DIP-32:
```
 NC   1 +-v-+ 32 VDD          pin 1 NC (EPROM VPP), pin 31 = A18, pin 30 = A17, 24 = OE#, 22 = CE#, 16 = GND
 A16  2 |   | 31 A18          -> AM27C040@DIP32 is the right T48 profile
 A15  3 |   | 30 A17
 A12  4 |   | 29 A14
 A7   5 |   | 28 A13
 A6   6 |   | 27 A8
 A5   7 |   | 26 A9
 A4   8 |   | 25 A11
 A3   9 |   | 24 OE#
 A2  10 |   | 23 A10
 A1  11 |   | 22 CE#
 A0  12 |   | 21 D7
 D0  13 |   | 20 D6
 D1  14 |   | 19 D5
 D2  15 |   | 18 D4
 GND 16 +---+ 17 D3
```
An earlier note here (nesdev forum pinout with VCC on pin 16) was WRONG for this part; removed. T48 "bad pin position" is therefore placement/contact, not the profile.
SST39SF040 (DIP-32): A18 on pin 1, WE# on pin 31 (mask: pin 1 NC, pin 31 A18). Everything else matches, so the swap needs only: mask pin 31 (A18) -> SST pin 1, SST pin 31 (WE#) tied to VDD. Verify CE#/OE# polarity is normal (active low per the manual).

## IC12 fully mapped (2026-10-05, second pass) - see IC12_MAP.md, ctrl/ic12_dump.py
- IC12 layout follows munt's ControlROMMap: 0x0000 preset timbre map (128 x u16), 0x0100 wave names (256), 0x0900 PCM table (256 x 4 B), 0x0D00 rhythm timbre map (pointer - 0x8000), 0x1200 rhythm timbres, 0x3000-0x3BFF drum patterns, 0x4000 preset timbres (compressed: 14 B + 58 B per unmuted partial), 0xB000-0x1EBFF three demo songs (~82 KB).
- PITCH FIELD SOLVED: u16, 4096/octave, 0x5000 = native 32 kHz at middle C; others are exact semitone offsets (AcPianoH +2.00 st). Swap formula: pitch = 4096*(5+log2(R/32000)) - (root-60)*4096/12.
- PCM table has 256 entries but 128 distinct addresses (bank 2 = drum set aliases + loop slices). Wave index of a PCM partial = pcmWave + 128 if waveform > 1. PCM-or-synth comes from the partial structure table PS=[0,0,2,2,1,3,3,0,3,0,2,1,3].
- Still open: 0x0D80-0x11FF blobs (rhythm key settings?), reserve/pan/program tables (not in IC12, probably IC19/IC6), whether the OS hard-codes table addresses.

## Rosetta ROM Studio v0.2 (2026-10-05): pitch + loop + three files
- rosetta_studio.pyw: per-wave ROOT NOTE (name or MIDI, middle C = C4 = 60) writes the IC12 pitch field (`0x5000 - (root-60)*4096/12`) to every table entry that points at the same data (bank-2 drum aliases follow automatically); LOOP combobox sets/clears the loop bit (0x80 of the len byte). BUILD always writes IC8, IC7 and IC12 patched + report.txt (with a decode check per swapped wave). Roots/loops saved in .rosetta and .rcard.
- Selftest (`--selftest`): decode check 1.0000, IC12 diff = only names, pitch and loop bytes. Hardware-untested: first test = one swapped wave with its root set, played at the root key.
- dist/RosettaROMStudio.exe is the OLD v0.1 build (not rebuilt).

## Rosetta ROM Studio v0.3 (2026-10-05): long samples via table rewrite
- A WAV longer than its slot MOVES to a bigger slot (0x800<<e samples, e up to 7 = 8.19 s) and every IC12 table entry sharing the old slot (same pos + length code, incl. the bank-2 drum aliases) is rewritten. plan_layout() allocates; rule seen on all 256 stock entries: every slot is aligned to its own length, so the 1 MB wave space (16.4 s, currently 100% occupied) holds 4 x 4.10 s or 2 x 8.19 s. "Free this wave's space" checkbox releases waves you do not need (their sub-slices lying in freed space go with them).
- test_repack.py: 3.9 s + 8.0 s waves relocate, decode corr 1.0000, all 256 entries stay aligned/in range, no-space case refused cleanly, in-place swap leaves IC12 byte-identical.
- HARDWARE UNKNOWN: no stock wave uses a length code above 3 (max 0.51 s), so whether the LA32 handles e = 4..7 is untested. Test with one 2-4 s sample first.

## Way-different ROM sets (2026-10-05): gen_way_different.py -> private_banks/way_different/{safe,long}/
- safe = stock table layout, 111 synthesised waves (drum voices from gen_test_card + 11 looped + 10 one-shot recipes, tonal ones get an exact pitch field), new IC12 names. long = same plus DroneL 4.10 s loop, SubBoom 2.05 s, LongCrsh 1.02 s, Kick808 1.02 s; 72 waves freed (play silence, parked on one silent unit), old audio wiped.
- Studio v0.3 additions used: pitches= override, freed waves parked on a silent unit, wipe of freed/moved audio. Decode check 1.0000 on both sets; no Roland audio left in IC8/IC7 (IC12 still holds Roland's control data -> private). Hardware: untested; burn safe/ first.

## D-110 OS ROM (IC19) disassembly started (2026-10-06) - see IC19_MAP.md
- Dump = MAME `d-110.v1.10.ic19.bin` (SHA1 28635510...). CPU N8097BH (MCS-96), memory map from MAME roland_d10.cpp: IC19 code at 0x1000-0x7FFF, 16 KB bank window at 0x8000 (latch 0x0100: page 0x00 IC19 low, 0x11 RAM, 0x20 IC12, 0x30/0x31 card), fixed RAM 0xC000.
- mcs96_dis.py: decoder matches MAME's i8x9x disassembler on every byte offset (random 64 KB + whole IC19). Tracer follows vectors, jump tables, rb4 UI handler pointers, window code (factory test mode at IC19 0x0A00) and the RAM trampoline (IC19 0x0F22 -> 0xF000). 15.3 KB of code traced, no conflicts.
- The OS reads IC12 tables at hard-coded addresses (0x0000, 0x0900, 0x0D00 and an unknown word table at 0x0F00) with bank page 0x20. IC6 = BOSS reverb program ROM.
- Next: decode the UI descriptor interpreter at 0x53A3 (most untraced code), identify the I/O at 0x0280/0x0400/0x0800/0x0C00-0x0DC2 (LA32?), trace the MIDI input path from the serial interrupt 0x1DAC.

## IC19 stage 2 done (2026-10-07) - see IC19_MAP.md
- UI menus decoded: `dw init` + entries `key, type, dw operand[, dw after]`, includes `FE lo hi`, end `00`; 15 action letters (call, push/set state, +/-1, +/-10, bit-field steps). Key codes = button bits (Exit 01 ... Enter 10, names from MAME). mcs96_dis.py now follows menus, state handlers passed to 0x57D1, sparse and byte-pair jump tables: 23.9 KB of code traced (was 15.3), ~1.5 KB untraced left, mostly strings/tables.
- MIDI: serial interrupt 0x1DAC -> 3-byte event ring 0xF9FB-0xFCE2 (SysEx bodies inline) -> reader 0x1D35 -> main-loop dispatch 0x22A8 (per message type, per part by receive channel), CC table 0x3BCE, SysEx parser 0x42C5 (model 0x16, full handshake), address map table 0x470C/0x4718 (00 patch temp ... 20 display).
- I/O: 0x0400/0x0800 = reverb latches (mode/time/level from system area 10 00 01-03), 0x0C00-0x0DFF = LA32 (EXTINT reads 0x0C00 for the partial that raised it), 0x0280 = LCD-side latch.
- Next: first small patch (text, menu binding or SysEx table), tested in MAME's d110 driver first.
