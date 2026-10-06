#!/bin/sh
# Builds mame_ref/mame_dasm: MAME's i8x9x disassembler (BSD-3, fetched here, not vendored) behind a tiny
# shim, used only by test_mcs96_dis.py as an independent reference.
set -e
cd "$(dirname "$0")"
M=https://raw.githubusercontent.com/mamedev/mame/master/src/devices/cpu/mcs96
for f in mcs96d.cpp mcs96d.h i8x9xd.cpp i8x9xd.h mcs96ops.lst mcs96make.py; do
    [ -f "$f" ] || curl -sSf -o "$f" "$M/$f"
done
mkdir -p cpu/mcs96
python3 mcs96make.py d i8x9x mcs96ops.lst cpu/mcs96/i8x9xd.hxx
g++ -O1 -std=c++17 -w -I. -o mame_dasm mame_dasm.cpp mcs96d.cpp i8x9xd.cpp
echo built mame_ref/mame_dasm
