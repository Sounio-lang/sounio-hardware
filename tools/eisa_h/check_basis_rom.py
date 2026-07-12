#!/usr/bin/env python3
"""Bind the RTL and testbench basis ROMs to the v1 Cayley-Dickson hash."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

EXPECTED_TABLE_SHA256 = "e2b59d42ab7d44ead7f085e9e9b34df2ba1667445b0c89eff79cd8d921faa19d"
ROM_PATTERN = re.compile(r"V1_BASIS_NEGATIVE\s*=\s*256'h([0-9a-fA-F]{64})", re.MULTILINE)


def read_rom(path: pathlib.Path) -> int:
    matches = ROM_PATTERN.findall(path.read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one V1 basis ROM in {path}, found {len(matches)}")
    return int(matches[0], 16)


def table_hash(negative_bits: int) -> str:
    encoded = bytes(255 if (negative_bits >> index) & 1 else 1 for index in range(256))
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    if len(sys.argv) not in (2, 3, 4):
        raise SystemExit("usage: check_basis_rom.py <repository-root> [rtl] [testbench]")
    root = pathlib.Path(sys.argv[1]).resolve()
    rtl_path = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) >= 3 else root / "rtl/eisa_h_sed16_zd_pair_v1.sv"
    testbench_path = (
        pathlib.Path(sys.argv[3]).resolve()
        if len(sys.argv) == 4
        else root / "tb/eisa_h/tb_sed16_zd_pair_v1.sv"
    )
    rtl_rom = read_rom(rtl_path)
    testbench_rom = read_rom(testbench_path)
    if rtl_rom != testbench_rom:
        raise SystemExit("RTL and testbench basis ROMs differ")
    observed_hash = table_hash(rtl_rom)
    if observed_hash != EXPECTED_TABLE_SHA256:
        raise SystemExit(f"basis ROM hash mismatch: {observed_hash}")
    print(f"EISA_H_BASIS_ROM_PASS cells=256 table_sha256={observed_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
