"""Where utilisation numbers come from. Only CloudWatch is implemented."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol


class MetricsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Utilisation:
    cpu: list[float]
    memory: list[float]  # empty when the CloudWatch agent isn't reporting


class MetricsSource(Protocol):
    def utilisation(self, instance_id: str, end: datetime) -> Utilisation: ...


class CloudWatchSource:
    """Hourly maxima for CPU (built in) and memory (CloudWatch agent only)."""

    def __init__(self, cloudwatch, lookback_days: int, period_seconds: int):
        self.cw = cloudwatch
        self.lookback = timedelta(days=lookback_days)
        self.period = period_seconds

    def _query(self, qid: str, namespace: str, metric: str, instance_id: str) -> dict:
        return {
            "Id": qid,
            "MetricStat": {
                "Metric": {
                    "Namespace": namespace,
                    "MetricName": metric,
                    "Dimensions": [{"Name": "InstanceId", "Value": instance_id}],
                },
                "Period": self.period,
                # Maximum per hour so short spikes still count.
                "Stat": "Maximum",
            },
            "ReturnData": True,
        }

    def utilisation(self, instance_id: str, end: datetime) -> Utilisation:
        request = {
            "MetricDataQueries": [
                self._query("cpu", "AWS/EC2", "CPUUtilization", instance_id),
                self._query("mem", "CWAgent", "mem_used_percent", instance_id),
            ],
            "StartTime": end - self.lookback,
            "EndTime": end,
        }
        values: dict[str, list[float]] = {"cpu": [], "mem": []}
        while True:
            page = self.cw.get_metric_data(**request)
            for result in page.get("MetricDataResults", []):
                status = result.get("StatusCode")
                if status not in ("Complete", "PartialData"):
                    raise MetricsError(f"{instance_id}: {result['Id']} returned {status}")
                # One query's values can be split across pages.
                values[result["Id"]].extend(float(v) for v in result.get("Values", []))
            token = page.get("NextToken")
            if not token:
                break
            request["NextToken"] = token
        return Utilisation(cpu=values["cpu"], memory=values["mem"])


class AzureMonitorSource:
    """Placeholder so the interface is clear. Not implemented."""

    def utilisation(self, instance_id: str, end: datetime) -> Utilisation:
        raise NotImplementedError("Azure Monitor is not implemented in this tool")
