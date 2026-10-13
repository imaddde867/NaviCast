"""Optional PostgreSQL checks, confined to session-local temporary tables.

Run with NAVICAST_TEST_DSN pointing to a disposable PostgreSQL instance.
"""
import json
import os
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest

import mqtt_client
import prediction_service


@pytest.fixture
def database(monkeypatch):
    dsn = os.getenv('NAVICAST_TEST_DSN')
    if not dsn:
        pytest.skip('NAVICAST_TEST_DSN is not set')
    connection = psycopg2.connect(dsn)
    with connection.cursor() as cursor:
        cursor.execute('''
            CREATE TEMP TABLE raw_ais_data (
                vessel_id INTEGER NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                raw_json JSONB,
                PRIMARY KEY (vessel_id, timestamp)
            );
            CREATE TEMP TABLE predictions (
                vessel_id INTEGER PRIMARY KEY,
                predicted_latitude DOUBLE PRECISION NOT NULL,
                predicted_longitude DOUBLE PRECISION NOT NULL,
                prediction_for_timestamp TIMESTAMPTZ NOT NULL,
                prediction_made_at TIMESTAMPTZ NOT NULL
            );
        ''')
    connection.commit()

    class ServiceConnection:
        """Keep the session's temporary tables alive until fixture teardown."""
        def cursor(self):
            return connection.cursor()

        def commit(self):
            connection.commit()

        def rollback(self):
            connection.rollback()

        def close(self):
            pass

    monkeypatch.setattr(psycopg2, 'connect', lambda **kwargs: ServiceConnection())
    yield connection
    connection.close()


def test_postgres_ingestion_sql_failure_preserves_neighbors_and_duplicates(database):
    source = datetime.now(timezone.utc).replace(microsecond=0)
    with database.cursor() as cursor:
        cursor.execute('ALTER TABLE pg_temp.raw_ais_data ADD CHECK (vessel_id <> 2)')
    observations = [dict(mmsi=mmsi, lat=60.0, lon=24.0, sog=8.0, cog=90.0,
                         time=int(source.timestamp() * 1000)) for mmsi in [1, 2, 3, 1]]
    assert mqtt_client.store_raw_data_batch(observations) is True
    assert mqtt_client.store_raw_data_batch(observations) is True
    with database.cursor() as cursor:
        cursor.execute('SELECT vessel_id, timestamp FROM pg_temp.raw_ais_data ORDER BY vessel_id')
        assert cursor.fetchall() == [(1, source), (3, source)]


def test_postgres_projection_isolates_bad_sql_and_malformed_motion_then_upserts(database):
    source = datetime.now(timezone.utc).replace(microsecond=0)
    with database.cursor() as cursor:
        cursor.execute('ALTER TABLE pg_temp.predictions ADD CHECK (vessel_id <> 2)')
        for mmsi, sog in [(1, '8'), (2, '8'), (3, 'garbage'), (4, '8')]:
            cursor.execute('''INSERT INTO pg_temp.raw_ais_data
                VALUES (%s, 60, 24, %s, %s)''',
                (mmsi, source, json.dumps({'properties': {'sog': sog, 'cog': '90'}})))
    database.commit()
    prediction_service.make_predictions()
    prediction_service.make_predictions()
    with database.cursor() as cursor:
        cursor.execute('''SELECT vessel_id, predicted_latitude, predicted_longitude,
                          prediction_for_timestamp FROM pg_temp.predictions ORDER BY vessel_id''')
        rows = cursor.fetchall()
        assert [row[0] for row in rows] == [1, 4]
        for row in rows:
            assert row[1] == pytest.approx(60)
            assert row[2] == pytest.approx(24.133343, abs=0.00001)
            assert row[3] == source + timedelta(minutes=30)


def test_live_api_list_detail_and_download_agree(database, monkeypatch):
    import api_server
    from fastapi.testclient import TestClient
    source = datetime.now(timezone.utc)
    with database.cursor() as cursor:
        cursor.execute('INSERT INTO pg_temp.raw_ais_data VALUES (1, 60, 24, %s, %s)',
                       (source, json.dumps({'properties': {'sog': 8, 'cog': 90, 'navStat': 0}})))
    database.commit()

    class APIConnection:
        def cursor(self, **kwargs):
            return database.cursor(**kwargs)
        def close(self):
            pass
    monkeypatch.setattr(api_server, 'DEMO_MODE', False)
    monkeypatch.setattr(api_server, 'get_db_connection', APIConnection)
    client = TestClient(api_server.app)
    fleet = client.get('/vessels')
    assert fleet.status_code == 200
    detail = client.get('/vessels/1')
    assert detail.status_code == 200
    assert detail.json() == fleet.json()[0]
    assert client.get('/vessels/download').json() == fleet.json()
    assert client.get('/vessels/2').status_code == 404
    assert client.get('/vessels/0').status_code == 404
