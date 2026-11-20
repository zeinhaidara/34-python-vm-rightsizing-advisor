"""Hand-written fake EC2 and CloudWatch clients. Read calls only."""

from __future__ import annotations


class FakeEC2:
    def __init__(self, instances: list[tuple[str, str]], page_size: int = 2):
        self.instances = instances  # (id, type), all "running"
        self.page_size = page_size
        self.calls: list[dict] = []

    def describe_instances(self, Filters, InstanceIds=None, NextToken=None):
        self.calls.append({"Filters": Filters, "InstanceIds": InstanceIds, "NextToken": NextToken})
        rows = [i for i in self.instances if not InstanceIds or i[0] in InstanceIds]
        start = int(NextToken or 0)
        chunk = rows[start : start + self.page_size]
        page = {
            "Reservations": [
                {"Instances": [{"InstanceId": i, "InstanceType": t} for i, t in chunk]}
            ]
        }
        if start + self.page_size < len(rows):
            page["NextToken"] = str(start + self.page_size)
        return page


class FakeCloudWatch:
    """Serves values per instance, split into pages of `page_size` values per query."""

    def __init__(
        self,
        data: dict[str, dict[str, list[float]]],
        page_size: int = 100,
        status: str = "Complete",
    ):
        self.data = data
        self.page_size = page_size
        self.status = status
        self.requests: list[dict] = []

    def get_metric_data(self, MetricDataQueries, StartTime, EndTime, NextToken=None):
        self.requests.append(
            {
                "Queries": MetricDataQueries,
                "StartTime": StartTime,
                "EndTime": EndTime,
                "NextToken": NextToken,
            }
        )
        start = int(NextToken or 0)
        results, more = [], False
        for q in MetricDataQueries:
            iid = q["MetricStat"]["Metric"]["Dimensions"][0]["Value"]
            values = self.data.get(iid, {}).get(q["Id"], [])
            chunk = values[start : start + self.page_size]
            more = more or start + self.page_size < len(values)
            results.append({"Id": q["Id"], "Values": chunk, "StatusCode": self.status})
        page = {"MetricDataResults": results}
        if more:
            page["NextToken"] = str(start + self.page_size)
        return page
