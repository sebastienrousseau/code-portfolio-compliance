<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->

# Policies

## Versioning

Versions increment by 0.0.1 a release (`v0.0.1` → `v0.0.2` → …), reaching
`v0.1.0` only after `v0.0.999`. Work for a release goes on
`feat/v<next-version>` and reaches `main` through one pull request. What
counts as breaking is in [README → Stability guarantees](../README.md#stability-guarantees).

## Supported Python

The tool requires **Python 3.12 or later** (`requires-python` in
`pyproject.toml`); CI tests 3.12 and 3.13. Raising the floor is a breaking
change.

## Report schema

`audit.json` carries `schema_version`, currently **2**. Any removal, rename
or type change of a field raises it.

## Dev tool versions

pytest, ruff, radon and complexipy are pinned in `pyproject.toml` and locked
in `uv.lock`; Dependabot proposes updates weekly. A tool update that changes
a complexity measurement updates `complexity-baseline.json` in the same
pull request, with the reason.
