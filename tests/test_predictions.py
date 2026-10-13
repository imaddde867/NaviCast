from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import prediction_service as predictions
from test_ingestion import TransactionConnection


SOURCE_TIME = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def observation(mmsi=1, **changes):
    values = dict(mmsi=mmsi, lat=60.0, lon=24.0, sog=8.0, cog=90.0, heading=511,
                  timestamp=SOURCE_TIME)
    values.update(changes)
    return tuple(values.values())


def test_projection_uses_constant_course_even_with_unverified_model(monkeypatch):
    conn = TransactionConnection(rows=[observation()])
    monkeypatch.setattr(predictions.psycopg2, 'connect', lambda **kwargs: conn)
    monkeypatch.setattr(predictions, 'model', SimpleNamespace(predict=lambda _: [[0, 0]]), raising=False)
    predictions.make_predictions()
    row = conn.committed[1]
    assert row[1] == pytest.approx(60)
    assert row[2] == pytest.approx(24.133343, abs=0.00001)
    assert row[3] == datetime(2026, 10, 13, 12, 30, tzinfo=timezone.utc)
    assert row[4].tzinfo is not None


def test_sql_failure_preserves_neighboring_predictions(monkeypatch):
    conn = TransactionConnection(rows=[observation(1), observation(2), observation(3)], fail_ids={2})
    monkeypatch.setattr(predictions.psycopg2, 'connect', lambda **kwargs: conn)
    predictions.make_predictions()
    assert list(conn.committed) == [1, 3]


@pytest.mark.parametrize('changes', [
    {'lat': float('nan')}, {'lon': float('inf')}, {'sog': float('nan')},
    {'cog': float('nan')}, {'sog': 102.3}, {'cog': 360}, {'cog': None},
    {'sog': 'broken'}, {'cog': 'broken'}, {'lat': 91}, {'lon': 181}, {'sog': 0},
    {'timestamp': None},
])
def test_invalid_or_unavailable_motion_does_not_project_or_break_neighbors(monkeypatch, changes):
    conn = TransactionConnection(rows=[observation(1, **changes), observation(3)])
    monkeypatch.setattr(predictions.psycopg2, 'connect', lambda **kwargs: conn)
    predictions.make_predictions()
    assert list(conn.committed) == [3]


def test_string_motion_from_json_is_normalized_per_row(monkeypatch):
    conn = TransactionConnection(rows=[observation(sog='8', cog='90')])
    monkeypatch.setattr(predictions.psycopg2, 'connect', lambda **kwargs: conn)
    predictions.make_predictions()
    assert conn.committed[1][2] == pytest.approx(24.133343, abs=0.00001)


@pytest.mark.parametrize('course,lat,lon', [
    (0, 0.083339, 0), (90, 0, 0.166678), (180, -0.083339, 0), (270, 0, -0.166678),
])
def test_dead_reckoning_uses_nautical_course(course, lat, lon):
    delta_lat, delta_lon = predictions.calculate_position_prediction(60, 24, 10, course, 1800)
    assert delta_lat == pytest.approx(lat, abs=0.00001)
    assert delta_lon == pytest.approx(lon, abs=0.00001)


def test_connection_lost_and_failed_rollback_do_not_stop_scheduler(monkeypatch, caplog):
    import psycopg2

    class LostConnection(TransactionConnection):
        def execute(self, query, params=None):
            raise psycopg2.OperationalError('connection lost')

        def rollback(self):
            raise psycopg2.InterfaceError('connection already closed')

    monkeypatch.setattr(predictions.psycopg2, 'connect', lambda **kwargs: LostConnection())
    predictions.make_predictions()
    assert 'Prediction cycle failed' in caplog.text
