"""Render recommendations as a Markdown table."""

from __future__ import annotations

from rightsizer.advisor import Recommendation


def _pct(value: float | None) -> str:
    return "unknown" if value is None else f"{value:.1f}%"


def to_markdown(recs: list[Recommendation], percentile: float) -> str:
    p = f"p{percentile:g}"
    lines = [
        f"| Instance | Type | {p} CPU | {p} memory | Action | Suggested type | Reason |",
        "|---|---|---:|---:|---|---|---|",
    ]
    for r in sorted(recs, key=lambda r: r.instance_id):
        lines.append(
            f"| {r.instance_id} | {r.instance_type} | {_pct(r.cpu_p)} | {_pct(r.mem_p)} | "
            f"{r.action} | {r.target or '-'} | {r.reason} |"
        )
    counts = {a: sum(1 for r in recs if r.action == a) for a in ("down", "up", "keep", "unknown")}
    summary = ", ".join(f"{n} {a}" for a, n in counts.items())
    return "\n".join(lines) + f"\n\n{len(recs)} instances: {summary}. Nothing was changed.\n"
