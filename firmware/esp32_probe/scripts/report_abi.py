#!/usr/bin/env python3
"""Read ABI sizeof values from a symbol in an actual linked Xtensa ELF."""
import pathlib
import struct
import sys

from elftools.elf.elffile import ELFFile

names = [
    "abi_layout_revision", "pointer", "size_t", "BasicProgram",
    "BasicExecutor", "BasicSessionRuntime", "BasicVariableStore",
    "BasicVariableEntry", "BasicVariableKey", "BasicVariableValue",
    "LocoProbeStorage", "program_buffer", "variable_entry_array",
    "source_buffer", "temporary_buffer", "output_buffer",
]
if len(sys.argv) != 2:
    raise SystemExit("usage: report_abi.py application.elf")
with pathlib.Path(sys.argv[1]).open("rb") as stream:
    elf = ELFFile(stream)
    if elf.elfclass != 32 or not elf.little_endian:
        raise SystemExit("Expected 32-bit little-endian Xtensa ELF")
    table = elf.get_section_by_name(".symtab")
    if table is None:
        raise SystemExit("ELF symbol table missing")
    symbols = table.get_symbol_by_name("loco_probe_abi_sizes")
    if not symbols or len(symbols) != 1:
        raise SystemExit("ABI symbol missing or ambiguous")
    sym = symbols[0]
    if not isinstance(sym["st_shndx"], int):
        raise SystemExit("ABI symbol is not mapped to a section")
    section = elf.get_section(sym["st_shndx"])
    start = sym["st_value"] - section["sh_addr"]
    length = 4 * len(names)
    blob = section.data()[start:start + length]
    if len(blob) != length or sym["st_size"] != length:
        raise SystemExit("Malformed ABI record")
    values = struct.unpack("<" + "I" * len(names), blob)
    if values[0] != 1 or values[1] != 4 or values[2] != 4:
        raise SystemExit("Unexpected layout revision or pointer/size_t")
    for name, value in zip(names, values):
        print(f"{name}={value} bytes")
    descriptor_bytes = values[3] + values[5] + values[6]
    reserved_bytes = sum(values[11:16])
    print(f"core_descriptor_bytes={descriptor_bytes}")
    print(f"owned_buffers_and_entries_bytes={reserved_bytes}")
    print(f"static_probe_total_bytes={values[10]}")
    print("Note: ELF-linked ABI facts; no on-device heap/stack claims.")
