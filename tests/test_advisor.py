from pathlib import Path

import pytest

from rightsizer.advisor import DOWN, KEEP, UNKNOWN, UP, percentile, recommend
from rightsizer.catalog import load_catalog
from rightsizer.metrics import Utilisation

CATALOG = load_catalog(Path(__file__).parent.parent / "config" / "catalog.yaml")


def flat(value: float, n: int = 100) -> list[float]:
    return [value] * n


def rec(itype, cpu, mem):
    return recommend("i-0123456789abcdef0", itype, Utilisation(cpu=cpu, memory=mem), CATALOG)


# --- percentile ---------------------------------------------------------------


def test_p95_ignores_the_top_five_percent():
    assert percentile([10.0] * 95 + [90.0] * 5, 95) == 10.0
    assert percentile([10.0] * 94 + [90.0] * 6, 95) == 90.0


def test_percentile_small_and_unsorted():
    assert percentile([3.0, 1.0, 2.0], 95) == 3.0
    assert percentile([5.0], 50) == 5.0


def test_percentile_of_nothing_raises():
    with pytest.raises(ValueError):
        percentile([], 95)


# --- rules --------------------------------------------------------------------


def test_idle_instance_goes_one_size_down():
    r = rec("m5.2xlarge", flat(5), flat(20))
    assert (r.action, r.target) == (DOWN, "m5.xlarge")
    assert (r.cpu_p, r.mem_p) == (5.0, 20.0)


def test_busy_cpu_goes_one_size_up():
    r = rec("m5.large", flat(92), flat(40))
    assert (r.action, r.target) == (UP, "m5.xlarge")
    assert "CPU" in r.reason


def test_busy_memory_goes_one_size_up():
    r = rec("r5.large", flat(30), flat(91))
    assert (r.action, r.target) == (UP, "r5.xlarge")
    assert "memory" in r.reason


def test_low_cpu_but_normal_memory_is_kept():
    r = rec("m5.xlarge", flat(5), flat(60))
    assert (r.action, r.target) == (KEEP, None)


def test_missing_memory_is_unknown_not_a_guess():
    r = rec("m5.2xlarge", flat(5), [])
    assert r.action == UNKNOWN
    assert r.target is None
    assert r.mem_p is None
    assert "memory" in r.reason


def test_too_little_memory_data_is_unknown():
    r = rec("m5.2xlarge", flat(5), flat(20, n=10))
    assert r.action == UNKNOWN
    assert r.reason == "only 10 memory datapoints"


def test_high_cpu_upsizes_even_without_memory():
    r = rec("c5.large", flat(95), [])
    assert (r.action, r.target) == (UP, "c5.xlarge")
    assert r.mem_p is None


def test_too_little_cpu_data_is_unknown():
    r = rec("m5.large", flat(5, n=10), flat(5))
    assert r.action == UNKNOWN
    assert "10 CPU datapoints" in r.reason


def test_type_not_in_catalog_is_unknown():
    assert rec("x2idn.32xlarge", flat(5), flat(5)).action == UNKNOWN


def test_smallest_size_cannot_go_down():
    r = rec("t3.micro", flat(1), flat(10))
    assert (r.action, r.target) == (KEEP, None)
    assert "smallest" in r.reason


def test_largest_size_cannot_go_up():
    r = rec("m5.8xlarge", flat(99), flat(50))
    assert (r.action, r.target) == (KEEP, None)
    assert "largest" in r.reason


def test_thresholds_are_strict():
    # Exactly on the line is not "above" or "below".
    assert rec("m5.xlarge", flat(80), flat(85)).action == KEEP
    assert rec("m5.xlarge", flat(20), flat(30)).action == KEEP


def test_short_spikes_do_not_trigger_upsize():
    cpu = [10.0] * 96 + [100.0] * 4  # four hot hours in 100
    assert rec("m5.xlarge", cpu, flat(50)).action == KEEP
