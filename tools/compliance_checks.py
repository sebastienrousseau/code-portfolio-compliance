# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""The 24 compliance checks: evidence gathered from a repository, the reasons a
check does not apply, and one function per category of the matrix."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
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


def has_terms(text: str, *terms: str) -> bool:
    return all(term.lower() in text for term in terms)


def has_any_term(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


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


REQ = ""  # a gate part that is always applicable


@dataclass(frozen=True)
class Evidence:
    """What the checks read from one repository: its files, README and workflows."""

    repo: Path
    text: str  # corpus(): README, manifests and workflows, lowercased
    readme: str
    workflows: str  # every workflow file, lowercased
    workflow_names: str
    has_workflows: bool

    def exists(self, *names: str) -> bool:
        return exists_any(self.repo, names)

    def is_file(self, name: str) -> bool:
        return (self.repo / name).is_file()

    def is_dir(self, name: str) -> bool:
        return (self.repo / name).is_dir()

    def in_workflows(self, *terms: str) -> bool:
        return has_any_term(self.workflows, terms)

    def anywhere(self, *terms: str) -> bool:
        return has_any_term(self.workflows + self.text, terms)


def gather_evidence(repo: Path, text: str) -> Evidence:
    workflow_paths = paths_matching(repo, [".github/workflows/*.yml", ".github/workflows/*.yaml"])
    return Evidence(
        repo=repo,
        text=text,
        readme=read_text(repo / "README.md"),
        workflows="\n".join(read_text(path) for path in workflow_paths).lower(),
        workflow_names=" ".join(path.name.lower() for path in workflow_paths),
        has_workflows=bool(workflow_paths),
    )


@dataclass(frozen=True)
class Applicability:
    """Reasons a check does not apply; an empty string means it applies."""

    cli: str = ""
    package: str = ""
    locked: str = ""
    code: str = ""
    api: str = ""
    powerset: str = ""


# Programs are looked for anywhere in the tree (workspace members ship
# binaries too), outside examples, fixtures and build-only xtask crates.
NOT_SHIPPED = {"testdata", "examples", "example", "fixtures", "xtask", "benches"}
GO_PRIVATE = {"internal", "cmd", "testdata", "examples", "scripts", "tools"}


def _is_go_main(path: Path) -> bool:
    return path.suffix == ".go" and not path.name.endswith("_test.go") and re.search(r"(?m)^package main\b", read_text(path, 4096)) is not None


def _is_rust_binary(path: Path) -> bool:
    if path.name == "main.rs" and path.parent.name == "src":
        return True
    return path.parent.name == "bin" and path.parent.parent.name == "src" and path.suffix == ".rs"


def _declares_program(path: Path) -> bool:
    if path.name == "Cargo.toml":
        return re.search(r"(?m)^\[\[bin\]\]", read_text(path)) is not None
    if path.name == "pyproject.toml":
        return re.search(r"(?m)^\[(project|tool\.poetry)\.scripts\]", read_text(path)) is not None
    if path.name == "package.json":
        return '"bin"' in read_text(path)
    return path.name in ("__main__.py", "Dockerfile", "Containerfile")


def is_program(path: Path) -> bool:
    return _is_go_main(path) or _is_rust_binary(path) or _declares_program(path)


def source_files(repo: Path) -> list[Path]:
    return [path for path in repo.rglob("*") if path.is_file() and not SKIP_DIRS.intersection(path.parts)]


def has_cli(repo: Path, files: list[Path]) -> bool:
    return any(is_program(path) for path in files if not NOT_SHIPPED & set(path.relative_to(repo).parts))


def has_public_go(repo: Path, files: list[Path]) -> bool:
    return any(not (GO_PRIVATE & set(path.relative_to(repo).parts)) and not path.name.endswith("_test.go") for path in files if path.suffix == ".go")


def _program_reasons(program_free: bool) -> dict[str, str]:
    if not program_free:
        return {}
    return {
        "cli": "no command-line entry point (library or action): nothing to complete or document as a manpage",
        "package": "ships no program a distribution or a container would package (library or action)",
    }


def _api_reason(repo: Path, files: list[Path], manifests: dict[str, str], na_code: str) -> str:
    go_mod = manifests["go.mod"]
    public_go = bool(go_mod) and has_public_go(repo, files)
    if public_go or manifests["Cargo.toml"] or manifests["pyproject.toml"] or manifests["package.json"]:
        return ""
    return "no public API: only commands and internal packages" if go_mod else na_code


def _dependency_reason(manifests: dict[str, str], is_action: bool) -> str:
    go_mod = manifests["go.mod"]
    other_manifest = bool(manifests["Cargo.toml"] or manifests["pyproject.toml"] or manifests["package.json"])
    has_manifest = bool(go_mod) or other_manifest
    go_requires_nothing = bool(go_mod) and re.search(r"(?m)^require\b", go_mod) is None
    if (not has_manifest and is_action) or (go_requires_nothing and not other_manifest):
        return "no third-party dependencies to lock or audit"
    return ""


def _code_reason(has_manifest: bool, is_action: bool) -> str:
    if is_action and not has_manifest:
        return "a composite action with no language manifest: no API, coverage or toolchain matrix to run"
    return ""


def applicability(repo: Path) -> Applicability:
    manifests = {name: read_text(repo / name) for name in ("go.mod", "Cargo.toml", "pyproject.toml", "package.json")}
    has_manifest = any(manifests.values())
    is_action = exists_any(repo, ["action.yml", "action.yaml"])
    files = source_files(repo)
    # Conservative: a repository is program-free only when a manifest says it
    # is a library, or it is an action. Anything unrecognised stays applicable.
    program_free = not has_cli(repo, files) and (has_manifest or is_action)
    na_code = _code_reason(has_manifest, is_action)
    return Applicability(
        **_program_reasons(program_free),
        locked=_dependency_reason(manifests, is_action),
        code=na_code,
        api=_api_reason(repo, files, manifests, na_code),
        powerset="" if manifests["Cargo.toml"] else "feature powersets are a Cargo concept; this ecosystem has no feature flags (AGENTS.md §6)",
    )


# --- one function per category; each returns its L1, L2 and L3 checks -------


def identity_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    readme = ev.readme
    license_present = ev.exists("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENSE-APACHE", "LICENSE-MIT", "COPYING")
    sections = "quick start" in readme.lower() and "development" in readme.lower()
    stability = re.search(r"(?im)^## stability guarantees\s*$", readme) is not None
    security_section = re.search(r"(?im)^## security\s*$", readme) is not None
    toolchain_matrix = has_any_term(readme, ["msrv by", "minimum toolchain", "toolchain policy"]) and "|" in readme
    return {
        "C1.L1": Check(bool(readme and license_present and sections), "README + Quick Start + Development + license"),
        "C1.L2": Check(bool("readme" in ev.workflows and stability and security_section), "README CI + Stability guarantees + Security"),
        "C1.L3": Check(bool(ev.in_workflows("readme", "install snippet", "doctest") and toolchain_matrix), "install-snippet CI + toolchain policy matrix"),
    }


def documentation_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    source = ev.exists("src", "lib", "cmd", "app", "scripts", "Cargo.toml", "pyproject.toml", "package.json", "go.mod", "action.yml", "action.yaml")
    docs_dir = ev.is_dir("docs") or ev.is_dir("doc")
    architecture = ev.exists("ARCHITECTURE.md", "docs/ARCHITECTURE.md", "doc/ARCHITECTURE.md")
    manual_deploy = docs_dir and ev.in_workflows("pages", "mkdocs", "mdbook", "sphinx", "docusaurus", "vitepress", "hugo")
    adr = any(ev.is_dir(name) for name in ("docs/adr", "docs/adrs", "doc/adr"))
    migration_globs = ["MIGRATION*.md", "docs/*MIGRATION*.md", "doc/*MIGRATION*.md", "docs/migrating/*.md", "docs/migration/*.md"]
    migration = bool(paths_matching(ev.repo, migration_globs))
    link_check = ev.in_workflows("lychee", "linkcheck", "link-check", "markdown-link-check")
    api_docs = ev.in_workflows("rustdoc", "cargo doc", "sphinx", "mkdocs", "typedoc", "pkgsite")
    strict_api_docs = api_docs and ev.in_workflows("warnings", "-d warnings", "deny(warnings)", "missing_docs")
    return {
        "C2.L1": Check(bool(ev.readme and source), "README + source/documentation surface"),
        "C2.L2": Check(bool(docs_dir and manual_deploy and architecture), "docs root + deployed manual CI + ARCHITECTURE.md"),
        "C2.L3": gate("ADRs + link CI + migration guide + strict API docs", (adr, REQ), (link_check, REQ), (migration, REQ), (strict_api_docs, na.api)),
    }


def build_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    native_build = ev.exists("Cargo.toml", "pyproject.toml", "package.json", "go.mod", "Makefile", "CMakeLists.txt", "Package.swift")
    completions = has_any_term(ev.text, ["completion", "completions", "clap_complete"])
    manpages = has_any_term(ev.text, ["manpage", "man page", "clap_mangen", "argparse-manpage"])
    return {
        "C3.L1": Check(native_build, "native build manifest/tool"),
        "C3.L2": gate("Makefile + completion generation", (ev.exists("Makefile", "makefile"), REQ), (completions, na.cli)),
        "C3.L3": gate("GNUmakefile + manpage generation", (ev.is_file("GNUmakefile"), REQ), (manpages, na.cli)),
    }


def release_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    tags = bool(git_output(ev.repo, "tag", "-l", timeout=4))
    changelog = ev.exists("CHANGELOG.md", "CHANGES.md", "HISTORY.md", "NEWS.md")
    release = has_any_term(ev.workflow_names + ev.workflows, ["release", "publish"])
    binaries = ev.in_workflows("upload-artifact", "upload-release-asset", "gh release", "release-action")
    static = ev.anywhere("musl", "static binary", "static binaries")
    signed = ev.anywhere("cosign", "signed tag", "git tag -s", "sigstore")
    slsa = "slsa" in ev.workflows or "slsa" in ev.text
    sbom = ev.anywhere("sbom", "syft", "cyclonedx", "spdx-json")
    return {
        "C4.L1": Check(bool(tags and changelog), "local tags + changelog"),
        "C4.L2": Check(bool(release and binaries), "release workflow + binary artifacts"),
        "C4.L3": Check(bool(static and signed and slsa and sbom), "static binaries + signing + SLSA + SBOM"),
    }


def packaging_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    container = ev.exists("Dockerfile", "Containerfile") or "docker build" in ev.workflows
    pkg = ev.is_dir("pkg") or ev.is_dir("packaging")
    reproducible = ev.in_workflows("reproducible", "reprotest", "diffoscope")
    return {
        "C5.L1": Check(True, "source or native registry packaging allowed"),
        "C5.L2": gate("container packaging + Repology tracking", (container, na.package), ("repology" in ev.text, na.package)),
        "C5.L3": gate("pkg/packaging generators + reproducibility CI", (pkg, na.package), (reproducible, na.package)),
    }


def _has_go_fuzz_targets(repo: Path) -> bool:
    if not (repo / "go.mod").is_file():
        return False
    return any("func Fuzz" in read_text(path) for path in repo.rglob("*_test.go") if not SKIP_DIRS.intersection(path.parts))


def ci_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    lint = ev.in_workflows("lint", "clippy", "ruff", "golangci-lint", "eslint", "biome")
    fmt = ev.in_workflows("format", "fmt", "rustfmt", "prettier", "ruff format")
    tests = ev.in_workflows(" test", "test ", "pytest", "cargo test", "go test", "npm test", "vitest", "smoke")
    matrix = "matrix:" in ev.workflows and ev.in_workflows("os:", "toolchain", "rust:", "python-version", "node-version", "go-version")
    coverage = ev.in_workflows("coverage", "codecov", "coveralls", "tarpaulin", "llvm-cov")
    api_docs = ev.in_workflows("rustdoc", "cargo doc", "sphinx", "mkdocs", "typedoc", "pkgsite")
    api_break = ev.in_workflows("semver-check", "cargo-semver", "griffe", "api-extractor", "apidiff", "gorelease")
    fuzz = (ev.is_dir("fuzz") or _has_go_fuzz_targets(ev.repo)) and ev.in_workflows("fuzz", "corpus")
    powerset = ev.in_workflows("powerset", "all-features", "feature matrix", "hack check")
    return {
        "C6.L1": Check(bool(ev.has_workflows and lint and fmt and tests), "CI lint + format + tests"),
        "C6.L2": gate("OS/toolchain matrix + coverage + API docs", (matrix, na.code), (coverage, na.code), (api_docs, na.api)),
        "C6.L3": gate("API breakage + fuzz replay + feature powerset", (api_break, na.api), (fuzz, na.code), (powerset, na.powerset)),
    }


def supply_chain_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    dependency_scan = ev.is_file(".github/dependabot.yml") or ev.in_workflows("dependency-review", "renovate", "dependabot")
    lockfile = ev.exists("Cargo.lock", "uv.lock", "poetry.lock", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "go.sum")
    advisory = ev.in_workflows("cargo audit", "cargo deny", "pip-audit", "npm audit", "govulncheck", "osv-scanner")
    scorecard = "scorecard" in ev.workflows or "scorecard" in ev.text
    provenance = ev.anywhere("provenance", "attestation", "attest-build-provenance", "npm publish --provenance")
    return {
        "C7.L1": Check(bool(ev.is_file("SECURITY.md") and dependency_scan), "SECURITY.md + dependency scanning"),
        "C7.L2": gate("lockfile + advisory audit CI", (lockfile, na.locked), (advisory, na.locked)),
        "C7.L3": Check(bool(scorecard and ev.is_file("KEYS.asc") and provenance), "Scorecard + KEYS.asc + provenance"),
    }


def community_checks(ev: Evidence, na: Applicability) -> dict[str, Check]:
    pr_templates = (".github/pull_request_template.md", ".github/PULL_REQUEST_TEMPLATE.md", ".github/PULL_REQUEST_TEMPLATE")
    templates = (ev.repo / ".github/ISSUE_TEMPLATE").exists() and ev.exists(*pr_templates)
    devcontainer = ev.is_dir(".devcontainer") and "devcontainer" in ev.workflows
    return {
        "C8.L1": Check(bool(ev.is_file("CODE_OF_CONDUCT.md") and ev.is_file("CONTRIBUTING.md")), "Code of Conduct + contributing guide"),
        "C8.L2": Check(bool(templates and "markdownlint" in ev.workflows), "issue/PR templates + markdownlint CI"),
        "C8.L3": Check(bool(ev.is_file("AGENTS.md") and ev.is_file("CITATION.cff") and devcontainer), "AGENTS.md + CITATION.cff + devcontainer CI"),
    }


CATEGORIES = (
    identity_checks,
    documentation_checks,
    build_checks,
    release_checks,
    packaging_checks,
    ci_checks,
    supply_chain_checks,
    community_checks,
)


def checks_for(repo: Path, text: str) -> dict[str, Check]:
    """The 24 checks for one repository, in C1.L1 ... C8.L3 order."""
    evidence = gather_evidence(repo, text)
    na = applicability(repo)
    checks: dict[str, Check] = {}
    for category in CATEGORIES:
        checks.update(category(evidence, na))
    return checks
