import os
from datetime import datetime, timezone

from fastapi.testclient import TestClient
import api_server

client = TestClient(api_server.app)


def test_demo_metadata_and_fleet():
    meta = client.get('/meta')
    assert meta.status_code == 200
    assert meta.json()['mode'] == 'demo'
    vessels = client.get('/vessels').json()
    assert len(vessels) == 4
    assert all(v['data_source'] == 'synthetic' for v in vessels)
    projected = next(v for v in vessels if v['predicted_latitude'] is not None)
    assert projected['prediction_method'] == 'dead_reckoning'
    source = datetime.fromisoformat(projected['current_timestamp'])
    target = datetime.fromisoformat(projected['prediction_for_timestamp'])
    assert (target - source).total_seconds() == 1800
    assert 0 <= (datetime.now(timezone.utc) - source).total_seconds() < 60


def test_demo_filter_detail_and_exports():
    vessels = client.get('/vessels?limit=2').json()
    assert len(vessels) == 2
    vessel_id = vessels[0]['vessel_id']
    assert len(client.get(f'/vessels?mmsi={vessel_id}').json()) == 1
    assert client.get(f'/vessels/{vessel_id}').json()['vessel_id'] == vessel_id
    assert client.get('/vessels/999999999').status_code == 404
    assert client.get('/vessels/download').json()[0]['vessel_id'] == vessel_id
    csv = client.get('/vessels/download?format=csv')
    assert csv.status_code == 200
    assert 'vessel_id' in csv.text.splitlines()[0]
    assert 'attachment' in csv.headers['content-disposition']
    assert client.get('/vessels/download?format=bad').status_code == 400


def test_invalid_and_reversed_time_bounds():
    assert client.get('/vessels?from_time=bad').status_code == 400
    assert client.get('/vessels?from_time=2026-01-02&to_time=2026-01-01').status_code == 400
    assert client.get('/vessels?from_time=2099-01-01').json() == []


def test_health_reports_db_failure(monkeypatch):
    monkeypatch.setattr(api_server, 'DEMO_MODE', False, raising=False)
    def unavailable():
        raise RuntimeError('private-database-detail')
    monkeypatch.setattr(api_server, 'get_db_connection', unavailable)
    response = client.get('/health')
    assert response.status_code == 503
    assert 'private-database-detail' not in response.text


def test_dashboard_served_from_import():
    response = client.get('/')
    assert response.status_code == 200
    assert 'NAVICAST' in response.text


def test_unknown_motion_is_not_reported_stationary():
    from demo_data import sample_rows
    row = sample_rows()[0]
    row.update(sog=None, cog='bad', heading='NaN', nav_stat='bad', pos_acc='false')
    result = api_server._format_vessel_row(row)
    assert result['sog'] is None
    assert result['cog'] is None
    assert result['heading'] is None
    assert result['nav_stat'] is None
    assert result['pos_acc'] is False


def test_expired_prediction_is_hidden():
    from demo_data import sample_rows
    row = sample_rows()[0]
    row['prediction_for_timestamp'] = datetime(2020, 1, 1, tzinfo=timezone.utc)
    assert api_server._format_vessel_row(row)['predicted_latitude'] is None


def test_demo_does_not_require_db_password(tmp_path):
    import subprocess
    env = {k: v for k, v in os.environ.items() if k != 'NAVICAST_DB_PASSWORD'}
    env['NAVICAST_MODE'] = 'demo'
    result = subprocess.run([os.sys.executable, '-c', 'import api_server'], env=env, capture_output=True)
    assert result.returncode == 0


def test_api_publishes_a_typed_vessel_contract():
    schemas = client.get('/openapi.json').json()['components']['schemas']
    assert 'Vessel' in schemas
    assert schemas['Vessel']['properties']['current_latitude']['maximum'] == 90


def test_bad_optional_vessel_type_does_not_break_the_fleet(monkeypatch):
    from demo_data import sample_rows
    for properties in ({'shipType': '70'}, {'shipType': []}, None):
        rows = sample_rows()
        rows[0]['raw_json'] = {'properties': properties}
        monkeypatch.setattr(api_server, '_fetch_latest_vessels', lambda *args, **kwargs: rows)
        response = client.get('/vessels')
        assert response.status_code == 200
        assert len(response.json()) == 4


def test_projection_from_an_older_fix_is_not_attached_to_new_position():
    from datetime import timedelta
    from demo_data import sample_rows
    row = sample_rows()[0]
    row['current_timestamp'] += timedelta(seconds=5)
    row['sog'] = 0
    result = api_server._format_vessel_row(row)
    assert result['predicted_latitude'] is None
    assert result['prediction_method'] is None
