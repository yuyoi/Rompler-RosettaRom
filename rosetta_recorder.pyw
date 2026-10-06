"""Rosetta Recorder: hold SPACE (or the big button) to record a snippet from your mic, release to save it.
Each take is trimmed, normalised, resampled to 32 kHz mono and saved as NNN_label.wav in the 'recordings' folder
(NNN = next free number, label = the text box).  Drag that folder into Rosetta ROM D110 (File > Import WAV folder).
Keys: SPACE hold = record, ENTER = play last take, BACKSPACE = delete last take."""
import os, glob, re, threading, time
import tkinter as tk
from tkinter import ttk
import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import resample_poly

R = 32000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'recordings'); os.makedirs(OUT, exist_ok=True)
SLOTS = [(0.064, 'loop slot (64 ms)'), (0.128, 'short slot (128 ms)'), (0.256, '256 ms slot'), (0.512, '512 ms slot')]


class App:
    def __init__(s, root):
        s.root = root; root.title('Rosetta Recorder'); root.geometry('520x360'); s.chunks = []; s.rec = False; s.last = None; s.level = 0.0
        ins = [(i, d['name']) for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0 and d['hostapi'] == sd.default.hostapi]
        s.devs = ins; s.dev = tk.StringVar(value=ins[0][1] if ins else '')
        f = ttk.Frame(root, padding=10); f.pack(fill='both', expand=True)
        ttk.Label(f, text='Input').grid(row=0, column=0, sticky='w'); cb = ttk.Combobox(f, textvariable=s.dev, values=[n for _, n in ins], width=48, state='readonly')
        cb.grid(row=0, column=1, sticky='we'); cb.bind('<<ComboboxSelected>>', lambda e: s.open())
        ttk.Label(f, text='Label').grid(row=1, column=0, sticky='w'); s.label = tk.StringVar(value='snap'); ttk.Entry(f, textvariable=s.label).grid(row=1, column=1, sticky='we')
        s.btn = tk.Label(f, text='HOLD SPACE TO RECORD', bg='#2b4c7e', fg='white', font=('Segoe UI', 18, 'bold'), height=3)
        s.btn.grid(row=2, column=0, columnspan=2, sticky='we', pady=10); s.btn.bind('<ButtonPress-1>', lambda e: s.start()); s.btn.bind('<ButtonRelease-1>', lambda e: s.stop())
        s.bar = ttk.Progressbar(f, maximum=1.0); s.bar.grid(row=3, column=0, columnspan=2, sticky='we')
        s.info = tk.StringVar(value='Ready.'); ttk.Label(f, textvariable=s.info, wraplength=480, justify='left').grid(row=4, column=0, columnspan=2, sticky='w', pady=10)
        f.columnconfigure(1, weight=1)
        s.rel = None; root.bind('<KeyPress-space>', s.kdown); root.bind('<KeyRelease-space>', s.kup)
        root.bind('<Return>', lambda e: s.play()); root.bind('<BackSpace>', lambda e: s.delete() if root.focus_get().winfo_class() != 'TEntry' else None)
        s.stream = None; s.open(); s.tick()

    def open(s):
        if s.stream: s.stream.close()
        idx = next((i for i, n in s.devs if n == s.dev.get()), None); d = sd.query_devices(idx)
        s.sr = int(d['default_samplerate']); s.nch = min(2, d['max_input_channels'])
        s.stream = sd.InputStream(device=idx, channels=s.nch, samplerate=s.sr, callback=s.cb, blocksize=1024); s.stream.start()

    def cb(s, x, n, t, st):
        m = x.mean(1) if x.ndim > 1 else x; s.level = float(np.abs(m).max())
        if s.rec: s.chunks.append(m.copy())

    def tick(s): s.bar['value'] = min(1.0, s.level * 1.5); s.level *= 0.6; s.root.after(40, s.tick)

    def kdown(s, e):                                  # Windows key-repeat sends release+press pairs: debounce the release
        if s.rel: s.root.after_cancel(s.rel); s.rel = None
        s.start(); return 'break'

    def kup(s, e): s.rel = s.root.after(70, s.stop); return 'break'

    def start(s):
        if s.rec: return
        s.chunks = []; s.rec = True; s.btn.config(bg='#b3261e', text='RECORDING...')

    def stop(s):
        if not s.rec: return
        s.rec = False; s.btn.config(bg='#2b4c7e', text='HOLD SPACE TO RECORD')
        x = np.concatenate(s.chunks) if s.chunks else np.zeros(0)
        if len(x) < s.sr * 0.03: s.info.set('Too short, ignored.'); return
        g = np.gcd(s.sr, R); x = resample_poly(x, R // g, s.sr // g); x = x - x.mean()
        on = np.where(np.abs(x) > 0.02 * np.abs(x).max())[0]
        if len(on) == 0: s.info.set('Silence, ignored.'); return
        a = max(0, on[0] - int(0.003 * R)); b = min(len(x), on[-1] + int(0.01 * R)); x = x[a:b]; x = x / np.abs(x).max() * 0.9
        used = [int(m.group(1)) for f in glob.glob(os.path.join(OUT, '*.wav')) if (m := re.match(r'(\d+)_', os.path.basename(f)))]
        n = max(used, default=-1) + 1; lab = re.sub(r'[^\w\-]+', '_', s.label.get()) or 'snap'; fn = os.path.join(OUT, '%03d_%s.wav' % (n, lab))
        sf.write(fn, x, R, subtype='PCM_16'); s.last = (fn, x); sec = len(x) / R
        fit = next((nm for lim, nm in SLOTS if sec <= lim), 'longer than 512 ms: use a stretched slot')
        s.info.set('Saved %s  (%.0f ms, fits: %s)' % (os.path.basename(fn), sec * 1000, fit)); s.play()

    def play(s):
        if s.last: sd.play(s.last[1], R)

    def delete(s):
        if s.last and os.path.exists(s.last[0]): os.remove(s.last[0]); s.info.set('Deleted %s' % os.path.basename(s.last[0])); s.last = None


if __name__ == '__main__':
    root = tk.Tk(); App(root); root.mainloop()
