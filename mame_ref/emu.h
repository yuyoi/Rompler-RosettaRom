// Minimal shim so MAME's mcs96 disassembler builds standalone (reference only).
#pragma once
#include <cstdint>
#include <cstdio>
#include <string>
#include <ostream>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32; typedef int8_t s8; typedef uint32_t offs_t;
template<typename T> constexpr int BIT(T x, int n) { return (x >> n) & 1; }
namespace util {
template<typename T> inline T fmtarg(T v) { return v; }
inline const char *fmtarg(const std::string &s) { return s.c_str(); }
template<typename... A> std::string string_format(const char *f, A&&... a) {
	char buf[256]; snprintf(buf, sizeof buf, f, fmtarg(a)...); return buf; }
template<typename... A> void stream_format(std::ostream &o, const char *f, A&&... a) { o << string_format(f, a...); }
class disasm_interface {
public:
	enum : u32 { SUPPORTED = 0x80000000, LENGTHMASK = 0xffff, STEP_OVER = 0x20000000, STEP_OUT = 0x40000000, STEP_COND = 0x10000000 };
	class data_buffer {
	public:
		const u8 *d; u32 n;
		u8 r8(offs_t pc) const { return pc < n ? d[pc] : 0xff; }
		u16 r16(offs_t pc) const { return r8(pc) | (r8(pc+1) << 8); }
	};
	virtual ~disasm_interface() = default;
	virtual u32 opcode_alignment() const = 0;
	virtual offs_t disassemble(std::ostream &stream, offs_t pc, const data_buffer &opcodes, const data_buffer &params) = 0;
};
}
