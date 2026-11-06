# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""A GitHub profile repository, and a pyproject that is not a package."""

import subprocess
from pathlib import Path

import audit_compliance as audit
import compliance_checks as checks
import compliance_report as report
import pytest

PROFILE_README = '<a href="https://example.test"><img src="assets/hero.svg" alt="hero"></a>\n'


def repo(path: Path, origin: str | None, owner: str | None = "someone") -> Path:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    if origin:
        subprocess.run(["git", "-C", str(path), "remote", "add", "origin", origin], check=True)
    if owner:
        (path / ".compliance.yml").write_text(f"tier: L2\nowner: {owner}\n")
    return path


@pytest.mark.parametrize(
    "origin",
    ["git@github.com:someone/someone.git", "https://github.com/Someone/someone", "https://github.com/someone/SOMEONE.git"],
)
def test_a_repository_named_for_its_declared_owner_is_a_profile(tmp_path, origin):
    assert checks.profile_reason(repo(tmp_path, origin)).startswith("a GitHub profile repository")


@pytest.mark.parametrize("owner", [None, "agentgateway-team", "someone-else"])
def test_an_org_repository_named_for_its_org_is_not(tmp_path, owner):
    # github.com/agentgateway/agentgateway is an organisation's main repo, not a
    # profile; only a declared owner matching the account makes it one.
    path = repo(tmp_path, "https://github.com/agentgateway/agentgateway.git", owner)
    assert checks.profile_reason(path) == ""


@pytest.mark.parametrize("origin", ["git@github.com:someone/tool.git", "https://gitlab.com/someone/someone", None])
def test_any_other_repository_is_not(tmp_path, origin):
    assert checks.profile_reason(repo(tmp_path, origin)) == ""


def c1(path: Path) -> dict[str, checks.Check]:
    found = audit.checks_for(path, audit.corpus(path))
    return {key: found[key] for key in ("C1.L1", "C1.L2", "C1.L3")}


def test_a_profile_needs_its_licence_but_not_project_readme_sections(tmp_path):
    path = repo(tmp_path, "git@github.com:someone/someone.git")
    (path / "README.md").write_text(PROFILE_README)
    assert not c1(path)["C1.L1"].ok
    (path / "LICENSE").write_text("MIT\n")
    got = c1(path)
    assert got["C1.L1"].ok
    assert got["C1.L3"].not_applicable.startswith("a GitHub profile repository")


def test_a_profile_l2_needs_readme_ci_and_a_security_policy(tmp_path):
    path = repo(tmp_path, "git@github.com:someone/someone.git")
    (path / "README.md").write_text(PROFILE_README)
    assert not c1(path)["C1.L2"].ok
    (path / ".github" / "workflows").mkdir(parents=True)
    (path / ".github" / "workflows" / "ci.yml").write_text("steps:\n  - name: README drift\n    run: make check\n")
    assert not c1(path)["C1.L2"].ok
    (path / "SECURITY.md").write_text("# Security\n")
    assert c1(path)["C1.L2"].ok


def test_the_same_files_outside_a_profile_still_fail_c1(tmp_path):
    path = repo(tmp_path, "git@github.com:someone/tool.git")
    (path / "README.md").write_text(PROFILE_README)
    (path / "LICENSE").write_text("MIT\n")
    got = c1(path)
    assert not got["C1.L1"].ok and not got["C1.L3"].not_applicable


def test_a_profile_readme_is_never_queued_for_a_template_rewrite(tmp_path):
    root = tmp_path / "ws"
    path = repo(root / "Public" / "someone", "git@github.com:someone/someone.git")
    (path / "README.md").write_text(PROFILE_README)
    result = audit.audit_repository(path.resolve(), root.resolve(), {path.resolve()})
    assert result["readme_template"] == "n/a"
    assert result["readme_issues"][0].startswith("a GitHub profile repository")
    assert not report.needs_rewrite(result)


def test_the_summary_counts_canonical_readmes_among_those_that_apply(tmp_path):
    def row(path, template):
        return {
            "path": path,
            "ecosystem": "python",
            "target_tier": "L1",
            "criticality": "incubator",
            "owner": "me",
            "candidate_tier": "L1",
            "score_percent": 50,
            "readme_template": template,
            "dirty": False,
            "embedded": False,
            "fork_or_vendor": False,
            "safe_rewrite": True,
            "missing_target_signals": [],
        }

    report.write_reports([row("Public/a", "pass"), row("Public/b", "fail"), row("Public/me", "n/a")], tmp_path, tmp_path)
    assert "- Canonical primary READMEs: **1/2**" in (tmp_path / "README.md").read_text()
    assert (tmp_path / "rewrite-queue.txt").read_text() == "Public/b\n"


NOT_A_PACKAGE = '[project]\nname = "x"\nversion = "0.0.1"\n\n[tool.uv]\npackage = false\n'


def test_a_pyproject_that_is_not_a_package_has_no_api(tmp_path):
    (tmp_path / "pyproject.toml").write_text(NOT_A_PACKAGE)
    assert checks.applicability(tmp_path).api.startswith("not a package")


@pytest.mark.parametrize(
    "pyproject",
    ['[project]\nname = "x"\n', "[tool.uv]\npackage = true\n", "[tool.other]\npackage = false\n"],
)
def test_a_package_still_has_an_api(tmp_path, pyproject):
    (tmp_path / "pyproject.toml").write_text(pyproject)
    assert checks.applicability(tmp_path).api == ""
