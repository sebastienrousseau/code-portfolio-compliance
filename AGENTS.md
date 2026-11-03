<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->

# AGENTS.md

This repository is the portfolio compliance audit named in
`~/Code/AGENTS.md` §8: a read-only Python tool that evaluates every
repository in the workspace against the 24-signal matrix and writes the
reports the portfolio is triaged from. Its value is that a signal means
exactly what the matrix says, no more and no less. The portfolio rules in
`~/Code/AGENTS.md` apply; these are the rules specific to this repository,
and where they are stricter they win.

## Rules

1. **A signal change is measured, not argued.** Run the full workspace
   audit before and after and compare `audit.json`. Report every check that
   moved, in which repositories. A change that also moves something
   unintended is wrong.
2. **Never make a repository pass by teaching the tool to look away.** A
   signal is widened only when the matrix's wording already covers what it
   missed (for example, `scripts/` as a source surface for C2.L1).
3. **Static means conservative.** The tool records that something is
   present; it never claims CI passed. Keep that wording in the reports.
4. **Not applicable needs a reason.** A check is `n/a` only with a reason
   string, and is then left out of the score.
5. **Generated output is regenerated, not edited:** `reports/` (`make
   audit`), `.github/demo.gif` (`make demo`).
6. **The report schema is an interface.** Changing `audit.json` fields
   raises `schema_version` and is a breaking CHANGELOG entry.
7. **Complexity only shrinks.** New code meets every ceiling; a function in
   `complexity-baseline.json` that you touch is brought under the ceiling in
   the same change, then `make baseline`.
8. **Commits** are signed, signed off (`git commit -s`), conventional, and
   carry an `Assisted-by:` trailer when an agent helped.

## The one command

```bash
make check
```

It runs lint (ruff, shellcheck, markdownlint, the README template check),
the complexity ratchet, pip-audit, pytest and `uv build`, as CI does.

## Leave alone

- `reports/` and `pr/`: local output, gitignored.
- `LICENSE-MIT`, `LICENSE-APACHE` and the licence statement in README →
  License.
