"""A green process exit must not conceal an empty or skipped required suite."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'check_test_report', Path(__file__).parents[1] / 'scripts/check_test_report.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


@pytest.mark.parametrize('body, accepted', [
    ('<testcase name="passes"/>', True),
    ('', False),
    ('<testcase><skipped message="missing DSN"/></testcase>', False),
    ('<testcase><failure/></testcase>', False),
    ('<testcase><error/></testcase>', False),
])
def test_required_report_rejects_missing_execution(tmp_path, body, accepted):
    path = tmp_path / 'report.xml'
    path.write_text(f'<testsuites><testsuite>{body}</testsuite></testsuites>')
    assert report.check(path) is accepted


def test_malformed_report_fails_closed(tmp_path):
    path = tmp_path / 'report.xml'
    path.write_text('not XML')
    with pytest.raises(report.ET.ParseError):
        report.check(path)


def test_required_ci_rejects_deselection():
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/test_config.py', '-q', '-k', 'bounded'],
        env={**os.environ, 'NAVICAST_REQUIRED_TESTS': '1'},
        capture_output=True, text=True,
    )
    assert result.returncode == 4
    assert 'must not be deselected' in result.stderr


def test_successful_subset_or_file_wrapper_cannot_replace_required_testcases(tmp_path):
    path = tmp_path / 'report.xml'
    path.write_text('<testsuites><testcase classname="browser" name="projection"/></testsuites>')
    required = ['browser::projection', 'browser::render limit notice']
    assert not report.check(path, required)
    path.write_text('<testsuites><testcase classname="test" name="tests/browser.spec.mjs"/></testsuites>')
    assert not report.check(path, required)
