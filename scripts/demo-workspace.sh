#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
#
# Build a throwaway workspace of three small repositories for the demo:
#
#   scripts/demo-workspace.sh <empty-dir>
#
# Public/Python/tidy meets every L1 signal, Private/Shell/toolkit has only a
# README and scripts/, Work/Go/service has only a go.mod.
set -euo pipefail

ws=${1:?usage: scripts/demo-workspace.sh <empty-dir>}
mkdir -p "${ws}"/{Public,Private,Work,Forks}

commit() {
  git -C "$1" init -q -b main
  git -C "$1" add -A
  git -C "$1" -c user.name=demo -c user.email=demo@example.invalid -c commit.gpgsign=false \
    commit -q -m "chore: initial commit"
}

tidy="${ws}/Public/Python/tidy"
mkdir -p "${tidy}/src/tidy" "${tidy}/.github/workflows"
printf '# tidy\n\n## Quick Start\n\nRun it.\n\n## Development\n\nmake check\n' >"${tidy}/README.md"
printf '[project]\nname = "tidy"\nversion = "0.1.0"\n' >"${tidy}/pyproject.toml"
printf 'MIT License\n' >"${tidy}/LICENSE"
printf '# Changelog\n\n## [0.1.0]\n' >"${tidy}/CHANGELOG.md"
for doc in SECURITY CODE_OF_CONDUCT CONTRIBUTING; do printf '# %s\n' "${doc}" >"${tidy}/${doc}.md"; done
printf 'version: 2\n' >"${tidy}/.github/dependabot.yml"
printf 'jobs:\n  ci:\n    steps:\n      - run: ruff check && ruff format --check && pytest\n' >"${tidy}/.github/workflows/ci.yml"
touch "${tidy}/src/tidy/__init__.py"
commit "${tidy}"
git -C "${tidy}" -c tag.gpgsign=false tag v0.1.0

toolkit="${ws}/Private/Shell/toolkit"
mkdir -p "${toolkit}/scripts"
printf '# toolkit\n' >"${toolkit}/README.md"
printf '#!/bin/sh\necho hi\n' >"${toolkit}/scripts/hello.sh"
commit "${toolkit}"

service="${ws}/Work/Go/service"
mkdir -p "${service}"
printf 'module example.invalid/service\n\ngo 1.24\n' >"${service}/go.mod"
commit "${service}"
