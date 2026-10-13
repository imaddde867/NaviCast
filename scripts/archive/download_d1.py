#!/usr/bin/env python3
"""Download and verify one closed day of archived D1 objects into two local copies."""
import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import urllib.error
import urllib.request

PAGE_SIZE_DEFAULT = 2
MAX_PAGE_SIZE = 10
MAX_BODY_BYTES = 1_900_000
MAX_METADATA_RAW_BYTES = 20_000_000
AIS_KEY = re.compile(r"ais/(\d{4})/(\d{2})/(\d{2})/(\d{2})/(\d{2})\.ndjson\.gz\Z")
META_KEY = re.compile(r"meta/(\d{4})/(\d{2})/(\d{2})\.json\.gz\Z")


def parse_day(value):
    try:
        day = dt.date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("day must be YYYY-MM-DD") from error
    if day.isoformat() != value:
        raise ValueError("day must be YYYY-MM-DD")
    if day >= dt.datetime.now(dt.timezone.utc).date():
        raise ValueError("day must be a closed UTC day before today")
    return day


def _utc_from_ms(value):
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("invalid archive timestamp")
    return dt.datetime.fromtimestamp(value / 1000, tz=dt.timezone.utc)


def _header_time_ms(value):
    if not isinstance(value, str):
        raise ValueError("invalid gzip header fetched_at")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid gzip header fetched_at") from error
    if parsed.tzinfo is None:
        raise ValueError("gzip header fetched_at must include a timezone")
    return int(parsed.timestamp() * 1000)


def _validate_mmsi(record):
    if not isinstance(record, dict):
        raise ValueError("archive record must be an object")
    mmsi = record.get("mmsi")
    if not isinstance(mmsi, int) or isinstance(mmsi, bool) or not 0 < mmsi <= 999999999:
        raise ValueError("archive record has invalid MMSI")


def _validate_record(record):
    _validate_mmsi(record)
    for name, lower, upper in (("lat", -90, 90), ("lon", -180, 180)):
        value = record.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"archive record has invalid {name}")
        if not lower <= value <= upper:
            raise ValueError(f"archive record has out-of-range {name}")
    timestamp = record.get("timestampExternal")
    if timestamp is not None and (not isinstance(timestamp, int) or isinstance(timestamp, bool)):
        raise ValueError("archive record has invalid timestampExternal")


def _decompress_metadata(body):
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(body), mode="rb") as stream:
            raw = stream.read(MAX_METADATA_RAW_BYTES + 1)
            if len(raw) > MAX_METADATA_RAW_BYTES or stream.read(1):
                raise ValueError("metadata archive exceeds the validation size limit")
            return raw
    except (OSError, EOFError) as error:
        raise ValueError("invalid or truncated metadata gzip archive") from error


def _validate_blob(row, day):
    key, kind = row.get("key"), row.get("kind")
    if not isinstance(key, str) or not isinstance(kind, str):
        raise ValueError("archive row has invalid key or kind")
    scheduled_at = _utc_from_ms(row.get("scheduled_at"))
    fetched_at = row.get("fetched_at")
    _utc_from_ms(fetched_at)
    count = row.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        raise ValueError("archive row has invalid count")
    body_hex = row.get("body_hex")
    if not isinstance(body_hex, str) or len(body_hex) % 2:
        raise ValueError("archive row has invalid body encoding")
    try:
        body = bytes.fromhex(body_hex)
    except ValueError as error:
        raise ValueError("archive row has invalid body encoding") from error
    if not body or len(body) > MAX_BODY_BYTES:
        raise ValueError("archive body is empty or exceeds the D1 row limit")

    if kind == "ais":
        match = AIS_KEY.fullmatch(key)
        if not match:
            raise ValueError("invalid AIS archive key")
        year, month, date, hour, minute = map(int, match.groups())
        try:
            key_time = dt.datetime(year, month, date, hour, minute, tzinfo=dt.timezone.utc)
        except ValueError as error:
            raise ValueError("invalid AIS archive key date") from error
        if key_time.date() != day or (scheduled_at.date(), scheduled_at.hour, scheduled_at.minute) != (
                day, hour, minute):
            raise ValueError("AIS key or scheduled_at is outside the requested UTC day/minute")
        with gzip.GzipFile(fileobj=io.BytesIO(body), mode="rb") as stream:
            try:
                first_line = stream.readline()
                header = json.loads(first_line)
                if not isinstance(header, dict) or header.get("schema") != 1:
                    raise ValueError("AIS archive header schema must be 1")
                source = header.get("source")
                if not isinstance(source, str) or not source.strip():
                    raise ValueError("AIS archive header source is missing")
                if _header_time_ms(header.get("fetched_at")) != fetched_at:
                    raise ValueError("AIS header fetched_at does not match the D1 row")
                if header.get("data_updated_at") != row.get("data_updated_at"):
                    raise ValueError("AIS header data_updated_at does not match the D1 row")
                header_count = header.get("count")
                if not isinstance(header_count, int) or isinstance(header_count, bool) or header_count != count:
                    raise ValueError("AIS header count does not match the D1 row")
                records = 0
                for line in stream:
                    try:
                        record = json.loads(line)
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise ValueError("AIS archive contains invalid NDJSON") from error
                    _validate_record(record)
                    records += 1
            except (OSError, EOFError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("invalid or truncated AIS gzip archive") from error
        if records != count:
            raise ValueError("AIS raw record count does not match the D1 row")
        return body, source.strip(), count

    if kind == "meta":
        match = META_KEY.fullmatch(key)
        if not match:
            raise ValueError("invalid metadata archive key")
        year, month, date = map(int, match.groups())
        try:
            key_day = dt.date(year, month, date)
        except ValueError as error:
            raise ValueError("invalid metadata archive key date") from error
        if key_day != day or scheduled_at.date() != day:
            raise ValueError("metadata key or scheduled_at is outside the requested UTC day")
        try:
            wrapper = json.loads(_decompress_metadata(body))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("invalid or truncated metadata gzip archive") from error
        if not isinstance(wrapper, dict) or wrapper.get("schema") != 1:
            raise ValueError("metadata archive wrapper schema must be 1")
        source = wrapper.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("metadata archive header source is missing")
        if _header_time_ms(wrapper.get("fetched_at")) != fetched_at:
            raise ValueError("metadata fetched_at does not match the D1 row")
        if "data_updated_at" in wrapper and wrapper["data_updated_at"] != row.get("data_updated_at"):
            raise ValueError("metadata data_updated_at does not match the D1 row")
        vessels = wrapper.get("vessels")
        wrapper_count = wrapper.get("count")
        if (not isinstance(vessels, list) or not isinstance(wrapper_count, int)
                or isinstance(wrapper_count, bool) or wrapper_count != count or len(vessels) != count):
            raise ValueError("metadata wrapper count does not match the D1 row")
        for record in vessels:
            _validate_mmsi(record)  # metadata feed has no lat/lon
        return body, source.strip(), count

    raise ValueError("archive row has unknown kind")


def _query_page(account_id, database_id, token, day, cursor, page_size):
    prefix = f"ais/{day:%Y/%m/%d}/"
    upper = prefix + "\uffff"
    meta_key = f"meta/{day:%Y/%m/%d}.json.gz"
    sql = (
        "SELECT key, kind, scheduled_at, fetched_at, data_updated_at, count, "
        "hex(body) AS body_hex FROM archive_objects "
        "WHERE ((kind = 'ais' AND key >= ? AND key < ?) OR (kind = 'meta' AND key = ?)) "
        f"AND key > ? ORDER BY key LIMIT {page_size}"
    )
    payload = json.dumps({"sql": sql, "params": [prefix, upper, meta_key, cursor]}).encode("utf-8")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/d1/database/{database_id}/query"
    request = urllib.request.Request(
        url, data=payload, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Cloudflare D1 request failed (HTTP {error.code})") from None
    except urllib.error.URLError:
        raise RuntimeError("Cloudflare D1 request failed") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("Cloudflare D1 returned an invalid response") from None
    if not isinstance(result, dict) or result.get("success") is not True:
        raise RuntimeError("Cloudflare D1 query was not successful")
    query_results = result.get("result")
    if not isinstance(query_results, list) or len(query_results) != 1:
        raise RuntimeError("Cloudflare D1 returned an invalid query result")
    query_result = query_results[0]
    if not isinstance(query_result, dict):
        raise RuntimeError("Cloudflare D1 returned an invalid page")
    rows = query_result.get("results")
    if query_result.get("success") is not True or not isinstance(rows, list) or len(rows) > page_size:
        raise RuntimeError("Cloudflare D1 returned an invalid page")
    return rows


def _safe_target(root, key):
    parts = key.split("/")
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("invalid archive path")
    target = root.joinpath(*parts)
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError("archive path escapes the requested output directory")
    return target


def _check_existing(target, body):
    if target.is_symlink():
        raise ValueError(f"refusing symlink at archive destination: {target}")
    if target.exists():
        if not target.is_file() or target.read_bytes() != body:
            raise ValueError(f"conflicting archive content already exists: {target}")


def _write_atomic(target, body):
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".d1-download-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _manifest_bytes(manifest):
    return (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _check_manifest(root, name, data):
    target = root / name
    if target.is_symlink():
        raise ValueError(f"refusing symlink at manifest destination: {target}")
    if target.exists() and (not target.is_file() or target.read_bytes() != data):
        raise ValueError(f"conflicting completed manifest already exists: {target}")


def _write_manifest(root, name, data):
    target = root / name
    if not target.exists():
        _write_atomic(target, data)


def _independent_roots(output_dir, backup_dir):
    output = Path(output_dir).expanduser().resolve()
    backup = Path(backup_dir).expanduser().resolve()
    if output == backup or output in backup.parents or backup in output.parents:
        raise ValueError("output and backup directories must be independent roots")
    return output, backup


def download_day(account_id, database_id, day_value, output_dir, backup_dir, token, page_size=PAGE_SIZE_DEFAULT):
    day = parse_day(day_value)
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", account_id):
        raise ValueError("invalid account ID")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", database_id):
        raise ValueError("invalid database ID")
    if not isinstance(page_size, int) or not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ValueError(f"page size must be 1-{MAX_PAGE_SIZE}")
    if not token:
        raise ValueError("CLOUDFLARE_API_TOKEN is required")
    output, backup = _independent_roots(output_dir, backup_dir)
    output.mkdir(parents=True, exist_ok=True)
    backup.mkdir(parents=True, exist_ok=True)

    cursor = ""
    entries = []
    ais_minutes = set()
    updated_counts = {}
    while True:
        rows = _query_page(account_id, database_id, token, day, cursor, page_size)
        if not rows:
            break
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Cloudflare D1 returned an invalid archive row")
            key = row.get("key")
            if not isinstance(key, str) or key <= cursor:
                raise ValueError("Cloudflare D1 page is not strictly key-ordered")
            body, source, count = _validate_blob(row, day)
            out_target = _safe_target(output, key)
            backup_target = _safe_target(backup, key)
            _check_existing(out_target, body)
            _check_existing(backup_target, body)
            for target in (out_target, backup_target):
                if not target.exists():
                    _write_atomic(target, body)
                actual = target.read_bytes()
                digest = hashlib.sha256(actual).hexdigest()
                if len(actual) != len(body) or digest != hashlib.sha256(body).hexdigest():
                    raise ValueError(f"archive copy failed verification: {target}")
            scheduled_at = _utc_from_ms(row["scheduled_at"])
            fetched_at = _utc_from_ms(row["fetched_at"])
            entries.append({
                "key": key, "kind": row["kind"], "sha256": hashlib.sha256(body).hexdigest(),
                "size": len(body), "source": source, "count": count,
                "scheduled_at": scheduled_at.isoformat().replace("+00:00", "Z"),
                "fetched_at": fetched_at.isoformat().replace("+00:00", "Z"),
                "data_updated_at": row.get("data_updated_at"),
            })
            if row["kind"] == "ais":
                match = AIS_KEY.fullmatch(key)
                ais_minutes.add((int(match.group(4)), int(match.group(5))))
                update = row.get("data_updated_at")
                if update is not None:
                    updated_counts[update] = updated_counts.get(update, 0) + 1
            cursor = key
        if len(rows) < page_size:
            break

    if not entries:
        raise ValueError("no archive rows found for the requested UTC day")
    missing_minutes = [f"{hour:02d}:{minute:02d}" for hour in range(24) for minute in range(60)
                       if (hour, minute) not in ais_minutes]
    manifest = {
        "schema": 1,
        "day": day.isoformat(),
        "files": entries,
        "ais_minutes_present": len(ais_minutes),
        "ais_minutes_missing": missing_minutes,
        "repeated_data_updated_at": {
            value: count for value, count in sorted(updated_counts.items()) if count > 1
        },
    }
    manifest_name = f"manifest-{day.isoformat()}.json"
    manifest_data = _manifest_bytes(manifest)
    _check_manifest(output, manifest_name, manifest_data)
    _check_manifest(backup, manifest_name, manifest_data)
    _write_manifest(output, manifest_name, manifest_data)
    _write_manifest(backup, manifest_name, manifest_data)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--database-id", required=True)
    parser.add_argument("--day", required=True, help="closed UTC day as YYYY-MM-DD")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--page-size", type=int, default=PAGE_SIZE_DEFAULT, choices=range(1, MAX_PAGE_SIZE + 1))
    args = parser.parse_args(argv)
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    try:
        manifest = download_day(args.account_id, args.database_id, args.day, args.output_dir,
                                args.backup_dir, token, args.page_size)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"archive download failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({
        "day": manifest["day"], "files": len(manifest["files"]),
        "ais_minutes_present": manifest["ais_minutes_present"],
        "ais_minutes_missing": len(manifest["ais_minutes_missing"]),
        "repeated_data_updated_at": manifest["repeated_data_updated_at"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
