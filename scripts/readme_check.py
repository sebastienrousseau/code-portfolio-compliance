#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Check this repository's README.md with the audit's own README template check."""

import sys
from pathlib import Path

import audit_compliance

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    ok, issues = audit_compliance.readme_template_status(ROOT)
    for issue in issues:
        print(f"README: {issue}", file=sys.stderr)
    print("README: follows ~/Code/README-TEMPLATE.md" if ok else "README: template check failed")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
