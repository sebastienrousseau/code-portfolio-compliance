# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Behaviour of the audit checks and tier calculation."""

import shutil
import subprocess
import sys
from pathlib import Path

import audit_compliance as audit
import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "audit_compliance.py"


def c2_l1(repo: Path) -> bool:
    return audit.checks_for(repo, audit.corpus(repo))["C2.L1"].ok


@pytest.mark.parametrize("surface", ["src", "lib", "scripts"])
def test_c2_l1_passes_with_readme_and_source_dir(tmp_path, surface):
    (tmp_path / "README.md").write_text("# demo\n")
    (tmp_path / surface).mkdir()
    assert c2_l1(tmp_path)


def test_c2_l1_fails_without_a_source_surface(tmp_path):
    (tmp_path / "README.md").write_text("# demo\n")
    (tmp_path / "images").mkdir()
    assert not c2_l1(tmp_path)


def test_c2_l1_fails_without_readme(tmp_path):
    (tmp_path / "scripts").mkdir()
    assert not c2_l1(tmp_path)


def check(ok, na=""):
    return audit.Check(ok, "evidence", na)


def test_candidate_tier_stops_at_first_incomplete_level():
    checks = {"C1.L1": check(True), "C1.L2": check(False), "C1.L3": check(True)}
    assert audit.candidate_tier(checks) == "L1"


def test_candidate_tier_counts_not_applicable_as_satisfied():
    checks = {"C1.L1": check(True), "C1.L2": check(False, "no CLI"), "C1.L3": check(True)}
    assert audit.candidate_tier(checks) == "L3"


def test_candidate_tier_is_l0_when_l1_fails():
    assert audit.candidate_tier({"C1.L1": check(False), "C2.L1": check(True)}) == "L0"


@pytest.mark.parametrize("flags", [[], ["-I"]])
def test_script_runs_directly_and_isolated(tmp_path, flags):
    # A copy run by the base interpreter: the project is not installed there,
    # so under -I the sibling module is found only by the path fallback.
    for name in ("audit_compliance.py", "compliance_report.py"):
        shutil.copy(TOOL.with_name(name), tmp_path / name)
    python = getattr(sys, "_base_executable", sys.executable)
    run = subprocess.run([python, *flags, str(tmp_path / "audit_compliance.py"), "--help"], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert "--root" in run.stdout


def test_missing_workspace_is_a_usage_error_not_a_traceback(tmp_path):
    shutil.copy(TOOL, tmp_path / "audit_compliance.py")
    shutil.copy(TOOL.with_name("compliance_report.py"), tmp_path / "compliance_report.py")
    run = subprocess.run([sys.executable, str(tmp_path / "audit_compliance.py")], capture_output=True, text=True, check=False, cwd=tmp_path)
    assert run.returncode == 2
    assert "Traceback" not in run.stderr
    assert "--root" in run.stderr
