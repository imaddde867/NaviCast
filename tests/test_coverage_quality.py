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


def test_inventory_requires_baseline_and_report_for_every_source():
    measured = {'critical.py': {'missing_statements': 0, 'missing_branches': 0}}
    required = {'critical.py', 'new.py'}
    assert not coverage_gate.check(measured, measured, required)
    assert not coverage_gate.check(measured, {**measured, 'new.py': measured['critical.py']}, required)
    assert not coverage_gate.check({**measured, 'new.py': measured['critical.py']}, measured, required)
    assert not coverage_gate.check(measured, measured, set())
    assert not coverage_gate.check({**measured, 'unknown.py': measured['critical.py']}, measured)


def test_source_inventory_discovers_new_modules_and_excludes_test_tools(tmp_path):
    for name in ('service.py', 'conftest.py', 'test_service.py', 'research/model.py',
                 'research/nested/helper.py', 'research/test_model.py', 'scripts/tool.py',
                 'tests/test_service.py', 'cloudflare/nested/handler.js', 'cloudflare/worker.mjs',
                 'static/index.html', 'static/frontend/dashboard.mjs', 'static/style.css'):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    assert coverage_gate.source_inventory(tmp_path, 'python') == {
        'service.py', 'research/model.py', 'research/nested/helper.py'}
    assert coverage_gate.source_inventory(tmp_path, 'node') == {
        'cloudflare/nested/handler.js', 'cloudflare/worker.mjs'}
    assert coverage_gate.source_inventory(tmp_path, 'browser') == {
        'static/index.html', 'static/frontend/dashboard.mjs'}
