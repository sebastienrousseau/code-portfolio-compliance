<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com> -->
<!-- SPDX-License-Identifier: MIT OR Apache-2.0 -->
<!--
Branch from main and target main: work for a release goes on
feat/v<next-version>. Every commit is signed and signed off (git commit -s).
The description follows ~/Code/PR-TEMPLATE.md: a two-line BLUF, then the
sections below. No em dashes.
-->

This PR <what it does, in one plain line>.

<why it matters, in one plain line>

## Highlights ⭐️

* **<Headline>**: <one or two plain sentences>.

## What's Changed

* `<commit subject>` by @<author>

## Validation

* `make check`: <result, with numbers>.
* Full audit before and after, `audit.json` compared: <checks that moved, in which repositories>.

## Checksums

SHA-256 of the artifacts produced by `make build` on this branch:

```text
<sha256>  dist/<artifact>
```

**Full Changelog**: <compare URL>
