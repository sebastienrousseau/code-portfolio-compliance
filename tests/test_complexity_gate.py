# SPDX-FileCopyrightText: 2026 Sebastien Rousseau <sebastian.rousseau@gmail.com>
# SPDX-License-Identifier: MIT OR Apache-2.0
"""The complexity baseline may only shrink."""

import complexity_gate as gate

BASE = {"f.py::big": {"cyclomatic": 20}}


def test_unchanged_offender_passes():
    assert gate.compare({"f.py::big": {"cyclomatic": 20}}, BASE) == []


def test_worse_offender_fails():
    assert gate.compare({"f.py::big": {"cyclomatic": 21}}, BASE)


def test_new_offender_fails():
    assert gate.compare({**BASE, "f.py::other": {"lines": 61}}, BASE)


def test_new_metric_on_baselined_function_fails():
    assert gate.compare({"f.py::big": {"cyclomatic": 20, "cognitive": 16}}, BASE)


def test_improvement_requires_tightening_the_baseline():
    assert gate.compare({"f.py::big": {"cyclomatic": 12}}, BASE)
    assert gate.compare({}, BASE)


def test_over_ceiling_uses_each_limit():
    metrics = {"cyclomatic": 10, "cognitive": 16, "halstead": 30.5, "lines": 60, "file_lines": 501}
    assert gate.over_ceiling(metrics) == {"cognitive": 16, "halstead": 30.5, "file_lines": 501}
