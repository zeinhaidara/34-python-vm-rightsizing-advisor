"""Load thresholds and the instance-size catalog from YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Band:
    low: float
    high: float


@dataclass(frozen=True)
class Thresholds:
    lookback_days: int
    period_seconds: int
    percentile: float
    min_datapoints: int
    cpu: Band
    memory: Band


@dataclass(frozen=True)
class Catalog:
    thresholds: Thresholds
    families: dict[str, list[str]]

    def neighbours(self, instance_type: str) -> tuple[str | None, str | None] | None:
        """(one size down, one size up), or None if the type isn't listed."""
        for sizes in self.families.values():
            if instance_type in sizes:
                i = sizes.index(instance_type)
                down = sizes[i - 1] if i > 0 else None
                up = sizes[i + 1] if i + 1 < len(sizes) else None
                return down, up
        return None


def load_catalog(path: Path) -> Catalog:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    try:
        t = raw["thresholds"]
        thresholds = Thresholds(
            lookback_days=int(t["lookback_days"]),
            period_seconds=int(t["period_seconds"]),
            percentile=float(t["percentile"]),
            min_datapoints=int(t["min_datapoints"]),
            cpu=_band(t["cpu"], "cpu"),
            memory=_band(t["memory"], "memory"),
        )
        families = raw["families"]
    except KeyError as exc:
        raise ConfigError(f"{path}: missing key {exc}") from exc

    if not 0 < thresholds.percentile <= 100:
        raise ConfigError("percentile must be in (0, 100]")
    if thresholds.lookback_days < 1 or thresholds.period_seconds < 60:
        raise ConfigError("lookback_days must be >= 1 and period_seconds >= 60")
    if not isinstance(families, dict) or not families:
        raise ConfigError("families must be a non-empty mapping")

    seen: set[str] = set()
    for name, sizes in families.items():
        if not isinstance(sizes, list) or not sizes:
            raise ConfigError(f"family {name!r} must list at least one size")
        for size in sizes:
            if size in seen:
                raise ConfigError(f"instance type {size!r} listed twice")
            seen.add(size)
    return Catalog(thresholds=thresholds, families=families)


def _band(raw: dict, name: str) -> Band:
    band = Band(low=float(raw["low"]), high=float(raw["high"]))
    if not 0 <= band.low < band.high <= 100:
        raise ConfigError(f"{name}: need 0 <= low < high <= 100")
    return band
