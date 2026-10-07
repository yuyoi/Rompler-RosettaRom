"""Rosetta OS extension: new features in IC15, called from small hooks in IC19 (two-chip mod, on top of the IC19-only
v6 mod in ic19_quick.py). See IC19_MAP.md, "Rosetta (IC15 code)".

  python patch_ic19.py ctrl/ic19.bin -o ctrl/ic19_ros.bin --quick --cc --rosetta ...
  python patch_ic15.py my_ic15.bin -o my_ic15_ros.bin --rosetta

IC19 side (build_ic19): a call system into IC15 page 0x27 (CPU 0xB000) that checks the magic word first, so a stock
IC15 just means "feature off", plus hooks:
  - Quick screen: Edit opens the Rosetta menu (raw UI state handler)
  - MIDI note on / off (jtab_241C) -> chord memory
  - CC70 -> wave scan (PCM partials of the part)
  - end of the per-partial note-on setup (0x3BB4) -> drift, random cutoff, wave offset
  - call19 / rd20: IC15 code calling IC19 routines (they may leave another page mapped) and reading IC15 page 0x20
IC15 side (build_ic15): jump table at 0xB002 (fixed, so IC15 can be updated without reburning IC19), menu, features.
Settings live in battery-backed RAM 0xF610-0xF66F (never used by the stock OS), with a magic byte.
"""
from mcs96_asm import Asm

MAGIC = 0x5a1c
RB = 0xf610
RAM = dict(R_MAGIC=RB + 0, MIDX=RB + 1, DRIFTP=RB + 2, RCUT=RB + 3, RWAVE=RB + 4, CHORD=RB + 5, CHPART=RB + 6,
           CHI=RB + 7, LASTSLOT=RB + 8, TGT=RB + 10, LFSR=RB + 12, NP=RB + 14, NC=RB + 16, NW=RB + 17,
           WAVE=RB + 18, OFS=RB + 32, R_END=RB + 96)
RAM_INIT_LEN = 96
IC15_ENTRY = dict(E_BANNER=0xb002, E_UI=0xb005, E_NON=0xb008, E_NOFF=0xb00b, E_WAVE=0xb00e, E_PART=0xb011)
STOCK = dict(NOTE_ON=0x24fc, NOTE_OFF=0x245d, ALL_OFF=0x3de2, POP_STATE=0x5391, REDRAW=0x53cb, API_LCD=0x208a,
             PART=0xf6cd, LCDBUF=0xf6ab)
WAVE_CC = 70
HOOK_PART = 0x3bb4          # st zero,0xf100[r54] (5 bytes), then ret at 0x3bb9: end of per-partial note-on setup


def build_ic19():
    """-> (patches, labels). Needs the dead demo code areas 0x7F57-0x7FFF and 0x3FB7-0x401B."""
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
    lab = dict(A.labels, **B.labels)
    patches = [(0x7f57, a), (0x3fb7, b),
               (HOOK_PART, bytes([0xe7]) + ((lab['h_part'] - (HOOK_PART + 3)) & 0xffff).to_bytes(2, 'little') + b'\xfd\xfd'),
               (0x241c, lab['h_noff'].to_bytes(2, 'little')), (0x241e, lab['h_non'].to_bytes(2, 'little')),
               (0x3bce + 2 * WAVE_CC, lab['h_wave'].to_bytes(2, 'little'))]
    return patches, lab


CHORDS = [('Off', []), ('Octave', [12]), ('Fifth', [7]), ('5th+Oct', [7, 12]), ('Major', [4, 7]),
          ('Minor', [3, 7]), ('Sus4', [5, 7]), ('Major7', [4, 7, 11]), ('Minor7', [3, 7, 10]),
          ('Dom7', [4, 7, 10]), ('Minor9', [3, 7, 10, 14]), ('Dim', [3, 6])]
# name (16), RAM byte, max, kind (0 number, 1 chord name, 2 part All/P1-8, 3 per part, live)
ITEMS = [('Wave Scan (CC70)', 'WAVE', 127, 3), ('Random Wave', 'RWAVE', 127, 0), ('Drift Pitch', 'DRIFTP', 31, 0),
         ('Random Cutoff', 'RCUT', 100, 0), ('Chord', 'CHORD', len(CHORDS) - 1, 1), ('Chord Part', 'CHPART', 8, 2)]


def build_ic15(ic19_labels, banner=(' ROSETTA OS  v7 ', ' D-110  + IC15  ')):
    syms = dict(MAGIC=MAGIC, **RAM, **STOCK, CALL19=ic19_labels['call19'], RD20=ic19_labels['rd20'],
                NITEMS=len(ITEMS), RAM_INIT_LEN=RAM_INIT_LEN)
    C = Asm(0xb000, syms).src('''
            dw    MAGIC
            ljmp  banner                ; 0xB002 (also the old --ic15-hook banner entry)
            ljmp  ui                    ; 0xB005
            ljmp  note_on               ; 0xB008
            ljmp  note_off              ; 0xB00B
            ljmp  cc_wave               ; 0xB00E
            ljmp  partial               ; 0xB011
            ret                         ; 0xB014- spare entries
            ret
            ret

    ; ---- settings RAM: battery-backed, garbage on a fresh unit -> zero it once (all features off)
    ramchk: push  r70
            ldb   r70, R_MAGIC
            cmpb  r70, #0xa7
            je    rc_ok
            ld    r70, #R_MAGIC
    rc_z:   stb   zero, [r70]+
            cmp   r70, #R_END
            jne   rc_z
            ldb   r70, #0xa7
            stb   r70, R_MAGIC
    rc_ok:  pop   r70
            ret

    banner: lcall ramchk
            ld    r78, #bantxt
            lcall API_LCD
            ret

    ; ---- random: 16-bit Galois LFSR, 8 steps per call -> r7e:r7f
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

    ; newnote: per-note random offsets (same for all partials of a note, so ring-mod pairs stay in tune)
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
            ret

    ; waddr: r74 = wave byte, r7d = PCM bank -> r74 = address of its 4-byte IC15 wave table entry (page 0x20)
    waddr:  andb  r74, #0x7f
            ldb   r75, r7d
            shlb  r74, #1
            shl   r74, #1
            add   r74, #0x8900
            ret

    ; wset: PCM partial r54 plays wave (block wave + r7c) & 0x7f; the pitch base 0xEF40 moves by the
    ; difference of the two waves' pitch words so it stays in tune. OFS[p] = offset now applied.
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
            ld    r72, r70              ; pos, len
            add   r74, #2
            lcall RD20
            sub   r70, r76
            add   r70, 0xef40[r54]
            cmp   r70, #0xe800
            jnh   ws1
            ld    r70, #0xe800
    ws1:    st    r70, 0xef40[r54]
            orb   r73, #0x08            ; as 0x36ed
            stb   r73, 0xef81[r54]
            ldb   r70, 0xef80[r54]      ; LA32 takes 0x0D00/0x0D01 as a pair
            stb   r70, 0x0d00[r54]
            stb   r73, 0x0d01[r54]
            stb   r72, 0xf1c0[r54]
            stb   r72, 0x0c41[r54]
            ret

    ; wave_apply: every sounding PCM partial of part r50 gets offset WAVE[part] (LA32 interrupt masked)
    wave_apply:
            ld    r7e, r50
            shr   r7e, #4
            ldb   r7c, WAVE[r7e]
            ldb   r7e, int_mask
            andb  int_mask, #0x7f
            ldbze r52, 0xf285[r50]
    wa_n:   cmpb  r52, #0xff
            je    wa_d
            ldbze r54, 0xf440[r52]
    wa_p:   cmpb  r54, #0xff
            je    wa_nn
            ldb   r70, 0xef80[r54]
            jbc   r70, 7, wa_pn         ; synth partial: no wave
            push  r7c
            push  r7e
            lcall wset
            pop   r7e
            pop   r7c
    wa_pn:  ldbze r54, 0xee40[r54]
            sjmp  wa_p
    wa_nn:  ldbze r52, 0xf3c0[r52]
            sjmp  wa_n
    wa_d:   ldb   int_mask, r7e
            ret

    ; ---- CC70 (MIDI per-part loop: r46 value, r50 part*16; keep r42, r44-r46, r50)
    cc_wave: lcall ramchk
            cmp   r50, #0x0080
            jc    cw_x
            ldb   rc7, #0x08            ; MIDI LED
            ld    r7e, r50
            shr   r7e, #4
            stb   r46, WAVE[r7e]
            lcall wave_apply
    cw_x:   ret

    ; ---- end of per-partial note-on setup: r54 partial*2, r56 block, r50 part*16, r52 note slot.
    ; Free: r70-r79 only; LA32 interrupt already masked; pitch register not written yet.
    partial: cmp  r50, #0x0080
            jnc   pt_go
            ret                         ; rhythm part: untouched (its block may be in another page)
    pt_go:  lcall ramchk
            push  r7a
            push  r7c
            push  r7e
            cmpb  r52, LASTSLOT
            je    pt_have
            stb   r52, LASTSLOT
            lcall newnote
    pt_have: ldb  r70, 0xef80[r54]
            jbs   r70, 7, pt_pcm
            ldb   r70, NC               ; synth: random cutoff
            cmpb  r70, zero
            je    pt_pitch
            ldbze r72, 0xf1c0[r54]
            ldbse r74, r70
            add   r72, r74
            jbc   r73, 7, pt_c1
            clr   r72
    pt_c1:  cmp   r72, #0x00ff
            jnh   pt_c2
            ld    r72, #0x00ff
    pt_c2:  stb   r72, 0xf1c0[r54]
            stb   r72, 0x0c41[r54]
            sjmp  pt_pitch
    pt_pcm: stb   zero, OFS[r54]        ; the note-on just set the timbre's own wave
            ld    r70, r50
            shr   r70, #4
            ldb   r7c, WAVE[r70]
            addb  r7c, NW
            andb  r7c, #0x7f
            je    pt_pitch
            lcall wset
    pt_pitch: ld  r70, NP
            cmp   r70, zero
            je    pt_d
            ld    r72, 0xef40[r54]
            add   r72, r70
            jbc   r71, 7, pt_p1
            jc    pt_p2                 ; down, no borrow
            clr   r72
            sjmp  pt_p2
    pt_p1:  cmp   r72, #0xe800
            jnh   pt_p2
            ld    r72, #0xe800
    pt_p2:  st    r72, 0xef40[r54]
    pt_d:   pop   r7e
            pop   r7c
            pop   r7a
            ret

    ; ---- MIDI note on / off (per part: r45 note, r46 velocity, r50 part*16; keep r42, r44-r46, r50)
    note_on: ld   r70, #NOTE_ON
            sjmp  chord
    note_off: ld  r70, #NOTE_OFF
    chord:  lcall ramchk
            st    r70, TGT
            ldb   r70, #0xff
            stb   r70, LASTSLOT         ; next partial setup = new note: new random offsets
            ldbze r7c, CHORD
            cmpb  r7c, zero
            je    ch_one
            cmpb  r7c, #NCHORDS
            jc    ch_one
            cmp   r50, #0x0080
            jc    ch_one
            ldb   r70, CHPART
            cmpb  r70, zero
            je    ch_many
            ld    r72, r50
            shr   r72, #4
            incb  r72
            cmpb  r72, r70
            jne   ch_one
    ch_many: push r44                   ; r45 = root note
            lcall CALL19
            stb   zero, CHI
    ch_l:   ldbze r78, CHORD
            shl   r78, #2
            ldbze r70, CHI
            add   r78, r70
            ldb   r70, chiv[r78]
            cmpb  r70, zero
            je    ch_d
            ld    r44, 0[sp]
            addb  r45, r70
            cmpb  r45, #0x80
            jc    ch_n
            ldb   r70, #0xff
            stb   r70, LASTSLOT
            lcall CALL19
    ch_n:   ldb   r70, CHI
            incb  r70
            stb   r70, CHI
            cmpb  r70, #4
            jne   ch_l
    ch_d:   pop   r44
            ret
    ch_one: ljmp  CALL19

    ; all notes off on parts 1-8 (chord changed while notes may be held)
    all_off: ld   r70, #ALL_OFF
            st    r70, TGT
            clr   r50
    ao_l:   lcall CALL19
            add   r50, #0x0010
            cmp   r50, #0x0080
            jne   ao_l
            ret

    ; ---- Rosetta menu. r70 = key (0xFF = draw). Return r70 = 1 to leave.
    ;   Group +/- : item      Bank +/- : value +/-1      Number +/- : value +/-10      Exit : back
    ui:     lcall ramchk
            cmpb  r70, #0xff
            je!   draw
            cmpb  r70, #0x01
            jne   u1
            ret
    u1:     ldbze r72, MIDX
            cmpb  r72, #NITEMS
            jnc   u1a
            clrb  r72
    u1a:    cmpb  r70, #0x05
            je    u_next
            cmpb  r70, #0x0d
            je    u_prev
            ldb   r76, #1
            cmpb  r70, #0x06
            je    u_val
            ldb   r76, #0xff
            cmpb  r70, #0x0e
            je    u_val
            ldb   r76, #10
            cmpb  r70, #0x07
            je    u_val
            ldb   r76, #0xf6
            cmpb  r70, #0x0f
            je    u_val
            sjmp  draw
    u_next: incb  r72
            cmpb  r72, #NITEMS
            jnc   u_st
            clrb  r72
            sjmp  u_st
    u_prev: decb  r72
            cmpb  r72, #NITEMS
            jnc   u_st
            ldb   r72, #NITEMS-1
    u_st:   stb   r72, MIDX
            sjmp  draw
    u_val:  lcall item
            jbs   r7c, 7, draw          ; per-part item on the rhythm part: no edit
            ldbze r7e, [r74]
            ldbse r70, r76
            add   r7e, r70
            jbc   r7f, 7, uv1
            clr   r7e
    uv1:    ldbze r70, r7a
            cmp   r7e, r70
            jnh   uv2
            ld    r7e, r70
    uv2:    stb   r7e, [r74]
            cmpb  r7b, #3
            jne   uv3
            ldbze r50, r7c
            shl   r50, #4
            lcall wave_apply
            sjmp  draw
    uv3:    cmpb  r7b, #1
            jne   draw
            lcall all_off

    draw:   ldbze r72, MIDX
            cmpb  r72, #NITEMS
            jnc   dr0
            clrb  r72
            stb   r72, MIDX
    dr0:    lcall item
            ld    r76, #LCDBUF
            stb   zero, [r76]+          ; LCD address byte: line 1
            ldb   r7e, #16
    dr1:    ldb   r70, [r78]+
            stb   r70, [r76]+
            djnz  r7e, dr1
            ld    r72, r76              ; line 2
            ldb   r70, #0x20
            ldb   r7e, #16
    dr2:    stb   r70, [r76]+
            djnz  r7e, dr2
            stb   zero, [r76]
            ld    r76, r72
            ldb   r7e, [r74]
            cmpb  r7b, #1
            je    d_ch
            cmpb  r7b, #2
            je    d_pt
            lcall put3
            inc   r76
            mulub r70, r7e, #10         ; bar: 10 chars = max
            divub r70, r7a
            ldb   r7e, r70
            cmpb  r7e, zero
            je    d_bar
            ldb   r70, #0xff
    d_b1:   stb   r70, [r76]+
            djnz  r7e, d_b1
    d_bar:  cmpb  r7b, #3
            jne   show
            ldb   r70, #0x50            ; 'P'
            stb   r70, LCDBUF+31
            ldb   r70, r7c
            addb  r70, #0x31
            jbc   r7c, 7, d_p3
            ldb   r70, #0x2d            ; rhythm part: '-'
    d_p3:   stb   r70, LCDBUF+32
            sjmp  show
    d_ch:   ldbze r78, r7e
            shl   r78, #3
            add   r78, #chname
            ldb   r7e, #8
    d_c1:   ldb   r70, [r78]+
            stb   r70, [r76]+
            djnz  r7e, d_c1
            sjmp  show
    d_pt:   cmpb  r7e, zero
            jne   d_p1
            ld    r70, #0x6c41          ; 'Al'
            st    r70, [r76]+
            ldb   r70, #0x6c
            stb   r70, [r76]
            sjmp  show
    d_p1:   ldb   r70, #0x50
            stb   r70, [r76]+
            addb  r7e, #0x30
            stb   r7e, [r76]
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

    ; item r72 -> r78 entry (name), r74 RAM byte, r7a max, r7b kind, r7c part (bit 7 = rhythm part)
    item:   mulub r78, r72, #20
            add   r78, #items
            ld    r74, 16[r78]
            ldb   r7a, 18[r78]
            ldb   r7b, 19[r78]
            ldbze r7c, PART
            cmpb  r7b, #3
            jne   it_x
            cmpb  r7c, #8
            jnc   it_p
            ldb   r7c, #0x80
            ret
    it_p:   add   r74, r7c
    it_x:   ret
    ''')
    # data
    items = ''.join("db %s\n dw %s\n db %d, %d\n" % (', '.join(str(b) for b in n.ljust(16)[:16].encode()), r, m, k)
                    for n, r, m, k in ITEMS)
    chname = ''.join('db %s\n' % ', '.join(str(b) for b in n.ljust(8)[:8].encode()) for n, _ in CHORDS)
    chiv = ''.join('db %s\n' % ', '.join(str(b) for b in (iv + [0, 0, 0, 0])[:4]) for _, iv in CHORDS)
    ban = (banner[0].ljust(16)[:16] + banner[1].ljust(16)[:16]).encode()
    C.src('items:\n' + items + 'chname:\n' + chname + 'chiv:\n' + chiv +
          'bantxt:\n db 0\n db %s\n db 0\n' % ', '.join(str(b) for b in ban))
    C.syms['NCHORDS'] = len(CHORDS)
    code = C.assemble()
    assert len(code) <= 0x1000, len(code)
    return code, C


if __name__ == '__main__':
    p, lab = build_ic19()
    for a, b in p: print('IC19 0x%04x %3d B' % (a, len(b)))
    code, C = build_ic15(lab)
    print('IC15 0x1F000 %d B' % len(code))
