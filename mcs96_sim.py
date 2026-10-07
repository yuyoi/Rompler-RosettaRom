"""Tiny MCS-96 simulator on top of mcs96_dis.decode, for checking patches on your own IC19 dump (no I/O, no timers,
no interrupts). Enough for UI routines: run a call, stub ROM routines by address, inspect RAM afterwards."""
from mcs96_dis import decode

M16, M8 = 0xffff, 0xff


class Sim:
    def __init__(self, ic19, ic15=None):
        self.m = bytearray(0x10000)
        self.m[0x1000:0x8000] = ic19[0x1000:0x8000]
        self.ic19, self.ic15 = ic19, ic15
        self.bank = 0
        self.Z = self.N = self.C = self.V = self.ST = 0
        self.pc, self.stubs, self.trace, self.steps = 0, {}, [], 0
        self.st(0x18, 0xf9d0, 2)

    # --- memory ---
    def win(self, a):
        page, off = self.bank, a - 0x8000
        if page < 0x10: return self.ic19[(page * 0x4000 + off) & 0x7fff]
        if 0x20 <= page < 0x28 and self.ic15: return self.ic15[((page - 0x20) * 0x4000 + off) & 0x1ffff]
        return 0xff

    def ld(self, a, size):
        a &= M16
        if a == 0: return 0
        r = lambda x: self.win(x) if 0x8000 <= x < 0xc000 else self.m[x & M16]
        return r(a) if size == 1 else r(a) | r(a + 1) << 8

    def st(self, a, v, size):
        a &= M16
        if a == 0x0100: self.bank = v & 0xff      # bank latch (write-only)
        if a in (0, 1, 0x0100) or 0x1000 <= a < 0xc000:
            return
        self.m[a] = v & 0xff
        if size == 2: self.m[a + 1] = (v >> 8) & 0xff

    @property
    def sp(self): return self.ld(0x18, 2)

    def push(self, v): self.st(0x18, self.sp - 2, 2); self.st(self.sp, v, 2)

    def pop(self): v = self.ld(self.sp, 2); self.st(0x18, self.sp + 2, 2); return v

    # --- operands ---
    def ea(self, o):
        k = o[0]
        if k == 'r': return o[1]
        if k == '[]': return self.ld(o[1], 2)
        if k == 'ix': return (self.ld(o[2], 2) + o[1]) & M16 if o[2] else o[1] & M16
        raise ValueError(o)

    def rd(self, o, size):
        if o[0] == '#': return o[1]
        v = self.ld(self.ea(o), size)
        if o[0] == '[]' and o[2]: self.st(o[1], self.ld(o[1], 2) + size, 2)
        return v

    def wr(self, o, v, size):
        a = self.ea(o)
        self.st(a, v, size)
        if o[0] == '[]' and o[2]: self.st(o[1], self.ld(o[1], 2) + size, 2)

    def flags(self, r, size):
        mask = M8 if size == 1 else M16
        self.Z = int(r & mask == 0); self.N = int(bool(r & (mask + 1) >> 1))

    def addf(self, a, b, size, c=0):
        mask = M8 if size == 1 else M16; r = a + b + c
        self.C = int(r > mask); top = (mask + 1) >> 1
        self.V = int(bool(~(a ^ b) & (a ^ r) & top)); self.flags(r, size); return r & mask

    def subf(self, a, b, size):
        mask = M8 if size == 1 else M16; r = (a - b) & mask
        self.C = int(a >= b); top = (mask + 1) >> 1
        self.V = int(bool((a ^ b) & (a ^ r) & top)); self.flags(r, size); return r

    # --- run ---
    def call(self, addr, max_steps=200000):
        """push a sentinel return address and run until it returns"""
        self.push(0xfffe); self.pc = addr
        while self.pc != 0xfffe:
            self.step()
            self.steps += 1
            if self.steps > max_steps: raise RuntimeError('runaway at %04x' % self.pc)

    def step(self):
        pc = self.pc
        if pc in self.stubs:
            self.stubs[pc](self); self.pc = self.pop(); return
        i = decode(lambda a: self.ld(a, 1), pc)
        self.trace.append(pc)
        self.pc = (pc + i.n) & M16
        mn, o = i.mn, i.ops
        size = 1 if (mn.endswith('b') and mn not in ('sub',) and mn not in ('djnz',)) or mn in ('ldbze', 'ldbse') else 2
        if mn in ('jbc', 'jbs', 'djnz'): size = 1
        if mn in ('ld', 'ldb'):
            self.wr(o[0], self.rd(o[1], size), size)
        elif mn in ('ldbze', 'ldbse'):
            v = self.rd(o[1], 1)
            if mn == 'ldbse' and v & 0x80: v |= 0xff00
            self.wr(o[0], v, 2)
        elif mn in ('st', 'stb'):
            self.wr(o[1], self.rd(o[0], size), size)
        elif mn in ('add', 'addb', 'addc', 'addcb', 'sub', 'subb', 'cmp', 'cmpb', 'and', 'andb', 'or', 'orb', 'xor', 'xorb'):
            base = mn.rstrip('b') if mn not in ('sub', 'subb') else 'sub'
            if mn == 'subb': base = 'sub'
            if len(o) == 3: a, b, dst = self.rd(o[1], size), self.rd(o[2], size), o[0]
            else: a, b, dst = self.rd(o[0], size), self.rd(o[1], size), o[0]
            if base in ('add', 'addc'): r = self.addf(a, b, size, self.C if base == 'addc' else 0)
            elif base in ('sub', 'cmp'): r = self.subf(a, b, size)
            else:
                r = {'and': a & b, 'or': a | b, 'xor': a ^ b}[base]; self.flags(r, size); self.C = self.V = 0
            if base != 'cmp': self.wr(dst, r, size)
        elif mn in ('inc', 'incb', 'dec', 'decb'):
            v = self.rd(o[0], size)
            r = self.addf(v, 1, size) if mn.startswith('inc') else self.subf(v, 1, size)
            self.wr(o[0], r, size)
        elif mn in ('clr', 'clrb'):
            self.wr(o[0], 0, size); self.Z, self.N, self.C, self.V = 1, 0, 0, 0
        elif mn in ('neg', 'negb', 'not', 'notb'):
            v = self.rd(o[0], size); mask = M8 if size == 1 else M16
            r = self.subf(0, v, size) if mn.startswith('neg') else (~v) & mask
            if mn.startswith('not'): self.flags(r, size)
            self.wr(o[0], r, size)
        elif mn in ('shl', 'shlb', 'shr', 'shrb'):
            cnt = o[1][1] if o[1][0] == '#' else self.ld(o[1][1], 1)
            v = self.rd(o[0], size); mask = M8 if size == 1 else M16
            r = (v << cnt) & mask if mn.startswith('shl') else v >> cnt
            self.flags(r, size)
            if cnt: self.C = (v >> (cnt - 1)) & 1 if mn.startswith('shr') else (v << cnt) >> (8 * size) & 1
            self.wr(o[0], r, size)
        elif mn in ('mulub', 'mulu'):
            if len(o) == 3: a, b = self.rd(o[1], 1 if mn == 'mulub' else 2), self.rd(o[2], 1 if mn == 'mulub' else 2)
            else: a, b = self.rd(o[0], 1 if mn == 'mulub' else 2), self.rd(o[1], 1 if mn == 'mulub' else 2)
            r = a * b; self.st(self.ea(o[0]), r & M16, 2)
            if mn == 'mulu': self.st(self.ea(o[0]) + 2, r >> 16, 2)
        elif mn in ('divub', 'divu'):
            n = self.rd(o[0], 2 if mn == 'divub' else 4) if mn == 'divub' else self.ld(self.ea(o[0]), 2) | self.ld(self.ea(o[0]) + 2, 2) << 16
            d = self.rd(o[1], 1 if mn == 'divub' else 2)
            if mn == 'divub': self.st(self.ea(o[0]), (n // d) & M8 | (n % d) << 8, 2)
            else: self.st(self.ea(o[0]), (n // d) & M16, 2); self.st(self.ea(o[0]) + 2, n % d, 2)
        elif mn == 'push': self.push(self.rd(o[0], 2))
        elif mn == 'pop': self.wr(o[0], self.pop(), 2)
        elif mn == 'pushf': self.push(self.Z << 7 | self.N << 6 | self.V << 5 | self.C << 3)
        elif mn == 'popf':
            f = self.pop(); self.Z, self.N, self.V, self.C = f >> 7 & 1, f >> 6 & 1, f >> 5 & 1, f >> 3 & 1
        elif mn in ('lcall', 'scall', 'call'): self.push(self.pc); self.pc = o[0][1]
        elif mn == 'ret': self.pc = self.pop()
        elif mn in ('ljmp', 'sjmp'): self.pc = o[0][1]
        elif mn == 'br': self.pc = self.ld(o[0][1], 2)
        elif mn == 'djnz':
            v = (self.rd(o[0], 1) - 1) & M8; self.wr(o[0], v, 1)
            if v: self.pc = o[1][1]
        elif mn in ('jbc', 'jbs'):
            bit = self.ld(o[0][1], 1) >> o[1][1] & 1
            if bit == (mn == 'jbs'): self.pc = o[2][1]
        elif mn.startswith('j') and o and o[0][0] == 'a':
            Z, N, C, V = self.Z, self.N, self.C, self.V
            cond = {'je': Z, 'jne': not Z, 'jc': C, 'jnc': not C, 'jh': C and not Z, 'jnh': (not C) or Z,
                    'jgt': not N and not Z, 'jle': N or Z, 'jge': not N, 'jlt': N, 'jv': V, 'jnv': not V,
                    'jst': self.ST, 'jnst': not self.ST, 'jvt': V, 'jnvt': not V}[mn]
            if cond: self.pc = o[0][1]
        elif mn in ('di', 'ei', 'nop', 'clrc', 'setc', 'clrvt', 'rst', 'skip'):
            if mn == 'clrc': self.C = 0
            if mn == 'setc': self.C = 1
        else:
            raise NotImplementedError('%s at %04x' % (mn, pc))
