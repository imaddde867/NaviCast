"""Run with: python -m pytest research -q   (needs numpy)"""
import os
import shutil
import sys

import pytest

np = pytest.importorskip("numpy")
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


def test_group_id_is_vessel_safe():
    assert len({evaluate.group_id(230000001, t, "vessel") for t in range(0, 10**12, 10**11)}) == 1
