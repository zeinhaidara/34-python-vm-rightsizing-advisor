from datetime import UTC, datetime, timedelta

import pytest

from rightsizer.catalog import ConfigError, load_catalog
from rightsizer.metrics import AzureMonitorSource, CloudWatchSource, MetricsError
from tests.fakes import FakeCloudWatch

END = datetime(2026, 11, 20, 12, tzinfo=UTC)
IID = "i-0123456789abcdef0"


def test_query_shape():
    cw = FakeCloudWatch({IID: {"cpu": [1.0], "mem": [2.0]}})
    CloudWatchSource(cw, lookback_days=14, period_seconds=3600).utilisation(IID, END)
    req = cw.requests[0]
    assert req["EndTime"] == END
    assert req["StartTime"] == END - timedelta(days=14)
    cpu, mem = req["Queries"]
    assert cpu["MetricStat"]["Metric"]["Namespace"] == "AWS/EC2"
    assert cpu["MetricStat"]["Metric"]["MetricName"] == "CPUUtilization"
    assert mem["MetricStat"]["Metric"]["Namespace"] == "CWAgent"
    assert mem["MetricStat"]["Metric"]["MetricName"] == "mem_used_percent"
    for q in (cpu, mem):
        assert q["MetricStat"]["Period"] == 3600
        assert q["MetricStat"]["Stat"] == "Maximum"
        assert q["MetricStat"]["Metric"]["Dimensions"] == [{"Name": "InstanceId", "Value": IID}]


def test_values_split_across_pages_are_merged():
    cpu = [float(i) for i in range(250)]
    cw = FakeCloudWatch({IID: {"cpu": cpu, "mem": cpu[:120]}}, page_size=100)
    u = CloudWatchSource(cw, 14, 3600).utilisation(IID, END)
    assert [r["NextToken"] for r in cw.requests] == [None, "100", "200"]
    assert u.cpu == cpu
    assert len(u.memory) == 120


def test_missing_memory_comes_back_empty():
    cw = FakeCloudWatch({IID: {"cpu": [5.0] * 3}})
    assert CloudWatchSource(cw, 14, 3600).utilisation(IID, END).memory == []


@pytest.mark.parametrize("status", ["InternalError", "Forbidden"])
def test_bad_status_raises(status):
    cw = FakeCloudWatch({IID: {"cpu": [1.0]}}, status=status)
    with pytest.raises(MetricsError, match=status):
        CloudWatchSource(cw, 14, 3600).utilisation(IID, END)


def test_azure_is_a_stub():
    with pytest.raises(NotImplementedError):
        AzureMonitorSource().utilisation("vm-1", END)


# --- config -------------------------------------------------------------------

GOOD = """
thresholds:
  lookback_days: 7
  period_seconds: 3600
  percentile: 95
  min_datapoints: 24
  cpu: {low: 20, high: 80}
  memory: {low: 30, high: 85}
families:
  m5: [m5.large, m5.xlarge]
"""


def write(tmp_path, text):
    p = tmp_path / "c.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_good_config_loads(tmp_path):
    c = load_catalog(write(tmp_path, GOOD))
    assert c.neighbours("m5.large") == (None, "m5.xlarge")
    assert c.neighbours("m5.xlarge") == ("m5.large", None)
    assert c.neighbours("t3.nano") is None


@pytest.mark.parametrize(
    ("old", "new", "match"),
    [
        ("{low: 20, high: 80}", "{low: 80, high: 20}", "low < high"),
        ("percentile: 95", "percentile: 0", "percentile"),
        ("m5: [m5.large, m5.xlarge]", "m5: [m5.large, m5.large]", "twice"),
        ("m5: [m5.large, m5.xlarge]", "m5: []", "at least one"),
        ("  lookback_days: 7\n", "", "lookback_days"),
    ],
)
def test_bad_config_is_rejected(tmp_path, old, new, match):
    with pytest.raises(ConfigError, match=match):
        load_catalog(write(tmp_path, GOOD.replace(old, new)))
