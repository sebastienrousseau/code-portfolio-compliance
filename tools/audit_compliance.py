#!/usr/bin/env python3
"""Statically audit repositories against the workspace compliance matrix.

The report is intentionally conservative: it records discoverable repository and
CI signals, but it does not turn a static match into a claim that a workflow has
passed. Generated reports are evidence for remediation and manual verification.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "bin",
    "build",
    "dist",
    "node_modules",
    "target",
}

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


@dataclass(frozen=True)
class Check:
    ok: bool
    evidence: str
    # A requirement whose subject does not exist in the repository (shell
    # completions for a library, a lockfile for a module with no
    # dependencies) is not applicable. It satisfies its tier, is reported
    # separately with its reason, and is left out of the score, so it can
    # never read as a pass.
    not_applicable: str = ""


def exists_any(repo: Path, names: Iterable[str]) -> bool:
    return any((repo / name).exists() for name in names)


def paths_matching(repo: Path, patterns: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        found.extend(repo.glob(pattern))
    return sorted(set(found))


def read_text(path: Path, limit: int = 512_000) -> str:
    try:
        with path.open("rb") as handle:
            return handle.read(limit).decode("utf-8", errors="replace")
    except (OSError, ValueError):
        return ""


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


def has_terms(text: str, *terms: str) -> bool:
    return all(term.lower() in text for term in terms)


def has_any_term(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


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


def git_output(repo: Path, *args: str, timeout: int = 8) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


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


def checks_for(repo: Path, text: str) -> dict[str, Check]:
    readme = read_text(repo / "README.md")
    workflow_paths = paths_matching(repo, [".github/workflows/*.yml", ".github/workflows/*.yaml"])
    workflow_text = "\n".join(read_text(path) for path in workflow_paths).lower()
    workflow_names = " ".join(path.name.lower() for path in workflow_paths)
    license_present = exists_any(
        repo,
        ["LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE-APACHE", "LICENSE-MIT", "COPYING"],
    )
    source_markers = exists_any(
        repo,
        ["src", "lib", "cmd", "app", "scripts", "Cargo.toml", "pyproject.toml", "package.json", "go.mod", "action.yml", "action.yaml"],
    )
    native_build = exists_any(
        repo,
        ["Cargo.toml", "pyproject.toml", "package.json", "go.mod", "Makefile", "CMakeLists.txt", "Package.swift"],
    )
    changelog = exists_any(repo, ["CHANGELOG.md", "CHANGES.md", "HISTORY.md", "NEWS.md"])
    tags = bool(git_output(repo, "tag", "-l", timeout=4))
    docs_dir = (repo / "docs").is_dir() or (repo / "doc").is_dir()
    architecture = exists_any(repo, ["ARCHITECTURE.md", "docs/ARCHITECTURE.md", "doc/ARCHITECTURE.md"])
    adr = any(path.is_dir() for path in [repo / "docs/adr", repo / "docs/adrs", repo / "doc/adr"])
    migration = bool(paths_matching(repo, ["MIGRATION*.md", "docs/*MIGRATION*.md", "doc/*MIGRATION*.md", "docs/migrating/*.md", "docs/migration/*.md"]))
    makefile = exists_any(repo, ["Makefile", "makefile"])
    gnufile = (repo / "GNUmakefile").is_file()
    completions = has_any_term(text, ["completion", "completions", "clap_complete"])
    manpages = has_any_term(text, ["manpage", "man page", "clap_mangen", "argparse-manpage"])
    release = has_any_term(workflow_names + workflow_text, ["release", "publish"])
    binaries = has_any_term(workflow_text, ["upload-artifact", "upload-release-asset", "gh release", "release-action"])
    static = has_any_term(workflow_text + text, ["musl", "static binary", "static binaries"])
    signed = has_any_term(workflow_text + text, ["cosign", "signed tag", "git tag -s", "sigstore"])
    slsa = "slsa" in workflow_text or "slsa" in text
    sbom = has_any_term(workflow_text + text, ["sbom", "syft", "cyclonedx", "spdx-json"])
    container = exists_any(repo, ["Dockerfile", "Containerfile"]) or "docker build" in workflow_text
    repology = "repology" in text
    pkg = (repo / "pkg").is_dir() or (repo / "packaging").is_dir()
    reproducible = has_any_term(workflow_text, ["reproducible", "reprotest", "diffoscope"])
    lint = has_any_term(workflow_text, ["lint", "clippy", "ruff", "golangci-lint", "eslint", "biome"])
    fmt = has_any_term(workflow_text, ["format", "fmt", "rustfmt", "prettier", "ruff format"])
    tests = has_any_term(workflow_text, [" test", "test ", "pytest", "cargo test", "go test", "npm test", "vitest", "smoke"])
    matrix = "matrix:" in workflow_text and has_any_term(workflow_text, ["os:", "toolchain", "rust:", "python-version", "node-version", "go-version"])
    coverage = has_any_term(workflow_text, ["coverage", "codecov", "coveralls", "tarpaulin", "llvm-cov"])
    api_docs = has_any_term(workflow_text, ["rustdoc", "cargo doc", "sphinx", "mkdocs", "typedoc", "pkgsite"])
    api_break = has_any_term(workflow_text, ["semver-check", "cargo-semver", "griffe", "api-extractor", "apidiff", "gorelease"])
    go_fuzz_targets = (repo / "go.mod").is_file() and any(
        "func Fuzz" in read_text(path) for path in repo.rglob("*_test.go") if not SKIP_DIRS.intersection(path.parts)
    )
    fuzz = ((repo / "fuzz").is_dir() or go_fuzz_targets) and has_any_term(workflow_text, ["fuzz", "corpus"])
    powerset = has_any_term(workflow_text, ["powerset", "all-features", "feature matrix", "hack check"])
    dependency_scan = (repo / ".github/dependabot.yml").is_file() or has_any_term(workflow_text, ["dependency-review", "renovate", "dependabot"])
    lockfile = exists_any(repo, ["Cargo.lock", "uv.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.sum"])
    advisory = has_any_term(workflow_text, ["cargo audit", "cargo deny", "pip-audit", "npm audit", "govulncheck", "osv-scanner"])
    scorecard = "scorecard" in workflow_text or "scorecard" in text
    keys = (repo / "KEYS.asc").is_file()
    provenance = has_any_term(workflow_text + text, ["provenance", "attestation", "attest-build-provenance", "npm publish --provenance"])
    templates = (repo / ".github/ISSUE_TEMPLATE").exists() and exists_any(
        repo, [".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE"]
    )
    markdownlint = "markdownlint" in workflow_text
    devcontainer = (repo / ".devcontainer").is_dir() and "devcontainer" in workflow_text
    readme_ci = "readme" in workflow_text
    stability = re.search(r"(?im)^## stability guarantees\s*$", readme) is not None
    security_section = re.search(r"(?im)^## security\s*$", readme) is not None
    toolchain_matrix = has_any_term(readme, ["msrv by", "minimum toolchain", "toolchain policy"]) and "|" in readme
    install_ci = has_any_term(workflow_text, ["readme", "install snippet", "doctest"])
    manual_deploy = docs_dir and has_any_term(workflow_text, ["pages", "mkdocs", "mdbook", "sphinx", "docusaurus", "vitepress", "hugo"])
    link_check = has_any_term(workflow_text, ["lychee", "linkcheck", "link-check", "markdown-link-check"])
    public_api_docs = api_docs and has_any_term(workflow_text, ["warnings", "-d warnings", "deny(warnings)", "missing_docs"])

    # --- applicability: what the repository is, from its manifests -------------
    go_mod = read_text(repo / "go.mod")
    cargo = read_text(repo / "Cargo.toml")
    pyproject = read_text(repo / "pyproject.toml")
    package_json = read_text(repo / "package.json")
    is_action = exists_any(repo, ["action.yml", "action.yaml"])
    has_manifest = bool(go_mod or cargo or pyproject or package_json)
    source_files = [path for path in repo.rglob("*") if path.is_file() and not SKIP_DIRS.intersection(path.parts)]
    # Programs are looked for anywhere in the tree (workspace members ship
    # binaries too), outside examples, fixtures and build-only xtask crates.
    not_shipped = {"testdata", "examples", "example", "fixtures", "xtask", "benches"}
    shipped = [path for path in source_files if not not_shipped & set(path.relative_to(repo).parts)]
    has_cli = any(
        (path.suffix == ".go" and not path.name.endswith("_test.go") and re.search(r"(?m)^package main\b", read_text(path, 4096)))
        or (path.name == "main.rs" and path.parent.name == "src")
        or (path.parent.name == "bin" and path.parent.parent.name == "src" and path.suffix == ".rs")
        or (path.name == "Cargo.toml" and re.search(r"(?m)^\[\[bin\]\]", read_text(path)))
        or (path.name == "pyproject.toml" and re.search(r"(?m)^\[(project|tool\.poetry)\.scripts\]", read_text(path)))
        or path.name == "__main__.py"
        or (path.name == "package.json" and '"bin"' in read_text(path))
        or path.name in ("Dockerfile", "Containerfile")
        for path in shipped
    )
    # Conservative: a repository is program-free only when a manifest says it
    # is a library, or it is an action. Anything unrecognised stays applicable.
    program_free = not has_cli and (has_manifest or is_action)
    go_requires_nothing = bool(go_mod) and re.search(r"(?m)^require\b", go_mod) is None
    no_dependencies = (not has_manifest and is_action) or (go_requires_nothing and not (cargo or pyproject or package_json))
    na_cli = "no command-line entry point (library or action): nothing to complete or document as a manpage" if program_free else ""
    na_package = "ships no program a distribution or a container would package (library or action)" if program_free else ""
    na_locked = "no third-party dependencies to lock or audit" if no_dependencies else ""
    na_code = "a composite action with no language manifest: no API, coverage or toolchain matrix to run" if is_action and not has_manifest else ""

    go_packages = [path for path in source_files if path.suffix == ".go"] if go_mod else []
    public_go = any(
        not ({"internal", "cmd", "testdata", "examples", "scripts", "tools"} & set(path.relative_to(repo).parts)) and not path.name.endswith("_test.go")
        for path in go_packages
    )
    na_api = "" if (public_go or cargo or pyproject or package_json) else ("no public API: only commands and internal packages" if go_mod else na_code)
    na_powerset = "" if cargo else "feature powersets are a Cargo concept; this ecosystem has no feature flags (AGENTS.md §6)"

    def gate(evidence: str, *parts: tuple[bool, str]) -> Check:
        """Each part is (present, not-applicable reason). The check passes when
        every part is present; it is not applicable when every missing part
        has a reason; otherwise it fails."""
        missing = [reason for present, reason in parts if not present]
        if not missing:
            return Check(True, evidence)
        if all(missing):
            return Check(False, evidence, "; ".join(dict.fromkeys(missing)))
        return Check(False, evidence)

    req = ""  # a part that is always applicable

    return {
        "C1.L1": Check(
            bool(readme and license_present and "quick start" in readme.lower() and "development" in readme.lower()),
            "README + Quick Start + Development + license",
        ),
        "C1.L2": Check(bool(readme_ci and stability and security_section), "README CI + Stability guarantees + Security"),
        "C1.L3": Check(bool(install_ci and toolchain_matrix), "install-snippet CI + toolchain policy matrix"),
        "C2.L1": Check(bool(readme and source_markers), "README + source/documentation surface"),
        "C2.L2": Check(bool(docs_dir and manual_deploy and architecture), "docs root + deployed manual CI + ARCHITECTURE.md"),
        "C2.L3": gate("ADRs + link CI + migration guide + strict API docs", (adr, req), (link_check, req), (migration, req), (public_api_docs, na_api)),
        "C3.L1": Check(native_build, "native build manifest/tool"),
        "C3.L2": gate("Makefile + completion generation", (makefile, req), (completions, na_cli)),
        "C3.L3": gate("GNUmakefile + manpage generation", (gnufile, req), (manpages, na_cli)),
        "C4.L1": Check(bool(tags and changelog), "local tags + changelog"),
        "C4.L2": Check(bool(release and binaries), "release workflow + binary artifacts"),
        "C4.L3": Check(bool(static and signed and slsa and sbom), "static binaries + signing + SLSA + SBOM"),
        "C5.L1": Check(True, "source or native registry packaging allowed"),
        "C5.L2": gate("container packaging + Repology tracking", (container, na_package), (repology, na_package)),
        "C5.L3": gate("pkg/packaging generators + reproducibility CI", (pkg, na_package), (reproducible, na_package)),
        "C6.L1": Check(bool(workflow_paths and lint and fmt and tests), "CI lint + format + tests"),
        "C6.L2": gate("OS/toolchain matrix + coverage + API docs", (matrix, na_code), (coverage, na_code), (api_docs, na_api)),
        "C6.L3": gate("API breakage + fuzz replay + feature powerset", (api_break, na_api), (fuzz, na_code), (powerset, na_powerset)),
        "C7.L1": Check(bool((repo / "SECURITY.md").is_file() and dependency_scan), "SECURITY.md + dependency scanning"),
        "C7.L2": gate("lockfile + advisory audit CI", (lockfile, na_locked), (advisory, na_locked)),
        "C7.L3": Check(bool(scorecard and keys and provenance), "Scorecard + KEYS.asc + provenance"),
        "C8.L1": Check(bool((repo / "CODE_OF_CONDUCT.md").is_file() and (repo / "CONTRIBUTING.md").is_file()), "Code of Conduct + contributing guide"),
        "C8.L2": Check(bool(templates and markdownlint), "issue/PR templates + markdownlint CI"),
        "C8.L3": Check(
            bool((repo / "AGENTS.md").is_file() and (repo / "CITATION.cff").is_file() and devcontainer), "AGENTS.md + CITATION.cff + devcontainer CI"
        ),
    }


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


def write_reports(results: list[dict[str, object]], output: Path, root: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload = {
        "schema_version": 2,
        "generated_at": generated,
        "workspace": str(root),
        "method": "static conservative signals; CI execution and business criticality require verification",
        "repositories": results,
    }
    (output / "audit.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    fields = [
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
    with (output / "audit.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            row = {key: result[key] for key in fields}
            row["missing_target_signals"] = "; ".join(result["missing_target_signals"])
            writer.writerow(row)

    target_counts = Counter(str(result["target_tier"]) for result in results)
    template_passes = sum(result["readme_template"] == "pass" for result in results)
    rewrite_queue = [str(result["path"]) for result in results if result["safe_rewrite"] and result["readme_template"] == "fail"]
    (output / "rewrite-queue.txt").write_text("\n".join(rewrite_queue) + ("\n" if rewrite_queue else ""), encoding="utf-8")

    portfolio: dict[str, Counter[str]] = defaultdict(Counter)
    for result in results:
        bucket = str(result["path"]).split("/", 1)[0]
        portfolio[bucket][str(result["candidate_tier"])] += 1

    try:
        script_name = Path(__file__).resolve().relative_to(root).as_posix()
    except ValueError:
        script_name = str(Path(__file__).resolve())

    lines = [
        "# Portfolio compliance audit",
        "",
        f"> Generated by `{script_name}` at {generated}. Do not edit by hand.",
        "",
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
        "## Summary",
        "",
        f"- Repositories: **{len(results)}**",
        f"- Canonical primary READMEs: **{template_passes}/{len(results)}**",
        f"- Safe README rewrite queue: **{len(rewrite_queue)}**",
        f"- Dirty repositories: **{sum(bool(result['dirty']) for result in results)}**",
        f"- Embedded/fork/vendor repositories excluded from automatic rewrites: **{sum(bool(result['embedded'] or result['fork_or_vendor']) for result in results)}**",
        "",
        "### Target tiers",
        "",
        "| L1 | L2 | L3 |",
        "| ---: | ---: | ---: |",
        f"| {target_counts['L1']} | {target_counts['L2']} | {target_counts['L3']} |",
        "",
        "### Candidate-tier heat map",
        "",
        "| Portfolio | L0 | L1 | L2 | L3 |",
        "| :--- | ---: | ---: | ---: | ---: |",
    ]
    for bucket in sorted(portfolio):
        counts = portfolio[bucket]
        lines.append(f"| {bucket} | {counts['L0']} | {counts['L1']} | {counts['L2']} | {counts['L3']} |")
    lines += [
        "",
        "## Repository results",
        "",
        "| Repository | Ecosystem | Target | Candidate | Score | README | Rewrite |",
        "| :--- | :--- | :---: | :---: | ---: | :---: | :---: |",
    ]
    for result in results:
        rewrite = "yes" if result["safe_rewrite"] and result["readme_template"] == "fail" else "no"
        lines.append(
            f"| `{result['path']}` | {result['ecosystem']} | {result['target_tier']} | "
            f"{result['candidate_tier']} | {result['score_percent']}% | {result['readme_template']} | {rewrite} |"
        )
    lines += [
        "",
        "## Artifacts",
        "",
        "- `audit.json`: complete machine-readable checks and evidence gaps.",
        "- `audit.csv`: portfolio triage table.",
        "- `rewrite-queue.txt`: clean, non-fork, non-embedded repositories whose primary README fails the template.",
        "",
    ]
    (output / "README.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    script_path = Path(__file__).resolve()
    parser.add_argument("--root", type=Path, default=find_workspace_root(script_path.parent))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--roots", nargs="*", default=["Public", "Private", "Work", "Forks"])
    args = parser.parse_args()

    root = args.root.resolve()
    output = (args.output or script_path.parents[1] / "reports").resolve()
    repositories = discover_repositories(root / name for name in args.roots)
    repo_set = set(repositories)
    results = [audit_repository(repo, root, repo_set) for repo in repositories]
    write_reports(results, output, root)
    print(f"Audited {len(results)} repositories; reports written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
