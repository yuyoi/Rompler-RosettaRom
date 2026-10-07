"""Rosetta OS extension: new features in IC15, called from small hooks in IC19 (two-chip mod, on top of the IC19-only
v6 mod in ic19_quick.py). See IC19_MAP.md, "Rosetta (IC15 code)".

  python patch_ic19.py ctrl/ic19.bin -o ctrl/ic19_ros.bin --quick --cc --rosetta ...
  python patch_ic15.py my_ic15.bin -o my_ic15_ros.bin --rosetta

IC19 side (build_ic19): a call system into IC15 page 0x27 that checks the magic word at CPU 0xB000 first, so a stock
IC15 just means "feature off", plus hooks:
  - Quick screen: Edit opens the Rosetta menu (raw UI state handler)
  - MIDI note on / off (jtab_241C) -> arp, mono/legato, chord memory, unison
  - CC70 -> wave scan; CC16/CC17 and aftertouch -> mod matrix sources
  - end of the per-partial note-on setup (0x3BB4) -> drift, random cutoff/wave, unison detune, glide, note mods, lab
  - main loop (0x22B9): the old demo tick (rc4, ~2 ms) -> arp clock, glide, wave sequence, LFO, mod matrix
  - serial interrupt: MIDI clock F8 / start FA are counted for the arp and the synced LFO (the stock OS ignores them)
  - MIDI out: arp notes through the stock transmit routine 0x1D8D
  - call19 / rd20: IC15 code calling IC19 routines (they may leave another page mapped) and reading IC15 page 0x20
IC15 side (build_ic15): magic + jump table at 0xB000 (fixed, so IC15 can be updated without reburning IC19), code
at 0x8000-0xAFFF (IC15 0x1C000, the end of the old demo song data, unused once the demo is gone), data after the
jump table (0xB020-0xBFFF).
Settings live in battery-backed RAM (0xF600-0xF62F, 0xF670-0xF69F, own magic word; the recorded arp sequence at
0xF650-0xF66F) and survive power-off.
"""
from mcs96_asm import Asm

MAGIC = 0x5a1c
S_MAGIC_V = 0x8a5f          # settings layout v9 (change it when the layout changes: old settings -> defaults)

# volatile state: registers (never used by the stock OS)
REG = dict(R_MAGIC=0x1a, LFSR=0x1c, TGT=0x1e, GLD=0x20, UDT=0x22, NP=0x24, LFOP=0x26, ARPT=0x28, AGT=0x2a,
           ASTP=0x2c, CLKAGE=0x2e, VCUT=0x30, LASTSLOT=0x32, NC=0x33, NW=0x34, CHI=0x35, UI=0x36, UNN=0x37,
           TDIV=0x38, SH=0x39, MCNT=0x3a, MCUR=0x3b, MVEL=0x3c, PF=0x3d, AN=0x3e, AH=0x3f,
           CLK=0x90, CLKS=0x91, WCB=0x92, MDC=0x94, MDP=0x96, MDW=0x98, MDL=0x9a, MDR=0x9c, SVM=0x9e, MDM=0x9f)
# per-partial tables, index r54 = partial * 2 (byte tables share a 64-byte block: even / odd bytes). A partial is
# either synth or PCM (TY bit 7), so synth-only and PCM-only tables share bytes: CB/WB, RB/OFS, LC/WS.
TAB = dict(PB=0xf500, GL=0xf540, CB=0xf580, WB=0xf580, LB=0xf581, RB=0xf5c0, OFS=0xf5c0, LC=0xf5c1, WS=0xf5c1,
           WT=0xf740, TY=0xf741, WI=0xf780)
# volatile RAM
VOL = dict(LASTN=0xf7c0, MSTK=0xf7c8, ABUF=0xf7d0, MNC=0xf7dc, MNP=0xf7de, MNW=0xf7e0, MNL=0xf7e2, MNR=0xf7e4,
           AT=0xf7e6, CCA=0xf7e7, CCB=0xf7e8, AD=0xf7e9, ACUR=0xf7ea, AV=0xf7eb, ALB=0xf7ec, ACLK=0xf7ed,
           AI=0xf7ee, AO=0xf7ef, TN=0xf7f2, TCK=0xf7f4, SCB=0xf7f6, LBUF=0xf7fa,     # 0xF7F0 = Info RAM test byte
           CIVP=0xf630, RTI=0xf632, RTT=0xf634, LCC=0xf636, LACC=0xf638, VPH=0xf63a, SLEN=0xf63c, MPAR=0xf63e,
           RTN=0xf63f, ARN=0xf640, AVL=0xf641, ECNT=0xf642, ASC=0xf643, HJ=0xf644, LARM=0xf645, LCNT=0xf646,
           LHC=0xf647, RECM=0xf648, RPOS=0xf649, LCUR=0xf64a, LNX=0xf64b, EPC=0xf64c, RRT=0xf64d, MON=0xf64e,
           MCH=0xf64f)
SEQ_DEFAULT = [0, 0x81, 12, 0, 0x80, 7, 10, 12, 0, 12, 0x80, 7, 3, 0x81, 5, 7]     # semitones, 0x80 rest, 0x81 tie
# persistent settings (battery RAM), with defaults, in blocks (start, end)
SETTINGS = [(0xf600, 0xf630, [
                ('S_MAGIC', 2, S_MAGIC_V), ('MIDX', 1, 0), ('DRIFTP', 1, 0), ('RCUT', 1, 0), ('RWAVE', 1, 0),
                ('CHORD', 1, 0), ('CHPART', 1, 0), ('WAVE', 8, 0), ('UNIV', 1, 0), ('UNID', 1, 20), ('UNIP', 1, 0),
                ('MONOP', 1, 0), ('LEGATO', 1, 0), ('GLTIME', 1, 0), ('GLPART', 1, 0), ('WSPAT', 1, 0),
                ('WSSPD', 1, 60), ('WSPART', 1, 0), ('WSUSER', 8, 0), ('MS', 4, 0), ('MD', 4, 0), ('MA', 4, 63),
                ('LFOR', 1, 40), ('MODP', 1, 0)]),
            (0xf670, 0xf6a0, [
                ('ARPM', 1, 0), ('ARPOCT', 1, 0), ('ARPRATE', 1, 3), ('ARPBPM', 1, 80), ('ARPGATE', 1, 50),
                ('ARPLATCH', 1, 0), ('ARPP', 1, 0), ('LRESO', 1, 0), ('LXOR', 1, 0),
                ('ARPPROB', 1, 100), ('RATCH', 1, 0), ('OJUMP', 1, 0), ('ACCENT', 1, 0), ('EUCK', 1, 3),
                ('EUCN', 1, 0), ('HUMT', 1, 0), ('HUMV', 1, 0), ('ARPOUT', 1, 0), ('VINT', 1, 0), ('VINTP', 1, 0),
                ('LFOSYNC', 1, 0), ('SCKEY', 1, 0), ('SCTYPE', 1, 0), ('LRLOW', 1, 0), ('LPXOR', 1, 0),
                ('LPPOS', 1, 0), ('LPART', 1, 0), ('SEQLEN', 1, len(SEQ_DEFAULT)), ('CLRN', 4, [7, 12, 0, 0]),
                ('MODOFF', 1, 0), ('LABOFF', 1, 0)]),          # v10: master switches, 0 = On (v9 RAM has 0 there)
            (0xf650, 0xf670, [
                ('SEQ', 32, [b + 64 if b < 0x80 else b for b in SEQ_DEFAULT] + [0x80] * (32 - len(SEQ_DEFAULT)))])]


def _settings():
    addr, img = {}, bytearray()
    for start, end, items in SETTINGS:
        at = start
        for name, n, dflt in items:
            addr[name] = at
            b = dflt.to_bytes(2, 'little') if n == 2 else bytes(dflt) if isinstance(dflt, list) else bytes([dflt]) * n
            assert len(b) == n, name
            img += b
            at += n
        assert at <= end, hex(at)
        img += bytes(end - at)
    return addr, bytes(img)


SET, SET_DEFAULTS = _settings()
RAM = dict(**REG, **TAB, **VOL, **SET)
IC15_ENTRY = dict(E_BANNER=0xb002, E_UI=0xb005, E_NON=0xb008, E_NOFF=0xb00b, E_WAVE=0xb00e, E_PART=0xb011,
                  E_TICK=0xb014, E_AT=0xb017, E_CC=0xb01a)
STOCK = dict(NOTE_ON=0x24fc, NOTE_OFF=0x245d, ALL_OFF=0x3de2, POP_STATE=0x5391, REDRAW=0x53cb, API_LCD=0x208a,
             PART=0xf6cd, LCDBUF=0xf6ab, MAIN_PASS=0x29f5, RT_STOP=0x1e88)
WAVE_CC, MOD_CC = 70, (16, 17)
HOOK_PART = 0x3bb4          # st zero,0xf100[r54] (5 bytes), then ret at 0x3bb9: end of per-partial note-on setup
TICK_MS = 1562 * 8 / 6000   # software timer 1 period rc2 = 0x061A timer1 counts (8 states of 1/6 us) = ~2.08 ms
CODE_ORG, CODE_END = 0x8000, 0xb000      # IC15 0x1C000-0x1EFFF (old demo song data)


def build_ic19():
    """-> (patches, labels). Needs the dead demo code areas 0x7F57-0x7FFF, 0x3FB7-0x401B and the demo sequencer
    0x2371-0x241B (only reached while the demo plays)."""
    syms = dict(MAGIC=MAGIC, **RAM, **IC15_ENTRY, **STOCK)
    A = Asm(0x7f57, syms).src('''
    ; enter: after `push rb6`. Maps IC15 page 0x27, Z = 1 when the magic word is there. Keeps all registers.
    enter:  ldb   rb7, #0x27
            stb   rb7, 0x0100
            push  r70
            ld    r70, 0xb000
            cmp   r70, #MAGIC
            pop   r70                   ; (pop keeps the flags)
            ret
    ; call19: IC15 code calls the IC19 routine at TGT; the page is put back to 0x27 afterwards
    call19: push  rb6
            lcall c19go
            pop   rb6
            stb   rb7, 0x0100
            ret
    c19go:  push  TGT
            ret
    ; rd20: r70 = word at [r74] in page 0x20 (IC15 0x0000-0x3FFF: wave table), back to page 0x27
    rd20:   ldb   rb7, #0x20
            stb   rb7, 0x0100
            ld    r70, [r74]
            ldb   rb7, #0x27
            stb   rb7, 0x0100
            ret
    h_non:  push  rb6
            lcall enter
            jne   hn_f
            lcall E_NON
    lv:     pop   rb6
            stb   rb7, 0x0100
            ret
    hn_f:   pop   rb6
            stb   rb7, 0x0100
            ljmp  NOTE_ON
    h_noff: push  rb6
            lcall enter
            jne   hf_f
            lcall E_NOFF
            sjmp  lv
    hf_f:   pop   rb6
            stb   rb7, 0x0100
            ljmp  NOTE_OFF
    h_wave: push  rb6
            lcall enter
            jne   lv
            lcall E_WAVE
            sjmp  lv
    h_part: st    zero, 0xf100[r54]     ; the instruction the hook replaced
            push  rb6
            lcall enter
            jne   lv
            lcall E_PART
            sjmp  lv
    ''')
    a = A.assemble()
    assert A.org + len(a) <= 0x8000, hex(A.org + len(a))
    B = Asm(0x3fb7, dict(syms, **A.labels)).src('''
    ; Rosetta menu: raw UI state handler (rb4), r70 = key, 0xFF = draw
    ros_ui: cmpb  r70, #0xf0
            jne   ru1
            ret
    ru1:    push  rb6
            lcall enter
            jne   ru_f
            lcall E_UI                  ; -> r70 = 1: leave the menu
            sjmp  ru_b
    ru_f:   ldb   r70, #1
    ru_b:   pop   rb6
            stb   rb7, 0x0100
            cmpb  r70, #1
            je    ru_x
            ret
    ru_x:   lcall POP_STATE
            ljmp  REDRAW
    ''')
    b = B.assemble()
    assert B.org + len(b) <= 0x401c, hex(B.org + len(b))
    C = Asm(0x2371, dict(syms, **A.labels)).src('''
    ; main loop, no MIDI event pending: rc4 counts software-timer-1 ticks (~2 ms; the demo player used them)
    h_tick: cmpb  rc4, zero
            je    ht_x
            di
            ldb   r70, rc4              ; ticks since the last call
            clrb  rc4
            ei
            push  rb6
            lcall enter
            jne   ht_n
            lcall E_TICK
    ht_n:   pop   rb6
            stb   rb7, 0x0100
    ht_x:   ljmp  MAIN_PASS
    ; aftertouch (An, Dn) and CC16/CC17 in the MIDI per-part loop
    h_at:   push  rb6
            lcall enter
            jne   hc_n
            lcall E_AT
    hc_n:   pop   rb6
            stb   rb7, 0x0100
            ret
    h_cc:   push  rb6
            lcall enter
            jne   hc_n
            lcall E_CC
            sjmp  hc_n
    ; serial interrupt, real-time byte 0xF8-0xFD in rf8 (replaces cmpb rf8,#0xfc / jne at 0x1E83)
    h_rt:   cmpb  rf8, #0xfc
            jne   hr1
            ljmp  RT_STOP
    hr1:    cmpb  rf8, #0xf8
            jne   hr2
            incb  CLK                   ; MIDI clock
    hr2:    cmpb  rf8, #0xfa
            jne   hr3
            ldb   CLKS, #1              ; MIDI start
    hr3:    popf
            ret
    ''')
    c = C.assemble()
    assert C.org + len(c) <= 0x241c, hex(C.org + len(c))
    lab = dict(A.labels, **B.labels, **C.labels)
    lj = lambda at, to: bytes([0xe7]) + ((to - (at + 3)) & 0xffff).to_bytes(2, 'little')
    w = lambda v: v.to_bytes(2, 'little')
    patches = [(0x7f57, a), (0x3fb7, b), (0x2371, c),
               (HOOK_PART, lj(HOOK_PART, lab['h_part']) + b'\xfd\xfd'),
               (0x241c, w(lab['h_noff'])), (0x241e, w(lab['h_non'])),
               (0x2420, w(lab['h_at'])), (0x2426, w(lab['h_at'])),
               (0x3bce + 2 * WAVE_CC, w(lab['h_wave'])),
               (0x3bce + 2 * MOD_CC[0], w(lab['h_cc'])), (0x3bce + 2 * MOD_CC[1], w(lab['h_cc'])),
               (0x22b9, lj(0x22b9, lab['h_tick'])),
               (0x1e83, lj(0x1e83, lab['h_rt']) + b'\xfd\xfd')]
    return patches, lab


CHORDS = [('Off', []), ('Octave', [12]), ('Fifth', [7]), ('5th+Oct', [7, 12]), ('Major', [4, 7]),
          ('Minor', [3, 7]), ('Sus4', [5, 7]), ('Major7', [4, 7, 11]), ('Minor7', [3, 7, 10]),
          ('Dom7', [4, 7, 10]), ('Minor9', [3, 7, 10, 14]), ('Dim', [3, 6]),
          ('Learned', None), ('Scale', None), ('Scale 7', None)]       # learned (CLRN), diatonic triad / 7th
NFIX = 12                   # chords with fixed intervals
KEYS = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
SCALES = [('Major', [0, 2, 4, 5, 7, 9, 11]), ('Minor', [0, 2, 3, 5, 7, 8, 10]), ('Dorian', [0, 2, 3, 5, 7, 9, 10]),
          ('Phrygian', [0, 1, 3, 5, 7, 8, 10]), ('Lydian', [0, 2, 4, 6, 7, 9, 11]),
          ('Mixolyd', [0, 2, 4, 5, 7, 9, 10]), ('Locrian', [0, 1, 3, 5, 6, 8, 10]),
          ('HarmMin', [0, 2, 3, 5, 7, 8, 11]), ('MelMin', [0, 2, 3, 5, 7, 9, 11])]
# wave sequences: name, steps (wave offsets), mode (0 loop, 1 once then hold, 2 random 0-31 each step, 3 user)
WSEQS = [('Off', [0], 0), ('Up 4', [0, 1, 2, 3], 0), ('Up 8', list(range(8)), 0), ('Down 4', [3, 2, 1, 0], 0),
         ('Ping 8', [0, 1, 2, 3, 4, 5, 6, 7, 6, 5, 4, 3, 2, 1], 0), ('Octo', [0, 8, 16, 24, 32, 40, 48, 56], 0),
         ('Strobe', [0, 16], 0), ('Once 4', [0, 1, 2, 3], 1), ('Random', [0], 2), ('User', [0] * 8, 3)]
MOD_SRC = ['Off', 'ModWheel', 'AftTouch', 'Velocity', 'Key', 'LFO', 'S&H', 'CC16', 'CC17']
MOD_DST = ['Cutoff', 'Pitch', 'Wave', 'Level', 'Reso']
ARP_MODES = ['Off', 'Up', 'Down', 'Up+Down', 'Random', 'Played', 'Seq']
ARP_RATES = [('1/4', 1, 24), ('1/8', 2, 12), ('1/8T', 3, 8), ('1/16', 4, 6), ('1/16T', 6, 4), ('1/32', 8, 3)]
ARP_OUT = ['Off', 'On', 'Only']
RATCHETS = ['Off', '2x', '3x', '4x', 'Random']
ACCENTS = ['Off', 'Every 2', 'Every 3', 'Every 4', 'Random']
LFO_SYNC = [('Off', 0), ('4 Bars', 384), ('2 Bars', 192), ('1 Bar', 96), ('1/2', 48), ('1/4', 24), ('1/8', 12),
            ('1/8T', 8), ('1/16', 6), ('1/16T', 4)]          # MIDI clocks (24 per beat) per LFO cycle
LAB_RESO = ['Off'] + [str(i) for i in range(8)]
OFFON = ['Off', 'On']
ONOFF = ['On', 'Off']
REC_MODES = ['Off ', 'Step', 'Live', 'Rec ']

# kinds: 0 number, 1 named list, 2 All/P1-8, 3 per-part number (live), 4 info, 5 Off/P1-8, 6 signed (63 = 0),
# 7 P1-8, 8 number with 0 = Off, 9 sequence record, 10 chord learn, 11 folder (submenu only)
K_SUB, K_SUBP, K_SECTION, K_ALLOFF = 0x10, 0x20, 0x40, 0x80     # in a submenu, opens a submenu (Edit), Edit stop,
                                                                # all notes off after a change


def _items():
    """-> list of (name, setting, max, kind, min, display offset, names). A K_SUBP item is followed by its
    K_SUB items: Edit opens them, Group +/- moves inside, Exit / Edit goes back."""
    it = []
    add = lambda name, s, mx, kind, mn=0, dofs=0, names=None: it.append(
        ((name.ljust(15)[:15] + '>') if kind & K_SUBP else name, s, mx, kind, mn, dofs, names))
    S = K_SUB
    add('Wave Scan (CC70)', 'WAVE', 127, 3 | K_SECTION)
    add('Wave Seq', 'WSPAT', len(WSEQS) - 1, 1 | K_SUBP, names=[n for n, _, _ in WSEQS])
    add('WSeq Speed', 'WSSPD', 99, 0 | S)
    add('WSeq Part', 'WSPART', 8, 2 | S)
    for i in range(8):
        add('WSeq User %d' % (i + 1), ('WSUSER', i), 127, 0 | S)
    add('Random', 'MIDX', 0, 11 | K_SUBP)
    add('Drift Pitch', 'DRIFTP', 31, 0 | S)
    add('Random Wave', 'RWAVE', 127, 0 | S)
    add('Random Cutoff', 'RCUT', 100, 0 | S)
    add('Vintage', 'VINT', 99, 0 | K_SUBP)
    add('Vintage Part', 'VINTP', 8, 2 | S | K_ALLOFF)
    add('Glide Time', 'GLTIME', 99, 0 | K_SECTION | K_SUBP | K_ALLOFF)
    add('Glide Part', 'GLPART', 8, 2 | S | K_ALLOFF)
    add('Mono Part', 'MONOP', 8, 5 | K_SUBP | K_ALLOFF)
    add('Legato', 'LEGATO', 1, 1 | S | K_ALLOFF, names=OFFON)
    add('Unison Voices', 'UNIV', 3, 0 | K_SECTION | K_SUBP | K_ALLOFF, dofs=1)
    add('Unison Detune', 'UNID', 99, 0 | S)
    add('Unison Part', 'UNIP', 8, 2 | S | K_ALLOFF)
    add('Chord', 'CHORD', len(CHORDS) - 1, 1 | K_SUBP | K_ALLOFF, names=[n for n, _ in CHORDS])
    add('Chord Part', 'CHPART', 8, 2 | S | K_ALLOFF)
    add('Chord Learn', 'MIDX', 0, 10 | S)
    add('Scale Key', 'SCKEY', len(KEYS) - 1, 1 | S | K_ALLOFF, names=KEYS)
    add('Scale Type', 'SCTYPE', len(SCALES) - 1, 1 | S | K_ALLOFF, names=[n for n, _ in SCALES])
    add('Mod Matrix', 'MODOFF', 1, 1 | K_SECTION | K_SUBP, names=ONOFF)
    for i in range(4):
        add('Mod%d Source' % (i + 1), ('MS', i), len(MOD_SRC) - 1, 1 | S, names=MOD_SRC)
        add('Mod%d Dest' % (i + 1), ('MD', i), len(MOD_DST) - 1, 1 | S, names=MOD_DST)
        add('Mod%d Amount' % (i + 1), ('MA', i), 126, 6 | S)
    add('LFO Rate', 'LFOR', 99, 0 | S)
    add('LFO Sync', 'LFOSYNC', len(LFO_SYNC) - 1, 1 | S, names=[n for n, _ in LFO_SYNC])
    add('Mod Part', 'MODP', 8, 2 | S)
    add('Arp Mode', 'ARPM', len(ARP_MODES) - 1, 1 | K_SECTION | K_SUBP | K_ALLOFF, names=ARP_MODES)
    add('Arp Octaves', 'ARPOCT', 3, 0 | S, dofs=1)
    add('Arp Rate', 'ARPRATE', len(ARP_RATES) - 1, 1 | S, names=[n for n, _, _ in ARP_RATES])
    add('Arp Tempo (BPM)', 'ARPBPM', 200, 0 | S, dofs=40)
    add('Arp Gate %', 'ARPGATE', 99, 0 | S, mn=5)
    add('Arp Latch', 'ARPLATCH', 1, 1 | S | K_ALLOFF, names=OFFON)
    add('Arp Part', 'ARPP', 7, 7 | S | K_ALLOFF)
    add('Arp MIDI Out', 'ARPOUT', len(ARP_OUT) - 1, 1 | S | K_ALLOFF, names=ARP_OUT)
    add('Seq Record', 'SEQLEN', 0, 9 | S)
    add('Seq Length', 'SEQLEN', 32, 0 | S, mn=1)
    add('Chance %', 'ARPPROB', 100, 0 | S)
    add('Ratchet', 'RATCH', len(RATCHETS) - 1, 1 | S, names=RATCHETS)
    add('Octave Jump %', 'OJUMP', 100, 0 | S)
    add('Accent', 'ACCENT', len(ACCENTS) - 1, 1 | S, names=ACCENTS)
    add('Euclid Hits', 'EUCK', 16, 0 | S, mn=1)
    add('Euclid Steps', 'EUCN', 16, 8 | S)
    add('Humanize Time', 'HUMT', 99, 0 | S)
    add('Humanize Vel', 'HUMV', 99, 0 | S)
    add('Lab', 'LABOFF', 1, 1 | K_SECTION | K_SUBP, names=ONOFF)
    add('Lab Reso High', 'LRESO', len(LAB_RESO) - 1, 1 | S, names=LAB_RESO)
    add('Lab Reso Low', 'LRLOW', 32, 8 | S, dofs=255)
    add('Lab Ctrl XOR', 'LXOR', 255, 0 | S)
    add('Lab PCM XOR', 'LPXOR', 255, 0 | S)
    add('Lab PCM Pos', 'LPPOS', 255, 0 | S)
    add('Lab Part', 'LPART', 8, 2 | S)
    add('Info', 'MIDX', 0, 4 | K_SECTION)
    return it


ITEMS = _items()


def _tables():
    """lookup tables: LFO phase step per pass, glide coefficient, wave-sequence step length"""
    pass_ms = 4 * TICK_MS
    lfo = [max(1, round(0.05 * 400 ** (r / 99) * 65536 * pass_ms / 1000)) for r in range(100)]     # 0.05-20 Hz
    glk = [0] + [max(1, min(255, round(256 * (1 - 0.02 ** (pass_ms / (15 + 4000 * (t / 99) ** 2)))))) for t in range(1, 100)]
    spd = [max(1, min(255, round((1200 * 0.008 ** (s / 99)) / pass_ms))) for s in range(100)]     # 1.2 s .. 10 ms
    return lfo, glk, spd


def build_ic15(ic19_labels, banner=(' ROSETTA OS v10 ', ' D-110  by JSW  ')):
    """-> ([(cpu address, bytes), ...], Asm of the main code). Page 0x27: CPU 0x8000 = IC15 0x1C000."""
    syms = dict(MAGIC=MAGIC, S_MAGIC_V=S_MAGIC_V, **RAM, **STOCK, CALL19=ic19_labels['call19'],
                RD20=ic19_labels['rd20'], NITEMS=len(ITEMS), TX_BYTE=0x1d8d, VOL_A=0xf630, VOL_B=0xf650,
                NCHORDS=len(CHORDS), NFIX=NFIX)
    C = Asm(CODE_ORG, syms).src(r'''
    ; ===================================================================== state
    ; init: called on every entry. Volatile state (registers, tables) after power-on, settings once.
    ; Keeps all registers.
    init:   cmp   R_MAGIC, #0xa75a
            je! in_s
            push  r70
            push  r72
            push  r74
            ld    r70, #LFSR
    iv1:    stb   zero, [r70]+
            cmp   r70, #0x40
            jne   iv1
            ld    r70, #0x90
    iv2:    stb   zero, [r70]+
            cmp   r70, #0xa0
            jne   iv2
            ld    r72, #0xf500
            ld    r74, #0xf600
            lcall wclr
            ld    r72, #VOL_A
            ld    r74, #VOL_B
            lcall wclr
            ld    r72, #0xf740
            ld    r74, #0xf800
            lcall wclr
            ld    r70, #0xffff
            st    r70, LASTN
            st    r70, LASTN+2
            st    r70, LASTN+4
            st    r70, LASTN+6
            stb   r70, MCUR
            stb   r70, ACUR
            stb   r70, LASTSLOT
            stb   r70, MPAR
            stb   r70, MON
            stb   r70, LCUR
            stb   r70, LNX
            ld    r70, #0xace1
            st    r70, LFSR
            ld    r70, #0x7fff
            st    r70, CLKAGE           ; no MIDI clock yet
            ld    r70, #0xa75a
            st    r70, R_MAGIC
            pop   r74
            pop   r72
            pop   r70
    in_s:   push  r70
            ld    r70, S_MAGIC
            cmp   r70, #S_MAGIC_V
            pop   r70                   ; (pop keeps the flags)
            je    in_x
            push  r70
            push  r72
            push  r74
            push  r76
            ld    r70, #sdef            ; settings -> defaults
            ld    r76, #sblk
    id0:    ld    r72, [r76]+           ; block start, end (0 = done)
            cmp   r72, zero
            je    id2
    id1:    ldb   r74, [r70]+
            stb   r74, [r72]+
            cmp   r72, [r76]
            jne   id1
            add   r76, #2
            sjmp  id0
    id2:    pop   r76
            pop   r74
            pop   r72
            pop   r70
    in_x:   ret
    wclr:   st    zero, [r72]+
            cmp   r72, r74
            jne   wclr
            ret

    banner: lcall init
            ld    r78, #bantxt
            lcall API_LCD
            ret

    ; ---- random: 16-bit Galois LFSR, 8 steps per call -> r7e:r7f (uses r7d)
    rnd:    ld    r7e, LFSR
            ldb   r7d, #8
    rn1:    shr   r7e, #1
            jnc   rn2
            xor   r7e, #0xb400
    rn2:    djnz  r7d, rn1
            cmp   r7e, zero
            jne   rn3
            ld    r7e, timer1
            orb   r7e, #1
    rn3:    st    r7e, LFSR
            ret

    ; smul: r72 = signed (r74 * r70) >> r71 (r74 signed byte, r70 amount 0-255)
    smul:   clrb  r79
            jbc   r74, 7, sm1
            negb  r74
            incb  r79
    sm1:    mulub r72, r74, r70
            shr   r72, r71
            jbc   r79, 0, sm2
            neg   r72
    sm2:    ret

    ; pmul: r74 = r72 (signed semitones) * 0x155 pitch units, clamped to +-0x4000. Uses r76-r7b.
    pmul:   ld    r76, r72
            jbc   r77, 7, pm1
            neg   r76
    pm1:    mulu  r78, r76, #0x155
            cmp   r78, #0x4000
            jnh   pm2
            ld    r78, #0x4000
    pm2:    ld    r74, r78
            jbc   r73, 7, pm3
            neg   r74
    pm3:    ret

    ; padd: r72 = r72 (pitch 0..0xE800) + r70 (signed), clamped to 0..0xE800
    padd:   jbs   r71, 7, pd_n
            add   r72, r70
            jc    pd_m
            cmp   r72, #0xe800
            jnh   pd_x
    pd_m:   ld    r72, #0xe800
    pd_x:   ret
    pd_n:   add   r72, r70
            jc    pd_x                  ; no borrow
            clr   r72
            ret

    ; clampw: r72 (signed word) clamped to 0..r74
    clampw: jbc   r73, 7, cw1
            clr   r72
            ret
    cw1:    cmp   r72, r74
            jnh   cw2
            ld    r72, r74
    cw2:    ret

    ; glclamp: r70 (signed word) clamped to +-0x4000
    glclamp: jbs  r71, 7, gc_n
            cmp   r70, #0x4000
            jnh   gc_x
            ld    r70, #0x4000
            ret
    gc_n:   cmp   r70, #0xc000
            jc    gc_x
            ld    r70, #0xc000
    gc_x:   ret

    ; scope: r70 = setting (0 All, 1-8 part), r50 part*16 -> Z = 1 when the part is in scope. scope1: 0 = Off.
    ; Uses r76.
    scope1: cmpb  r70, zero
            jne   sc_p
            cmpb  r70, #1               ; Z = 0
            ret
    scope:  cmpb  r70, zero
            je    sc_x
    sc_p:   ld    r76, r50
            shr   r76, #4
            incb  r76
            cmpb  r70, r76
    sc_x:   ret

    jmp76:  br    [r76]

    ; ===================================================================== mod matrix
    ; modv: r72 = r74 (source, signed word -127..127) * (r70 - 63) / 64. Uses r76, r79.
    modv:   subb  r70, #63
            clrb  r79
            jbc   r70, 7, mv1
            negb  r70
            incb  r79
    mv1:    ld    r76, r74
            jbc   r77, 7, mv2
            neg   r76
            xorb  r79, #1
    mv2:    mulub r72, r76, r70
            shr   r72, #6
            jbc   r79, 0, mv3
            neg   r72
    mv3:    ret

    ; modsum: r7c = 0: continuous sources (wheel, aftertouch, LFO, S&H, CC), 1: note sources (velocity r46,
    ; key r45). -> MDC cutoff, MDP pitch (x16), MDW wave (/2), MDL level (/2), MDR reso (/8), signed words.
    ; Part r50. Uses r70-r7b.
    modsum: clr   MDC
            clr   MDP
            clr   MDW
            clr   MDL
            clr   MDR
            ldb   r70, MODOFF           ; Mod Matrix Off: nothing
            cmpb  r70, zero
            je    ms_on
            ret
    ms_on:  clr   r7a
    ms_l:   ldbze r70, MS[r7a]
            cmpb  r70, zero
            je    ms_n
            cmpb  r70, #3
            je    ms_nt
            cmpb  r70, #4
            je    ms_nt
            cmpb  r7c, zero
            jne   ms_n
            sjmp  ms_g
    ms_nt:  cmpb  r7c, zero
            je    ms_n
    ms_g:   shl   r70, #1
            ld    r76, srctab[r70]
            lcall jmp76                 ; -> r74
            ldb   r70, MA[r7a]
            lcall modv
            ldbze r70, MD[r7a]
            shl   r70, #1
            ld    r76, dsttab[r70]
            lcall jmp76
    ms_n:   inc   r7a
            cmp   r7a, #4
            jne   ms_l
            ret
    s_mw:   ldbze r74, 0xf287[r50]
            ret
    s_at:   ldbze r74, AT
            ret
    s_vel:  ldbze r74, r46
            ret
    s_key:  ldbze r74, r45
            sub   r74, #60
            shl   r74, #1
            ld    r72, r74
            add   r72, #127
            ld    r74, #254
            lcall clampw
            sub   r72, #127
            ld    r74, r72
            ret
    s_lfo:  ldbze r74, LFOP+1           ; triangle -127..127
            jbc   r74, 7, sl1
            xorb  r74, #0xff
    sl1:    shl   r74, #1
            sub   r74, #127
            ret
    s_sh:   ldbse r74, SH
            ret
    s_cca:  ldbze r74, CCA
            ret
    s_ccb:  ldbze r74, CCB
            ret
    d_cut:  add   MDC, r72
            ret
    d_pit:  shl   r72, #4
            add   MDP, r72
            ret
    d_wav:  shra  r72, #1
            add   MDW, r72
            ret
    d_lev:  shra  r72, #1
            add   MDL, r72
            ret
    d_res:  shra  r72, #3
            add   MDR, r72
            ret

    ; mdmask: MDM bit d = some continuous slot has dest d, bit 7 = any continuous slot
    mdmask: clrb  MDM
            ldb   r70, MODOFF
            cmpb  r70, zero
            jne   mm_x
            clr   r7a
    mm_l:   ldb   r70, MS[r7a]
            cmpb  r70, zero
            je    mm_n
            cmpb  r70, #3
            je    mm_n
            cmpb  r70, #4
            je    mm_n
            ldb   r71, MD[r7a]
            ldb   r72, #1
            shlb  r72, r71
            orb   MDM, r72
            orb   MDM, #0x80
    mm_n:   inc   r7a
            cmp   r7a, #4
            jne   mm_l
    mm_x:   ret

    ; ===================================================================== waves
    ; waddr: r74 = wave byte, r7d = PCM bank -> r74 = address of its 4-byte IC15 wave table entry (page 0x20)
    waddr:  andb  r74, #0x7f
            ldb   r75, r7d
            shlb  r74, #1
            shl   r74, #1
            add   r74, #0x8900
            ret

    ; wset: PCM partial r54 plays wave (block wave + r7c) & 0x7f; the pitch (PB and 0xEF40) moves by the
    ; difference of the two waves' pitch words so it stays in tune. OFS[p] = offset now applied. Uses r70-r7d.
    wset:   ld    r78, 0xee80[r54]
            ldb   r7a, 0x05[r78]        ; wave number in the timbre
            ldb   r7d, 0x04[r78]
            shrb  r7d, #1
            andb  r7d, #0x03            ; bank, as at 0x36ce
            ldb   r74, OFS[r54]
            addb  r74, r7a
            lcall waddr
            add   r74, #2
            lcall RD20
            ld    r76, r70              ; old pitch word
            stb   r7c, OFS[r54]
            ldb   r74, r7c
            addb  r74, r7a
            lcall waddr
            lcall RD20
            ld    r78, r70              ; pos, len
            add   r74, #2
            lcall RD20
            sub   r70, r76
            ld    r76, r70
            ld    r72, PB[r54]
            lcall padd
            st    r72, PB[r54]
            ld    r70, r76
            ld    r72, 0xef40[r54]
            lcall padd
            st    r72, 0xef40[r54]
            orb   r79, #0x08            ; as 0x36ed
            stb   r79, 0xef81[r54]
            ldb   r70, 0xef80[r54]      ; LA32 takes 0x0D00/0x0D01 as a pair
            stb   r70, 0x0d00[r54]
            stb   r79, 0x0d01[r54]
            lcall lpos
            stb   r78, 0xf1c0[r54]
            stb   r78, 0x0c41[r54]
            ret

    ; lscope: Z = 1 when Lab is On and part r50 is in Lab Part. Uses r70, r76.
    lscope: ldb   r70, LABOFF
            cmpb  r70, zero
            jne   lb_x
            ldb   r70, LPART
            ljmp  scope
    lb_x:   ret

    ; lpos: r78 ^= Lab PCM Pos when part r50 is in the lab scope. Uses r70, r76.
    lpos:   ldb   r70, LPPOS
            cmpb  r70, zero
            je    lp_x
            lcall lscope
            jne   lp_x
            xorb  r78, LPPOS
    lp_x:   ret

    ; wseqv: r70 = wave sequence offset of partial r54 now (0 when off or the part is not in scope). Uses r76.
    wseqv:  ldb   r70, WSPAT
            cmpb  r70, zero
            je    wv_x
            ldb   r70, WSPART
            lcall scope
            jne   wv_0
            ldb   r70, WS[r54]
            ret
    wv_0:   clrb  r70
    wv_x:   ret

    ; wtarget: r7c = wave offset partial r54 of part r50 should play (scan + note + sequence). Uses r70, r76, r78.
    wtarget: ld   r78, r50
            shr   r78, #4
            ldb   r7c, WAVE[r78]
            addb  r7c, WB[r54]
            lcall wseqv
            addb  r7c, r70
            andb  r7c, #0x7f
            ret

    ; wstep: next wave sequence step of partial r54 (WSPAT != 0): WT reloaded, WI/WS advanced. Uses r70-r7e.
    wstep:  ldbze r70, WSSPD
            ldb   r70, spdtab[r70]
            stb   r70, WT[r54]
            ldbze r76, WSPAT
            shl   r76, #2
            ld    r78, wsp[r76]         ; steps
            ldb   r7a, wsp+2[r76]       ; length
            ldb   r7b, wsp+3[r76]       ; mode
            ldb   r70, WI[r54]
            incb  r70
            cmpb  r70, r7a
            jnc   ws_in
            clrb  r70
            cmpb  r7b, #1
            jne   ws_in
            ldb   r70, r7a              ; once: stay on the last step
            decb  r70
    ws_in:  stb   r70, WI[r54]
            cmpb  r7b, #2
            je    ws_r
            ldbze r76, r70
            add   r76, r78
            ldb   r70, [r76]
            stb   r70, WS[r54]
            ret
    ws_r:   lcall rnd
            andb  r7e, #31
            stb   r7e, WS[r54]
            ret

    ; walk: call [WCB] for every partial of part r50 (r52 slot, r54 partial*2; the callback keeps r50-r54)
    walk:   ldbze r52, 0xf285[r50]
    wk_n:   cmpb  r52, #0xff
            je    wk_d
            ldbze r54, 0xf440[r52]
    wk_p:   cmpb  r54, #0xff
            je    wk_nn
            lcall wk_cb
            ldbze r54, 0xee40[r54]
            sjmp  wk_p
    wk_nn:  ldbze r52, 0xf3c0[r52]
            sjmp  wk_n
    wk_d:   ret
    wk_cb:  br    [WCB]

    ; wave_apply: PCM partials of part r50 play their target wave now (CC70 / menu)
    wave_apply:
            ld    r70, #wa_cb
            st    r70, WCB
            ldb   SVM, int_mask
            andb  int_mask, #0x7f
            lcall walk
            ldb   int_mask, SVM
            ret
    wa_cb:  ldb   r70, TY[r54]
            jbc   r70, 7, wa_x          ; synth partial: no wave
            lcall wtarget
            cmpb  r7c, OFS[r54]
            je    wa_x
            lcall wset
    wa_x:   ret

    ; ---- CC70 (MIDI per-part loop: r46 value, r50 part*16; keep r42, r44-r46, r50)
    cc_wave: lcall init
            cmp   r50, #0x0080
            jc    cw_x
            ldb   rc7, #0x08            ; MIDI LED
            ld    r7e, r50
            shr   r7e, #4
            stb   r46, WAVE[r7e]
            lcall wave_apply
    cw_x:   ret

    ; ---- CC16 / CC17, aftertouch: mod matrix sources
    cc_in:  lcall init
            cmpb  r45, #16
            jne   ci1
            stb   r46, CCA
            ret
    ci1:    stb   r46, CCB
            ret
    at_in:  lcall init
            stb   r46, AT
            ret

    ; wreso: synth partial r54 gets resonance r70 (0-30), as 0x3781, + Lab Reso High / Low when part r50 is in the
    ; lab scope; 0x0D00/0x0D01 written. Uses r70, r71, r76.
    wreso:  incb  r70
            ldb   r71, r70
            shlb  r71, #3
            andb  r71, #0xe0
            orb   r71, r70
            lcall lscope
            jne   wr2
            ldb   r70, LRESO
            cmpb  r70, zero
            je    wr1
            decb  r70
            shlb  r70, #5
            andb  r71, #0x1f
            orb   r71, r70
    wr1:    ldb   r70, LRLOW
            cmpb  r70, zero
            je    wr2
            decb  r70
            andb  r71, #0xe0
            orb   r71, r70
    wr2:    stb   r71, 0xef81[r54]
            ldb   r70, 0xef80[r54]
            stb   r70, 0x0d00[r54]
            stb   r71, 0x0d01[r54]
            ret

    ; ===================================================================== note-on per partial
    ; newnote: per-note random offsets and note mods (same for all partials of a note: ring pairs stay in tune)
    newnote: lcall rnd
            ldb   r74, r7e
            ldb   r70, DRIFTP
            ldb   r71, #5               ; +-31 * 128 / 32 = +-124 pitch units (~ +-36 cents at 31)
            lcall smul
            st    r72, NP
            ldb   r74, r7f
            ldb   r70, RCUT
            ldb   r71, #7               ; +-RCUT cutoff steps
            lcall smul
            stb   r72, NC
            lcall rnd
            ldb   r70, RWAVE
            incb  r70
            mulub r72, r7e, r70
            stb   r73, NW               ; 0..RWAVE
            ldb   r70, MODP
            lcall scope
            jne   nn_0
            ldb   r7c, #1
            lcall modsum
            sjmp  nn_1
    nn_0:   clr   MDC
            clr   MDP
            clr   MDW
            clr   MDL
            clr   MDR
    nn_1:   ld    r70, MDC
            st    r70, MNC
            ld    r70, MDP
            st    r70, MNP
            ld    r70, MDW
            st    r70, MNW
            ld    r70, MDL
            st    r70, MNL
            ld    r70, MDR
            st    r70, MNR
            ret

    ; ---- end of per-partial note-on setup: r54 partial*2, r56 block, r50 part*16, r52 note slot.
    ; Free: r70-r79 only (r7a-r7f saved here); LA32 interrupt already masked; LA32 pitch not written yet.
    partial: cmp  r50, #0x0080
            jnc   pt_go
            ret                         ; rhythm part: untouched (its block may be in another page)
    pt_go:  lcall init
            push  r7a
            push  r7c
            push  r7e
            cmpb  r52, LASTSLOT
            je    pt_have
            stb   r52, LASTSLOT
            lcall newnote
    pt_have: ld   r70, NP               ; pitch base: drift + unison detune + note mods
            add   r70, UDT
            add   r70, MNP
            ld    r72, 0xef40[r54]
            lcall padd
            st    r72, PB[r54]
            ld    r70, GLD              ; glide: start from the previous note
            st    r70, GL[r54]
            lcall padd
            push  r72
            lcall vint                  ; vintage: this note's wander now
            pop   r72
            lcall padd
            st    r72, 0xef40[r54]
            ldb   r70, 0xef80[r54]
            andb  r70, #0x80
            stb   r70, TY[r54]          ; partial type (bit 7 = PCM), before any Lab bit flips
            jbs!  r70, 7, pt_pcm
            ldbze r72, 0xf1c0[r54]      ; synth: random cutoff + note mods
            ldbse r70, NC
            add   r72, r70
            add   r72, MNC
            ld    r74, #0xff
            lcall clampw
            stb   r72, 0xf1c0[r54]
            stb   r72, 0x0c41[r54]
            stb   r72, CB[r54]
            stb   r72, LC[r54]
            lcall lscope                ; Lab: flip control bits of synth partials
            jne   pt_r
            ldb   r70, LXOR
            xorb  r70, 0xef80[r54]
            stb   r70, 0xef80[r54]
    pt_r:   ldbze r72, 0xef81[r54]      ; resonance base
            andb  r72, #0x1f
            dec   r72
            add   r72, MNR
            ld    r74, #30
            lcall clampw
            stb   r72, RB[r54]
            ldb   r70, r72
            lcall wreso
            sjmp  pt_lev
    pt_pcm: ldb   r70, NW               ; PCM: random wave + note mods, wave sequence start
            addb  r70, MNW
            stb   r70, WB[r54]
            stb   zero, OFS[r54]        ; the note-on just set the timbre's own wave
            stb   zero, WS[r54]
            ldb   r70, WSPAT
            cmpb  r70, zero
            je    pt_w
            ldb   r70, #0xff
            stb   r70, WI[r54]
            lcall wstep
    pt_w:   lcall wtarget
            cmpb  r7c, zero
            je    pt_lab
            lcall wset                  ; (Lab PCM Pos applied there)
            sjmp  pt_lx
    pt_lab: ldb   r78, 0xf1c0[r54]      ; same wave: Lab PCM Pos on the note-on position
            lcall lpos
            stb   r78, 0xf1c0[r54]
            stb   r78, 0x0c41[r54]
    pt_lx:  lcall lscope                ; Lab PCM XOR: control byte of PCM partials
            jne   pt_lev
            ldb   r70, LPXOR
            cmpb  r70, zero
            je    pt_lev
            xorb  r70, 0xef80[r54]
            stb   r70, 0xef80[r54]
            stb   r70, 0x0d00[r54]      ; LA32 takes 0x0D00/0x0D01 as a pair
            ldb   r70, 0xef81[r54]
            stb   r70, 0x0d01[r54]
    pt_lev: ldbze r72, 0xf180[r54]      ; level (velocity attenuation) - note mods
            sub   r72, MNL
            ld    r74, #0x9b
            lcall clampw
            stb   r72, 0xf180[r54]
            stb   r72, LB[r54]
            pop   r7e
            pop   r7c
            pop   r7a
            ret

    ; vint: vintage wander of note slot r52 (part r50) -> r70 pitch offset, VCUT cutoff offset (signed words).
    ; Smooth noise: VPH moves slowly, every slot reads the noise table at its own offset. Uses r70-r7a.
    vint:   clr   VCUT
            ldb   r70, VINT
            cmpb  r70, zero
            je    vi_0
            ldb   r70, VINTP
            lcall scope
            jne   vi_0
            ldbze r76, r52
            mulu  r78, r76, #0x2f1d
            add   r78, VPH
            ldbze r76, r79
            ldb   r7a, ntab[r76]        ; n0 (-63..63)
            incb  r76
            ldb   r74, ntab[r76]        ; n1
            subb  r74, r7a
            ldb   r70, r78              ; fraction
            ldb   r71, #8
            lcall smul                  ; (n1 - n0) * f / 256
            addb  r7a, r72              ; v = -63..63
            ldb   r74, r7a
            ldb   r70, VINT
            ldb   r71, #9
            lcall smul
            st    r72, VCUT             ; cutoff: +-12 at 99
            ldb   r74, r7a
            ldb   r70, VINT
            ldb   r71, #6
            lcall smul
            ld    r70, r72              ; pitch: +-97 units (~28 cents) at 99
            ret
    vi_0:   clr   r70
            ret

    ; ===================================================================== notes: arp > mono > chord > unison
    ; MIDI note on / off (per part: r45 note, r46 velocity, r50 part*16; keep r42, r44-r46, r50)
    note_on: lcall init
            cmpb  r46, zero
            je    note_off
            cmp   r50, #0x0080
            jc    no_st
            lcall rec_mine
            je!   rec_on
            lcall lrn_mine
            je!   lrn_on
            lcall arp_mine
            jne   play_on
            ljmp  arp_key_on
    no_st:  ld    r70, #NOTE_ON
            st    r70, TGT
            ljmp  CALL19
    note_off: lcall init
            cmp   r50, #0x0080
            jc    nf_st
            lcall rec_mine
            je!   rec_off
            lcall lrn_mine
            je!   lrn_off
            lcall arp_mine
            jne   play_off
            ljmp  arp_key_off
    nf_st:  ld    r70, #NOTE_OFF
            st    r70, TGT
            ljmp  CALL19

    ; play_on / play_off: r45 note, r46 velocity, r50 part. Mono part: one note (stack of held keys), legato
    ; moves the sounding note instead of a new attack.
    play_on: ldb  r70, MONOP
            lcall scope1
            jne! chord_on
            lcall mstk_push
            stb   r46, MVEL
            ldb   r70, MCUR
            cmpb  r70, #0xff
            je    po_new
            ldb   r70, LEGATO
            cmpb  r70, zero
            je    po_rt
            lcall legato
            stb   r45, MCUR
            ret
    po_rt:  push  r44
            ldb   r45, MCUR
            lcall chord_off
            pop   r44
    po_new: stb   r45, MCUR
            sjmp  chord_on
    play_off: ldb r70, MONOP
            lcall scope1
            jne! chord_off
            lcall mstk_del
            ldb   r70, MCUR
            cmpb  r70, r45
            je    pf_cur
            ret                         ; a held key that was not sounding
    pf_cur: cmpb  MCNT, zero
            jne   pf_bk
            ldb   r70, #0xff
            stb   r70, MCUR
            sjmp  chord_off
    pf_bk:  push  r44
            push  r46
            ldbze r70, MCNT
            ldb   r70, MSTK-1[r70]      ; back to the last key still held
            ldb   r71, LEGATO
            cmpb  r71, zero
            je    pf_rt
            ldb   r45, r70
            lcall legato
            stb   r45, MCUR
            sjmp  pf_x
    pf_rt:  push  r70
            lcall chord_off
            pop   r70
            ldb   r45, r70
            ldb   r46, MVEL
            stb   r45, MCUR
            lcall chord_on
    pf_x:   pop   r46
            pop   r44
            ret

    ; mono key stack (MSTK, MCNT): mstk_del removes r45, mstk_push puts it on top. Uses r70, r72.
    mstk_del: clr r72
    md_l:   cmpb  r72, MCNT
            je    md_x
            cmpb  r45, MSTK[r72]
            je    md_s
            incb  r72
            sjmp  md_l
    md_s:   incb  r72
            cmpb  r72, MCNT
            je    md_e
            ldb   r70, MSTK[r72]
            stb   r70, MSTK-1[r72]
            sjmp  md_s
    md_e:   decb  MCNT
    md_x:   ret
    mstk_push: lcall mstk_del
            cmpb  MCNT, #8
            jne   mp1
            clr   r72                   ; full: drop the oldest
    mp_s:   ldb   r70, MSTK+1[r72]
            stb   r70, MSTK[r72]
            incb  r72
            cmpb  r72, #7
            jne   mp_s
            decb  MCNT
    mp1:    ldbze r72, MCNT
            stb   r45, MSTK[r72]
            incb  MCNT
            ret

    ; legato: the sounding note of mono part r50 (MCUR) moves to r45 without a new attack: slot note numbers
    ; follow, the pitch glides (Glide Time) or jumps.
    legato: ldb   r70, r45
            subb  r70, MCUR
            ldb   r7e, r70              ; semitones
            ldbse r72, r70
            lcall pmul
            ld    r7c, r74              ; pitch units
            ldb   r7f, int_mask
            andb  int_mask, #0x7f
            ldbze r52, 0xf285[r50]
    lg_n:   cmpb  r52, #0xff
            je    lg_d
            ldb   r70, 0xf460[r52]
            jbs   r70, 6, lg_nx         ; released
            ldb   r70, 0xf400[r52]
            jbs   r70, 7, lg_nx         ; held by the pedal only
            addb  r70, r7e
            stb   r70, 0xf400[r52]
            ldbze r54, 0xf440[r52]
    lg_p:   cmpb  r54, #0xff
            je    lg_nx
            ld    r72, PB[r54]
            ld    r70, r7c
            lcall padd
            st    r72, PB[r54]
            ldb   r70, GLTIME
            cmpb  r70, zero
            je    lg_j
            ldb   r70, GLPART
            lcall scope
            jne   lg_j
            ld    r70, GL[r54]          ; glide: the sound stays, the target moves
            sub   r70, r7c
            lcall glclamp
            st    r70, GL[r54]
            sjmp  lg_nn
    lg_j:   ld    r72, 0xef40[r54]
            ld    r70, r7c
            lcall padd
            st    r72, 0xef40[r54]
    lg_nn:  ldbze r54, 0xee40[r54]
            sjmp  lg_p
    lg_nx:  ldbze r52, 0xf3c0[r52]
            sjmp  lg_n
    lg_d:   ldb   int_mask, r7f
            ld    r70, r50
            shr   r70, #4
            stb   r45, LASTN[r70]
            ret

    ; chord_on / chord_off: r45 root (r46 velocity) -> chord notes -> unison voices -> stock note on / off
    chord_on: ld  r70, #NOTE_ON
            sjmp  chord
    chord_off: ld r70, #NOTE_OFF
    chord:  st    r70, TGT
            clr   GLD
            cmp   r70, #NOTE_ON
            jne   ch_u
            ldb   r70, GLTIME           ; glide from the previous note of this part
            cmpb  r70, zero
            je    ch_u
            ldb   r70, GLPART
            lcall scope
            jne   ch_u
            ld    r70, r50
            shr   r70, #4
            ldb   r71, LASTN[r70]
            cmpb  r71, #0xff
            je    ch_u
            subb  r71, r45
            ldbse r72, r71
            lcall pmul
            st    r74, GLD
    ch_u:   ldb   r70, UNIV             ; unison voices for this part
            incb  r70
            stb   r70, UNN
            ldb   r70, UNIP
            lcall scope
            je    ch_c
            ldb   r70, #1
            stb   r70, UNN
    ch_c:   ldbze r7c, CHORD
            cmpb  r7c, zero
            je!   ch_one
            cmpb  r7c, #NCHORDS
            jc!   ch_one
            ldb   r70, CHPART
            lcall scope
            jne!  ch_one
            ld    r70, #CLRN            ; interval list: learned, scale (computed for this root) or fixed
            cmpb  r7c, #NFIX
            je    ch_p
            jnc   ch_f
            lcall scalc
            ld    r70, #SCB
            sjmp  ch_p
    ch_f:   ldbze r70, r7c
            shl   r70, #2
            add   r70, #chiv
    ch_p:   st    r70, CIVP
            push  r44                   ; r45 = root note
            lcall uni
            stb   zero, CHI
    ch_l:   ld    r78, CIVP
            ldbze r70, CHI
            add   r78, r70
            ldb   r70, [r78]
            cmpb  r70, zero
            je    ch_d
            ld    r44, 0[sp]
            addb  r45, r70
            cmpb  r45, #0x80
            jc    ch_n
            lcall uni
    ch_n:   incb  CHI
            cmpb  CHI, #4
            jne   ch_l
    ch_d:   pop   r44
            sjmp  ch_x
    ch_one: lcall uni
    ch_x:   ld    r70, TGT
            cmp   r70, #NOTE_ON
            jne   ch_r
            ld    r70, r50
            shr   r70, #4
            stb   r45, LASTN[r70]
    ch_r:   clr   GLD
            ret

    ; uni: r45 played UNN times; voice i gets detune (2i + 1 - UNN) * UNID pitch units
    uni:    stb   zero, UI
    un_l:   ldb   r70, UI
            shlb  r70, #1
            incb  r70
            subb  r70, UNN              ; signed -3..3
            clrb  r79
            jbc   r70, 7, un1
            negb  r70
            incb  r79
    un1:    mulub r72, r70, UNID
            jbc   r79, 0, un2
            neg   r72
    un2:    st    r72, UDT
            ldb   r70, #0xff
            stb   r70, LASTSLOT         ; next partial setup = new note: new random offsets
            lcall CALL19
            incb  UI
            cmpb  UI, UNN
            jne   un_l
            clr   UDT
            ret

    ; scalc: SCB = diatonic chord intervals on root r45 in Scale Key / Type (r7c = NFIX+1 triad, NFIX+2 7th).
    ; A note outside the scale uses the degree below it. Uses r70-r7b.
    scalc:  ldbze r70, r45
            add   r70, #12
            ldbze r72, SCKEY
            sub   r70, r72
            divub r70, #12              ; r71 = pitch class above the key
            ldbze r74, SCTYPE
            shl   r74, #4
            add   r74, #sctab           ; 14 bytes: the scale over two octaves
            ldbze r76, #6
    sk_d:   ld    r78, r74
            add   r78, r76
            ldb   r72, [r78]
            cmpb  r72, r71
            jnh   sk_f                  ; degree r76: tone <= pitch class
            dec   r76
            sjmp  sk_d
    sk_f:   ldb   r7a, r72              ; tone of the degree
            ldb   r7b, #2
            ld    r72, #SCB
    sk_i:   ldbze r70, r7b
            add   r70, r78
            ldb   r70, [r70]
            subb  r70, r7a
            stb   r70, [r72]+
            addb  r7b, #2
            cmpb  r7b, #8
            jne   sk_i
            stb   zero, [r72]
            cmpb  r7c, #NFIX+2
            je    sk_x
            stb   zero, SCB+2           ; triad: no 7th
    sk_x:   ret

    ; all notes off on parts 1-8 (a setting changed while notes may be held), mono / arp state cleared
    all_off: ld   r70, #ALL_OFF
            st    r70, TGT
            clr   r50
    ao_l:   lcall CALL19
            add   r50, #0x0010
            cmp   r50, #0x0080
            jne   ao_l
            lcall mo_off                ; arp note still sounding on MIDI out
            clrb  MCNT
            clrb  AN
            clrb  AH
            stb   zero, RTN
            ldb   r70, #0xff
            stb   r70, MCUR
            stb   r70, ACUR
            ld    r70, #0xffff
            st    r70, LASTN
            st    r70, LASTN+2
            st    r70, LASTN+4
            st    r70, LASTN+6
            ret

    ; ===================================================================== arpeggiator
    ; arp_mine: Z = 1 when the arp is on and r50 is the arp part. Uses r70, r71.
    arp_mine: ldb r70, ARPM
            cmpb  r70, zero
            je    am_no
            ldb   r70, ARPP
            shlb  r70, #4
            cmpb  r70, r50
            ret
    am_no:  cmpb  r70, #1               ; Z = 0
            ret

    arp_key_on: ldb r70, ARPLATCH       ; latch: the first key after all keys were up starts a new set
            cmpb  r70, zero
            je    ak1
            cmpb  AH, zero
            jne   ak1
            clrb  AN
    ak1:    incb  AH
            stb   r46, AV
            clr   r72
    ak_f:   cmpb  r72, AN
            je    ak_a
            cmpb  r45, ABUF[r72]
            je    ak_x
            incb  r72
            sjmp  ak_f
    ak_a:   cmpb  r72, #12
            je    ak_x
            stb   r45, ABUF[r72]
            incb  AN
            cmpb  AN, #1
            jne   ak_x
            lcall arp_reset             ; first key: start now
    ak_x:   ret

    arp_key_off: cmpb AH, zero
            je    af1
            decb  AH
    af1:    ldb   r70, ARPLATCH
            cmpb  r70, zero
            jne   af_x
            clr   r72
    af_f:   cmpb  r72, AN
            je    af_x
            cmpb  r45, ABUF[r72]
            je    af_s
            incb  r72
            sjmp  af_f
    af_s:   incb  r72
            cmpb  r72, AN
            je    af_e
            ldb   r70, ABUF[r72]
            stb   r70, ABUF-1[r72]
            sjmp  af_s
    af_e:   decb  AN
    af_x:   ret

    arp_reset: ldb r70, #0xff
            stb   r70, ALB
            stb   r70, AI
            stb   r70, ASC
            stb   zero, AD
            stb   zero, ACLK
            stb   zero, AO
            stb   zero, ECNT
            stb   zero, RTN
            stb   zero, HJ
            cmp   CLKAGE, #240
            jnc   ar0                   ; MIDI clock: the synced LFO follows the clock
            clr   r70
            st    r70, LCC              ; internal tempo: the synced LFO starts with the arp
            st    r70, LACC
    ar0:    ldb   r70, ARPM
            cmpb  r70, #2
            jne   ar1
            ldb   r70, ARPOCT           ; Down starts at the top octave
            stb   r70, AO
    ar1:    ld    r70, #0x4000
            st    r70, ARPT             ; next tick steps
            ld    r70, #0x7fff
            st    r70, ASTP             ; (no last step: the first gate uses the tempo)
            ret

    ; arp_tick: TN = ticks since the last call, TCK = MIDI clocks, TCK+1 = MIDI start seen
    arp_tick: ldb r70, RECM
            cmpb  r70, #3
            je!   at_tm                 ; live recording: the step clock runs
            cmpb  r70, zero
            jne   at_off                ; recording: the arp waits
            ldb   r70, ARPM
            cmpb  r70, zero
            je    at_off
            cmpb  AN, zero
            jne   at_go
    at_off: stb   zero, RTN             ; arp off or no keys: release the sounding note
            ldb   r70, ACUR
            cmpb  r70, #0xff
            je    at_r
            lcall arp_rel
    at_r:   ret
    at_go:  ldb   r70, ACUR             ; gate
            cmpb  r70, #0xff
            je    at_rt
            ld    r7e, TN
            sub   AGT, r7e
            jgt   at_rt
            lcall arp_rel
    at_rt:  ldb   r70, RTN              ; ratchet: more hits in this step
            cmpb  r70, zero
            je    at_tm
            ld    r72, RTT
            sub   r72, TN
            st    r72, RTT
            jgt   at_tm
            decb  r70
            stb   r70, RTN
            add   r72, RTI
            st    r72, RTT
            ldb   r70, ACUR
            cmpb  r70, #0xff
            je    at_r2
            lcall arp_rel
    at_r2:  ld    r70, RTI
            lcall gate
            ldb   r45, ARN
            ldb   r46, AVL
            lcall arp_play
    at_tm:  ld    r7e, TN
            add   ASTP, r7e
            ld    r7c, TCK
            cmpb  r7c, zero
            je    at_nc
            cmpb  r7d, zero             ; MIDI start: from the top
            je    at_cs
            lcall arp_reset
            ldbze r70, ARPRATE
            mulub r70, r70, #3
            ldb   r70, rates+2[r70]
            decb  r70
            stb   r70, ACLK             ; the first clock steps
    at_cs:  ldb   r70, ACLK
            addb  r70, TCK
            stb   r70, ACLK
            ldbze r72, ARPRATE
            mulub r72, r72, #3
            ldb   r71, rates+2[r72]     ; clocks per step
            cmpb  r70, r71
            jnc   at_x
            subb  r70, r71
            stb   r70, ACLK
            sjmp  dostep
    at_nc:  cmp   CLKAGE, #240          ; no clock for ~0.5 s: internal tempo
            jc    at_int
            ret
    at_int: add   ARPT, r7e             ; (signed: Humanize Time can make it negative)
            lcall arp_ivl
            cmp   ARPT, r70
            jlt   at_x
            sub   ARPT, r70
            cmp   ARPT, r70
            jlt   dostep
            clr   ARPT                  ; late by more than a step: no catching up
    dostep: ldb   r70, RECM
            cmpb  r70, #3
            je!   rec_step
            ljmp  arp_step
    at_x:   ret

    ; arp_ivl: r70 = internal step length in ticks = 28800 / (BPM * steps per beat)
    arp_ivl: ldbze r70, ARPBPM
            add   r70, #40
            ldbze r74, ARPRATE
            mulub r74, r74, #3
            ldbze r72, rates+1[r74]
            mulu  r74, r70, r72
            ld    r78, #28800
            clr   r7a
            divu  r78, r74
            ld    r70, r78
            ret

    ; gate: AGT = r70 ticks * Arp Gate %. Uses r72-r7b.
    gate:   ldbze r72, ARPGATE
            mulu  r74, r70, r72
            ld    r78, r74
            ld    r7a, r76
            ld    r74, #100
            divu  r78, r74
            st    r78, AGT
            ret

    ; arp_play: arp note r45 (velocity r46) on: MIDI out, and inside unless Arp MIDI Out = Only.
    ; arp_rel: the sounding arp note off.
    arp_play: stb r45, ACUR
            lcall arp_part
            lcall mo_on
            ldb   r70, ARPOUT
            cmpb  r70, #2
            je    ap_x
            ljmp  play_on
    ap_x:   ret
    arp_rel: lcall arp_part
            lcall mo_off
            ldb   r45, ACUR
            ldb   r70, #0xff
            stb   r70, ACUR
            ldb   r70, ARPOUT
            cmpb  r70, #2
            je    ap_x
            ljmp  play_off
    arp_part: ldbze r50, ARPP
            shl   r50, #4
            ldb   r44, 0xf28b[r50]
            ret

    ; ---- MIDI out (stock transmit ring, routine 0x1D8D sends rd0): one arp note at a time, on the arp part's
    ; MIDI channel. mo_on: r45 note, r46 velocity, r50 part. mo_off: the note sent last (MON / MCH) off.
    mo_on:  ldb   r70, ARPOUT
            cmpb  r70, zero
            je    mo_x
            lcall mo_off
            ldb   r70, 0xf28b[r50]      ; the part's receive channel
            cmpb  r70, #16
            jc    mo_x                  ; part off
            stb   r70, MCH
            stb   r45, MON
            orb   r70, #0x90
            lcall mo_tx
            ldb   r70, r45
            lcall mo_tx
            ldb   r70, r46
            sjmp  mo_tx
    mo_off: ldb   r70, MON
            cmpb  r70, #0xff
            je    mo_x
            ldb   r70, MCH
            orb   r70, #0x80
            lcall mo_tx
            ldb   r70, MON
            lcall mo_tx
            ldb   r70, #0xff
            stb   r70, MON
            ldb   r70, #0x40
    mo_tx:  ldb   rd0, r70
            push  TGT
            ld    r70, #TX_BYTE
            st    r70, TGT
            lcall CALL19
            pop   TGT
    mo_x:   ret

    ; arp_step: step boundary: next note (or rest / tie), Euclid / chance masks, octave jump, accent, humanize,
    ; ratchet, then note on
    arp_step: ld  r70, ASTP             ; step length from the last step
            clr   ASTP
            cmp   r70, #2000
            jnh   as0
            lcall arp_ivl
    as0:    st    r70, SLEN
            stb   zero, RTN
            ldb   r70, ASC              ; step count (accents)
            incb  r70
            stb   r70, ASC
            lcall humt
            lcall arp_next              ; -> r45 (0x80+ = rest, 0x81 = tie)
            cmpb  r45, #0x81
            jne   as1
            ret                         ; tie: the note goes on sounding
    as1:    stb   r45, ARN
            lcall amask
            cmpb  r70, zero
            je    as2
            ldb   r70, #0x80            ; masked: rest
            stb   r70, ARN
    as2:    ldb   r70, ACUR
            cmpb  r70, #0xff
            je    as3
            lcall arp_rel
    as3:    ldb   r45, ARN
            cmpb  r45, #0x80
            jnc   as4
            ret
    as4:    ldb   r70, OJUMP            ; octave jump
            lcall chance
            cmpb  r70, zero
            jne   as5
            ldb   r70, r45
            addb  r70, #12
            cmpb  r70, #0x80
            jc    as5
            stb   r70, ARN
    as5:    lcall avel
            stb   r46, AVL
            ldb   r70, RATCH            ; ratchet: hits in this step
            cmpb  r70, #4
            jne   as6
            lcall rnd
            ldb   r70, r7e
            andb  r70, #3
    as6:    cmpb  r70, zero
            je    as_1
            stb   r70, RTN
            incb  r70
            ld    r78, SLEN
            clr   r7a
            ldbze r7c, r70
            divu  r78, r7c
            st    r78, RTI
            st    r78, RTT
            ld    r70, r78
            lcall gate
            sjmp  as_p
    as_1:   ld    r70, SLEN             ; one hit: gate + following tie steps (Seq)
            lcall gate
            lcall ties
            mulu  r74, r72, SLEN
            add   AGT, r74
    as_p:   ldb   r45, ARN
            ldb   r46, AVL
            ljmp  arp_play

    ; ties: r72 = tie steps after the current Seq step (Arp Mode Seq). Uses r70, r74-r76.
    ties:   clr   r72
            ldb   r70, ARPM
            cmpb  r70, #6
            jne   ti_x
            ldb   r74, AI
            ldb   r75, SEQLEN
    ti_l:   incb  r74
            cmpb  r74, r75
            jnc   ti_n
            clrb  r74
    ti_n:   ldbze r76, r74
            ldb   r70, SEQ[r76]
            cmpb  r70, #0x81
            jne   ti_x
            incb  r72
            cmpb  r72, r75
            jnc   ti_l
    ti_x:   ret

    ; amask: r70 = 0 when this step plays: Euclid (hit when step * hits mod steps < hits), then Chance %.
    amask:  ldb   r70, EUCN
            cmpb  r70, zero
            je    am_p
            ldb   r72, ECNT
            cmpb  r72, r70
            jnc   am_1
            clrb  r72
    am_1:   ldb   r73, r72
            incb  r73
            cmpb  r73, r70
            jnc   am_2
            clrb  r73
    am_2:   stb   r73, ECNT
            ldb   r74, EUCK
            cmpb  r74, r70
            jnh   am_3
            ldb   r74, r70
    am_3:   mulub r76, r72, r74
            divub r76, r70
            cmpb  r77, r74
            jnc   am_p
            ldb   r70, #1
            ret
    am_p:   ldb   r70, ARPPROB

    ; chance: r70 = percent -> r70 = 0 (yes) with that chance. Uses r71-r73, r7d-r7f.
    chance: ldb   r71, r70
            clrb  r70
            cmpb  r71, #100
            jc    pr_x
            lcall rnd
            mulub r72, r7e, #100
            cmpb  r73, r71
            jnc   pr_x
            ldb   r70, #1
    pr_x:   ret

    ; avel: r46 = arp velocity: held velocity, accent (accented 127, others 3/4), humanize. Uses r70-r7f.
    avel:   ldb   r46, AV
            ldb   r70, ACCENT
            cmpb  r70, zero
            je    av_h
            cmpb  r70, #4
            jne   av_n
            lcall rnd                   ; random: about 1 step in 3
            cmpb  r7e, #85
            jc    av_s
            sjmp  av_a
    av_n:   incb  r70                   ; every 2 / 3 / 4 steps
            ldbze r72, ASC
            divub r72, r70
            cmpb  r73, zero
            jne   av_s
    av_a:   ldb   r46, #127
            sjmp  av_h
    av_s:   ldb   r70, r46
            shrb  r70, #2
            subb  r46, r70
    av_h:   ldb   r70, HUMV
            cmpb  r70, zero
            je    av_x
            lcall rnd
            ldb   r74, r7e
            ldb   r71, #7
            lcall smul                  ; +-HUMV
            ldbze r70, r46
            add   r72, r70
            ld    r74, #127
            lcall clampw
            cmpb  r72, zero
            jne   av_1
            incb  r72
    av_1:   ldb   r46, r72
    av_x:   ret

    ; humt: Humanize Time (internal tempo only): the next step moves by up to +-12 ticks (~25 ms)
    humt:   ldb   r70, HUMT
            cmpb  r70, zero
            je    hu_x
            cmp   CLKAGE, #240
            jnc   hu_x
            lcall rnd
            ldb   r74, r7e
            ldb   r70, HUMT
            ldb   r71, #10
            lcall smul
            ldbse r70, HJ
            stb   r72, HJ
            sub   r72, r70              ; this step's shift - the last one: the tempo stays
            add   ARPT, r72
    hu_x:   ret

    ; arp_next: -> r45 = next note (ALB base note + 12 * AO), >= 0x80 = none
    arp_next: ldbze r70, ARPM
            shl   r70, #1
            ld    r76, arpjt-2[r70]
            lcall jmp76                 ; -> r75 base note (ALB set), 0x80+ = rest / tie / none
            ldb   r45, r75
            cmpb  r75, #0x80
            jc    an_x
            ldbze r72, AO
            mulub r72, r72, #12
            addb  r72, r75
            ldb   r45, r72
            cmpb  r72, #0x80
            jnc   an_x
            ldb   r45, r75              ; over 127: base octave
    an_x:   ret
    nx_up:  ldb   r74, ALB
            incb  r74
            lcall fmin
            cmpb  r75, #0xff
            jne   nu_x
            lcall oct_up
            clrb  r74
            lcall fmin
    nu_x:   stb   r75, ALB
            ret
    nx_dn:  ldb   r74, ALB
            cmpb  r74, zero
            je    nd_w
            decb  r74
            lcall fmax
            cmpb  r75, #0xff
            jne! nd_x
    nd_w:   lcall oct_dn
            ldb   r74, #0xfe
            lcall fmax
    nd_x:   stb   r75, ALB
            ret
    nx_ud:  ldb   r70, AD
            cmpb  r70, zero
            jne   ud_d
            ldb   r74, ALB
            incb  r74
            lcall fmin
            cmpb  r75, #0xff
            jne! nd_x
            ldb   r70, AO
            cmpb  r70, ARPOCT
            jc    ud_td                 ; top octave: turn
            incb  r70
            stb   r70, AO
            clrb  r74
            lcall fmin
            sjmp  nd_x
    ud_td:  ldb   r70, #1
            stb   r70, AD
    ud_d:   ldb   r74, ALB
            cmpb  r74, zero
            je    ud_b
            decb  r74
            lcall fmax
            cmpb  r75, #0xff
            jne! nd_x
    ud_b:   ldb   r70, AO
            cmpb  r70, zero
            je    ud_tu
            decb  r70
            stb   r70, AO
            ldb   r74, #0xfe
            lcall fmax
            sjmp  nd_x
    ud_tu:  stb   zero, AD              ; bottom: turn
            ldb   r74, ALB
            incb  r74
            lcall fmin
            cmpb  r75, #0xff
            jne! nd_x
            ldb   r75, ALB              ; one key only
            sjmp  nd_x
    nx_rnd: lcall rnd
            ldbze r70, r7e
            divub r70, AN
            ldbze r72, r71
            ldb   r75, ABUF[r72]
            ldbze r70, r7f
            ldb   r72, ARPOCT
            incb  r72
            divub r70, r72
            stb   r71, AO
            sjmp  nd_x
    nx_pl:  ldb   r70, AI
            incb  r70
            cmpb  r70, AN
            jnc   np1
            clrb  r70
            lcall oct_up
    np1:    stb   r70, AI
            ldbze r72, r70
            ldb   r75, ABUF[r72]
            sjmp  nd_x
    ; nx_sq: recorded sequence; notes move with the last key pressed (the first recorded note = that key)
    nx_sq:  ldb   r70, SEQLEN
            ldb   r75, #0x80
            cmpb  r70, zero
            je    sq_x
            ldb   r72, AI
            incb  r72
            cmpb  r72, r70
            jnc   sq_1
            clrb  r72
            lcall oct_up
    sq_1:   stb   r72, AI
            ldbze r72, r72
            ldb   r75, SEQ[r72]
            cmpb  r75, #0x80
            jc    sq_x                  ; rest / tie
            ldbze r72, AN
            ldbze r70, ABUF-1[r72]
            ldbze r76, r75
            add   r76, r70
            sub   r76, #64
            ldb   r75, #0x80
            cmp   r76, #0x7f
            jh    sq_x                  ; out of range: rest
            ldb   r75, r76
    sq_x:   ret
    oct_up: ldb   r71, AO
            incb  r71
            cmpb  r71, ARPOCT
            jnh   ou1
            clrb  r71
    ou1:    stb   r71, AO
            ret
    oct_dn: ldb   r71, AO
            cmpb  r71, zero
            jne   od1
            ldb   r71, ARPOCT
            incb  r71
    od1:    decb  r71
            stb   r71, AO
            ret
    ; fmin: r75 = lowest held note >= r74 (0xFF none). fmax: highest held note <= r74. Use r72, r76.
    fmin:   ldb   r75, #0xff
            clr   r72
    fn_l:   cmpb  r72, AN
            je    fn_x
            ldb   r76, ABUF[r72]
            cmpb  r76, r74
            jnc   fn_n
            cmpb  r76, r75
            jc    fn_n
            ldb   r75, r76
    fn_n:   incb  r72
            sjmp  fn_l
    fn_x:   ret
    fmax:   ldb   r75, #0xff
            clr   r72
    fx_l:   cmpb  r72, AN
            je    fn_x
            ldb   r76, ABUF[r72]
            cmpb  r76, r74
            jh    fx_n
            cmpb  r75, #0xff
            je    fx_s
            cmpb  r76, r75
            jnh   fx_n
    fx_s:   ldb   r75, r76
    fx_n:   incb  r72
            sjmp  fx_l

    ; ===================================================================== sequence record, chord learn
    ; rec_mine: Z = 1 when recording (Seq Record) and r50 is the arp part. Uses r70.
    rec_mine: ldb r70, RECM
            cmpb  r70, zero
            je! rm_no
            ldb   r70, ARPP
            shlb  r70, #4
            cmpb  r70, r50
            ret
    rm_no:  cmpb  r70, #1               ; Z = 0
            ret
    ; rec_on: Step = the key is the next step; Live = the first key starts the arp clock, then each key goes to
    ; the step it is nearest to. Keys sound as played.
    rec_on: incb  AH
            ldb   r70, RECM
            cmpb  r70, #1
            je    rc_st
            cmpb  r70, #2
            je    rc_go
            ld    r70, ASTP             ; running: a key in the second half of a step is for the next step
            shl   r70, #1
            cmp   r70, SLEN
            jh    rc_nx
            ldb   r70, LCUR
            cmpb  r70, #0xff
            jne   rc_p
            stb   r45, LCUR
            sjmp  rc_p
    rc_nx:  ldb   r70, LNX
            cmpb  r70, #0xff
            jne   rc_p
            stb   r45, LNX
            sjmp  rc_p
    rc_go:  stb   r45, RRT
            stb   r45, LCUR
            stb   zero, RPOS
            ldb   r70, #3
            stb   r70, RECM
            clr   ARPT
            clr   ASTP
            stb   zero, ACLK
            lcall arp_ivl
            st    r70, SLEN
            sjmp  rc_p
    rc_st:  ldb   r70, RPOS
            cmpb  r70, zero
            jne   rc_s1
            stb   r45, RRT
    rc_s1:  lcall rnote
            lcall rput
    rc_p:   ljmp  play_on
    rec_off: cmpb AH, zero
            je    rf1
            decb  AH
    rf1:    ljmp  play_off

    ; rnote: r70 = step byte of note r45 (semitones from the first recorded note + 64, 0-127). Uses r72, r74.
    rnote:  ldbze r70, r45
            add   r70, #64
            ldbze r72, RRT
            sub   r70, r72
            ld    r72, r70
            ld    r74, #127
            lcall clampw
            ldb   r70, r72
            ret
    ; rput: step byte r70 at RPOS, next position; at 32 the recording ends. Uses r70, r72.
    rput:   ldbze r72, RPOS
            stb   r70, SEQ[r72]
            incb  r72
            stb   r72, RPOS
            cmpb  r72, #32
            jne   rp_x
    rec_end: ldb  r70, RPOS             ; stop recording: steps so far = the new length
            cmpb  r70, zero
            je    re1
            stb   r70, SEQLEN
    re1:    stb   zero, RECM
            stb   zero, RPOS
            ldb   r70, #0xff
            stb   r70, LCUR
            stb   r70, LNX
    rp_x:   ret
    ; rec_step: live recording, step boundary: the key of this step, else a tie while a key is held, else a rest
    rec_step: ld  r70, ASTP
            clr   ASTP
            cmp   r70, #2000
            jnh   rs0
            lcall arp_ivl
    rs0:    st    r70, SLEN
            ldb   r70, LCUR
            cmpb  r70, #0xff
            je    rs_e
            ldb   r45, r70
            lcall rnote
            sjmp  rs_w
    rs_e:   ldb   r70, #0x80            ; tie: a key held, not one already waiting for the next step
            cmpb  AH, zero
            je    rs_w
            ldb   r72, LNX
            cmpb  r72, #0xff
            jne   rs_w
            ldb   r72, RPOS
            cmpb  r72, zero
            je    rs_w
            ldb   r70, #0x81
    rs_w:   lcall rput
            ldb   r70, LNX
            stb   r70, LCUR
            ldb   r70, #0xff
            stb   r70, LNX
            ret

    ; lrn_mine: Z = 1 when Chord Learn is armed and r50 is in the Chord Part scope. Uses r70, r76.
    lrn_mine: ldb r70, LARM
            cmpb  r70, zero
            je! rm_no
            ldb   r70, CHPART
            ljmp  scope
    ; lrn_on / lrn_off: keys play as they are; the held notes are collected, all keys up -> learned
    lrn_on: ldb   r70, LHC
            incb  r70
            stb   r70, LHC
            ldbze r72, LCNT
            clr   r74
    lo_f:   cmpb  r74, r72
            je    lo_a
            cmpb  r45, LBUF[r74]
            je    lo_p
            incb  r74
            sjmp  lo_f
    lo_a:   cmpb  r72, #5
            je    lo_p
            stb   r45, LBUF[r72]
            incb  r72
            stb   r72, LCNT
    lo_p:   ljmp  no_st
    lrn_off: ldb  r70, LHC
            cmpb  r70, zero
            je    lf1
            decb  r70
            stb   r70, LHC
            jne   lf1
            ldb   r70, LCNT
            cmpb  r70, zero
            je    lf1
            lcall lrn_end
    lf1:    ljmp  nf_st
    ; lrn_end: lowest note = root, the next higher ones -> up to 4 intervals in CLRN; Chord = Learned
    lrn_end: clrb r74
            lcall lmin
            ldb   r7a, r75              ; root
            ldb   r7b, r75              ; last note taken
            clr   r78
    le_l:   ldb   r74, r7b
            incb  r74
            lcall lmin
            cmpb  r75, #0xff
            je    le_z
            ldb   r7b, r75
            subb  r75, r7a
            stb   r75, CLRN[r78]
            incb  r78
            cmpb  r78, #4
            jne   le_l
            sjmp  le_d
    le_z:   stb   zero, CLRN[r78]
            incb  r78
            cmpb  r78, #4
            jne   le_z
    le_d:   stb   zero, LARM
            stb   zero, LCNT
            ldb   r70, #NFIX
            stb   r70, CHORD
            ret
    ; lmin: r75 = lowest learned note >= r74 (0xFF none). Uses r72, r76.
    lmin:   ldb   r75, #0xff
            clr   r72
    lm_l:   cmpb  r72, LCNT
            je    lm_x
            ldb   r76, LBUF[r72]
            cmpb  r76, r74
            jnc   lm_n
            cmpb  r76, r75
            jc    lm_n
            ldb   r75, r76
    lm_n:   incb  r72
            sjmp  lm_l
    lm_x:   ret

    ; ===================================================================== tick (~2 ms, main loop)
    ; r70 = ticks since the last call. Free: r42-r7f.
    tick:   lcall init
            ldbze r7e, r70
            st    r7e, TN
            di
            ldb   r7c, CLK
            clrb  CLK
            ldb   r7d, CLKS
            clrb  CLKS
            ei
            st    r7c, TCK
            cmpb  r7c, zero             ; MIDI clock age (ticks since the last clock), clock period EPC
            je    tk_a
            ld    r70, CLKAGE
            add   r70, r7e
            cmp   r70, #240
            jc    tk_c
            divub r70, r7c
            stb   r70, EPC
    tk_c:   clr   CLKAGE
            sjmp  tk_s
    tk_a:   cmp   CLKAGE, #0x7000
            jc    tk_s
            add   CLKAGE, r7e
    tk_s:   lcall lsync
            lcall arp_tick
            ldb   r7e, TN
            addb  TDIV, r7e
            cmpb  TDIV, #4
            jnc   tk_x
            clrb  TDIV
            sjmp  mpass
    tk_x:   ret

    ; lsync: synced LFO position LCC (1/64 MIDI clocks, modulo the cycle): MIDI clock when there is one (between
    ; clocks it moves on at the measured clock period), else the arp tempo
    lsync:  ldbze r70, LFOSYNC
            cmpb  r70, zero
            je! ls_x
            shl   r70, #1
            ld    r7a, lsctab[r70]      ; cycle length in 1/64 clocks
            ld    r7c, TCK
            cmpb  r7d, zero             ; MIDI start: cycle from the top
            je    ls_0
            clr   r70
            st    r70, LCC
            st    r70, LACC
    ls_0:   cmp   CLKAGE, #240
            jc    ls_i
            ld    r70, LCC
            cmpb  r7c, zero
            je    ls_m
            andb  r70, #0xc0            ; MIDI clocks: to the clock boundary
            ldbze r72, r7c
            shl   r72, #6
            add   r70, r72
            sjmp  ls_w
    ls_m:   ldbze r72, EPC              ; between clocks: TN * 64 / clock period, up to the next clock
            cmpb  r72, zero
            je! ls_x
            ld    r74, TN
            shl   r74, #6
            divub r74, r72
            ldb   r72, r70
            andb  r72, #0x3f
            addb  r72, r74
            cmpb  r72, #0x3f
            jnh   ls_f
            ldb   r72, #0x3f
    ls_f:   andb  r70, #0xc0
            orb   r70, r72
            sjmp  ls_w
    ls_i:   ldbze r70, ARPBPM           ; internal: TN * BPM * 64 / 1200 (+ remainder LACC)
            add   r70, #40
            shl   r70, #6
            ld    r72, TN
            mulu  r74, r70, r72
            add   r74, LACC
            addc  r76, zero
            ld    r70, #1200
            divu  r74, r70
            st    r76, LACC
            ld    r70, LCC
            add   r70, r74
    ls_w:   ld    r74, r70              ; modulo the cycle
            clr   r76
            divu  r74, r7a
            st    r76, LCC
    ls_x:   ret

    ; pass (~8 ms): LFO (free or synced), then glide / wave sequence / mod matrix / vintage on every partial of
    ; the parts that need it
    mpass:  ldbze r70, LFOSYNC
            cmpb  r70, zero
            je    ps_f
            shl   r70, #1
            ld    r74, lsctab[r70]
            clr   r78                   ; phase = LCC * 65536 / cycle
            ld    r7a, LCC
            divu  r78, r74
            ld    r70, LFOP
            st    r78, LFOP
            cmp   r78, r70
            jc    ps1
            sjmp  ps_sh                 ; wrapped: new S&H value
    ps_f:   ldbze r70, LFOR
            shl   r70, #1
            ld    r72, lfotab[r70]
            add   LFOP, r72
            jnc   ps1
    ps_sh:  lcall rnd                   ; S&H: new value each LFO cycle
            stb   r7e, SH
    ps1:    ld    r70, VPH              ; vintage wander moves on
            add   r70, #2
            st    r70, VPH
            lcall mdmask
            clr   r50
    ps_l:   lcall ppart
            add   r50, #0x0010
            cmp   r50, #0x0080
            jne   ps_l
            ret
    ppart:  clrb  PF
            ldb   r70, GLTIME
            cmpb  r70, zero
            je    pp1
            ldb   r70, GLPART
            lcall scope
            jne   pp1
            orb   PF, #0x01
    pp1:    ldb   r70, WSPAT
            cmpb  r70, zero
            je    pp2
            ldb   r70, WSPART
            lcall scope
            jne   pp2
            orb   PF, #0x02
    pp2:    jbc   MDM, 7, pp3
            ldb   r70, MODP
            lcall scope
            jne   pp3
            orb   PF, #0x04
            clr   r7c
            lcall modsum
    pp3:    ldb   r70, VINT
            cmpb  r70, zero
            je    pp4
            ldb   r70, VINTP
            lcall scope
            jne   pp4
            orb   PF, #0x08
    pp4:    cmpb  PF, zero
            je    pp_x
            ld    r70, #ptick
            st    r70, WCB
            ldb   SVM, int_mask
            andb  int_mask, #0x7f
            lcall walk
            ldb   int_mask, SVM
    pp_x:   ret

    ; ptick: one partial (r54, slot r52) of part r50: glide step, pitch, cutoff / reso (synth), wave (PCM), level
    ptick:  jbc   PF, 0, pk_p
            ld    r70, GL[r54]
            cmp   r70, zero
            je    pk_p
            ld    r72, r70
            jbc   r73, 7, pk_g1
            neg   r72
    pk_g1:  ldbze r74, GLTIME
            ldbze r74, glktab[r74]
            mulu  r78, r72, r74
            ldb   r76, r79
            ldb   r77, r7a
            cmp   r76, zero
            jne   pk_g2
            ld    r76, #1
    pk_g2:  cmp   r76, r72
            jnh   pk_g3
            ld    r76, r72
    pk_g3:  jbs   r71, 7, pk_g4
            sub   r70, r76
            sjmp  pk_g5
    pk_g4:  add   r70, r76
    pk_g5:  st    r70, GL[r54]
    pk_p:   clr   r70
            jbc   PF, 0, pk_p1
            add   r70, GL[r54]
    pk_p1:  jbc   PF, 2, pk_p2
            add   r70, MDP
    pk_p2:  jbc   PF, 3, pk_p3
            push  r70
            lcall vint                  ; -> r70 pitch, VCUT cutoff
            pop   r72
            add   r70, r72
    pk_p3:  ld    r72, PB[r54]
            lcall padd
            st    r72, 0xef40[r54]
            ldb   r70, TY[r54]
            jbs!  r70, 7, pk_pcm
            clr   r7c                   ; synth: cutoff = base + mod + vintage
            clrb  r7e
            jbc   PF, 2, pk_c0
            jbc   MDM, 0, pk_c0
            add   r7c, MDC
            incb  r7e
    pk_c0:  jbc   PF, 3, pk_c1
            add   r7c, VCUT
            incb  r7e
    pk_c1:  cmpb  r7e, zero
            je    pk_r
            ldbze r72, 0xf1c0[r54]      ; a live edit (CC74 / Quick) since our last write moves the base
            ldbze r74, LC[r54]
            cmp   r72, r74
            je    pk_c2
            sub   r72, r74
            ldbze r74, CB[r54]
            add   r72, r74
            ld    r74, #0xff
            lcall clampw
            stb   r72, CB[r54]
    pk_c2:  ldbze r72, CB[r54]
            add   r72, r7c
            ld    r74, #0xff
            lcall clampw
            stb   r72, 0xf1c0[r54]
            stb   r72, 0x0c41[r54]
            stb   r72, LC[r54]
    pk_r:   jbc!  PF, 2, pk_x
            jbc   MDM, 4, pk_lv
            ldbze r72, RB[r54]
            add   r72, MDR
            ld    r74, #30
            lcall clampw
            ldb   r70, r72
            lcall wreso
            sjmp  pk_lv
    pk_pcm: jbc   PF, 1, pk_w
            ldb   r70, WT[r54]
            decb  r70
            stb   r70, WT[r54]
            jne   pk_w
            lcall wstep
    pk_w:   lcall wtarget
            jbc   PF, 2, pk_w1
            jbc   MDM, 2, pk_w1
            addb  r7c, MDW
            andb  r7c, #0x7f
    pk_w1:  cmpb  r7c, OFS[r54]
            je    pk_lv
            lcall wset
    pk_lv:  jbc!  PF, 2, pk_x
            jbc   MDM, 3, pk_x
            ldbze r72, LB[r54]
            sub   r72, MDL
            ld    r74, #0x9b
            lcall clampw
            stb   r72, 0xf180[r54]
    pk_x:   ret

    ; ===================================================================== menu
    ; r70 = key (0xFF = draw). Return r70 = 1 to leave.
    ;   Group +/- : item      Bank +/- : value +/-1      Number +/- : value +/-10      Exit : back / leave
    ;   Edit : open the submenu of a '>' item, else next section (in a submenu: back)
    ;   Part : current part P1..P8 (0xF6CD, as on the Quick screen)
    ui:     lcall init
            cmpb  r70, #0xff
            je!   draw
            ldbze r72, MIDX
            cmpb  r72, #NITEMS
            jnc   u1a
            clrb  r72
    u1a:    cmpb  r70, #0x01
            je    u_exit
            cmpb  r70, #0x0a
            je!   u_part
            cmpb  r70, #0x09
            je    u_sec
            cmpb  r70, #0x05
            je    u_next
            cmpb  r70, #0x0d
            je!   u_prev
            ldb   r76, #1
            cmpb  r70, #0x06
            je!   u_val
            ldb   r76, #0xff
            cmpb  r70, #0x0e
            je!   u_val
            ldb   r76, #10
            cmpb  r70, #0x07
            je!   u_val
            ldb   r76, #0xf6
            cmpb  r70, #0x0f
            je!   u_val
            ljmp  draw
    u_exit: ldb   r70, MPAR
            cmpb  r70, #0xff
            jne   u_up
            ldb   r70, #1               ; top level: leave the menu
            ret
    u_up:   ldbze r72, MPAR             ; submenu: back to its item
            ldb   r70, #0xff
            stb   r70, MPAR
            sjmp  u_st
    u_sec:  ldb   r70, MPAR
            cmpb  r70, #0xff
            jne   u_up
            lcall item
            jbc   r7f, 5, u_s1
            stb   r72, MPAR             ; open the submenu
            incb  r72
            sjmp  u_st
    u_s1:   incb  r72                   ; next item that starts a section
            cmpb  r72, #NITEMS
            jnc   us1
            clrb  r72
    us1:    lcall item
            jbc   r7f, 6, u_s1
            sjmp  u_st
    u_next: ldb   r70, MPAR
            cmpb  r70, #0xff
            je    un_t
            incb  r72                   ; submenu: wrap to its first item
            cmpb  r72, #NITEMS
            jc    un_w
            lcall item
            jbs   r7f, 4, u_st
    un_w:   ldb   r72, MPAR
            incb  r72
            sjmp  u_st
    un_t:   incb  r72                   ; top level: skip submenu items
            cmpb  r72, #NITEMS
            jnc   un_1
            clrb  r72
    un_1:   lcall item
            jbs   r7f, 4, un_t
    u_st:   stb   r72, MIDX
            ljmp  draw
    u_prev: ldb   r70, MPAR
            cmpb  r70, #0xff
            je    up_t
            incb  r70
            cmpb  r70, r72
            je    up_l
            decb  r72
            sjmp  u_st
    up_l:   incb  r72                   ; first item of the submenu: to its last item
            cmpb  r72, #NITEMS
            jc    up_e
            lcall item
            jbs   r7f, 4, up_l
    up_e:   decb  r72
            sjmp  u_st
    up_t:   decb  r72                   ; top level: skip submenu items
            cmpb  r72, #NITEMS
            jnc   up_1
            ldb   r72, #NITEMS-1
    up_1:   lcall item
            jbs   r7f, 4, up_t
            sjmp  u_st
    u_part: ldb   r70, PART
            incb  r70
            cmpb  r70, #8
            jnc   up2
            clrb  r70
    up2:    stb   r70, PART
            ljmp  draw
    u_val:  lcall item
            cmpb  r7b, #4
            je!   draw                  ; Info: nothing to edit
            cmpb  r7b, #11
            je!   draw                  ; folder
            cmpb  r7b, #9
            je!   u_rec
            cmpb  r7b, #10
            je!   u_lrn
            jbs!  r7c, 7, draw          ; per-part item on the rhythm part: no edit
            ldbze r70, [r74]
            ldbse r72, r76
            add   r70, r72
            ldbze r72, 20[r78]          ; min
            jbs   r71, 7, uv0
            cmp   r70, r72
            jge   uv1
    uv0:    ld    r70, r72
    uv1:    ldbze r72, r7a
            cmp   r70, r72
            jnh   uv2
            ld    r70, r72
    uv2:    stb   r70, [r74]
            cmpb  r7b, #3
            jne   uv3
            ldbze r50, r7c
            shl   r50, #4
            lcall wave_apply
            sjmp  draw
    uv3:    jbc! r7f, 7, draw
            lcall all_off
            sjmp  draw
    ; Seq Record: Bank+ Off -> Step (-> Live before the first step), Bank- stop; in Step, Number+ rest,
    ; Number- tie
    u_rec:  ldb   r71, RECM
            cmpb  r70, #0x06
            jne   ur1
            cmpb  r71, #2
            jc    draw
            cmpb  r71, #1
            je    ur_lv
            lcall all_off               ; start: the arp stops, keys are recorded
            ldb   r70, #1
            sjmp  ur_s
    ur_lv:  ldb   r70, RPOS
            cmpb  r70, zero
            jne   draw
            ldb   r70, #2
    ur_s:   stb   r70, RECM
            stb   zero, RPOS
            clrb  AH
            sjmp  draw
    ur1:    cmpb  r71, zero
            je    draw
            cmpb  r70, #0x0e
            jne   ur2
            lcall rec_end
            sjmp  draw
    ur2:    cmpb  r71, #1
            jne   draw
            ldb   r71, RPOS
            ldb   r70, #0x80            ; Number+: rest
            cmpb  r76, #10
            je    ur3
            cmpb  r71, zero             ; Number-: tie (not as the first step)
            je    draw
            ldb   r70, #0x81
    ur3:    lcall rput
            sjmp  draw
    ; Chord Learn: Bank+ / Number+ arm, Bank- / Number- cancel
    u_lrn:  clrb  r70
            jbs   r76, 7, ul1
            incb  r70
    ul1:    stb   r70, LARM
            stb   zero, LCNT
            stb   zero, LHC

    draw:   ldbze r72, MIDX
            cmpb  r72, #NITEMS
            jnc   dr0
            clrb  r72
    dr0:    ldb   r70, MPAR             ; a submenu item with no submenu open: show its '>' item
            cmpb  r70, #0xff
            jne   dr1a
    dr0a:   lcall item
            jbc   r7f, 4, dr1a
            decb  r72
            sjmp  dr0a
    dr1a:   stb   r72, MIDX
            lcall item
            ld    r76, #LCDBUF
            stb   zero, [r76]+          ; LCD address byte: line 1
            ldb   r7e, #16
    dr1:    ldb   r70, [r78]+
            stb   r70, [r76]+
            djnz  r7e, dr1
            sub   r78, #16
            ld    r72, r76              ; line 2
            ldb   r70, #0x20
            ldb   r7e, #16
    dr2:    stb   r70, [r76]+
            djnz  r7e, dr2
            stb   zero, [r76]
            ld    r76, r72
            ldb   r7e, [r74]
            cmpb  r7b, #4
            je!   d_inf
            cmpb  r7b, #1
            je!   d_nm
            cmpb  r7b, #2
            je!   d_all
            cmpb  r7b, #5
            je!   d_off
            cmpb  r7b, #6
            je!   d_sg
            cmpb  r7b, #7
            je!   d_p
            cmpb  r7b, #8
            je!   d_on
            cmpb  r7b, #9
            je!   d_rec
            cmpb  r7b, #10
            je!   d_lrn
            cmpb  r7b, #11
            je!   d_fold
            push  r7e                   ; number (0, 3): value + display offset, bar
            addb  r7e, 21[r78]
            lcall put3
            pop   r7e
            inc   r76
            subb  r7e, 20[r78]          ; bar: 10 chars = max
            mulub r70, r7e, #10
            ldb   r72, r7a
            subb  r72, 20[r78]
            divub r70, r72
            ldb   r7e, r70
            cmpb  r7e, zero
            je    d_bar
            ldb   r70, #0xff
    d_b1:   stb   r70, [r76]+
            djnz  r7e, d_b1
    d_bar:  cmpb  r7b, #3
            jne!  show
            ldb   r70, #0x50            ; 'P'
            stb   r70, LCDBUF+31
            ldb   r70, r7c
            addb  r70, #0x31
            jbc   r7c, 7, d_p3
            ldb   r70, #0x2d            ; rhythm part: '-'
    d_p3:   stb   r70, LCDBUF+32
            sjmp  show
    d_nm:   ldbze r70, r7e              ; named: 8-char names
            shl   r70, #3
            add   r70, 22[r78]
            ldb   r7e, #8
    d_c1:   ldb   r72, [r70]+
            stb   r72, [r76]+
            djnz  r7e, d_c1
            sjmp  show
    d_off:  cmpb  r7e, zero
            jne   d_p1
            ld    r70, #0x664f          ; 'Of'
            lcall put2
            stb   r71, [r76]            ; 'f'
            sjmp  show
    d_all:  cmpb  r7e, zero
            jne   d_p1
            ld    r70, #0x6c41          ; 'Al'
            lcall put2
            stb   r71, [r76]
            sjmp  show
    d_p:    incb  r7e
    d_p1:   ldb   r70, #0x50
            stb   r70, [r76]+
            addb  r7e, #0x30
            stb   r7e, [r76]
            sjmp  show
    d_sg:   ldb   r70, #0x2b            ; signed: '+' / '-'
            subb  r7e, #63
            jbc   r7e, 7, d_s1
            negb  r7e
            ldb   r70, #0x2d
    d_s1:   cmpb  r7e, zero
            jne   d_s2
            ldb   r70, #0x20
    d_s2:   stb   r70, [r76]+
            ldbze r70, r7e
            divub r70, #10
            addb  r70, #0x30
            stb   r70, [r76]+
            addb  r71, #0x30
            stb   r71, [r76]
            sjmp  show
    ; Info: RAM test (write a5/5a, read back, restore) at 0xF500 0xF6A0 0xF740 0xF7F0, the part byte 0xF6CD
    d_inf:  ld    r78, #inftxt
            ldb   r7e, #4
    d_i1:   ldb   r70, [r78]+
            stb   r70, [r76]+
            djnz  r7e, d_i1
            ld    r74, #0xf500
            lcall rtest
            ld    r74, #0xf6a0
            lcall rtest
            ld    r74, #0xf740
            lcall rtest
            ld    r74, #0xf7f0
            lcall rtest
            ld    r70, #0x5020          ; ' P'
            lcall put2
            ldb   r7e, PART
            ldb   r70, r7e
            shrb  r70, #4
            lcall hexd
            ldb   r70, r7e
            lcall hexd
            ld    r70, #0x7620          ; ' v'
            lcall put2
            ld    r70, #0x3031          ; '10'
            lcall put2
            sjmp  show
    d_on:   cmpb  r7e, zero             ; number, 0 = Off
            je    d_of
            addb  r7e, 21[r78]
            lcall put3
            sjmp  show
    d_of:   ld    r70, #0x664f          ; 'Of'
            lcall put2
            stb   r71, [r76]            ; 'f'
            sjmp  show
    d_rec:  ldbze r70, RECM             ; 'Step 05/32' (Off: the length)
            shl   r70, #2
            add   r70, #rectxt
            ldb   r7e, #4
    d_r1:   ldb   r72, [r70]+
            stb   r72, [r76]+
            djnz  r7e, d_r1
            inc   r76
            ldb   r7e, RPOS
            ldb   r70, RECM
            cmpb  r70, zero
            jne   d_r2
            ldb   r7e, SEQLEN
    d_r2:   ldbze r70, r7e
            divub r70, #10
            addb  r70, #0x30
            stb   r70, [r76]+
            addb  r71, #0x30
            stb   r71, [r76]+
            ld    r70, #0x332f          ; '/3'
            lcall put2
            ldb   r70, #0x32            ; '2'
            stb   r70, [r76]
            sjmp  show
    d_lrn:  ld    r70, #lrntx0          ; armed / idle text
            ldb   r72, LARM
            cmpb  r72, zero
            je    d_t
            ld    r70, #lrntx1
            sjmp  d_t
    d_fold: ld    r70, #foldtx
    d_t:    ldb   r72, [r70]+
            cmpb  r72, zero
            je    show
            stb   r72, [r76]+
            sjmp  d_t
    hexd:   andb  r70, #0x0f
            addb  r70, #0x30
            cmpb  r70, #0x3a
            jnc   hx1
            addb  r70, #7
    hx1:    stb   r70, [r76]+
            ret
    rtest:  ldb   r72, [r74]
            ldb   r70, #0xa5
            stb   r70, [r74]
            ldb   r71, [r74]
            cmpb  r71, r70
            jne   rt_ng
            ldb   r70, #0x5a
            stb   r70, [r74]
            ldb   r71, [r74]
            cmpb  r71, r70
            jne   rt_ng
            ldb   r70, #0x6f            ; 'o'
            sjmp  rt_w
    rt_ng:  ldb   r70, #0x58            ; 'X'
    rt_w:   stb   r72, [r74]
            stb   r70, [r76]+
            ret
    ; put2: r70, r71 at [r76]+ (byte stores: the LCD buffer pointer can be odd)
    put2:   stb   r70, [r76]+
            stb   r71, [r76]+
            ret
    show:   ld    r78, #LCDBUF
            lcall API_LCD
            clrb  r70
            ret

    ; put3: 3 digits of r7e at [r76]+
    put3:   ldbze r70, r7e
            divub r70, #100
            addb  r70, #0x30
            stb   r70, [r76]+
            ldbze r70, r71
            divub r70, #10
            addb  r70, #0x30
            stb   r70, [r76]+
            addb  r71, #0x30
            stb   r71, [r76]+
            ret

    ; item r72 -> r78 entry, r74 setting byte, r7a max, r7b kind (low 4 bits), r7f kind flags,
    ; r7c part (bit 7 = rhythm part / none picked, for kind 3)
    item:   mulub r78, r72, #24
            add   r78, #items
            ld    r74, 16[r78]
            ldb   r7a, 18[r78]
            ldb   r7f, 19[r78]
            ldb   r7b, r7f
            andb  r7b, #0x0f
            ldbze r7c, PART
            cmpb  r7b, #3
            je    it_3
            clr   r7c                   ; (not per part: always editable)
            ret
    it_3:   cmpb  r7c, #8
            jnc   it_p
            ldb   r7c, #0x80
            ret
    it_p:   add   r74, r7c
    it_x:   ret
    ''')
    # ---- data
    lfo, glk, spd = _tables()
    db = lambda bs: ''.join(' db %s\n' % ', '.join(str(b) for b in bs[i:i + 16]) for i in range(0, len(bs), 16))
    dw = lambda ws: ''.join(' dw %s\n' % ', '.join(str(w) for w in ws[i:i + 8]) for i in range(0, len(ws), 8))
    name8 = lambda ns: db(b''.join(n.ljust(8)[:8].encode() for n in ns))
    named, named_src = {}, ''
    for _, _, _, _, _, _, names in ITEMS:
        if names and tuple(names) not in named:
            named[tuple(names)] = 'nm%d' % len(named)
            named_src += '%s:\n%s' % (named[tuple(names)], name8(names))
    items = ''
    for name, s, mx, kind, mn, dofs, names in ITEMS:
        addr = SET[s[0]] + s[1] if isinstance(s, tuple) else SET[s]
        items += db(name.ljust(16)[:16].encode()) + ' dw %d\n db %d, %d, %d, %d\n dw %s\n' % (
            addr, mx, kind, mn, dofs, named[tuple(names)] if names else 0)
    wsteps, wsp = '', ''
    for i, (n, steps, mode) in enumerate(WSEQS):
        if mode == 3:
            wsp += ' dw %d\n db 8, 0\n' % SET['WSUSER']
        else:
            wsteps += 'wst%d:\n%s' % (i, db(steps))
            wsp += ' dw wst%d\n db %d, %d\n' % (i, len(steps), mode)
    rates = db([x for _, spb, cps in ARP_RATES for x in (0, spb, cps)])
    chiv = db([b for _, iv in CHORDS[:NFIX] for b in (iv + [0, 0, 0, 0])[:4]])
    sct = db([b for _, sc in SCALES for b in sc + [x + 12 for x in sc] + [0, 0]])
    rng = __import__('random').Random(110)
    ntab = db([rng.randint(-63, 63) & 0xff for _ in range(256)])        # vintage noise points
    lsc = dw([c * 64 for _, c in LFO_SYNC])
    blocks = ''.join(' dw %d, %d\n' % (st, en) for st, en, _ in SETTINGS) + ' dw 0\n'
    ban = (banner[0].ljust(16)[:16] + banner[1].ljust(16)[:16]).encode()
    # IC15 page 0x27: code 0x8000-0xAFFF, jump table at 0xB000 (fixed), data 0xB020-0xBFFF
    C.src('''
            pad   0xb000
            dw    MAGIC
            ljmp  banner                ; 0xB002 (also the old --ic15-hook banner entry)
            ljmp  ui                    ; 0xB005
            ljmp  note_on               ; 0xB008
            ljmp  note_off              ; 0xB00B
            ljmp  cc_wave               ; 0xB00E
            ljmp  partial               ; 0xB011
            ljmp  tick                  ; 0xB014
            ljmp  at_in                 ; 0xB017
            ljmp  cc_in                 ; 0xB01A
            ret                         ; 0xB01D- spare
            ret
            ret
    ''')
    C.src('even\nitems:\n' + items +
          'even\nsrctab:\n dw 0, s_mw, s_at, s_vel, s_key, s_lfo, s_sh, s_cca, s_ccb\n' +
          'dsttab:\n dw d_cut, d_pit, d_wav, d_lev, d_res\n' +
          'arpjt:\n dw nx_up, nx_dn, nx_ud, nx_rnd, nx_pl, nx_sq\n' +
          'lsctab:\n' + lsc + 'sblk:\n' + blocks +
          'lfotab:\n' + dw(lfo) + 'wsp:\n' + wsp + 'glktab:\n' + db(glk) + 'spdtab:\n' + db(spd) +
          'rates:\n' + rates + 'chiv:\n' + chiv + 'sctab:\n' + sct + 'ntab:\n' + ntab + wsteps + named_src +
          'inftxt:\n db 77, 101, 109, 32\n' +
          'rectxt:\n' + db(''.join(REC_MODES).encode()) +
          'lrntx0:\n' + db(b'Bank+ = learn\0') + 'lrntx1:\n' + db(b'Play a chord\0') +
          'foldtx:\n' + db(b'Edit = open\0') +
          'sdef:\n' + db(SET_DEFAULTS) +
          'bantxt:\n db 0\n%s db 0\n' % db(ban))
    img = C.assemble()
    assert C.org + len(img) <= 0xc000, hex(C.org + len(img))
    return [(CODE_ORG, img[:CODE_END - CODE_ORG]), (CODE_END, img[CODE_END - CODE_ORG:])], C


if __name__ == '__main__':
    p, lab = build_ic19()
    for a, b in p: print('IC19 0x%04x %3d B' % (a, len(b)))
    segs, C = build_ic15(lab)
    code_end = max(v for v in C.labels.values() if v < 0xb000)
    print('IC15 code 0x8000-0x%04x (%d B free), data 0xb020-0x%04x (%d B free)' % (
        code_end, 0xb000 - code_end, 0xb000 + len(segs[1][1]), 0x1000 - len(segs[1][1])))
