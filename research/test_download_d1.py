"""Offline tests for the read-only, local D1 archive downloader."""
import datetime as dt
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import urllib.error

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "archive"))
import download_d1  # noqa: E402

DAY = "2025-02-03"
TOKEN = "test-token-that-must-not-appear"
SOURCE = "https://meri.digitraffic.fi/api/ais/v1/locations"


def _timestamp_ms(day, hour, minute, second=0):
    value = dt.datetime.fromisoformat(f"{day}T{hour:02d}:{minute:02d}:{second:02d}+00:00")
    return int(value.timestamp() * 1000)


def _gzip_json(value):
    return gzip.compress(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def _ais_row(day=DAY, hour=0, minute=0, source=SOURCE, update="2025-02-03T00:00:00Z", body_override=None):
    scheduled = _timestamp_ms(day, hour, minute)
    fetched = scheduled + 5000
    stamp = dt.datetime.fromtimestamp(fetched / 1000, tz=dt.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")
    record = {"mmsi": 230000001, "lat": 60.0, "lon": 24.0, "timestampExternal": scheduled,
              "sog": 12.0, "cog": 90.0}
    body = body_override if body_override is not None else gzip.compress(
        (json.dumps({"schema": 1, "source": source, "fetched_at": stamp, "count": 1,
                     "data_updated_at": update}) + "\n" + json.dumps(record) + "\n").encode("utf-8"))
    return {"key": f"ais/{day.replace('-', '/')}/{hour:02d}/{minute:02d}.ndjson.gz", "kind": "ais",
            "scheduled_at": scheduled, "fetched_at": fetched, "data_updated_at": update,
            "count": 1, "body_hex": body.hex().upper()}


def _meta_row(day=DAY):
    scheduled = _timestamp_ms(day, 23, 59)
    fetched = scheduled + 2000
    stamp = dt.datetime.fromtimestamp(fetched / 1000, tz=dt.timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z")
    record = {"mmsi": 230000002, "lat": 61.0, "lon": 25.0, "timestampExternal": scheduled,
              "sog": 8.0, "cog": 180.0}
    body = _gzip_json({"schema": 1, "source": "metadata fixture", "fetched_at": stamp,
                       "count": 1, "vessels": [record]})
    return {"key": f"meta/{day.replace('-', '/')}.json.gz", "kind": "meta",
            "scheduled_at": scheduled, "fetched_at": fetched, "data_updated_at": None,
            "count": 1, "body_hex": body.hex().upper()}


def _fake_cloudflare(rows, page_sizes, expected_day=DAY):
    ordered = sorted(rows, key=lambda row: row["key"])

    def urlopen(request, timeout):
        assert request.full_url == (
            "https://api.cloudflare.com/client/v4/accounts/account123/d1/database/"
            "00000000-0000-0000-0000-000000000001/query")
        assert request.get_method() == "POST"
        assert request.get_header("Authorization") == f"Bearer {TOKEN}"
        payload = json.loads(request.data)
        sql = payload["sql"].upper()
        assert sql.lstrip().startswith("SELECT")
        assert not re.search(r"\b(?:INSERT|UPDATE|DELETE|DROP|ALTER)\b", sql)
        assert payload["params"][:2] == [f"ais/{expected_day.replace('-', '/')}/",
                                        f"ais/{expected_day.replace('-', '/')}/\uffff"]
        assert payload["params"][2] == f"meta/{expected_day.replace('-', '/')}.json.gz"
        cursor = payload["params"][3]
        page_size = int(sql.rsplit("LIMIT ", 1)[1])
        page_sizes.append(page_size)
        selected = [row for row in ordered if row["key"] > cursor and (
            row["key"].startswith(f"ais/{expected_day.replace('-', '/')}/")
            or row["key"] == f"meta/{expected_day.replace('-', '/')}.json.gz")]
        result = {"success": True, "result": [{"success": True, "results": selected[:page_size]}]}
        return io.BytesIO(json.dumps(result).encode("utf-8"))

    return urlopen


def _run(monkeypatch, rows, tmp_path, page_size=1):
    page_sizes = []
    monkeypatch.setattr(download_d1.urllib.request, "urlopen", _fake_cloudflare(rows, page_sizes))
    output, backup = tmp_path / "primary", tmp_path / "backup"
    manifest = download_d1.download_day("account123", "00000000-0000-0000-0000-000000000001", DAY,
                                        output, backup, TOKEN, page_size)
    return manifest, output, backup, page_sizes


def test_paginates_day_scope_verifies_two_copies_and_reports_continuity(monkeypatch, tmp_path):
    rows = [_ais_row(), _ais_row(minute=2), _meta_row()]

    manifest, output, backup, pages = _run(monkeypatch, rows, tmp_path)

    assert pages == [1, 1, 1, 1]
    assert manifest["ais_minutes_present"] == 2
    assert len(manifest["ais_minutes_missing"]) == 1438
    assert manifest["repeated_data_updated_at"] == {"2025-02-03T00:00:00Z": 2}
    assert json.loads((output / f"manifest-{DAY}.json").read_text()) == manifest
    assert (backup / f"manifest-{DAY}.json").read_bytes() == (output / f"manifest-{DAY}.json").read_bytes()
    for entry in manifest["files"]:
        a, b = output / entry["key"], backup / entry["key"]
        assert a.read_bytes() == b.read_bytes()
        assert hashlib.sha256(a.read_bytes()).hexdigest() == entry["sha256"]


def test_matching_files_resume_and_conflicting_existing_content_fails(monkeypatch, tmp_path):
    rows = [_ais_row()]
    first, output, backup, _ = _run(monkeypatch, rows, tmp_path)
    second, _, _, _ = _run(monkeypatch, rows, tmp_path)
    assert second == first

    (backup / rows[0]["key"]).write_bytes(b"conflicting bytes")
    with pytest.raises(ValueError, match="conflicting archive content"):
        _run(monkeypatch, rows, tmp_path)


@pytest.mark.parametrize("row, message", [
    (_ais_row(body_override=b"not gzip"), "invalid or truncated AIS gzip"),
    (_ais_row(body_override=gzip.compress(
        (json.dumps({"schema": 1, "source": SOURCE, "fetched_at": "2025-02-03T00:00:05Z",
                    "count": 2, "data_updated_at": "2025-02-03T00:00:00Z"}) + "\n"
         + json.dumps({"mmsi": 230000001, "lat": 60, "lon": 24, "timestampExternal": 1}) + "\n").encode())),
     "header count does not match"),
])
def test_malformed_gzip_and_count_are_rejected_without_manifest(monkeypatch, tmp_path, row, message):
    page_sizes = []
    monkeypatch.setattr(download_d1.urllib.request, "urlopen", _fake_cloudflare([row], page_sizes))
    output, backup = tmp_path / "primary", tmp_path / "backup"

    with pytest.raises(ValueError, match=message):
        download_d1.download_day("account123", "00000000-0000-0000-0000-000000000001", DAY,
                                 output, backup, TOKEN, 1)

    assert not list(tmp_path.rglob("manifest-*.json"))


def test_path_traversal_key_is_rejected_before_any_manifest(monkeypatch, tmp_path):
    row = _ais_row()
    row["key"] = f"ais/{DAY.replace('-', '/')}/../outside.ndjson.gz"
    pages = []
    monkeypatch.setattr(download_d1.urllib.request, "urlopen", _fake_cloudflare([row], pages))

    with pytest.raises(ValueError, match="invalid AIS archive key"):
        download_d1.download_day("account123", "00000000-0000-0000-0000-000000000001", DAY,
                                 tmp_path / "primary", tmp_path / "backup", TOKEN, 1)

    assert not list(tmp_path.rglob("manifest-*.json"))


def test_failure_does_not_write_completed_manifest_or_expose_token(monkeypatch, tmp_path, capsys):
    def fail(_request, timeout):
        raise urllib.error.HTTPError("https://api.cloudflare.com", 403, "denied", {},
                                     io.BytesIO(f"echo {TOKEN}".encode()))

    monkeypatch.setattr(download_d1.urllib.request, "urlopen", fail)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", TOKEN)

    code = download_d1.main(["--account-id", "account123", "--database-id",
                             "00000000-0000-0000-0000-000000000001", "--day", DAY,
                             "--output-dir", str(tmp_path / "primary"), "--backup-dir", str(tmp_path / "backup")])
    captured = capsys.readouterr()

    assert code == 1
    assert TOKEN not in captured.out + captured.err
    assert not list(tmp_path.rglob("manifest-*.json"))


def test_today_and_future_days_are_rejected(tmp_path):
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    with pytest.raises(ValueError, match="closed UTC day"):
        download_d1.download_day("account123", "00000000-0000-0000-0000-000000000001", today,
                                 tmp_path / "primary", tmp_path / "backup", TOKEN)
