"""Run with: python -m pytest research -q   (needs numpy)"""
import json
import gzip
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))
import evaluate  # noqa: E402
import make_synthetic  # noqa: E402

MINUTES = 45


def run(tmp_path, vessels, name="d"):
    out = tmp_path / name
    make_synthetic.make(str(out), MINUTES, vessels)
    return evaluate.evaluate(str(out))[0]["horizons"]


def pick(mmsi):
    return [v for v in make_synthetic.DEFAULT_VESSELS if v["mmsi"] == mmsi]


def set_header_source(paths, source):
    for path in paths:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            rows = handle.readlines()
        header = json.loads(rows[0])
        if source is None:
            header.pop("source", None)
        else:
            header["source"] = source
        rows[0] = json.dumps(header) + "\n"
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.writelines(rows)


def test_straight_vessels_dead_reckoning_is_exact_persistence_is_speed_times_h(tmp_path):
    for mmsi in (230000001, 230000002, 230000003):
        v = pick(mmsi)[0]
        summary = run(tmp_path, pick(mmsi), f"v{mmsi}")
        for h in evaluate.HORIZONS_MIN:
            row = summary[str(h)]["all"]
            assert row["n"] == MINUTES - h + 1  # +1: last obs matches the final snapshot 60 s early
            assert row["dead_reckoning"]["median"] < 50
            expected = v["sog"] * 0.51444 * h * 60
            assert row["persistence"]["median"] == pytest.approx(expected, rel=0.01)


def test_turning_vessel_breaks_dead_reckoning_at_30_min(tmp_path):
    row = run(tmp_path, pick(230000004))["30"]["all"]
    assert row["dead_reckoning"]["median"] > 500


def test_sentinel_sog_is_not_scored_and_buckets_split(tmp_path):
    summary = run(tmp_path, pick(230000005) + pick(230000002) + pick(230000001))
    row = summary["15"]
    assert row["all"]["n"] == 2 * (MINUTES - 15 + 1)
    assert row["2-8"]["n"] == row[">=8"]["n"] == MINUTES - 15 + 1 and row["<2"]["n"] == 0


def test_duplicate_observations_are_deduped(tmp_path):
    out = tmp_path / "d"
    paths = make_synthetic.make(str(out), MINUTES, pick(230000001))
    before = evaluate.evaluate(str(out))[0]
    for p in paths:  # a silent vessel shows up unchanged in later snapshots
        shutil.copy(p, p.replace(".ndjson.gz", "_copy.ndjson.gz"))
    assert evaluate.evaluate(str(out))[0] == {**before, "files": 2 * before["files"]}


def test_synthetic_metrics_do_not_claim_digitraffic_license(tmp_path):
    out = tmp_path / "d"
    make_synthetic.make(str(out), MINUTES, pick(230000001))

    metrics, _tracks = evaluate.evaluate(str(out))

    attribution = metrics["data_attribution"]
    assert attribution["status"] == "synthetic"
    assert attribution["sources"] == [{"source": "synthetic"}]
    assert attribution["files_without_source"] == 0
    assert all("license" not in source for source in attribution["sources"])
    assert "230000001" not in json.dumps(metrics)


def test_digitraffic_metrics_include_cc_by_attribution(tmp_path):
    out = tmp_path / "d"
    paths = make_synthetic.make(str(out), MINUTES, pick(230000001))
    set_header_source(paths, evaluate.DIGITRAFFIC_SOURCE_URL)

    attribution = evaluate.evaluate(str(out))[0]["data_attribution"]

    assert attribution["status"] == "digitraffic"
    assert attribution["sources"] == [{
        "source": "Fintraffic Digitraffic Marine AIS locations API",
        "source_url": evaluate.DIGITRAFFIC_SOURCE_URL,
        "license": "Creative Commons Attribution 4.0 International (CC BY 4.0)",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
    }]


def test_mixed_provenance_applies_license_only_to_digitraffic_source(tmp_path):
    out = tmp_path / "d"
    paths = make_synthetic.make(str(out), 2, pick(230000001))
    set_header_source([paths[0]], evaluate.DIGITRAFFIC_SOURCE_URL)

    attribution = evaluate.evaluate(str(out))[0]["data_attribution"]

    assert attribution["status"] == "mixed"
    assert [source["source"] for source in attribution["sources"]] == [
        "Fintraffic Digitraffic Marine AIS locations API", "synthetic"]
    assert "license" in attribution["sources"][0]
    assert "license" not in attribution["sources"][1]


def test_missing_provenance_does_not_invent_source_or_license(tmp_path):
    out = tmp_path / "d"
    paths = make_synthetic.make(str(out), 1, pick(230000001))
    set_header_source(paths, None)

    attribution = evaluate.evaluate(str(out))[0]["data_attribution"]

    assert attribution["status"] == "missing"
    assert attribution["sources"] == []
    assert attribution["files_without_source"] == 1


def test_cli_rejects_removed_split_by_option():
    with pytest.raises(SystemExit) as error:
        evaluate.main(["unused", "--split-by", "vessel"])

    assert error.value.code == 2
