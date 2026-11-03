<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->

# Contributing

Thank you for helping. Most changes are a signal that should accept or
reject something it does not today, or a fix to the reports.

## Changing a signal

1. Reproduce first: show the repository (or a fixture under `tmp_path`) the
   signal gets wrong, as a failing test in `tests/`.
2. Make the smallest change that fixes it.
3. Run the full audit before and after (`python3 tools/audit_compliance.py
   --output <dir>`) and compare the two `audit.json` files. Say in the pull
   request which checks changed in which repositories; a change that moves
   anything you did not intend is not ready.
4. Record it in `CHANGELOG.md` under **Changed** or **Fixed**.
5. Run `make check` before opening the pull request.

Never edit `reports/` by hand; regenerate it with `make audit`.

## Commits

- Conventional commits: `<type>: <subject>`, at most 50 characters,
  imperative mood; the body explains what and why, wrapped at 72.
- **Sign every commit** (`commit.gpgsign=true`) and **sign off** every
  commit (`git commit -s`), certifying the
  [Developer Certificate of Origin](https://developercertificate.org). CI
  checks the trailer on every commit in a pull request.
- Work for a release goes on `feat/v<next-version>`, opened as a pull request
  into `main`.

## Development

`make help` lists the targets; `make check` runs everything CI runs. See
[README → Development](README.md#development).
