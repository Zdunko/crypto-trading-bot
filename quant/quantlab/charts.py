"""Dependency-free SVG line charts (equity curves, drawdowns, exposure) for the evaluation report."""

from __future__ import annotations

import math

PALETTE = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#7f7f7f", "#8c564b", "#e377c2", "#bcbd22", "#17becf"]


def drawdown(series: list[float]) -> list[float]:
    peak, out = -math.inf, []
    for v in series:
        peak = max(peak, v)
        out.append(v / peak - 1.0 if peak > 0 else 0.0)
    return out


def line_chart(
    series: dict[str, list[float]], title: str, ylabel: str, start: str = "2021-01-01", log: bool = False,
    dashed: tuple[str, ...] = (), width: int = 980, height: int = 460,
) -> str:  # fmt: skip
    import datetime as dt

    left, right, top, bottom = 70, 200, 40, 40
    n = max(len(v) for v in series.values())
    vals = [x for v in series.values() for x in v if x is not None and (x > 0 or not log)]
    lo, hi = min(vals), max(vals)
    if log:
        lo, hi = math.log10(lo), math.log10(hi)
    pad = (hi - lo) * 0.05 or 1.0
    lo, hi = lo - pad, hi + pad
    px = lambda i: left + (width - left - right) * i / max(n - 1, 1)  # noqa: E731
    py = lambda y: top + (height - top - bottom) * (1 - ((math.log10(y) if log else y) - lo) / (hi - lo))  # noqa: E731
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif" font-size="11">',
           f'<rect width="{width}" height="{height}" fill="white"/>',
           f'<text x="{left}" y="22" font-size="14" font-weight="bold">{title}</text>',
           f'<text x="14" y="{top + 10}" transform="rotate(-90 14 {top + 10})" text-anchor="end">{ylabel}</text>']  # fmt: skip
    for k in range(6):
        y = top + (height - top - bottom) * k / 5
        val = hi - (hi - lo) * k / 5
        label = f"{10**val:,.0f}" if log else f"{val:.0%}" if abs(hi) <= 2 else f"{val:.2f}"
        out += [f'<line x1="{left}" x2="{width - right}" y1="{y:.1f}" y2="{y:.1f}" stroke="#e5e5e5"/>',
                f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end">{label}</text>']  # fmt: skip
    d0 = dt.date.fromisoformat(start)
    for yr in range(d0.year, d0.year + n // 365 + 2):
        i = (dt.date(yr, 1, 1) - d0).days
        if 0 <= i < n:
            out += [f'<line x1="{px(i):.1f}" x2="{px(i):.1f}" y1="{top}" y2="{height - bottom}" stroke="#f0f0f0"/>',
                    f'<text x="{px(i):.1f}" y="{height - bottom + 16}" text-anchor="middle">{yr}</text>']  # fmt: skip
    for k, (name, v) in enumerate(series.items()):
        pts = " ".join(f"{px(i):.1f},{py(x):.1f}" for i, x in enumerate(v) if x is not None and (x > 0 or not log))
        dash = ' stroke-dasharray="5 3"' if name in dashed else ""
        c = PALETTE[k % len(PALETTE)]
        out.append(f'<polyline fill="none" stroke="{c}" stroke-width="1.6"{dash} points="{pts}"/>')
        out.append(f'<rect x="{width - right + 12}" y="{top + 16 * k}" width="10" height="3" fill="{c}"/>'
                   f'<text x="{width - right + 28}" y="{top + 16 * k + 5}">{name}</text>')  # fmt: skip
    out.append("</svg>")
    return "\n".join(out)
