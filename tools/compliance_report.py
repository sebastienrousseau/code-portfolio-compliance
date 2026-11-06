# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Write the audit results as JSON, CSV, a rewrite queue and a Markdown summary."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

# The report names the audit script, not this module.
AUDIT_SCRIPT = Path(__file__).resolve().with_name("audit_compliance.py")

CSV_FIELDS = [
    "path",
    "ecosystem",
    "target_tier",
    "criticality",
    "owner",
    "candidate_tier",
    "score_percent",
    "readme_template",
    "dirty",
    "embedded",
    "fork_or_vendor",
    "safe_rewrite",
    "missing_target_signals",
]

REPORT_PREAMBLE = [
    "This is a conservative static audit. A candidate tier records discoverable",
    "signals; it is not proof that CI has passed or that the repository may claim",
    "the tier. Business criticality remains unclassified until `.compliance.yml`",
    "declares it.",
    "",
    "A check is `n/a` when its subject does not exist in the repository, for",
    "example completions for a library or a lockfile for a module with no",
    "dependencies. An `n/a` check satisfies its tier, is listed with its reason",
    "under `not_applicable` in `audit.json`, and is left out of the score.",
    "",
]

REPORT_ARTIFACTS = [
    "",
    "## Artifacts",
    "",
    "- `audit.json`: complete machine-readable checks and evidence gaps.",
    "- `audit.csv`: portfolio triage table.",
    "- `rewrite-queue.txt`: clean, non-fork, non-embedded repositories whose primary README fails the template.",
    "",
]


def needs_rewrite(result: dict[str, object]) -> bool:
    return bool(result["safe_rewrite"]) and result["readme_template"] == "fail"


def write_json(results: list[dict[str, object]], output: Path, root: Path, generated: str) -> None:
    payload = {
        "schema_version": 2,
        "generated_at": generated,
        "workspace": str(root),
        "method": "static conservative signals; CI execution and business criticality require verification",
        "repositories": results,
    }
    (output / "audit.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_csv(results: list[dict[str, object]], output: Path) -> None:
    with (output / "audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for result in results:
            row = {key: result[key] for key in CSV_FIELDS}
            row["missing_target_signals"] = "; ".join(result["missing_target_signals"])
            writer.writerow(row)


def write_rewrite_queue(results: list[dict[str, object]], output: Path) -> list[str]:
    queue = [str(result["path"]) for result in results if needs_rewrite(result)]
    (output / "rewrite-queue.txt").write_text("\n".join(queue) + ("\n" if queue else ""), encoding="utf-8")
    return queue


def script_display_name(root: Path) -> str:
    try:
        return AUDIT_SCRIPT.relative_to(root).as_posix()
    except ValueError:
        return str(AUDIT_SCRIPT)


def summary_lines(results: list[dict[str, object]], queue: list[str]) -> list[str]:
    template_passes = sum(result["readme_template"] == "pass" for result in results)
    template_applies = sum(result["readme_template"] != "n/a" for result in results)
    dirty = sum(bool(result["dirty"]) for result in results)
    excluded = sum(bool(result["embedded"] or result["fork_or_vendor"]) for result in results)
    target_counts = Counter(str(result["target_tier"]) for result in results)
    return [
        "## Summary",
        "",
        f"- Repositories: **{len(results)}**",
        f"- Canonical primary READMEs: **{template_passes}/{template_applies}**",
        f"- Safe README rewrite queue: **{len(queue)}**",
        f"- Dirty repositories: **{dirty}**",
        f"- Embedded/fork/vendor repositories excluded from automatic rewrites: **{excluded}**",
        "",
        "### Target tiers",
        "",
        "| L1 | L2 | L3 |",
        "| ---: | ---: | ---: |",
        f"| {target_counts['L1']} | {target_counts['L2']} | {target_counts['L3']} |",
        "",
    ]


def heat_map_lines(results: list[dict[str, object]]) -> list[str]:
    portfolio: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        bucket = str(result["path"]).split("/", 1)[0]
        portfolio[bucket][str(result["candidate_tier"])] += 1
    lines = [
        "### Candidate-tier heat map",
        "",
        "| Portfolio | L0 | L1 | L2 | L3 |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    for bucket in sorted(portfolio):
        counts = portfolio[bucket]
        lines.append(f"| {bucket} | {counts['L0']} | {counts['L1']} | {counts['L2']} | {counts['L3']} |")
    return lines


def results_table_lines(results: list[dict[str, object]]) -> list[str]:
    lines = [
        "",
        "## Repository results",
        "",
        "| Repository | Ecosystem | Target | Candidate | Score | README | Rewrite |",
        "| :--- | :--- | :---: | :---: | ---: | :---: | :---: |",
    ]
    for result in results:
        rewrite = "yes" if needs_rewrite(result) else "no"
        lines.append(
            f"| `{result['path']}` | {result['ecosystem']} | {result['target_tier']} | "
            f"{result['candidate_tier']} | {result['score_percent']}% | {result['readme_template']} | {rewrite} |"
        )
    return lines


def write_markdown(results: list[dict[str, object]], output: Path, root: Path, generated: str, queue: list[str]) -> None:
    lines = [
        "# Portfolio compliance audit",
        "",
        f"> Generated by `{script_display_name(root)}` at {generated}. Do not edit by hand.",
        "",
        *REPORT_PREAMBLE,
        *summary_lines(results, queue),
        *heat_map_lines(results),
        *results_table_lines(results),
        *REPORT_ARTIFACTS,
    ]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def write_reports(results: list[dict[str, object]], output: Path, root: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(UTC).replace(microsecond=0).isoformat()
    write_json(results, output, root, generated)
    write_csv(results, output)
    queue = write_rewrite_queue(results, output)
    write_markdown(results, output, root, generated, queue)
