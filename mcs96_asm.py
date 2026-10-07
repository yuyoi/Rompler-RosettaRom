"""Small two-pass MCS-96 assembler for the OS patches. Syntax = what mcs96_dis prints, so every instruction is checked
by decoding it again (asm text and disassembly must agree).

    a = Asm(0xb000, {'PART': 0xf6cd})
    a.src('''
    top:  ldb   r70, PART          ; long-indexed off zero
          cmpb  r70, #8
          jc    done
          stb   r70, 0xf1c0[r54]
    done: ret
    ''')
    code = a.bytes()

`je! label` (any jcc + '!') = far branch: the inverse jcc over an ljmp (5 bytes).
Operands: rNN / sfr names (r70, rb7, int_mask, sp, zero), #imm, [rNN], [rNN]+, off[rNN], plain address (= long
indexed off zero; registers 0x00-0xff are written rNN). Numbers and symbols may be Python expressions (labels, the
symbol dict, hi(x)/lo(x)). `db` / `dw` emit data, `even` pads to an even address (word tables: the CPU cannot
read or write a word at an odd address).
"""
import re
from mcs96_dis import decode, fmt_ins, SFR8_R, SFR8_W, SFR16_R, SFR16_W

NAME2REG = {v: k for t in (SFR8_R, SFR8_W, SFR16_R, SFR16_W) for k, v in t.items()}
W2 = {'and': 0x60, 'add': 0x64, 'sub': 0x68, 'mulu': 0x6c, 'or': 0x80, 'xor': 0x84, 'cmp': 0x88, 'divu': 0x8c,
      'ld': 0xa0, 'addc': 0xa4, 'subc': 0xa8, 'ldbze': 0xac, 'ldbse': 0xbc}
B2 = {'andb': 0x70, 'addb': 0x74, 'subb': 0x78, 'mulub': 0x7c, 'orb': 0x90, 'xorb': 0x94, 'cmpb': 0x98,
      'divub': 0x9c, 'ldb': 0xb0, 'addcb': 0xb4, 'subcb': 0xb8}
W3 = {'and': 0x40, 'add': 0x44, 'sub': 0x48, 'mulu': 0x4c}
B3 = {'andb': 0x50, 'addb': 0x54, 'subb': 0x58, 'mulub': 0x5c}
ONE = {'clr': 0x01, 'not': 0x02, 'neg': 0x03, 'dec': 0x05, 'inc': 0x07,
       'clrb': 0x11, 'notb': 0x12, 'negb': 0x13, 'decb': 0x15, 'incb': 0x17}
SHIFT = {'shr': 0x08, 'shl': 0x09, 'shra': 0x0a, 'shrb': 0x18, 'shlb': 0x19, 'shrab': 0x1a}
JCC = {'jnst': 0xd0, 'jnh': 0xd1, 'jgt': 0xd2, 'jnc': 0xd3, 'jnvt': 0xd4, 'jnv': 0xd5, 'jge': 0xd6, 'jne': 0xd7,
       'jst': 0xd8, 'jh': 0xd9, 'jle': 0xda, 'jc': 0xdb, 'jvt': 0xdc, 'jv': 0xdd, 'jlt': 0xde, 'je': 0xdf}
NOARG = {'ret': 0xf0, 'pushf': 0xf2, 'popf': 0xf3, 'di': 0xfa, 'ei': 0xfb, 'nop': 0xfd, 'clrc': 0xf8, 'setc': 0xf9}
BYTE_SRC = set(B2) | set(B3) | {'ldbze', 'ldbse'}


class AsmError(Exception): pass


class Asm:
    def __init__(s, org, syms=None):
        s.org, s.syms, s.lines = org, dict(syms or {}), []

    def src(s, text):
        for ln in text.splitlines():
            ln = ln.split(';')[0].strip()
            while True:
                m = re.match(r'^([A-Za-z_]\w*):\s*(.*)$', ln)
                if not m: break
                s.lines.append(('label', m.group(1))); ln = m.group(2).strip()
            if ln: s.lines.append(('ins', ln))
        return s

    def val(s, e, env):
        try:
            return eval(e, {'hi': lambda x: (x >> 8) & 0xff, 'lo': lambda x: x & 0xff}, env)
        except NameError:
            if env.get('_pass') == 1: return 0
            raise

    def reg(s, t, env):
        t = t.strip()
        if t in NAME2REG: return NAME2REG[t]
        if re.fullmatch(r'r[0-9a-f]{2}', t): return int(t[1:], 16)
        v = s.val(t, env)
        if not 0 <= v < 0x100: raise AsmError('not a register: %s' % t)
        return v

    def aop(s, t, size, env, allow_imm=True):
        """-> (mode, bytes)"""
        t = t.strip()
        if t.startswith('#'):
            if not allow_imm: raise AsmError('no immediate here')
            v = s.val(t[1:], env) & (0xff if size == 1 else 0xffff)
            return 1, bytes([v]) if size == 1 else v.to_bytes(2, 'little')
        m = re.fullmatch(r'\[(\w+)\](\+?)', t)
        if m: return 2, bytes([s.reg(m.group(1), env) | (1 if m.group(2) else 0)])
        m = re.fullmatch(r'(.*)\[(\w+)\]', t)
        if m:
            off, r = s.val(m.group(1), env), s.reg(m.group(2), env)
            short = -128 <= off < 128 and not s.force_long(m.group(1), env)
            if short: return 3, bytes([r, off & 0xff])
            return 3, bytes([r | 1]) + (off & 0xffff).to_bytes(2, 'little')
        if t in NAME2REG or re.fullmatch(r'r[0-9a-f]{2}', t): return 0, bytes([s.reg(t, env)])
        v = s.val(t, env)
        return 3, bytes([1]) + (v & 0xffff).to_bytes(2, 'little')         # long indexed off zero

    def force_long(s, e, env):
        """labels/symbols in an index offset: keep the size stable between passes"""
        return bool(re.search(r'[A-Za-z_]', re.sub(r'\b0x[0-9a-fA-F]+\b|\b\d+\b', '', e)))

    def enc(s, ins, pc, env):
        mn, _, rest = ins.partition(' ')
        ops = [o.strip() for o in re.split(r',(?![^\[]*\])', rest)] if rest.strip() else []
        rel8 = lambda t, n: (s.val(t, env) - (pc + n))
        if mn == 'even': return b'\xff' if pc & 1 else b''
        if mn in ('db', 'dw'):
            out = b''
            for o in ops:
                if o.startswith('"') or o.startswith("'"): out += eval(o).encode('latin-1')
                else: out += (s.val(o, env) & 0xffff).to_bytes(2, 'little') if mn == 'dw' else bytes([s.val(o, env) & 0xff])
            return out
        if mn in NOARG: return bytes([NOARG[mn]])
        if mn in ONE: return bytes([ONE[mn], s.reg(ops[0], env)])
        if mn in SHIFT:
            c = ops[1]
            cnt = s.val(c[1:], env) if c.startswith('#') else s.reg(c, env)
            return bytes([SHIFT[mn], cnt, s.reg(ops[0], env)])
        if mn.endswith('!') and mn[:-1] in JCC:          # far conditional: inverse jcc over an ljmp
            inv = JCC[mn[:-1]] ^ 0x08
            d = (s.val(ops[0], env) - (pc + 5)) & 0xffff
            return bytes([inv, 3, 0xe7]) + d.to_bytes(2, 'little')
        if mn in JCC:
            d = rel8(ops[0], 2); s.chk8(d, ins, env); return bytes([JCC[mn], d & 0xff])
        if mn == 'djnz':
            d = rel8(ops[1], 3); s.chk8(d, ins, env); return bytes([0xe0, s.reg(ops[0], env), d & 0xff])
        if mn in ('jbc', 'jbs'):
            d = rel8(ops[2], 3); s.chk8(d, ins, env)
            return bytes([(0x30 if mn == 'jbc' else 0x38) + s.val(ops[1], env), s.reg(ops[0], env), d & 0xff])
        if mn in ('sjmp', 'scall'):
            d = s.val(ops[0], env) - (pc + 2)
            if env.get('_pass') == 2 and not -1024 <= d < 1024: raise AsmError('%s out of range' % ins)
            return bytes([(0x20 if mn == 'sjmp' else 0x28) | ((d >> 8) & 7), d & 0xff])
        if mn in ('ljmp', 'lcall'):
            d = (s.val(ops[0], env) - (pc + 3)) & 0xffff
            return bytes([0xe7 if mn == 'ljmp' else 0xef]) + d.to_bytes(2, 'little')
        if mn == 'br': return bytes([0xe3, s.reg(ops[0].strip('[]'), env)])
        if mn in ('st', 'stb'):
            mode, b = s.aop(ops[1], 2 if mn == 'st' else 1, env, allow_imm=False)
            return bytes([(0xc0 if mn == 'st' else 0xc4) + mode]) + b + bytes([s.reg(ops[0], env)])
        if mn == 'push':
            mode, b = s.aop(ops[0], 2, env); return bytes([0xc8 + mode]) + b
        if mn == 'pop':
            mode, b = s.aop(ops[0], 2, env, allow_imm=False); return bytes([0xcc + mode]) + b
        size = 1 if mn in BYTE_SRC else 2
        if len(ops) == 3:
            tab = B3 if mn in B3 else W3
            mode, b = s.aop(ops[2], size, env)
            return bytes([tab[mn] + mode]) + b + bytes([s.reg(ops[1], env), s.reg(ops[0], env)])
        tab = B2 if mn in B2 else W2
        if mn not in tab: raise AsmError('unknown: %s' % ins)
        mode, b = s.aop(ops[1], size, env)
        return bytes([tab[mn] + mode]) + b + bytes([s.reg(ops[0], env)])

    def chk8(s, d, ins, env):
        if env.get('_pass') == 2 and not -128 <= d < 128: raise AsmError('%s: jump out of range (%d)' % (ins, d))

    def run(s, pas, labels):
        env = dict(s.syms, **labels, _pass=pas)
        pc, out, lab = s.org, bytearray(), {}
        for kind, x in s.lines:
            if kind == 'label': lab[x] = pc; env[x] = pc; continue
            try:
                b = s.enc(x, pc, env)
            except AsmError: raise
            except Exception as e:
                raise AsmError('%s: %s' % (x, e))
            if pas == 2 and not x.startswith(('db', 'dw', 'even')):
                if x.split()[0].endswith('!'):
                    s.check(x.split()[0][:-1] + ' x', b[:2], pc, env, inverse=True); s.check('ljmp x', b[2:], pc + 2, env)
                else: s.check(x, b, pc, env)
            out += b; pc += len(b)
        return bytes(out), lab

    def check(s, text, b, pc, env, inverse=False):
        mem = lambda a: b[a - pc] if 0 <= a - pc < len(b) else 0xff
        i = decode(mem, pc)
        if i.n != len(b): raise AsmError('%s: length %d, decodes as %d (%s)' % (text, len(b), i.n, fmt_ins(i)))
        got = fmt_ins(i)
        mn = got.split()[0]
        want = text.split()[0]
        if inverse: want = [k for k, v in JCC.items() if v == JCC[want] ^ 0x08][0]
        if mn != want: raise AsmError('%s: decodes as %s' % (text, got))

    def assemble(s, ext=None):
        _, lab1 = s.run(1, dict(ext or {}))
        code, lab2 = s.run(2, dict(ext or {}, **lab1))
        assert lab1 == lab2, 'label drift'
        s.labels = lab2
        return code

    def listing(s, code):
        mem = lambda a: code[a - s.org] if 0 <= a - s.org < len(code) else 0xff
        a, out, inv = s.org, [], {v: k for k, v in s.labels.items()}
        while a < s.org + len(code):
            i = decode(mem, a)
            out.append('%s%04x  %-15s %s' % ((inv[a] + ':\n') if a in inv else '', a, code[a - s.org:a - s.org + i.n].hex(' '), fmt_ins(i)))
            a += i.n
        return '\n'.join(out)
