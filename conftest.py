"""Expose deselection and reject it when CI requests complete required suites."""
import os

import pytest


def pytest_deselected(items):
    if items and os.getenv('NAVICAST_REQUIRED_TESTS') == '1':
        raise pytest.UsageError('Required CI tests must not be deselected')


def pytest_terminal_summary(terminalreporter):
    count = len(terminalreporter.stats.get('deselected', []))
    terminalreporter.write_line(f'Deselected tests: {count}')
