<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->

# Security Policy

This repository holds a read-only audit tool that walks a local workspace.
Its security posture is about what it reads and runs on your machine, and
about the small supply chain of its CI.

## Reporting a Vulnerability

The repository is private, so GitHub's private vulnerability reporting is not
available. Report security issues by email to
**<sebastian.rousseau@gmail.com>**. Do not open a public issue.

You will receive an acknowledgement within **72 hours**. A confirmed issue is
fixed within **90 days** of the report, or sooner when a fix is
straightforward; if the window cannot be met you will be told why and given a
revised date.

## Supported Versions

Only the latest release on the `main` branch is supported. A fix ships as the
next release, never as a backport.

## Security Measures

Each item names the file that enforces it, so it can be checked rather than
taken on trust.

- **Read-only, offline.** `tools/audit_compliance.py` reads files and runs
  only `git tag -l` and `git status --porcelain` in each repository, each
  with a timeout; it makes no network calls and writes only to `--output`.
- **No runtime dependencies.** The tool uses the Python standard library.
  The dev tools are pinned in `uv.lock`, `make deps-audit` checks them with
  pip-audit in CI, and Dependabot watches them (`.github/dependabot.yml`).
- **Every GitHub Action is pinned to a commit SHA**, and Dependabot keeps the
  pins current.
- **Secrets.** Gitleaks scans the full history on each pull request, each
  push to `main` and weekly (`.github/workflows/secret-scan.yml`). GitHub's
  own secret scanning and code scanning are not enabled: on a private
  repository they need GitHub Secret Protection and Code Security.
- **Signed, certified commits.** `.github/workflows/dco.yml` requires a
  `Signed-off-by` trailer on every commit in a pull request.
- **Workflows run with least privilege**: `permissions: {}` at the top of
  each workflow, `contents: read` per job, and `persist-credentials: false`
  on every checkout.
