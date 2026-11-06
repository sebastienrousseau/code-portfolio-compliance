<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->

# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions move
by 0.0.1 a release (see [docs/POLICIES.md](docs/POLICIES.md)).

## [Unreleased]

## [0.0.4] - 2026-11-06

### Fixed

- The README's install steps and the issue form name the repository's real
  location, `~/Code/Private/Python/code-portfolio-compliance`, not
  `Private/Other`.

### Changed

- A GitHub profile repository (origin `<account>/<account>`, and that
  account declared as `owner` in `.compliance.yml`) is audited as one: its
  README is the rendered profile, so the template check is `n/a` and the
  repository leaves the rewrite queue, where an agent following
  `~/Code/AGENTS.md` section 8 would have rewritten the profile into a
  project README. C1.L1 still requires the licence, C1.L2 README-enforcing
  CI and `SECURITY.md`; C1.L3 is `n/a`. `readme_template` gains the value
  `n/a`; no field is removed, renamed or retyped, so `schema_version`
  stays 2. The summary counts canonical READMEs among repositories where
  the template applies.
- A `pyproject.toml` with `[tool.uv] package = false` has no public API:
  the API checks are `n/a`.
- Measured over the full workspace (433 repositories), one moved:
  `Public/Python/sebastienrousseau` (C1.L1 and C1.L2 to pass, C1.L3 and
  C6.L2 to `n/a`, candidate tier L0 to L2). A first version keyed on the
  remote alone also moved `Forks/agentgateway`, an organisation repository;
  requiring the declared owner fixed that.

## [0.0.3] - 2026-11-03

### Changed

- `readme_template_status` and `audit_repository` are split into small
  functions (`readme_blocking_issue`, `heading_issues`, `score`,
  `missing_signals`, `rewrite_safety`). Results are identical for all 436
  repositories in the workspace.
- `complexity-baseline.json` is empty: every function is within the
  AGENTS.md ceilings.

### Added

- Tests for the README template check and for scoring and rewrite safety.

## [0.0.2] - 2026-11-03

### Changed

- The 24 checks moved from `checks_for` in `tools/audit_compliance.py` to
  `tools/compliance_checks.py`, split into evidence gathering, the
  not-applicable reasons and one function per category. Every check gives
  the same result as in 0.0.1 for all 436 repositories in the workspace.
- `checks_for` left `complexity-baseline.json`; two offenders remain
  (`audit_repository`, `readme_template_status`).

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

[Unreleased]: https://github.com/sebastienrousseau/code-portfolio-compliance/compare/v0.0.4...HEAD
[0.0.4]: https://github.com/sebastienrousseau/code-portfolio-compliance/compare/v0.0.3...v0.0.4
[0.0.3]: https://github.com/sebastienrousseau/code-portfolio-compliance/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/sebastienrousseau/code-portfolio-compliance/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/sebastienrousseau/code-portfolio-compliance/releases/tag/v0.0.1
