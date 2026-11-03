# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""The README template check, using this repository's README as the passing case."""

from pathlib import Path

import audit_compliance as audit
import pytest

GOOD = (Path(__file__).resolve().parents[1] / "README.md").read_text()


def status(tmp_path, text):
    (tmp_path / "README.md").write_text(text)
    return audit.readme_template_status(tmp_path)


def swap_headings(text, first, second):
    return text.replace(f"## {first}\n", "## @@\n").replace(f"## {second}\n", f"## {first}\n").replace("## @@\n", f"## {second}\n")


def test_this_readme_passes(tmp_path):
    assert status(tmp_path, GOOD) == (True, [])


def test_missing_readme(tmp_path):
    assert audit.readme_template_status(tmp_path) == (False, ["README.md missing or unreadable"])


@pytest.mark.parametrize(
    ("text", "issue"),
    [
        (GOOD + "\n{{PROJECT_NAME}}\n", "unresolved template variables"),
        (GOOD.replace('<h1 align="center">', "<h1>"), "centered project h1 missing"),
        (swap_headings(GOOD, "Benchmarks", "Features"), "required headings are out of order"),
        (GOOD.replace("ossf-scorecard", "scorecard"), "missing structure: ossf-scorecard"),
    ],
)
def test_single_issue(tmp_path, text, issue):
    assert status(tmp_path, text) == (False, [issue])


def test_renamed_heading_reports_missing_and_unexpected(tmp_path):
    ok, issues = status(tmp_path, GOOD.replace("## Benchmarks\n", "## Speed\n"))
    assert not ok
    assert issues == ["missing heading: Benchmarks", "unexpected heading: Speed"]


def test_tokens_inside_code_are_content(tmp_path):
    assert status(tmp_path, GOOD + "\n`{{PROJECT_NAME}}`\n\n```text\n{{ALSO_FINE}}\n```\n") == (True, [])
