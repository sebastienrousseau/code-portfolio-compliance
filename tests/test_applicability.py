# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""When completions, manpages and API checks apply: an argument-less server
entry point, and a private package.json that only locks dev tooling."""

import json
from pathlib import Path

import audit_compliance as audit
import compliance_checks as checks
import pytest

SERVER = 'def main() -> None:\n    """Start the language server over stdio."""\n    server.start_io()\n'


def server_repo(path: Path, table: str = "tool.poetry.scripts", target: str = "demo_lsp.server:main", layout: str = "") -> Path:
    """A Python project shaped like bankstatementparser-lsp: one console script, a Dockerfile, argparse only in dev scripts."""
    (path / "pyproject.toml").write_text(f'[tool.poetry]\nname = "demo-lsp"\n\n[{table}]\ndemo-lsp = "{target}"\n')
    package = path / layout / "demo_lsp"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "server.py").write_text(SERVER)
    (path / "Dockerfile").write_text('FROM python:3.13-slim\nENTRYPOINT ["demo-lsp"]\n')
    (path / "Makefile").write_text("all:\n")
    (path / "GNUmakefile").write_text("include Makefile\n")
    (path / "scripts").mkdir()
    (path / "scripts" / "release_notes.py").write_text("import argparse\n")
    return path


def run_checks(repo: Path) -> dict[str, checks.Check]:
    return audit.checks_for(repo, audit.corpus(repo))


@pytest.mark.parametrize(
    ("table", "layout"),
    [("tool.poetry.scripts", ""), ("project.scripts", ""), ("project.scripts", "src")],
)
def test_an_entry_point_without_an_argument_parser_has_nothing_to_complete(tmp_path, table, layout):
    repo = server_repo(tmp_path, table=table, layout=layout)
    na = checks.applicability(repo)
    assert na.cli.startswith("no entry point parses arguments")
    assert na.package == ""  # the Dockerfile still ships a program
    result = run_checks(repo)
    assert result["C3.L2"].not_applicable == na.cli
    assert result["C3.L3"].not_applicable == na.cli


@pytest.mark.parametrize(
    "source",
    [
        "import argparse\n",
        "from argparse import ArgumentParser\n",
        "import click\n",
        "import typer\n",
        "from docopt import docopt\n",
        "import sys\nNAME = sys.argv[1]\n",
        "def main(argv=None):\n    pass\n",
    ],
)
def test_an_entry_point_package_that_parses_arguments_stays_applicable(tmp_path, source):
    # bankstatementparser-mcp: its package builds an argparse parser, so it
    # has options to complete.
    repo = server_repo(tmp_path)
    (repo / "demo_lsp" / "_cli.py").write_text(source)
    assert checks.applicability(repo).cli == ""


def test_an_entry_point_outside_the_repository_stays_applicable(tmp_path):
    repo = server_repo(tmp_path, target="somewhere_else.server:main")
    assert checks.applicability(repo).cli == ""


def test_an_unrecognised_script_table_entry_stays_applicable(tmp_path):
    repo = server_repo(tmp_path)
    (repo / "scripts" / "release_notes.py").unlink()  # no parser anywhere: the entry alone must keep the checks
    text = (repo / "pyproject.toml").read_text() + 'other = { callable = "demo_lsp.server:main" }\n'
    (repo / "pyproject.toml").write_text(text)
    assert checks.applicability(repo).cli == ""


@pytest.mark.parametrize(
    ("name", "body"),
    [("cmd/tool/main.go", "package main\n"), ("src/main.rs", "fn main() {}\n"), ("__main__.py", "print(1)\n")],
)
def test_any_other_program_stays_applicable(tmp_path, name, body):
    repo = server_repo(tmp_path)
    (repo / name).parent.mkdir(parents=True, exist_ok=True)
    (repo / name).write_text(body)
    assert checks.applicability(repo).cli == ""


def test_a_dockerfile_without_a_declared_entry_point_stays_applicable(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "app"\n')
    (tmp_path / "Dockerfile").write_text("FROM python:3.13-slim\n")
    assert checks.applicability(tmp_path).cli == ""


TOOLING = {
    "name": "site.github.io",
    "private": True,
    "description": "Build and audit tooling for the site.",
    "devDependencies": {"markdownlint-cli2": "0.24.2"},
}


def site_repo(path: Path, manifest: dict) -> Path:
    """A static site shaped like bankstatementparser.github.io: a package.json for dev tooling only."""
    (path / "package.json").write_text(json.dumps(manifest))
    (path / "index.html").write_text("<!doctype html>\n")
    workflows = path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("jobs:\n  test:\n    strategy:\n      matrix:\n        os: [ubuntu-latest]\n    steps:\n      - run: make coverage\n")
    return path


def test_a_private_tooling_package_publishes_no_api_or_program(tmp_path):
    na = checks.applicability(site_repo(tmp_path, TOOLING))
    assert na.api.startswith("a private package.json with no bin, main or exports")
    assert na.cli.startswith("a private package.json with no bin, main or exports")
    assert na.package.startswith("a private package.json with no bin, main or exports")
    result = run_checks(tmp_path)
    assert result["C6.L2"].not_applicable == na.api  # matrix and coverage present, API docs n/a
    assert result["C5.L2"].not_applicable == na.package


@pytest.mark.parametrize(
    "change",
    [
        {"private": False},
        {"bin": {"site": "cli.js"}},
        {"main": "index.js"},
        {"exports": "./index.js"},
        {"module": "index.mjs"},
        {"types": "index.d.ts"},
        {"workspaces": ["packages/*"]},
    ],
)
def test_a_package_json_that_may_publish_stays_applicable(tmp_path, change):
    na = checks.applicability(site_repo(tmp_path, {**TOOLING, **change}))
    assert na.api == ""


def test_a_package_json_without_private_stays_applicable(tmp_path):
    manifest = {key: value for key, value in TOOLING.items() if key != "private"}
    assert checks.applicability(site_repo(tmp_path, manifest)).api == ""


def test_an_unreadable_package_json_stays_applicable(tmp_path):
    site_repo(tmp_path, TOOLING)
    (tmp_path / "package.json").write_text('{"private": true,')
    assert checks.applicability(tmp_path).api == ""


def test_a_private_tooling_package_beside_a_python_package_keeps_its_api(tmp_path):
    site_repo(tmp_path, TOOLING)
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "lib"\n')
    assert checks.applicability(tmp_path).api == ""
