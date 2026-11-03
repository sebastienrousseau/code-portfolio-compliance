#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Enforce the per-function complexity ceilings (~/Code/AGENTS.md section 0).

Usage: complexity_gate.py [--write] FILE...

Every function must be within every ceiling unless it is listed in
complexity-baseline.json, and a listed function may not get worse. The
baseline may only shrink: an entry that is looser than the code fails the
gate until it is rewritten with --write, so an improvement is locked in.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import complexipy
from radon.complexity import cc_visit
from radon.metrics import h_visit

CEILINGS = {"cyclomatic": 10, "cognitive": 15, "halstead": 30, "lines": 60}
FILE_CEILING = 500
BASELINE = Path(__file__).resolve().parents[1] / "complexity-baseline.json"


def measure_file(path: str) -> dict[str, dict[str, float]]:
    """Return {"<path>::<function>": {metric: value}} plus "<path>" for file length."""
    code = Path(path).read_text(encoding="utf-8")
    halstead = {name: report.difficulty for name, report in h_visit(code).functions}
    cognitive = {fn.name: fn.complexity for fn in complexipy.file_complexity(path).functions}
    out: dict[str, dict[str, float]] = {path: {"file_lines": len(code.splitlines())}}
    for block in cc_visit(code):
        out[f"{path}::{block.name}"] = {
            "cyclomatic": block.complexity,
            "cognitive": cognitive.get(block.name, 0),
            "halstead": round(halstead.get(block.name, 0), 2),
            "lines": block.endline - block.lineno + 1,
        }
    return out


def over_ceiling(metrics: dict[str, float]) -> dict[str, float]:
    """The metrics of one function or file that exceed their ceiling."""
    limits = {**CEILINGS, "file_lines": FILE_CEILING}
    return {name: value for name, value in metrics.items() if value > limits[name]}


def offenders(paths: list[str]) -> dict[str, dict[str, float]]:
    found: dict[str, dict[str, float]] = {}
    for path in paths:
        for key, metrics in measure_file(path).items():
            over = over_ceiling(metrics)
            if over:
                found[key] = over
    return found


def compare(current: dict[str, dict[str, float]], baseline: dict[str, dict[str, float]]) -> list[str]:
    """Return one message per regression (new or worse) and per loose baseline entry."""
    problems = []
    for key, metrics in current.items():
        for name, value in metrics.items():
            allowed = baseline.get(key, {}).get(name)
            if allowed is None or value > allowed:
                problems.append(f"over ceiling: {key} {name}={value} (baseline {allowed})")
    for key, metrics in baseline.items():
        for name, allowed in metrics.items():
            value = current.get(key, {}).get(name)
            if value is None or value < allowed:
                problems.append(f"baseline is loose: {key} {name} {allowed} -> {value}; run with --write")
    return problems


def main(argv: list[str]) -> int:
    write = "--write" in argv
    paths = sorted(arg for arg in argv if arg != "--write")
    if not paths:
        sys.exit(__doc__)
    current = offenders(paths)
    if write:
        BASELINE.write_text(json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"complexity: baseline written with {len(current)} offenders")
        return 0
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else {}
    problems = compare(current, baseline)
    for problem in problems:
        print(problem, file=sys.stderr)
    print(f"complexity: {len(current)} baselined offenders, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
