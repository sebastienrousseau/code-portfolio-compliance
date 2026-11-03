# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Scoring, missing target signals and README rewrite safety for one repository."""

import subprocess

import audit_compliance as audit

CHECKS = {
    "C1.L1": audit.Check(True, "readme"),
    "C1.L2": audit.Check(False, "stability"),
    "C2.L1": audit.Check(False, "source"),
    "C3.L2": audit.Check(False, "completions", "no CLI"),
}


def test_score_leaves_not_applicable_out():
    assert audit.score(CHECKS) == {"signals_passed": 1, "signals_total": 3, "signals_not_applicable": 1, "score_percent": 33}


def test_score_of_only_not_applicable_checks_is_100():
    assert audit.score({"C3.L2": audit.Check(False, "x", "n/a")})["score_percent"] == 100


def test_missing_signals_stop_at_the_target_tier():
    assert audit.missing_signals(CHECKS, "L1") == ["C2.L1 (source)"]
    assert audit.missing_signals(CHECKS, "L2") == ["C1.L2 (stability)", "C2.L1 (source)"]


def git_repo(path):
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def test_clean_standalone_repository_is_safe_to_rewrite(tmp_path):
    repo = git_repo(tmp_path / "Public" / "tool")
    assert audit.rewrite_safety(repo, tmp_path, {repo}) == {"dirty": False, "embedded": False, "fork_or_vendor": False, "safe_rewrite": True}


def test_dirty_repository_is_not_safe(tmp_path):
    repo = git_repo(tmp_path / "Public" / "tool")
    (repo / "notes.txt").write_text("wip\n")
    safety = audit.rewrite_safety(repo, tmp_path, {repo})
    assert safety["dirty"] and not safety["safe_rewrite"]


def test_embedded_fork_and_vendored_repositories_are_not_safe(tmp_path):
    outer = git_repo(tmp_path / "Public" / "outer")
    inner = git_repo(outer / "inner")
    fork = git_repo(tmp_path / "Forks" / "lib")
    vendored = git_repo(tmp_path / "Public" / "app" / "vendor" / "dep")
    repos = {outer, inner, fork, vendored}
    assert audit.rewrite_safety(inner, tmp_path, repos)["embedded"]
    assert audit.rewrite_safety(fork, tmp_path, repos)["fork_or_vendor"]
    assert audit.rewrite_safety(vendored, tmp_path, repos)["fork_or_vendor"]
    assert not any(audit.rewrite_safety(r, tmp_path, repos)["safe_rewrite"] for r in (inner, fork, vendored))
