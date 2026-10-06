// Reference harness: disassemble given addresses of a ROM image with MAME's i8x9x disassembler.
// usage: mame_dasm rom.bin < addrs.txt   (hex addresses, file offset == CPU address)
#include "emu.h"
#include "i8x9xd.h"
#include <sstream>
#include <vector>
#include <iostream>
int main(int argc, char **argv) {
	FILE *f = fopen(argv[1], "rb"); std::vector<u8> rom(0x10000, 0xff);
	size_t n = fread(rom.data(), 1, rom.size(), f); fclose(f); (void)n;
	util::disasm_interface::data_buffer b{rom.data(), (u32)rom.size()};
	i8x9x_disassembler d; unsigned a;
	while(scanf("%x", &a) == 1) {
		std::ostringstream o; u32 r = d.disassemble(o, a, b, b);
		printf("%04x %u %s\n", a, r & 0xffff, o.str().c_str());
	}
}
