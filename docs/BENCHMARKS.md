<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->

# Benchmarks

There is no benchmark suite. The one number in the README is a single
measured run, recorded so a slowdown is noticeable.

| Scenario | Result | Environment |
| :--- | ---: | :--- |
| Full workspace audit, 435 repositories | 4 min 12 s wall clock (58 s user, 90 s system) | macOS 26, Apple silicon, Python 3.12.15, 2026-11-02 |

Method: `time python3 -I tools/audit_compliance.py --root ~/Code --output
<scratch dir>`, run once. The cause of the time was not profiled; expect it
to grow with the number and size of repositories in the workspace.
