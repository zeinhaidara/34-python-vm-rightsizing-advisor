"""Turn utilisation into a one-step rightsizing recommendation."""

from __future__ import annotations

import math
from dataclasses import dataclass

from rightsizer.catalog import Catalog
from rightsizer.metrics import Utilisation

UP, DOWN, KEEP, UNKNOWN = "up", "down", "keep", "unknown"


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. No interpolation, so the answer is a real sample."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    rank = math.ceil(pct / 100 * len(ordered))
    return ordered[max(rank, 1) - 1]


@dataclass(frozen=True)
class Recommendation:
    instance_id: str
    instance_type: str
    cpu_p: float | None
    mem_p: float | None
    action: str
    target: str | None
    reason: str


def recommend(
    instance_id: str, instance_type: str, usage: Utilisation, catalog: Catalog
) -> Recommendation:
    t = catalog.thresholds

    def result(action, target, reason, cpu=None, mem=None):
        return Recommendation(instance_id, instance_type, cpu, mem, action, target, reason)

    sizes = catalog.neighbours(instance_type)
    if sizes is None:
        return result(UNKNOWN, None, "instance type not in catalog")
    down, up = sizes

    if len(usage.cpu) < t.min_datapoints:
        return result(
            UNKNOWN, None, f"only {len(usage.cpu)} CPU datapoints, need {t.min_datapoints}"
        )
    cpu = percentile(usage.cpu, t.percentile)

    mem = None
    if len(usage.memory) >= t.min_datapoints:
        mem = percentile(usage.memory, t.percentile)

    if cpu > t.cpu.high or (mem is not None and mem > t.memory.high):
        if up is None:
            return result(KEEP, None, "busy, but already the largest size in catalog", cpu, mem)
        hot = "CPU" if cpu > t.cpu.high else "memory"
        return result(UP, up, f"p{t.percentile:g} {hot} above threshold", cpu, mem)

    if mem is None:
        # Without memory data a downsize could starve the box. Don't guess.
        why = (
            f"only {len(usage.memory)} memory datapoints"
            if usage.memory
            else "no memory data (CloudWatch agent?)"
        )
        return result(UNKNOWN, None, why, cpu, None)

    if cpu < t.cpu.low and mem < t.memory.low:
        if down is None:
            return result(KEEP, None, "idle, but already the smallest size in catalog", cpu, mem)
        return result(DOWN, down, "CPU and memory below low thresholds", cpu, mem)

    return result(KEEP, None, "within thresholds", cpu, mem)
