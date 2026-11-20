from datetime import UTC, datetime

from botocore.exceptions import ClientError

from rightsizer.cli import main
from tests.fakes import FakeCloudWatch, FakeEC2

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)


def fleet():
    ec2 = FakeEC2(
        [
            ("i-0000000000000001", "m5.2xlarge"),  # idle -> down
            ("i-0000000000000002", "m5.large"),  # hot -> up
            ("i-0000000000000003", "m5.xlarge"),  # no agent -> unknown
        ]
    )
    cw = FakeCloudWatch(
        {
            "i-0000000000000001": {"cpu": [4.0] * 200, "mem": [12.0] * 200},
            "i-0000000000000002": {"cpu": [93.0] * 200, "mem": [50.0] * 200},
            "i-0000000000000003": {"cpu": [4.0] * 200},
        }
    )
    return ec2, cw


def test_table_output(capsys):
    ec2, cw = fleet()
    assert main([], ec2=ec2, cloudwatch=cw, now=NOW) == 0
    out = capsys.readouterr().out
    assert "| i-0000000000000001 | m5.2xlarge | 4.0% | 12.0% | down | m5.xlarge |" in out
    assert "| i-0000000000000002 | m5.large | 93.0% | 50.0% | up | m5.xlarge |" in out
    assert "| i-0000000000000003 | m5.xlarge | 4.0% | unknown | unknown | - |" in out
    assert "3 instances: 1 down, 1 up, 0 keep, 1 unknown. Nothing was changed." in out


def test_reads_every_instance_page():
    ec2, cw = fleet()
    main([], ec2=ec2, cloudwatch=cw, now=NOW)
    assert [c["NextToken"] for c in ec2.calls] == [None, "2"]
    assert ec2.calls[0]["Filters"] == [{"Name": "instance-state-name", "Values": ["running"]}]


def test_instance_id_filter(tmp_path):
    ec2, cw = fleet()
    out = tmp_path / "r.md"
    args = ["--instance-id", "i-0000000000000002", "--output", str(out)]
    assert main(args, ec2=ec2, cloudwatch=cw, now=NOW) == 0
    text = out.read_text(encoding="utf-8")
    assert "i-0000000000000002" in text
    assert "i-0000000000000001" not in text


def test_api_error_exits_non_zero(capsys):
    class Broken(FakeCloudWatch):
        def get_metric_data(self, **kwargs):
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "GetMetricData")

    ec2, _ = fleet()
    assert main([], ec2=ec2, cloudwatch=Broken({}), now=NOW) == 1
    assert "AccessDenied" in capsys.readouterr().err


def test_no_instances_exits_non_zero(capsys):
    assert main([], ec2=FakeEC2([]), cloudwatch=FakeCloudWatch({}), now=NOW) == 1
    assert "no running instances" in capsys.readouterr().err


def test_azure_provider_is_not_implemented(capsys):
    assert main(["--provider", "azure"], ec2=FakeEC2([]), cloudwatch=FakeCloudWatch({})) == 1
    assert "NotImplementedError" in capsys.readouterr().err
