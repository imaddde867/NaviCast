"""Ingestion regressions with PostgreSQL's aborted-transaction behavior."""
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import psycopg2
import pytest

import mqtt_client as ingestion


class TransactionConnection:
    """Model commits, row conflicts and SQL failures without an external server."""

    def __init__(self, rows=(), fail_ids=()):
        self.rows = rows
        self.fail_ids = set(fail_ids)
        self.pending = {}
        self.saved = {}
        self.committed = {}
        self.aborted = False
        self.rowcount = 0

    def cursor(self):
        return self

    def execute(self, query, params=None):
        command = query.strip().split()[0].upper()
        if command == 'ROLLBACK':
            self.aborted = False
            self.pending = dict(self.saved)
            return
        if self.aborted:
            raise psycopg2.InternalError('current transaction is aborted')
        if command == 'SAVEPOINT':
            self.saved = dict(self.pending)
        elif command == 'INSERT':
            if params[0] in self.fail_ids:
                self.aborted = True
                raise psycopg2.DataError('rejected row')
            key = (params[0], params[3]) if 'raw_ais_data' in query else params[0]
            self.rowcount = int(key not in self.pending)
            self.pending[key] = params

    def fetchall(self):
        return self.rows

    def commit(self):
        if self.aborted:
            self.pending.clear()
            self.aborted = False
        else:
            self.committed.update(self.pending)
            self.pending.clear()

    def rollback(self):
        self.pending.clear()
        self.aborted = False

    def close(self):
        pass


def vessel(mmsi=1, **overrides):
    return {'mmsi': mmsi, 'lat': 60.0, 'lon': 24.0, 'time': 1791892800,
            'sog': 8.0, 'cog': 90.0, **overrides}


def test_sql_failure_preserves_valid_neighbors_and_duplicate_is_idempotent(monkeypatch):
    conn = TransactionConnection(fail_ids={2})
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    assert ingestion.store_raw_data_batch([vessel(1), vessel(2), vessel(3), vessel(1)]) is True
    assert [key[0] for key in conn.committed] == [1, 3]


@pytest.mark.parametrize('overrides', [
    {'lat': float('nan')}, {'lon': float('inf')}, {'lat': 91}, {'lon': 181},
    {'mmsi': 0}, {'mmsi': True}, {'mmsi': 1.5}, {'lat': True},
    {'time': 'garbage'}, {'time': float('inf')}, {'time': -1}, {'time': None},
    {'properties': []},
])
def test_invalid_observation_is_skipped_without_losing_next_row(monkeypatch, overrides):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    ingestion.store_raw_data_batch([vessel(**overrides), vessel(3)])
    assert [key[0] for key in conn.committed] == [3]


@pytest.mark.parametrize('raw', [1791892800, 1791892800000, '1791892800000'])
def test_source_timestamp_accepts_seconds_and_milliseconds(raw):
    assert ingestion._normalize_timestamp_ms(raw) == 1791892800000


@pytest.mark.parametrize('raw', ['not a time', None, True, float('nan'), float('inf'), -1])
def test_invalid_timestamp_never_becomes_receipt_time(raw):
    with pytest.raises(ValueError):
        ingestion._normalize_timestamp_ms(raw)


def test_unknown_ais_motion_is_null_without_inventing_northward_motion(monkeypatch):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    observation = vessel(sog=102.3, cog=360, heading=511)
    ingestion.store_raw_data_batch([observation])
    raw = json.loads(next(iter(conn.committed.values()))[4])
    assert raw['properties']['sog'] is None
    assert raw['properties']['cog'] is None
    assert raw['properties']['heading'] is None
    assert 'properties' not in observation


def test_ais_speed_above_50_knots_is_preserved(monkeypatch):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    ingestion.store_raw_data_batch([vessel(sog=60)])
    raw = json.loads(next(iter(conn.committed.values()))[4])
    assert raw['properties']['sog'] == 60


def test_failed_flush_retains_bounded_batch_and_retry_commits_it(monkeypatch, caplog):
    monkeypatch.setattr(ingestion, 'batch', [])
    monkeypatch.setattr(ingestion, 'BATCH_SIZE', 2)
    def unavailable(**kwargs):
        raise psycopg2.OperationalError('database offline')
    monkeypatch.setattr(ingestion.psycopg2, 'connect', unavailable)
    def receive(mmsi):
        ingestion.on_message(None, None, SimpleNamespace(
            topic=f'vessels-v2/{mmsi}/location', payload=json.dumps(vessel(mmsi)).encode()))
    receive(1)
    receive(2)
    receive(3)
    assert [int(row['mmsi']) for row in ingestion.batch] == [1, 2]
    assert 'batch' in caplog.text.lower()
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    ingestion.on_disconnect(None, None, SimpleNamespace(is_disconnect_packet_from_server=False), 0, None)
    assert [key[0] for key in conn.committed] == [1, 2]
    assert ingestion.batch == []


def test_paho_v2_disconnect_reads_reason_code(monkeypatch, caplog):
    monkeypatch.setattr(ingestion, 'batch', [])
    ingestion.on_disconnect(None, None, SimpleNamespace(is_disconnect_packet_from_server=False), 0, None)
    assert 'Unexpected disconnection' not in caplog.text


def test_connection_failure_is_visible_to_batch_caller(monkeypatch):
    def unavailable(**kwargs):
        raise psycopg2.OperationalError('database offline')
    monkeypatch.setattr(ingestion.psycopg2, 'connect', unavailable)
    assert ingestion.store_raw_data_batch([vessel()]) is False


def test_connection_lost_during_write_retains_batch_even_if_rollback_fails(monkeypatch):
    class LostConnection(TransactionConnection):
        def execute(self, query, params=None):
            raise psycopg2.OperationalError('connection lost')

        def rollback(self):
            raise psycopg2.InterfaceError('connection already closed')

    monkeypatch.setattr(ingestion, 'batch', [vessel()])
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: LostConnection())
    ingestion._flush_batch()
    assert ingestion.batch == [vessel()]


@pytest.mark.parametrize('status', [0, 5, 15])
def test_top_level_navigation_status_is_available_to_api(monkeypatch, status):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    ingestion.store_raw_data_batch([vessel(navStat=status)])
    raw = json.loads(next(iter(conn.committed.values()))[4])
    assert raw['properties']['navStat'] == status


@pytest.mark.parametrize('status', [None, True, 'garbage', -1, 16, 1.5])
def test_invalid_navigation_status_is_null(monkeypatch, status):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    ingestion.store_raw_data_batch([vessel(navStat=status)])
    raw = json.loads(next(iter(conn.committed.values()))[4])
    assert raw['properties']['navStat'] is None


@pytest.mark.parametrize('accuracy', ['garbage', 'false', 1, None])
def test_nonboolean_position_accuracy_is_null(monkeypatch, accuracy):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    ingestion.store_raw_data_batch([vessel(posAcc=accuracy)])
    raw = json.loads(next(iter(conn.committed.values()))[4])
    assert raw['properties']['posAcc'] is None


@pytest.mark.parametrize('accuracy', [True, False])
def test_boolean_position_accuracy_is_preserved(monkeypatch, accuracy):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    ingestion.store_raw_data_batch([vessel(posAcc=accuracy)])
    raw = json.loads(next(iter(conn.committed.values()))[4])
    assert raw['properties']['posAcc'] is accuracy


def test_connect_subscribes_once_to_location_observations():
    subscriptions = []
    client = SimpleNamespace(subscribe=lambda topic, qos: subscriptions.append((topic, qos)))
    ingestion.on_connect(client, None, {}, 0, None)
    assert subscriptions == [('vessels-v2/+/location', 1)]


@pytest.fixture
def mqtt_runtime(monkeypatch):
    client = SimpleNamespace(
        tls_set=lambda: None, reconnect_delay_set=lambda **kwargs: None,
        connect=lambda *args, **kwargs: None, loop_start=lambda: None,
        loop_stop=lambda: None, disconnect=lambda: None)
    monkeypatch.setattr(ingestion.mqtt, 'Client', lambda **kwargs: client)
    monkeypatch.setattr(ingestion, 'batch', [])
    elapsed = SimpleNamespace(seconds=0)
    monkeypatch.setattr(ingestion.time, 'time', lambda: elapsed.seconds)
    monkeypatch.setattr(ingestion.time, 'monotonic', lambda: elapsed.seconds)
    return client, elapsed


def test_initialization_error_propagates_for_process_supervisor(monkeypatch, mqtt_runtime):
    client, _ = mqtt_runtime
    def fail_connect(*args, **kwargs):
        raise RuntimeError('broker unavailable')
    client.connect = fail_connect
    with pytest.raises(RuntimeError, match='broker unavailable'):
        ingestion.main()


def test_ingestion_continues_after_24_hours(monkeypatch, mqtt_runtime):
    _, elapsed = mqtt_runtime
    sleeps = []
    def sleep(seconds):
        sleeps.append(seconds)
        elapsed.seconds = 86401
        if len(sleeps) == 2:
            raise KeyboardInterrupt
    monkeypatch.setattr(ingestion.time, 'sleep', sleep)
    ingestion.main()
    assert sleeps == [1, 1]


def test_status_logs_once_after_five_minute_deadline(monkeypatch, mqtt_runtime, caplog):
    _, elapsed = mqtt_runtime
    times = iter([299, 300, 300.1, 300.2])
    def sleep(seconds):
        try:
            elapsed.seconds = next(times)
        except StopIteration:
            raise KeyboardInterrupt
    monkeypatch.setattr(ingestion.time, 'sleep', sleep)
    caplog.set_level('INFO', logger=ingestion.__name__)
    ingestion.main()
    assert sum('MQTT client uptime' in entry.message for entry in caplog.records) == 1


def test_unexpected_loop_error_flushes_buffer_before_propagating(monkeypatch, mqtt_runtime):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    monkeypatch.setattr(ingestion, 'batch', [vessel()])
    def fail_sleep(seconds):
        raise RuntimeError('loop failed')
    monkeypatch.setattr(ingestion.time, 'sleep', fail_sleep)
    with pytest.raises(RuntimeError, match='loop failed'):
        ingestion.main()
    assert [key[0] for key in conn.committed] == [1]
    assert ingestion.batch == []


def test_keyboard_interrupt_flushes_buffer(monkeypatch, mqtt_runtime):
    conn = TransactionConnection()
    monkeypatch.setattr(ingestion.psycopg2, 'connect', lambda **kwargs: conn)
    monkeypatch.setattr(ingestion, 'batch', [vessel()])
    def interrupt(seconds):
        raise KeyboardInterrupt
    monkeypatch.setattr(ingestion.time, 'sleep', interrupt)
    ingestion.main()
    assert [key[0] for key in conn.committed] == [1]
    assert ingestion.batch == []
