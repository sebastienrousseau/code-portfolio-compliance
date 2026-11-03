#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""Statically audit repositories against the workspace compliance matrix.

The report is intentionally conservative: it records discoverable repository and
CI signals, but it does not turn a static match into a claim that a workflow has
passed. Generated reports are evidence for remediation and manual verification.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import re
import sys
from collections.abc import Iterable
from pathlib import Path


def _load_sibling(name: str):
    """Import a module that sits next to this script, also under ``python -I`` (no script dir on sys.path)."""
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        path = Path(__file__).resolve().with_name(f"{name}.py")
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module


_checks = _load_sibling("compliance_checks")
write_reports = _load_sibling("compliance_report").write_reports
SKIP_DIRS = _checks.SKIP_DIRS
Check = _checks.Check
checks_for = _checks.checks_for
exists_any = _checks.exists_any
git_output = _checks.git_output
has_any_term = _checks.has_any_term
has_terms = _checks.has_terms
paths_matching = _checks.paths_matching
read_text = _checks.read_text

README_HEADINGS = [
    "Contents",
    "Install",
    "Requirements",
    "Quick Start",
    "The {project} ecosystem",
    "Capabilities at a glance",
    "Ecosystem comparison",
    "Benchmarks",
    "Features",
    "Configuration",
    "Examples",
    "When not to use {project}",
    "Development",
    "Security",
    "Documentation",
    "Stability guarantees",
    "License",
]

CATEGORY_NAMES = {
    1: "Identity & README",
    2: "Documentation",
    3: "Build & Install UX",
    4: "Releases & Binaries",
    5: "Packaging",
    6: "CI Quality Gates",
    7: "Supply Chain",
    8: "Community",
}


def corpus(repo: Path) -> str:
    paths = [
        repo / "README.md",
        repo / "Cargo.toml",
        repo / "pyproject.toml",
        repo / "package.json",
        repo / "go.mod",
        repo / "Makefile",
        repo / "GNUmakefile",
    ]
    paths += paths_matching(repo, [".github/workflows/*.yml", ".github/workflows/*.yaml"])
    return "\n".join(read_text(path) for path in paths if path.is_file()).lower()


def discover_repositories(roots: Iterable[Path]) -> list[Path]:
    repositories: set[Path] = set()
    for root in roots:
        if not root.exists():
            continue
        for current, dirs, files in os.walk(root):
            current_path = Path(current)
            if ".git" in dirs or ".git" in files:
                repositories.add(current_path.resolve())
            dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
    return sorted(repositories)


def find_workspace_root(start: Path) -> Path:
    """Find the portfolio root without requiring tooling at workspace top level."""
    for candidate in (start, *start.parents):
        if all((candidate / name).is_dir() for name in ("Forks", "Private", "Public", "Work")):
            return candidate
    raise RuntimeError("could not locate a workspace containing Forks, Private, Public, and Work")


def infer_ecosystem(repo: Path) -> str:
    markers = [
        ("Rust", ["Cargo.toml"]),
        ("Python", ["pyproject.toml", "setup.py", "setup.cfg"]),
        ("Node.js / TypeScript", ["package.json"]),
        ("Go", ["go.mod"]),
        ("Swift", ["Package.swift"]),
        ("Ruby", ["Gemfile", "*.gemspec"]),
        ("PHP", ["composer.json"]),
        ("C / C++", ["CMakeLists.txt", "meson.build"]),
    ]
    for label, names in markers:
        if any(list(repo.glob(name)) for name in names):
            return label
    return "Other"


def parse_declaration(repo: Path, relative: str) -> tuple[str, str, str]:
    declaration = read_text(repo / ".compliance.yml", 32_000)
    values: dict[str, str] = {}
    for key in ("tier", "criticality", "owner"):
        match = re.search(rf"(?m)^\s*{key}\s*:\s*['\"]?([^#'\"\n]+)", declaration)
        if match:
            values[key] = match.group(1).strip()

    portfolio = relative.split("/", 1)[0]
    default_tier = "L1" if portfolio in {"Private", "Forks"} else "L2"
    tier = values.get("tier", default_tier).upper()
    if tier not in {"L1", "L2", "L3"}:
        tier = default_tier
    criticality = values.get("criticality", "unclassified").lower()
    if criticality not in {"incubator", "standard", "core", "unclassified"}:
        criticality = "unclassified"
    return tier, criticality, values.get("owner", "")


# The template's variables are {{UPPER_SNAKE_CASE}}. Braces inside code
# (a Go composite literal, JSON, a GitHub Actions ${{ expression }}) are
# content, not an unresolved variable.
UNRESOLVED_TOKEN = re.compile(r"\{\{\s*[A-Z][A-Z0-9_]*\s*\}\}")
FENCED_CODE = re.compile(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$")
INLINE_CODE = re.compile(r"`[^`\n]*`")


def strip_code(text: str) -> str:
    return INLINE_CODE.sub("", FENCED_CODE.sub("", text))


def readme_template_status(repo: Path) -> tuple[bool, list[str]]:
    text = read_text(repo / "README.md")
    if not text:
        return False, ["README.md missing or unreadable"]
    if UNRESOLVED_TOKEN.search(strip_code(text)):
        return False, ["unresolved template variables"]
    project_match = re.search(r'<h1 align="center">([^<]+)</h1>', text)
    if not project_match:
        return False, ["centered project h1 missing"]
    project = project_match.group(1).strip()
    actual = re.findall(r"(?m)^## ([^\n]+)$", text)
    required = [heading.format(project=project) for heading in README_HEADINGS]
    if actual != required:
        missing = [heading for heading in required if heading not in actual]
        extra = [heading for heading in actual if heading not in required]
        issues = [f"missing heading: {heading}" for heading in missing]
        issues += [f"unexpected heading: {heading}" for heading in extra]
        if not issues:
            issues.append("required headings are out of order")
        return False, issues
    prefix_signals = [
        "<!-- SPDX-License-Identifier:",
        '<p align="center">',
        '<h1 align="center">',
        "ossf-scorecard",
    ]
    missing_prefix = [signal for signal in prefix_signals if signal not in text]
    return (not missing_prefix, [f"missing structure: {item}" for item in missing_prefix])


def candidate_tier(checks: dict[str, Check]) -> str:
    achieved = "L0"
    for level in range(1, 4):
        required = [check.ok or bool(check.not_applicable) for key, check in checks.items() if int(key[-1]) <= level]
        if required and all(required):
            achieved = f"L{level}"
        else:
            break
    return achieved


def audit_repository(repo: Path, root: Path, repo_set: set[Path]) -> dict[str, object]:
    relative = repo.relative_to(root).as_posix()
    text = corpus(repo)
    checks = checks_for(repo, text)
    target, criticality, owner = parse_declaration(repo, relative)
    template_ok, template_issues = readme_template_status(repo)
    status = git_output(repo, "status", "--porcelain", "--untracked-files=normal", timeout=10)
    dirty = bool(status)
    parents = [parent for parent in repo.parents if parent in repo_set]
    embedded = bool(parents)
    path_parts = set(repo.relative_to(root).parts)
    fork_or_vendor = relative.startswith("Forks/") or bool(path_parts & {"vendor", "vendors", "third_party", "tests", "fixtures"})
    safe_rewrite = not dirty and not embedded and not fork_or_vendor
    passed = sum(check.ok for check in checks.values())
    applicable = [check for check in checks.values() if not check.not_applicable]
    target_level = int(target[-1])
    missing = [f"{key} ({check.evidence})" for key, check in checks.items() if int(key[-1]) <= target_level and not check.ok and not check.not_applicable]
    not_applicable = {key: check.not_applicable for key, check in checks.items() if check.not_applicable}
    return {
        "path": relative,
        "ecosystem": infer_ecosystem(repo),
        "target_tier": target,
        "criticality": criticality,
        "owner": owner,
        "candidate_tier": candidate_tier(checks),
        "signals_passed": passed,
        "signals_total": len(applicable),
        "signals_not_applicable": len(not_applicable),
        "score_percent": round(100 * passed / len(applicable)) if applicable else 100,
        "readme_template": "pass" if template_ok else "fail",
        "readme_issues": template_issues,
        "dirty": dirty,
        "embedded": embedded,
        "fork_or_vendor": fork_or_vendor,
        "safe_rewrite": safe_rewrite,
        "missing_target_signals": missing,
        "checks": {key: ("n/a" if check.not_applicable else check.ok) for key, check in checks.items()},
        "not_applicable": not_applicable,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    script_path = Path(__file__).resolve()
    parser.add_argument("--root", type=Path, default=None, help="workspace root (default: the nearest parent holding Forks, Private, Public and Work)")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--roots", nargs="*", default=["Public", "Private", "Work", "Forks"])
    args = parser.parse_args()

    try:
        root = (args.root or find_workspace_root(script_path.parent)).resolve()
    except RuntimeError as exc:
        parser.error(f"{exc}; pass --root")
    output = (args.output or script_path.parents[1] / "reports").resolve()
    repositories = discover_repositories(root / name for name in args.roots)
    repo_set = set(repositories)
    results = [audit_repository(repo, root, repo_set) for repo in repositories]
    write_reports(results, output, root)
    print(f"Audited {len(results)} repositories; reports written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
