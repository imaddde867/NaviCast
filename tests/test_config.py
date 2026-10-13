import pytest
from config import get_db_config


def test_database_connections_have_a_bounded_timeout(monkeypatch):
    monkeypatch.setenv('NAVICAST_DB_PASSWORD', 'test-only')
    assert get_db_config()['connect_timeout'] == 5


def test_live_database_requires_an_explicit_password(monkeypatch):
    monkeypatch.delenv('NAVICAST_DB_PASSWORD', raising=False)
    with pytest.raises(RuntimeError, match='NAVICAST_DB_PASSWORD'):
        get_db_config()
