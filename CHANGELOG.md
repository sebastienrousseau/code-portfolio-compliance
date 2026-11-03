<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->

# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions move
by 0.0.1 a release (see [docs/POLICIES.md](docs/POLICIES.md)).

## [Unreleased]

## [0.0.1] - 2026-11-03

First versioned release of the audit tool, previously an unversioned script.

### Added

- `pyproject.toml` with an `audit-compliance` entry point, licensed
  MIT OR Apache-2.0.
- `make check` (ruff, shellcheck, markdownlint, README template check,
  complexity ratchet, pip-audit, pytest, `uv build`) and the CI, DCO, PR
  base and Gitleaks workflows that run it.
- `scripts/complexity_gate.py` and `complexity-baseline.json`: the AGENTS.md
  complexity ceilings, with the three existing offenders baselined.
- Tests for C2.L1, the candidate tier, the four reports, the complexity
  ratchet and the command line.
- README to the portfolio template, with a demo rendered from
  `.github/demo.tape`, and the security, contributing, conduct and policy
  documents.

### Changed

- C2.L1 counts `scripts/` as a source surface. In the 435-repository
  workspace this moved C2.L1 from fail to pass in 44 repositories and
  changed nothing else.
- Report writing moved to `tools/compliance_report.py`; the reports are
  byte-identical.

### Fixed

- The tool raised `RuntimeError` outside a workspace even for `--help` or
  with `--root` given. The default root is now resolved only when needed,
  and a missing workspace is a usage error that names `--root`.

[Unreleased]: https://github.com/sebastienrousseau/code-portfolio-compliance/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/sebastienrousseau/code-portfolio-compliance/releases/tag/v0.0.1
