import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    'check_coverage', Path(__file__).parents[1] / 'scripts/check_coverage.py')
coverage_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(coverage_gate)


def test_missing_required_module_and_lost_branch_coverage_cannot_pass():
    baseline = {'critical.py': {'missing_statements': 2, 'missing_branches': 1}}
    assert coverage_gate.check({'critical.py': {'missing_statements': 2, 'missing_branches': 1}}, baseline)
    assert not coverage_gate.check({}, baseline)
    assert not coverage_gate.check({'critical.py': {'missing_statements': 2, 'missing_branches': 2}}, baseline)
    assert not coverage_gate.check({'critical.py': {'missing_statements': 3, 'missing_branches': 1}}, baseline)


def test_lcov_reader_counts_uncovered_ranges(tmp_path):
    path = tmp_path / 'node.lcov'
    path.write_text('SF:critical.mjs\nLF:10\nLH:8\nBRF:4\nBRH:3\nend_of_record\n')
    assert coverage_gate.read_report('node', path) == {
        'critical.mjs': {'missing_lines': 2, 'missing_branches': 1}}
