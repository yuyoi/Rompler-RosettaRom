"""Rosetta ROM Studio v0.1 - swap single waves in a Roland D-110 (IC8 drums, IC7 instruments, IC12 names).
Pick a wave, drop in a WAV, rename, BUILD -> patched ROM images for your programmer. Hardware-untested.
File menu: import ROM dumps, import a folder of WAVs (named 003_..., or by wave name), export all originals,
save/open project, build. Look and feel follows U110 RomHex Studio."""
import os, sys, glob, wave, io, json, re
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import numpy as np
from rosetta_d110 import rom_to_log, log_to_rom, log_to_lin, lin_to_log
from swap_ic8 import read_wav
try:
    import winsound
except ImportError:
    winsound = None

HERE = os.path.dirname(os.path.abspath(__file__)); os.chdir(HERE)
APP = 'Rosetta ROM Studio'; EXT = '.rosetta'; CFG = os.path.join(HERE, 'rosetta_config.json')
FULL = 2.0 ** (32766 / 2048); RATE = 32000; NW = 128
PANEL, PANEL_HI, RECESS, EDGE = '#1d2228', '#2a3038', '#12161a', '#0a0c0e'
TEXT, DIM, SILK = '#eef1f3', '#8a96a0', '#ffffff'
RED, AMBER, BLUE = '#c8322a', '#6ec8e8', '#6ec8e8'
LCD_A, LCD_B, LCD_CELL, LCD_INK = '#94ec44', '#5cc41c', '#80da32', '#10280a'
WAVE_BG, WAVE_FG, GRID, NEW_COL = '#0c0f0d', '#8fe05a', '#161d17', '#f0b12a'


def apply_theme(root):
    st = ttk.Style(root); st.theme_use('clam'); root.configure(bg=PANEL)
    st.configure('.', background=PANEL, foreground=TEXT, fieldbackground=RECESS, bordercolor=EDGE, lightcolor=PANEL_HI,
                 darkcolor=EDGE, troughcolor=RECESS, focuscolor=AMBER, selectbackground=AMBER, selectforeground='#111',
                 insertcolor=TEXT, arrowcolor=TEXT, font=('Segoe UI', 9))
    st.configure('TLabelframe', background=PANEL, bordercolor='#46494e')
    st.configure('TLabelframe.Label', background=PANEL, foreground=SILK, font=('Arial', 8, 'bold'))
    st.configure('TButton', background='#3a3f46', foreground=TEXT, bordercolor=EDGE, lightcolor='#50565e', darkcolor='#1a1d21',
                 padding=(9, 3), font=('Arial', 9, 'bold'))
    st.map('TButton', background=[('pressed', '#23272c'), ('active', '#474d55')])
    st.configure('Build.TButton', background='#3a4048', foreground=BLUE, font=('Bahnschrift', 13, 'bold'), padding=(20, 10),
                 lightcolor='#4d545d', darkcolor='#16191d', bordercolor=BLUE)
    st.map('Build.TButton', background=[('pressed', '#23272c'), ('active', '#454c55')])
    st.configure('Treeview', background=RECESS, fieldbackground=RECESS, foreground=TEXT, rowheight=21, bordercolor=EDGE)
    st.map('Treeview', background=[('selected', '#2f6f8a')], foreground=[('selected', '#ffffff')])
    st.configure('Treeview.Heading', background=PANEL_HI, foreground=SILK, font=('Segoe UI', 8, 'bold'), relief='flat')
    st.map('Treeview.Heading', background=[('active', '#44474c')])
    for w in ('TEntry', 'TCombobox'):
        st.configure(w, fieldbackground=RECESS, foreground=TEXT, background='#4a4d53', arrowcolor=TEXT)
    st.map('TCombobox', fieldbackground=[('readonly', RECESS)], foreground=[('readonly', TEXT)],
           selectbackground=[('readonly', RECESS)], selectforeground=[('readonly', TEXT)])
    st.configure('TCheckbutton', background=PANEL, foreground=TEXT, indicatorbackground=RECESS, indicatorforeground=AMBER)
    st.map('TCheckbutton', background=[('active', PANEL)])
    st.configure('TScrollbar', background='#4a4d53', troughcolor=RECESS, arrowcolor=TEXT)
    st.configure('Dim.TLabel', foreground=DIM); st.configure('Silk.TLabel', foreground=SILK, font=('Arial', 8, 'bold'))
    st.configure('Title.TLabel', foreground=BLUE, font=('Bahnschrift SemiLight SemiConde', 30))
    st.configure('Sub.TLabel', foreground=BLUE, font=('Bahnschrift', 10))
    st.configure('Status.TFrame', background=RECESS); st.configure('Status.TLabel', background=RECESS, foreground=DIM)


def dark_titlebar(win):
    try:
        import ctypes
        win.update_idletasks(); hwnd = ctypes.windll.user32.GetParent(win.winfo_id()); v = ctypes.c_int(1)
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0:
                break
    except Exception:
        pass


class LCD(tk.Canvas):
    CW, CH = 11, 20

    def __init__(self, master, cols=40):
        self.cols = cols
        super().__init__(master, width=cols * self.CW + 26, height=2 * self.CH + 22, bg=PANEL, highlightthickness=0)
        self.lines = ['', '']; self.text_ids = []; W, H = int(self['width']), int(self['height'])
        self.create_rectangle(0, 0, W, H, fill=EDGE, outline='#0b0b0c'); x0, y0, x1, y1 = 6, 6, W - 6, H - 6; n = y1 - y0
        a = [int(LCD_A[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(LCD_B[i:i + 2], 16) for i in (1, 3, 5)]
        for i in range(n):
            t = abs(i / n - 0.35) * 1.3
            self.create_line(x0, y0 + i, x1, y0 + i, fill='#%02x%02x%02x' % tuple(int(a[k] * (1 - t) + b[k] * t) for k in range(3)))
        for r in range(2):
            for c in range(cols):
                cx, cy = 13 + c * self.CW, 11 + r * self.CH
                self.create_rectangle(cx, cy, cx + self.CW - 2, cy + self.CH - 3, fill=LCD_CELL, outline='')

    def set(self, l1, l2):
        lines = [l1[:self.cols].ljust(self.cols), l2[:self.cols].ljust(self.cols)]
        if lines == self.lines:
            return
        self.lines = lines
        for i in self.text_ids:
            self.delete(i)
        self.text_ids = []
        for r, s in enumerate(lines):
            for c, ch in enumerate(s):
                if ch != ' ':
                    self.text_ids.append(self.create_text(13 + c * self.CW + (self.CW - 2) / 2, 11 + r * self.CH + (self.CH - 3) / 2,
                                                          text=ch, fill=LCD_INK, font=('Consolas', 12, 'bold')))


class LEDMeter(tk.Canvas):
    def __init__(self, master, segs=26):
        self.segs = segs
        super().__init__(master, width=segs * 8 + 4, height=18, bg=PANEL, highlightthickness=0); self.set(0)

    def set(self, frac, over=False):
        self.delete('all'); lit = int(round(frac * self.segs))
        for i in range(self.segs):
            p = i / self.segs; on = over or i < lit
            col = ('#ff3b30' if over or p >= 0.9 else '#f0b12a' if p >= 0.7 else '#6fd13a') if on else \
                  ('#3a1e1c' if p >= 0.9 else '#3a3218' if p >= 0.7 else '#1f3319')
            self.create_rectangle(2 + i * 8, 2, 2 + i * 8 + 6, 16, fill=col, outline='')


def load_cfg():
    try:
        return json.load(open(CFG))
    except Exception:
        return {}


class Rom:
    """wave space = IC8 (first 256K samples) then IC7; names + table come from IC12"""

    def __init__(s, ic8=None, ic7=None, ic12=None):
        c = load_cfg()
        ic8 = ic8 or c.get('ic8') or 'dumps/r15179880.ic8.bin'
        ic7 = ic7 or c.get('ic7') or 'dumps/r15179878.ic7.bin'
        ic12 = ic12 or c.get('ic12') or glob.glob('ctrl/Roland D110 (v1.06*/r15179873*.bin')[0]
        s.paths = {'ic8': ic8, 'ic7': ic7, 'ic12': ic12}
        s.ic8 = np.fromfile(ic8, np.uint8); s.ic7 = np.fromfile(ic7, np.uint8); s.ctrl = np.fromfile(ic12, np.uint8)
        if len(s.ic8) != 524288 or len(s.ic7) != 524288 or len(s.ctrl) != 131072:
            raise ValueError('Expected IC8 and IC7 = 512 KB each, IC12 = 128 KB (got %d / %d / %d bytes)' % (len(s.ic8), len(s.ic7), len(s.ctrl)))
        s.wave = np.concatenate([log_to_lin(rom_to_log(s.ic8)), log_to_lin(rom_to_log(s.ic7))])
        s.names = [bytes(s.ctrl[0x100 + 8 * i:0x108 + 8 * i]).decode('latin1') for i in range(NW)]
        s.ent = [(int(s.ctrl[0x900 + 4 * i]) * 0x800, 0x800 << ((int(s.ctrl[0x901 + 4 * i]) >> 4) & 7),
                  bool(s.ctrl[0x901 + 4 * i] & 0x80)) for i in range(NW)]

    def orig(s, i):
        a, n, _ = s.ent[i]; return s.wave[a:a + n]

    def chip(s, i):
        return 'IC8' if s.ent[i][0] < 0x40000 else 'IC7'


def fit(x, n, norm=True):
    x = np.asarray(x, float)[:n]; x = np.concatenate([x, np.zeros(n - len(x))])
    return x / (np.abs(x).max() + 1e-9) * 0.98 if norm else np.clip(x, -1, 1)


def write_wav(fn, x):
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    w = wave.open(fn, 'wb') if isinstance(fn, str) else wave.open(fn, 'wb')
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes((x * 32767).astype(np.int16).tobytes()); w.close()


def wav_bytes(x):
    b = io.BytesIO(); write_wav(b, x); return b.getvalue()


def build(rom, swaps, renames, out='patched', norm=True):
    ic8, ic7, c = rom.ic8.copy(), rom.ic7.copy(), rom.ctrl.copy(); hit8 = hit7 = False
    for i, x in swaps.items():
        a, n, _ = rom.ent[i]; r, base = (ic8, 0) if a < 0x40000 else (ic7, 0x40000)
        r[(a - base) * 2:(a - base + n) * 2] = log_to_rom(lin_to_log(fit(x, n, norm) * FULL))
        hit8 |= a < 0x40000; hit7 |= a >= 0x40000
    for i, nm in renames.items():
        c[0x100 + 8 * i:0x108 + 8 * i] = list(nm.encode('ascii', 'replace')[:8].ljust(8))
    os.makedirs(out, exist_ok=True); files = []
    if hit8: ic8.tofile(f'{out}/r15179880.ic8_patched.bin'); files.append('IC8 (drums)')
    if hit7: ic7.tofile(f'{out}/r15179878.ic7_patched.bin'); files.append('IC7 (instruments)')
    if renames: c.tofile(f'{out}/r15179873.ic12_patched.bin'); files.append('IC12 (names)')
    with open(f'{out}/report.txt', 'w') as f:
        for i in sorted(set(swaps) | set(renames)):
            f.write('%3d %s -> %s %s\n' % (i, rom.names[i], renames.get(i, rom.names[i]).ljust(8), '(wave replaced)' if i in swaps else ''))
    return files


class WaveView(tk.Canvas):
    """original (green) with the replacement overlaid (amber); wheel = zoom, shift+wheel = pan, right-click = fit"""

    def __init__(s, master):
        super().__init__(master, bg=WAVE_BG, highlightthickness=1, highlightbackground=EDGE, height=260)
        s.o = s.n = None; s.z, s.p = 1.0, 0.0; s.loop = False
        s.bind('<Configure>', lambda e: s.draw()); s.bind('<MouseWheel>', s.wheel); s.bind('<Button-3>', s.fit_view)

    def fit_view(s, e=None):
        s.z, s.p = 1.0, 0.0; s.draw()

    def show(s, o, n, loop):
        s.o, s.n, s.loop = o, n, loop; s.fit_view()

    def wheel(s, e):
        if e.state & 1:
            s.p = min(max(s.p - np.sign(e.delta) * 0.1 / s.z, 0), 1 - 1 / s.z)
        else:
            s.z = min(max(s.z * (1.25 if e.delta > 0 else 0.8), 1.0), 64.0); s.p = min(s.p, 1 - 1 / s.z)
        s.draw()

    def trace(s, x, W, mid, amp, col, pk):
        n = len(x); seg = x[int(s.p * n):int((s.p + 1 / s.z) * n)]
        if len(seg) < 2:
            return
        for px in range(W):
            a = int(px * len(seg) / W); b = max(int((px + 1) * len(seg) / W), a + 1); c = seg[a:b]
            s.create_line(px, mid - c.max() / pk * amp, px, mid - c.min() / pk * amp + 1, fill=col)

    def draw(s):
        s.delete('all'); W, H = s.winfo_width(), s.winfo_height()
        if W < 10:
            return
        mid, amp = H / 2, H / 2 - 14
        for k in range(1, 8):
            s.create_line(k * W / 8, 0, k * W / 8, H, fill=GRID)
        s.create_line(0, mid, W, mid, fill='#24302a')
        if s.o is None:
            s.create_text(W / 2, H / 2, text='SELECT A WAVE', fill='#4d6b45', font=('Consolas', 12, 'bold')); return
        pk = np.abs(s.o).max() + 1e-9
        s.trace(s.o, W, mid, amp, WAVE_FG, pk)
        if s.n is not None:
            s.trace(s.n, W, mid, amp, NEW_COL, np.abs(s.n).max() + 1e-9)
        s.create_text(4, H - 4, anchor='sw', text='%.3fs' % (s.p * len(s.o) / RATE), fill='#5f7a58', font=('Consolas', 9))
        s.create_text(W - 4, H - 4, anchor='se', text='%.3fs' % ((s.p + 1 / s.z) * len(s.o) / RATE), fill='#5f7a58', font=('Consolas', 9))
        s.create_text(W - 6, 6, anchor='ne', text='ORIGINAL' + ('  (loops)' if s.loop else ''), fill=WAVE_FG, font=('Consolas', 9, 'bold'))
        if s.n is not None:
            s.create_text(W - 6, 20, anchor='ne', text='REPLACEMENT', fill=NEW_COL, font=('Consolas', 9, 'bold'))


class Studio(tk.Tk):
    def __init__(s):
        super().__init__(); s.geometry('1180x720'); s.minsize(980, 620); s.title(APP)
        apply_theme(s); dark_titlebar(s)
        s.rom = Rom(); s.swaps = {}; s.src = {}; s.renames = {}; s.path = None
        s.norm = tk.BooleanVar(value=True); s.filt = tk.StringVar(value='All')
        s.menu(); s.ui(); s.fill(); s.sel_first()

    def menu(s):
        mb = tk.Menu(s); f = tk.Menu(mb, tearoff=0)
        for l, c, a in (('Open project...', s.open, 'Ctrl+O'), ('Save project', s.save, 'Ctrl+S'), ('Save project as...', lambda: s.save(True), ''), (None,) * 3,
                        ('Import ROM dumps (IC8, IC7, IC12)...', s.import_roms, ''), ('Import WAV folder...', s.import_folder, ''),
                        ('Export all original waves to folder...', s.export_all, ''), (None,) * 3,
                        ('Build ROM images...', s.build, 'Ctrl+B'), (None,) * 3, ('Exit', s.destroy, '')):
            f.add_separator() if l is None else f.add_command(label=l, command=c, accelerator=a)
        mb.add_cascade(label='File', menu=f)
        h = tk.Menu(mb, tearoff=0); h.add_command(label='How it works', command=s.help); mb.add_cascade(label='Help', menu=h); s.config(menu=mb)
        for k, fn in (('<Control-o>', s.open), ('<Control-s>', s.save), ('<Control-b>', s.build)):
            s.bind(k, lambda e, fn=fn: fn())

    def ui(s):
        head = ttk.Frame(s, padding=(12, 10, 12, 4)); head.pack(fill='x'); plate = ttk.Frame(head); plate.pack(side='left', padx=(0, 16))
        ttk.Label(plate, text='D-110', style='Title.TLabel').pack(anchor='w'); ttk.Label(plate, text='ROSETTA ROM STUDIO', style='Sub.TLabel').pack(anchor='w')
        s.lcd = LCD(head, 40); s.lcd.pack(side='left'); mf = ttk.Frame(head); mf.pack(side='left', padx=16)
        ttk.Label(mf, text='WAVES CHANGED', style='Silk.TLabel').pack(anchor='w'); s.meter = LEDMeter(mf); s.meter.pack(anchor='w', pady=(2, 2))
        s.v_cnt = tk.StringVar(); ttk.Label(mf, textvariable=s.v_cnt, style='Dim.TLabel').pack(anchor='w')
        bf = ttk.Frame(head); bf.pack(side='right'); ttk.Label(bf, text='WRITE ROMS', style='Silk.TLabel').pack()
        ttk.Button(bf, text='BUILD', style='Build.TButton', command=s.build).pack(pady=(2, 0))
        main = ttk.PanedWindow(s, orient='horizontal'); main.pack(fill='both', expand=True, padx=8, pady=(4, 4))
        lf = ttk.Labelframe(main, text=' WAVES ', padding=6); main.add(lf, weight=1)
        fb = ttk.Frame(lf); fb.pack(fill='x', pady=(0, 4)); ttk.Label(fb, text='SHOW', style='Silk.TLabel').pack(side='left')
        cb = ttk.Combobox(fb, textvariable=s.filt, values=['All', 'IC8 drums', 'IC7 instruments', 'Changed'], width=16, state='readonly')
        cb.pack(side='left', padx=6); cb.bind('<<ComboboxSelected>>', lambda e: s.fill())
        cols = (('n', '#', 36), ('name', 'Name', 90), ('chip', 'Chip', 44), ('sec', 'Time', 54), ('st', '', 70))
        s.tv = ttk.Treeview(lf, columns=[c[0] for c in cols], show='headings', selectmode='browse')
        for c, t, w in cols:
            s.tv.heading(c, text=t); s.tv.column(c, width=w, anchor='w' if c in ('name', 'st') else 'center')
        sb = ttk.Scrollbar(lf, command=s.tv.yview); s.tv.configure(yscrollcommand=sb.set); sb.pack(side='right', fill='y'); s.tv.pack(fill='both', expand=True)
        s.tv.bind('<<TreeviewSelect>>', lambda e: s.on_sel()); s.tv.bind('<Double-1>', lambda e: s.play_orig())
        rf = ttk.Labelframe(main, text=' WAVEFORM ', padding=6); main.add(rf, weight=3); s.wv = WaveView(rf); s.wv.pack(fill='both', expand=True)
        info = ttk.Frame(rf); info.pack(fill='x', pady=(6, 0)); s.v_info = tk.StringVar(); ttk.Label(info, textvariable=s.v_info, style='Dim.TLabel').pack(side='left')
        row = ttk.Frame(rf); row.pack(fill='x', pady=(8, 0))
        for t, c in (('Play original', s.play_orig), ('Play replacement', s.play_new), ('Load WAV...', s.load), ('Undo', s.undo), ('Save original WAV...', s.save_orig)):
            ttk.Button(row, text=t, command=c).pack(side='left', padx=(0, 6))
        ttk.Checkbutton(row, text='Normalize', variable=s.norm, command=s.on_sel).pack(side='left', padx=8)
        nr = ttk.Frame(rf); nr.pack(fill='x', pady=(8, 0)); ttk.Label(nr, text='NAME (8)', style='Silk.TLabel').pack(side='left'); s.v_name = tk.StringVar()
        e = ttk.Entry(nr, textvariable=s.v_name, width=12, validate='key', validatecommand=(s.register(lambda v: len(v) <= 8 and v.isascii()), '%P'))
        e.pack(side='left', padx=6); ttk.Button(nr, text='Set name', command=s.set_name).pack(side='left'); e.bind('<Return>', lambda ev: s.set_name())
        stf = ttk.Frame(s, style='Status.TFrame'); stf.pack(fill='x', side='bottom')
        s.v_st = tk.StringVar(value='Hardware-untested. Each wave keeps its slot position and length (no table edits). 32 kHz mono.')
        ttk.Label(stf, textvariable=s.v_st, style='Status.TLabel', padding=(8, 3)).pack(side='left')

    # ---- list
    def state(s, i):
        return ('WAV ' if i in s.swaps else '') + ('NAME' if i in s.renames else '')

    def vis(s, i):
        f = s.filt.get()
        return f == 'All' or (f == 'IC8 drums' and s.rom.chip(i) == 'IC8') or (f == 'IC7 instruments' and s.rom.chip(i) == 'IC7') \
            or (f == 'Changed' and (i in s.swaps or i in s.renames))

    def row_vals(s, i):
        return (i, s.renames.get(i, s.rom.names[i]), s.rom.chip(i), '%.2f' % (s.rom.ent[i][1] / RATE) + ('*' if s.rom.ent[i][2] else ''), s.state(i))

    def fill(s):
        cur = s.cur(); s.tv.delete(*s.tv.get_children())
        for i in range(NW):
            if s.vis(i):
                s.tv.insert('', 'end', iid=str(i), values=s.row_vals(i))
        if cur is not None and s.tv.exists(str(cur)):
            s.tv.selection_set(str(cur))
        s.update_head()

    def cur(s):
        x = s.tv.selection(); return int(x[0]) if x else None

    def sel_first(s):
        k = s.tv.get_children()
        if k:
            s.tv.selection_set(k[0])

    def refresh_row(s, i):
        if s.tv.exists(str(i)):
            s.tv.item(str(i), values=s.row_vals(i))

    def update_head(s):
        n = len(set(s.swaps) | set(s.renames)); s.meter.set(n / NW); s.v_cnt.set('%d of %d' % (n, NW)); s.on_sel()

    def on_sel(s):
        i = s.cur()
        if i is None:
            s.lcd.set('', ''); return
        a, n, l = s.rom.ent[i]; nm = s.renames.get(i, s.rom.names[i])
        s.lcd.set('%03d %-8s %s %.2fs%s' % (i, nm, s.rom.chip(i), n / RATE, ' LOOP' if l else ''),
                  ('NEW: ' + os.path.basename(s.src[i])) if i in s.src else 'ORIGINAL')
        s.v_name.set(nm.strip())
        s.wv.show(s.rom.orig(i), fit(s.swaps[i], n, s.norm.get()) if i in s.swaps else None, l)
        if i in s.swaps:
            ln = len(s.swaps[i])
            s.v_info.set('slot %d samples (%.2fs) at wave pos 0x%05X  |  replacement %.2fs%s' %
                         (n, n / RATE, a, ln / RATE, '  -> TRUNCATED' if ln > n else '  (padded with silence)'))
        else:
            s.v_info.set('slot %d samples (%.2fs) at wave pos 0x%05X' % (n, n / RATE, a))

    # ---- play / edit
    def play(s, x):
        if winsound:
            winsound.PlaySound(wav_bytes(x), winsound.SND_MEMORY | winsound.SND_ASYNC)

    def play_orig(s):
        i = s.cur()
        if i is not None:
            o = s.rom.orig(i); s.play(np.tile(o, 3) if s.rom.ent[i][2] else o)

    def play_new(s):
        i = s.cur()
        if i is None:
            return
        if i not in s.swaps:
            s.v_st.set('No replacement loaded for this wave.'); return
        x = fit(s.swaps[i], s.rom.ent[i][1], s.norm.get()); s.play(np.tile(x, 3) if s.rom.ent[i][2] else x)

    def load(s):
        i = s.cur()
        if i is None:
            return
        fn = filedialog.askopenfilename(filetypes=[('WAV files', '*.wav')])
        if fn and s.set_wav(i, fn):
            s.update_head(); s.play_new()

    def set_wav(s, i, fn, quiet=False):
        try:
            x = read_wav(fn)
        except Exception as e:
            if not quiet:
                messagebox.showerror('WAV', '%s: %s' % (os.path.basename(fn), e))
            return False
        s.swaps[i] = x; s.src[i] = fn; n = s.rom.ent[i][1]; s.refresh_row(i)
        s.v_st.set('Loaded %s (%.2fs). Slot holds %.2fs%s.' % (os.path.basename(fn), len(x) / RATE, n / RATE, ': will be truncated' if len(x) > n else ''))
        return True

    def set_name(s):
        i = s.cur()
        if i is None:
            return
        v = s.v_name.get()
        if v.strip() == s.rom.names[i].strip():
            s.renames.pop(i, None)
        else:
            s.renames[i] = v
        s.refresh_row(i); s.update_head()

    def undo(s):
        i = s.cur()
        if i is None:
            return
        for d in (s.swaps, s.src, s.renames):
            d.pop(i, None)
        if s.filt.get() == 'Changed':
            s.fill()
        else:
            s.refresh_row(i); s.update_head()

    def save_orig(s):
        i = s.cur()
        if i is None:
            return
        fn = filedialog.asksaveasfilename(defaultextension='.wav', initialfile='%03d_%s.wav' % (i, s.rom.names[i].strip()))
        if fn:
            write_wav(fn, s.rom.orig(i))

    # ---- import / export
    def import_roms(s):
        d = {}
        for key, title in (('ic8', 'IC8 drum ROM (512 KB, r15179880)'), ('ic7', 'IC7 instrument ROM (512 KB, r15179878)'), ('ic12', 'IC12 control ROM (128 KB, r15179873)')):
            fn = filedialog.askopenfilename(title='Select ' + title, initialdir=os.path.dirname(s.rom.paths[key]), filetypes=[('ROM dump', '*.bin;*.rom'), ('All', '*.*')])
            if not fn:
                return
            d[key] = fn
        try:
            new = Rom(**d)
        except Exception as e:
            messagebox.showerror(APP, str(e)); return
        s.rom = new; json.dump(d, open(CFG, 'w'), indent=1); s.fill(); s.v_st.set('Loaded ROM dumps (remembered for next time).')

    def import_folder(s):
        d = filedialog.askdirectory(title='Folder of WAVs (named 003_..., or by wave name)')
        if not d:
            return
        byname = {}
        for i in range(NW):
            byname.setdefault(re.sub(r'\W', '', s.rom.names[i]).lower(), i)
        ok = skip = 0
        for fn in sorted(glob.glob(os.path.join(d, '*.wav'))):
            base = os.path.splitext(os.path.basename(fn))[0]; m = re.match(r'^(\d{1,3})(?:\D|$)', base); i = None
            if m and int(m.group(1)) < NW:
                i = int(m.group(1))
            else:
                i = byname.get(re.sub(r'\W', '', base).lower())
            if i is not None and s.set_wav(i, fn, quiet=True):
                ok += 1
            else:
                skip += 1
        s.fill(); s.v_st.set('Imported %d WAVs, skipped %d (name them 003_x.wav or use the wave name).' % (ok, skip))

    def export_all(s):
        d = filedialog.askdirectory(title='Folder for the original waves')
        if not d:
            return
        for i in range(NW):
            o = s.rom.orig(i); write_wav(os.path.join(d, '%03d_%s.wav' % (i, re.sub(r'[^\w-]', '_', s.rom.names[i].strip()))), o)
        s.v_st.set('Exported %d original waves to %s (re-import them as-is after editing).' % (NW, d))

    def build(s):
        if not (s.swaps or s.renames):
            messagebox.showinfo(APP, 'Nothing changed yet: load a WAV or rename a wave first.'); return
        d = filedialog.askdirectory(title='Folder for the patched ROM images', initialdir=HERE)
        if not d:
            return
        files = build(s.rom, s.swaps, s.renames, d, s.norm.get()); s.v_st.set('Built: ' + ', '.join(files))
        messagebox.showinfo(APP, 'Wrote %s\nto %s\n\nProgram each image to its own chip. Images are in chip byte order, as dumped.' % (', '.join(files), d))

    def save(s, as_new=False):
        fn = (None if as_new else s.path) or filedialog.asksaveasfilename(defaultextension=EXT, filetypes=[('Rosetta project', '*' + EXT)])
        if not fn:
            return
        json.dump({'wavs': {str(i): p for i, p in s.src.items()}, 'names': {str(i): n for i, n in s.renames.items()}}, open(fn, 'w'), indent=1)
        s.path = fn; s.title('%s - %s' % (APP, os.path.basename(fn))); s.v_st.set('Saved ' + fn)

    def open(s):
        fn = filedialog.askopenfilename(filetypes=[('Rosetta project', '*' + EXT)])
        if not fn:
            return
        d = json.load(open(fn)); s.swaps.clear(); s.src.clear(); s.renames.clear(); s.path = fn
        for i, p in d.get('wavs', {}).items():
            if not s.set_wav(int(i), p, quiet=True):
                messagebox.showwarning(APP, 'Could not load ' + p)
        s.renames.update({int(i): n for i, n in d.get('names', {}).items()}); s.title('%s - %s' % (APP, os.path.basename(fn))); s.fill()

    def help(s):
        messagebox.showinfo('How it works',
            'WAVES are the first 128 entries of the D-110 control ROM table (IC12).\n\n'
            'Pick a wave, Load WAV: it replaces that slot in IC8 (drums, #0-31) or IC7 (instruments, #32+).\n'
            'The slot keeps its position and length: longer WAVs are cut, shorter ones padded. 32 kHz mono.\n'
            'Rename edits the 8-character name in IC12 (IC12 must be reprogrammed too).\n\n'
            'File > Export all original waves, edit them, then File > Import WAV folder to swap them all back in.\n'
            'Wheel = zoom, Shift+wheel = pan, right-click = fit. Double-click a wave to hear the original.\n'
            'Looped waves (* in Time) preview 3x. BUILD writes patched .bin images. Hardware-untested.')


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        r = Rom(); t = np.sin(np.arange(9000) / 20.0); print(build(r, {3: t, 32: t}, {3: 'MyKick', 32: 'Zap'}, 'selftest_out')); sys.exit()
    Studio().mainloop()
