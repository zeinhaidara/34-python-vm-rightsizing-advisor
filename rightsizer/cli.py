"""python -m rightsizer --region eu-west-2 [--instance-id i-...] [--output report.md]"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from rightsizer.advisor import recommend
from rightsizer.catalog import load_catalog
from rightsizer.metrics import CloudWatchSource
from rightsizer.report import to_markdown

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "catalog.yaml"


def running_instances(ec2, instance_ids: list[str] | None) -> Iterator[tuple[str, str]]:
    """(instance id, type) for running instances. Follows NextToken."""
    kwargs: dict = {"Filters": [{"Name": "instance-state-name", "Values": ["running"]}]}
    if instance_ids:
        kwargs["InstanceIds"] = instance_ids
    while True:
        page = ec2.describe_instances(**kwargs)
        for res in page.get("Reservations", []):
            for inst in res.get("Instances", []):
                yield inst["InstanceId"], inst["InstanceType"]
        token = page.get("NextToken")
        if not token:
            return
        kwargs["NextToken"] = token


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only EC2 rightsizing report.")
    p.add_argument("--provider", choices=["aws", "azure"], default="aws")
    p.add_argument("--region", help="AWS region (default: from your AWS config)")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    p.add_argument("--instance-id", action="append", dest="instance_ids")
    p.add_argument("--output", type=Path)
    return p.parse_args(argv)


def main(argv=None, ec2=None, cloudwatch=None, now: datetime | None = None) -> int:
    args = parse_args(argv)
    try:
        catalog = load_catalog(args.config)
        t = catalog.thresholds
        if args.provider == "azure":
            # Only the AzureMonitorSource interface stub exists.
            raise NotImplementedError("Azure VMs are not implemented")

        if ec2 is None or cloudwatch is None:
            import boto3

            session = boto3.Session(region_name=args.region)
            ec2 = ec2 or session.client("ec2")
            cloudwatch = cloudwatch or session.client("cloudwatch")

        source = CloudWatchSource(cloudwatch, t.lookback_days, t.period_seconds)
        end = now or datetime.now(UTC)
        recs = [
            recommend(iid, itype, source.utilisation(iid, end), catalog)
            for iid, itype in running_instances(ec2, args.instance_ids)
        ]
        if not recs:
            raise RuntimeError("no running instances found")
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    text = to_markdown(recs, t.percentile)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0
