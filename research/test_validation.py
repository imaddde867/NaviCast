import copy
import math

import numpy as np
import pytest

import evaluate


def track(target_time=300000, target_lat=1):
    return {1: (np.array([0, target_time]), np.array([0., target_lat]), np.array([0., 0.]),
                np.array([8., np.nan]), np.array([0., np.nan]))}


def test_errors_are_independently_known_metres_and_cross_dateline():
    assert evaluate.haversine_m(0, 0, 0, 1) == pytest.approx(111195.0802335329)
    assert evaluate.haversine_m(0, 179.5, 0, -179.5) == pytest.approx(111195.0802335329)
    assert evaluate.haversine_m(0, 0, 0, 180) == pytest.approx(math.pi * 6371008.8)


@pytest.mark.parametrize('offset, matched', [(-60001, False), (-60000, True), (60000, True), (60001, False)])
def test_prototype_matching_tolerance_boundary_is_locked(offset, matched):
    assert len(evaluate.score(track(300000 + offset))[5]['t']) == int(matched)


def test_future_target_coordinates_do_not_enter_prediction_inputs(monkeypatch):
    original = evaluate.dead_reckon
    calls = []
    def record(*args):
        calls.append(tuple(np.asarray(arg).tolist() for arg in args))
        return original(*args)
    monkeypatch.setattr(evaluate, 'dead_reckon', record)
    evaluate.score(track(target_lat=1))
    first = copy.deepcopy(calls)
    calls.clear()
    evaluate.score(track(target_lat=80))
    assert calls == first


def test_invalid_motion_and_unmatched_targets_are_counted():
    rec = evaluate.score(track())[5]
    assert rec['accounting'] == {'origins': 2, 'invalid_motion': 1, 'unmatched_targets': 0, 'matched': 1}
    unmatched = evaluate.score(track(500000))[5]
    assert unmatched['accounting'] == {'origins': 2, 'invalid_motion': 1, 'unmatched_targets': 1, 'matched': 0}


def test_abstaining_predictor_remains_in_shared_scoring_population(monkeypatch):
    monkeypatch.setattr(evaluate, 'dead_reckon', lambda *args: (np.array([np.nan]), np.array([np.nan])))
    row = evaluate.summarize(evaluate.score(track()))['5']['all']
    assert row['n'] == 1
    assert row['missing_predictions'] == {'persistence': 0, 'dead_reckoning': 1}
    assert row['coverage'] == {'persistence': 1., 'dead_reckoning': 0.}
    assert row['persistence']['median'] > 100000
    assert row['dead_reckoning'] is None
    assert '100.0% | 0.0%' in evaluate.markdown(evaluate.summarize(evaluate.score(track())))


def test_vessel_split_never_separates_adjacent_duplicate_rows_or_locked_targets():
    from splits import vessel_split, validate_split
    windows = [(1, 0, 30), (1, 0, 30), (2, 0, 30), (3, 0, 30), (1, 80, 110)]
    split = vessel_split(windows, {1}, {2}, {3}, locked_period=(100, 200))
    assert split == {'train': [0, 1], 'validation': [2], 'test': [3]}
    validate_split(windows, split, 'vessel', locked_period=(100, 200), purge_ms=0)
    bad = {'train': [0, 2], 'validation': [1], 'test': [3]}
    with pytest.raises(ValueError, match='vessel'):
        validate_split(windows, bad, 'vessel', locked_period=(100, 200), purge_ms=0)
    with pytest.raises(ValueError):
        vessel_split(windows, {1}, {1, 2}, {3}, locked_period=(100, 200))


def test_temporal_split_purges_targets_and_training_assets_cannot_use_full_archive():
    from splits import time_split, training_rows
    windows = [(1, 0, 30), (1, 70, 100), (1, 100, 130), (1, 200, 230), (1, 290, 320)]
    split = time_split(windows, validation_start=100, test_start=200, purge_ms=10, locked_period=(300, 400))
    assert split == {'train': [0], 'validation': [2], 'test': [3]}
    assert training_rows(windows, split, 'time', locked_period=(300, 400), purge_ms=10) == [(1, 0, 30)]
    bad = {**split, 'train': list(range(len(windows)))}
    with pytest.raises(ValueError):
        training_rows(windows, bad, 'time', locked_period=(300, 400), purge_ms=10)


def test_vessel_bootstrap_does_not_treat_repeated_rows_as_independent():
    from uncertainty import bootstrap_improvement
    one = bootstrap_improvement(np.arange(1, 6), np.full(5, 20.), np.arange(0., 25., 5.), seed=42, draws=1000)
    repeated = bootstrap_improvement(np.repeat(np.arange(1, 6), 100), np.full(500, 20.), np.repeat(np.arange(0., 25., 5.), 100), seed=42, draws=1000)
    assert one == repeated
    assert one['improvement_m'] == 10
    assert one['ci95_m'] == [0., 20.]
    assert one['vessels'] == 5
    with pytest.raises(ValueError):
        bootstrap_improvement(np.array([1]), np.array([20.]), np.array([10.]), seed=42, draws=1000)


def test_published_prototype_rules_are_explicit_and_versioned(tmp_path):
    assert evaluate.evaluate(str(tmp_path))[0]['evaluation_rules'] == {
        'version': 'prototype-1', 'validation_status': 'unvalidated',
        'horizons_minutes': [5, 10, 15, 30], 'target_tolerance_ms': 60000,
        'target_tie': 'earlier', 'projection_elapsed': 'matched_observation',
        'percentile_method': 'linear', 'error_units': 'metres',
        'earth_radius_m': 6371008.8, 'knots_to_mps': .51444,
        'metres_per_degree': 111111, 'production_caps': 'not_applied',
        'prediction_population': 'identical_matched_rows_with_counted_abstentions',
    }


@pytest.mark.parametrize('bad', [True, -1, float('nan')])
def test_split_guard_rejects_invalid_policy_inputs(bad):
    from splits import time_split, validate_split
    windows = [(1, 0, 30)]
    with pytest.raises(ValueError):
        time_split(windows, validation_start=100, test_start=200, purge_ms=bad, locked_period=(300, 400))
    with pytest.raises(ValueError):
        validate_split(windows, {'train': [0], 'validation': [], 'test': []}, 'time', purge_ms=bad, locked_period=(300, 400))
