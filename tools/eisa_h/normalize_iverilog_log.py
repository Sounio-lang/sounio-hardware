#!/usr/bin/env python3
"""Remove exactly one Icarus $finish line from a simulation receipt."""

from __future__ import annotations

import argparse
import pathlib
import re


FINISH_LINE = re.compile(r"^.+:\d+: \$finish called at \d+ \(1ps\)\n$")


def normalize(source: pathlib.Path, target: pathlib.Path) -> None:
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    chatter = [line for line in lines if FINISH_LINE.fullmatch(line)]
    if len(chatter) != 1:
        raise ValueError(f"expected one Icarus finish line, observed {len(chatter)}")
    target.write_text(
        "".join(line for line in lines if not FINISH_LINE.fullmatch(line)),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=pathlib.Path)
    parser.add_argument("target", type=pathlib.Path)
    args = parser.parse_args()
    try:
        normalize(args.source, args.target)
    except (OSError, ValueError) as error:
        print(f"IVERILOG_LOG_NORMALIZATION_FAIL detail={error}")
        return 1
    print("IVERILOG_LOG_NORMALIZATION_PASS removed_finish_lines=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
