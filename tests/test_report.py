# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""The four report artifacts written from audit results."""

import csv
import json

import compliance_report as report


def result(path, *, template="fail", safe=True, tier="L1"):
    return {
        "path": path,
        "ecosystem": "python",
        "target_tier": "L1",
        "criticality": "incubator",
        "owner": "me",
        "candidate_tier": tier,
        "score_percent": 50,
        "readme_template": template,
        "dirty": False,
        "embedded": False,
        "fork_or_vendor": False,
        "safe_rewrite": safe,
        "missing_target_signals": ["C4.L1 (tags)", "C6.L1 (ci)"],
    }


RESULTS = [result("Public/a"), result("Private/b", template="pass", tier="L0"), result("Public/c", safe=False)]


def written(tmp_path):
    report.write_reports(RESULTS, tmp_path, tmp_path)
    return tmp_path


def test_json_holds_every_result(tmp_path):
    payload = json.loads((written(tmp_path) / "audit.json").read_text())
    assert payload["schema_version"] == 2
    assert payload["repositories"] == RESULTS


def test_csv_joins_missing_signals(tmp_path):
    rows = list(csv.DictReader((written(tmp_path) / "audit.csv").open()))
    assert [row["path"] for row in rows] == ["Public/a", "Private/b", "Public/c"]
    assert rows[0]["missing_target_signals"] == "C4.L1 (tags); C6.L1 (ci)"


def test_rewrite_queue_holds_only_clean_failing_readmes(tmp_path):
    assert (written(tmp_path) / "rewrite-queue.txt").read_text() == "Public/a\n"


def test_markdown_summary_and_heat_map(tmp_path):
    md = (written(tmp_path) / "README.md").read_text()
    assert "- Repositories: **3**" in md
    assert "- Canonical primary READMEs: **1/3**" in md
    assert "| Private | 1 | 0 | 0 | 0 |" in md
    assert "| Public | 0 | 2 | 0 | 0 |" in md


def test_markdown_results_table(tmp_path):
    md = (written(tmp_path) / "README.md").read_text()
    assert "| `Public/a` | python | L1 | L1 | 50% | fail | yes |" in md
    assert "| `Public/c` | python | L1 | L1 | 50% | fail | no |" in md


def test_empty_rewrite_queue_is_an_empty_file(tmp_path):
    report.write_reports([result("Public/a", template="pass")], tmp_path, tmp_path)
    assert (tmp_path / "rewrite-queue.txt").read_text() == ""
