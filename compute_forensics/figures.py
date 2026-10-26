"""Figures for the paper (PDF for LaTeX, PNG for the README and visuals page).

Style rules, applied everywhere:
- one validated categorical order (blue, orange, aqua, yellow), used by entity, never cycled;
  a fifth bucket is always "other" in neutral gray
- one y-axis per plot; two measures with different units get two stacked panels
- solid hairline y-grid, no box, no tick marks, ink-colored text, thin marks
- a legend for two or more series, plus direct labels where they fit
IEEE column width is 3.5 in, so base type is 7.5 pt.
"""
from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

# Palette (validated: adjacent CVD dE >= 9.1, normal-vision dE >= 22.9 on light surface)
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
SERIES = [BLUE, ORANGE, AQUA, YELLOW]
OTHER = "#b9b7b0"
BLUE_RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#104281"]   # ordinal steps of the blue ramp
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASE, SURFACE, EMPTY = "#e1e0d9", "#c3c2b7", "#ffffff", "#f0efec"

plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Helvetica", "Arial", "Liberation Sans", "DejaVu Sans"],
    "font.size": 7.5, "axes.labelsize": 7.5, "axes.titlesize": 8, "legend.fontsize": 7,
    "xtick.labelsize": 7, "ytick.labelsize": 7,
    "text.color": INK, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": BASE, "axes.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID,
    "grid.linewidth": 0.5, "grid.linestyle": "-", "axes.axisbelow": True,
    "xtick.major.size": 0, "ytick.major.size": 0, "xtick.major.pad": 4, "ytick.major.pad": 3,
    "lines.linewidth": 1.4, "lines.solid_capstyle": "round", "patch.linewidth": 0,
    "legend.frameon": False, "legend.handlelength": 1.2, "legend.handleheight": 0.8, "legend.columnspacing": 1.2,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "figure.dpi": 220, "savefig.bbox": "tight", "savefig.pad_inches": 0.04, "pdf.fonttype": 42,
})
COL = 3.5


def _tidy_dates(fig) -> None:
    """Quarterly ticks on every date axis so labels never collide at column width."""
    for ax in fig.axes:
        fmt = ax.xaxis.get_major_formatter()
        if isinstance(fmt, (mdates.DateFormatter, mdates.AutoDateFormatter, mdates.ConciseDateFormatter)):
            ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
            ax.tick_params(axis="x", rotation=0)


def _save(fig, out: Path, name: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    _tidy_dates(fig)
    fig.savefig(out / f"{name}.pdf")
    fig.savefig(out / f"{name}.png")
    plt.close(fig)


def _d(s: str):
    return date.fromisoformat(s[:10])


def _legend_top(ax, ncol: int = 4, **kw) -> None:
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=ncol, borderaxespad=0.3, **kw)


def _short(a: str) -> str:
    return f"{a[:6]}…{a[-4:]}"


def _month_axis(months: list[str]) -> list[str]:
    return [date(int(m[:4]), int(m[5:7]), 1).strftime("%b\n%y") if m[5:7] in ("01", "04", "07", "10")
            else "" for m in months]


def _fill_months(first: str, last: str) -> list[str]:
    out, (y, m) = [], map(int, first.split("-"))
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _stack(ax, months, layers, width=0.72):
    """Stacked monthly bars with a surface gap between segments."""
    bottom = [0.0] * len(months)
    x = list(range(len(months)))
    for label, vals, color in layers:
        ax.bar(x, vals, bottom=bottom, color=color, width=width, label=label, edgecolor=SURFACE, linewidth=0.7)
        bottom = [a + b for a, b in zip(bottom, vals)]
    ax.set_xticks(x, _month_axis(months))
    ax.set_xlim(-0.6, len(months) - 0.4)
    return bottom


# ---------------------------------------------------------------------------- USD.AI

def originations(loans, out: Path) -> None:
    """Monthly originated principal, stacked by the four largest borrowers."""
    real = [ln for ln in loans if ln.principal >= 1000]
    tot = {}
    for ln in real:
        tot[ln.borrower] = tot.get(ln.borrower, 0) + ln.principal
    top = [b for b, _ in sorted(tot.items(), key=lambda kv: -kv[1])[:4]]
    seen = sorted({ln.originated[:7] for ln in real})
    months = _fill_months(seen[0], seen[-1])
    layers = []
    for i, who in enumerate(top + ["other"]):
        vals = [sum(ln.principal for ln in real if ln.originated[:7] == m and
                    ((ln.borrower == who) if who != "other" else ln.borrower not in top)) / 1e6 for m in months]
        layers.append((_short(who) if who != "other" else "other borrowers", vals,
                       SERIES[i] if who != "other" else OTHER))
    fig, ax = plt.subplots(figsize=(COL, 2.2))
    totals = _stack(ax, months, layers)
    for x, v in enumerate(totals):
        if v >= 20:
            ax.text(x, v + 1.5, f"{v:,.0f}", ha="center", va="bottom", fontsize=6.3, color=INK2)
    ax.set_ylabel("Originated principal, USD m")
    ax.set_ylim(0, max(totals) * 1.15)
    _legend_top(ax, ncol=3)
    _save(fig, out, "fig_originations")


def _rolling_median(rows: list[dict], days: int = 7) -> tuple[list, list]:
    from statistics import median
    pts = sorted((r["date"], r["price"]) for r in rows if r.get("price"))
    xs, ys = [], []
    for i in range(len(pts)):
        win = [p for _, p in pts[max(0, i - days + 1): i + 1]]
        xs.append(_d(pts[i][0]))
        ys.append(median(win))
    return xs, ys


def nav_and_peg(nav: dict, prices: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    ax.axhline(1.0, color=BASE, lw=0.6, zorder=1)
    sp, up = prices.get("sUSDai") or [], prices.get("USDai") or []
    if up:
        xs, ys = _rolling_median(up)
        ax.plot(xs, ys, color=AQUA, lw=1.0, label="USDai market price, 7-day median")
    if sp:
        xs, ys = _rolling_median(sp)
        ax.plot(xs, ys, color=ORANGE, lw=1.0, label="sUSDai market price, 7-day median")
    xs = [_d(k) for k in nav]
    ax.plot(xs, list(nav.values()), color=BLUE, lw=1.8, label="sUSDai NAV per share (vault)")
    last_x, last_v = xs[-1], list(nav.values())[-1]
    ax.annotate(f"{last_v:.4f}", (last_x, last_v), xytext=(3, 0), textcoords="offset points",
                va="center", fontsize=6.5, color=INK)
    ax.set_ylabel("USD")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _legend_top(ax, ncol=1)
    _save(fig, out, "fig_nav")


def yield_sources(accrued: dict, cash: dict, out: Path) -> None:
    months = [m for m in sorted(set(accrued) | set(cash)) if m >= "2025-06"]
    keys = [("loan_interest", "borrower interest"), ("base_yield", "base yield (stablecoin issuers)"),
            ("fees", "fees"), ("escrow_interest", "escrow interest")]
    layers = [(lab, [cash.get(m, {}).get(k, 0.0) / 1e6 for m in months], SERIES[i]) for i, (k, lab) in enumerate(keys)]
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    _stack(ax, months, layers)
    acc = [accrued.get(m, 0.0) / 1e6 for m in months]
    ax.plot(range(len(months)), acc, color=INK, lw=1.1, marker="o", ms=3, mfc=SURFACE, mew=1.0,
            label="yield credited to holders")
    ax.set_ylabel("USD m per month")
    _legend_top(ax, ncol=2)
    _save(fig, out, "fig_yield")


def balance_sheet(parts: list[tuple[str, float]], liabilities: list[tuple[str, float]], out: Path) -> None:
    """Two horizontal stacked bars: what backs sUSDai, and who holds the shares."""
    fig, ax = plt.subplots(figsize=(COL * 2, 2.1))
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    rows = [("Assets, vault accounting", parts, [BLUE, ORANGE, AQUA, YELLOW]),
            ("Shares at redemption price", liabilities, BLUE_RAMP[:3])]
    for y, (title, items, pal) in enumerate(rows):
        yy = 1 - y
        left = 0.0
        tot = sum(v for _, v in items) / 1e6
        small = []
        for i, (lab, v) in enumerate(items):
            w = v / 1e6
            ax.barh(yy, w, left=left, height=0.62, color=pal[i], edgecolor=SURFACE, linewidth=1.5)
            lab1 = lab.replace("\n", " ")
            dark = pal[i] in (BLUE, ORANGE, BLUE_RAMP[1], BLUE_RAMP[2], BLUE_RAMP[3])
            if w / tot > 0.13:
                ax.text(left + w / 2, yy, f"{lab1}\n${w:,.0f}M", ha="center", va="center", fontsize=8,
                        color="white" if dark else INK, linespacing=1.15)
            else:
                small.append((left + w, f"{lab1} ${w:,.1f}M" if w < 10 else f"{lab1} ${w:,.0f}M"))
            left += w
        for k, (xr, txt) in enumerate(small):
            ax.annotate(txt, (xr - 1, yy + 0.31), xytext=(xr, yy + 0.47 + 0.17 * k), ha="right", va="bottom",
                        fontsize=7.2, color=INK2, arrowprops=dict(arrowstyle="-", lw=0.6, color=MUTED))
        ax.text(-6, yy, f"{title}\n${tot:,.0f}M", ha="right", va="center", fontsize=8, color=INK, linespacing=1.25)
    ax.set_yticks([])
    ax.set_xticks([])
    ax.set_ylim(-0.45, 1.85)
    _save(fig, out, "fig_balance_sheet")


def flow_graph(nodes: dict[str, tuple[float, float]], edges: list[tuple[str, str, float, str]], out: Path,
               name: str = "fig_escrow_flow") -> None:
    """Directed money-flow graph; arrow width is proportional to USD. Arrows run
    from box edge to box edge, and each label sits beside its arrow."""
    from matplotlib.patches import FancyArrowPatch
    fig, ax = plt.subplots(figsize=(COL * 2, 2.7))
    ax.axis("off")
    ax.set_xlim(-0.04, 1.04)
    ax.set_ylim(0.0, 1.1)
    boxes = {}
    for n, (x, y) in nodes.items():
        boxes[n] = ax.text(x, y, n, ha="center", va="center", fontsize=7.6, color=INK, linespacing=1.15, zorder=3,
                           bbox=dict(boxstyle="round,pad=0.45,rounding_size=0.4", fc="#f3f6fb", ec=BLUE, lw=0.7))
    fig.canvas.draw()
    inv = ax.transData.inverted()
    ext = {}
    for n, t in boxes.items():
        bb = t.get_bbox_patch().get_window_extent()
        (x0, y0), (x1, y1) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
        ext[n] = (x0, y0, x1, y1)

    def edge_point(n, tx, ty):
        """Where the segment from the box centre toward (tx, ty) leaves the box."""
        x0, y0, x1, y1 = ext[n]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        dx, dy = tx - cx, ty - cy
        sx = (x1 - x0) / 2 / abs(dx) if dx else float("inf")
        sy = (y1 - y0) / 2 / abs(dy) if dy else float("inf")
        k = min(sx, sy) * 1.04
        return cx + dx * k, cy + dy * k

    mx = max(e[2] for e in edges) if edges else 1
    for a, b, v, lab in edges:
        (ax_, ay), (bx, by) = nodes[a], nodes[b]
        p0, p1 = edge_point(a, bx, by), edge_point(b, ax_, ay)
        ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>,head_length=4,head_width=2.6", mutation_scale=1.6,
                                     lw=0.8 + 5 * v / mx, color=ORANGE, alpha=0.9, zorder=2))
        mxp, myp = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        horizontal = abs(p1[1] - p0[1]) < 0.05
        txt = f"${v / 1e6:,.1f}M\n{lab}" if horizontal else f"${v / 1e6:,.1f}M {lab}"
        ax.text(mxp, myp + (0.06 if horizontal else 0), txt, ha="center", linespacing=1.1,
                va="bottom" if horizontal else "center", fontsize=7, color=INK, zorder=4,
                bbox=None if horizontal else dict(boxstyle="round,pad=0.2", fc=SURFACE, ec="none"))
    _save(fig, out, name)


# ---------------------------------------------------------------------------- holders

def lorenz(snapshots: dict, out: Path, name: str = "fig_lorenz",
           xlabel: str = "Cumulative share of participants (smallest first)") -> None:
    fig, ax = plt.subplots(figsize=(COL, 2.3))
    ax.grid(True, axis="both")
    ax.plot([0, 1], [0, 1], color=BASE, lw=0.7, zorder=1)
    ax.text(0.52, 0.56, "perfect equality", rotation=33, fontsize=6, color=MUTED, ha="center")
    for i, (label, bals) in enumerate(snapshots.items()):
        b = sorted(x for x in bals if x > 0)
        tot = sum(b)
        if not tot:
            continue
        cum, xs, ys = 0, [0.0], [0.0]
        for k, v in enumerate(b, 1):
            cum += v
            xs.append(k / len(b))
            ys.append(cum / tot)
        ax.plot(xs, ys, color=SERIES[i] if i < 4 else OTHER, lw=1.4, label=label)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel(xlabel)
    ax.set_ylabel("Cumulative share of USD")
    ax.legend(loc="upper left")
    _save(fig, out, name)


def lorenz_named(curves: dict[str, list[float]], out: Path, name: str) -> None:
    lorenz(curves, out, name)


def holder_concentration(conc: dict[str, dict], out: Path) -> None:
    """Share of each chain's sUSDai held by its largest holder and its ten largest."""
    rows = sorted(((k, v) for k, v in conc.items() if v.get("holders")), key=lambda kv: -kv[1]["total"])
    fig, ax = plt.subplots(figsize=(COL, 1.75))
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    ys = list(range(len(rows)))
    h = 0.36
    ax.barh([y - h / 2 for y in ys], [100 * v["top1"] for _, v in rows], height=h, color=BLUE, label="largest holder")
    ax.barh([y + h / 2 for y in ys], [100 * v["top10"] for _, v in rows], height=h, color=ORANGE,
            label="ten largest holders")
    for y, (_, v) in zip(ys, rows):
        ax.text(100 * v["top1"] + 1.5, y - h / 2, f"{100 * v['top1']:.0f}%", va="center", fontsize=6.2, color=INK)
        ax.text(100 * v["top10"] + 1.5, y + h / 2, f"{100 * v['top10']:.0f}%", va="center", fontsize=6.2, color=INK)
    ax.set_yticks(ys, [f"{k}  ({v['holders']:,} holders)" for k, v in rows], color=INK)
    ax.set_xlim(0, 112)
    ax.set_xlabel("Share of the chain's sUSDai supply, %")
    ax.invert_yaxis()
    _legend_top(ax, ncol=2)
    _save(fig, out, "fig_concentration")


def supply_chains(supply: dict, out: Path) -> None:
    items = sorted(supply.items(), key=lambda kv: -kv[1])
    fig, ax = plt.subplots(figsize=(COL, 1.55))
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    pretty = {"eth": "Ethereum"}
    names = [pretty.get(k, k.capitalize()) for k, _ in items]
    vals = [v / 1e6 for _, v in items]
    ax.barh(names, vals, color=BLUE, height=0.62)
    for y, v in enumerate(vals):
        ax.text(v + max(vals) * 0.015, y, f"{v:,.1f}M", va="center", fontsize=6.6, color=INK)
    ax.set_xlabel("sUSDai shares, millions")
    ax.set_xlim(0, max(vals) * 1.15)
    ax.invert_yaxis()
    ax.tick_params(axis="y", colors=INK)
    _save(fig, out, "fig_supply")


def eth_holders(snaps: dict[str, dict], out: Path) -> None:
    ks = sorted(k for k, v in snaps.items() if v.get("holders"))
    if not ks:
        return
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(COL, 2.4), sharex=True, gridspec_kw={"hspace": 0.35})
    xs = [_d(k) for k in ks]
    a1.bar(xs, [snaps[k]["supply"] / 1e6 for k in ks], width=20, color=BLUE)
    a1.set_title("sUSDai on Ethereum, millions of shares", loc="left", fontsize=7, color=INK)
    a2.plot(xs, [snaps[k]["holders"] for k in ks], color=ORANGE, marker="o", ms=3, mfc=SURFACE, mew=1)
    a2.set_title("Holders", loc="left", fontsize=7, color=INK)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _save(fig, out, "fig_eth_holders")


def activity_heatmap(activity: dict[str, list[str]], roles: dict[str, str], out: Path, max_rows: int = 22) -> None:
    """Which chains each key address has ever touched (GoldRush cross-chain activity)."""
    import numpy as np
    from matplotlib.colors import ListedColormap
    addrs = sorted(activity, key=lambda a: (roles.get(a, "z"), -len(activity[a])))[:max_rows]
    chains = sorted({c for a in addrs for c in activity[a]},
                    key=lambda c: -sum(c in activity[a] for a in addrs))[:18]
    if not addrs or not chains:
        return
    m = np.array([[1 if c in activity[a] else 0 for a in addrs] for c in chains])
    fig, ax = plt.subplots(figsize=(COL * 2, 0.14 * len(chains) + 1.2))
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.imshow(m, cmap=ListedColormap([EMPTY, BLUE]), aspect="auto", vmin=0, vmax=1)
    ax.set_yticks(range(len(chains)), [c.replace("-mainnet", "") for c in chains], fontsize=6, color=INK2)
    ax.set_xticks(range(len(addrs)), [a[:6] for a in addrs], rotation=90, fontsize=5.6, color=INK2)
    ax.set_xticks([x - 0.5 for x in range(1, len(addrs))], minor=True)
    ax.set_yticks([y - 0.5 for y in range(1, len(chains))], minor=True)
    ax.grid(which="minor", color=SURFACE, lw=1.2)
    ax.tick_params(which="minor", length=0)
    nb = sum(1 for a in addrs if roles.get(a) == "borrower")
    if 0 < nb < len(addrs):
        ax.axvline(nb - 0.5, color=INK, lw=1.0)
    for lab, x0, x1 in (("borrowers", 0, nb), ("top holders", nb, len(addrs))):
        if x1 > x0:
            ax.text((x0 + x1 - 1) / 2, -0.9, lab, ha="center", va="bottom", fontsize=7, color=INK)
    _save(fig, out, "fig_activity")


# ---------------------------------------------------------------------------- exits

def _weekly_usd(weekly_req: dict, nav_daily: dict):
    xs = [_d(k) for k in weekly_req]
    return xs, [v * nav_daily.get(k, 1.0) / 1e6 for k, v in weekly_req.items()]


def queue_timeline(batches: list[dict], weekly_req: dict, nav_daily: dict, out: Path) -> None:
    fig, ax = plt.subplots(figsize=(COL, 2.0))
    xs, ys = _weekly_usd(weekly_req, nav_daily)
    ax.bar(xs, ys, width=5, color=BLUE_RAMP[0], label="requested per week")
    ax.scatter([_d(b["t"]) for b in batches], [b["amount"] / 1e6 for b in batches], color=ORANGE, s=16,
               edgecolor=SURFACE, linewidth=1.0, zorder=3, label="queue serviced (one batch)")
    big = max(batches, key=lambda b: b["amount"]) if batches else None
    if big:
        ax.annotate(f"${big['amount'] / 1e6:,.0f}M", (_d(big["t"]), big["amount"] / 1e6), xytext=(5, 0),
                    textcoords="offset points", va="center", fontsize=6.3, color=INK2)
    ax.set_ylabel("USD m")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _legend_top(ax, ncol=2)
    _save(fig, out, "fig_queue")


def redemptions_vs_gpu(weekly_req: dict, nav_daily: dict, gpu: list[tuple[str, float]], out: Path) -> None:
    """Two panels on a shared time axis, not a dual-axis chart."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(COL, 2.6), sharex=True, gridspec_kw={"hspace": 0.4})
    xs, ys = _weekly_usd(weekly_req, nav_daily)
    a1.bar(xs, ys, width=5, color=BLUE)
    a1.set_title("Redemption requests, USD m per week", loc="left", fontsize=7, color=INK)
    if gpu:
        lo = min(xs)
        g = [(_d(d), p) for d, p in gpu if _d(d) >= lo]
        a2.plot([x for x, _ in g], [p for _, p in g], color=ORANGE)
        a2.set_title("H100 on-demand rental, median USD per GPU-hour (GetDeploying)", loc="left", fontsize=7, color=INK)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _save(fig, out, "fig_redemptions")


# ---------------------------------------------------------------------------- compute markets

def markets_monthly(series: dict[str, dict[str, float]], out: Path) -> None:
    """Monthly USD flows on one log axis, each line labeled at its end."""
    fig, ax = plt.subplots(figsize=(COL, 2.4))
    for i, (label, s) in enumerate(series.items()):
        ks = sorted(k for k, v in s.items() if v > 0 and "2025-05" <= k <= "2026-10")
        if not ks:
            continue
        span = _fill_months(ks[0], ks[-1])            # a month with no flow is a gap, not a line to zero
        xs = [_d(k + "-15") for k in span]
        ys = [s[k] if s.get(k, 0) > 0 else float("nan") for k in span]
        ax.plot(xs, ys, color=SERIES[i], lw=1.4, marker="o", ms=2.6, mfc=SERIES[i], mew=0, label=label)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"${v / 1e6:,.0f}M" if v >= 1e6 else f"${v / 1e3:,.0f}k"))
    ax.set_ylabel("USD per month, log scale")
    _legend_top(ax, ncol=2)
    _save(fig, out, "fig_markets")


def akash_gpu(gpu_series: dict, monthly_usd: dict, out: Path) -> None:
    """Two panels on a shared time axis, not a dual-axis chart."""
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(COL, 2.5), sharex=True, gridspec_kw={"hspace": 0.4})
    ks = [k for k in gpu_series if k >= "2025-05-01"]
    a1.plot([_d(k) for k in ks], [gpu_series[k] for k in ks], color=BLUE, lw=1.1)
    a1.set_title("Akash active leased GPUs", loc="left", fontsize=7, color=INK)
    ms = [m for m in monthly_usd if "2025-05" <= m <= "2026-10"]
    a2.bar([_d(m + "-15") for m in ms], [monthly_usd[m] / 1e3 for m in ms], width=22, color=AQUA)
    a2.set_title("Akash spend, USD k per month", loc="left", fontsize=7, color=INK)
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    _save(fig, out, "fig_akash")


def gpu_prices(rows: list[tuple[str, float]], out: Path) -> None:
    fig, ax = plt.subplots(figsize=(COL, 1.35))
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    names = [textwrap.fill(r[0], 30) for r in rows]
    vals = [r[1] for r in rows]
    colors = [OTHER if "centralized" in r[0].lower() else BLUE for r in rows]
    ax.barh(names, vals, color=colors, height=0.6)
    for y, v in enumerate(vals):
        ax.text(v + 0.05, y, f"${v:.2f}", va="center", fontsize=6.6, color=INK)
    ax.set_xlabel("USD per GPU-hour")
    ax.set_xlim(0, max(vals) * 1.18)
    ax.invert_yaxis()
    ax.tick_params(axis="y", colors=INK, labelsize=6.3)
    _save(fig, out, "fig_gpu_prices")


# ---------------------------------------------------------------------------- summary

def at_a_glance(tiles: list[tuple[str, str]], out: Path) -> None:
    """Graphical abstract: key measured quantities as stat tiles."""
    cols = 5
    rows = (len(tiles) + cols - 1) // cols
    fig = plt.figure(figsize=(COL * 2, 0.92 * rows))
    for i, (value, label) in enumerate(tiles):
        r, c = divmod(i, cols)
        ax = fig.add_axes([c / cols + 0.006, 1 - (r + 1) / rows + 0.04, 1 / cols - 0.012, 1 / rows - 0.08])
        ax.axis("off")
        ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.08",
                                    transform=ax.transAxes, fc="#f7f7f5", ec=GRID, lw=0.7))
        ax.text(0.09, 0.64, value, ha="left", va="center", fontsize=13, color=INK, weight="bold",
                transform=ax.transAxes)
        ax.text(0.09, 0.27, textwrap.fill(label, 24), ha="left", va="center", fontsize=6.4, color=INK2,
                transform=ax.transAxes, linespacing=1.15)
    _save(fig, out, "fig_glance")


def implied_gpus(curve: list[tuple[float, int]], akash_total: int | None, out: Path) -> None:
    """GPUs that must run, at a given rental price and utilization, to service the
    outstanding debt. One line, one axis, with the Akash network size as a reference."""
    fig, ax = plt.subplots(figsize=(COL, 2.1))
    xs = [p for p, _ in curve]
    ys = [g for _, g in curve]
    ax.plot(xs, ys, color=BLUE, lw=1.8)
    for p, g in curve:
        if abs(p - 2.56) < 0.01 or abs(p - 3.36) < 0.01:
            ax.scatter([p], [g], color=ORANGE, s=18, zorder=3, edgecolor=SURFACE, linewidth=1)
            ax.annotate(f"${p:.2f}/h: {g:,} GPUs", (p, g), xytext=(6, 6), textcoords="offset points", fontsize=6.3,
                        color=INK)
    if akash_total:
        ax.axhline(akash_total, color=OTHER, lw=1, ls="-")
        ax.text(xs[-1], akash_total, f" all GPUs on Akash: {akash_total:,}", ha="right", va="bottom", fontsize=6.3,
                color=INK2)
    ax.set_xlabel("H100 rental price, USD per GPU-hour")
    ax.set_ylabel("H100s needed at 70% use")
    ax.set_ylim(0, max(ys) * 1.12)
    _save(fig, out, "fig_implied_gpus")


def collateral_ltv(rows: list[dict], out: Path) -> None:
    """Stated collateral value against outstanding principal, one pair of bars per
    active loan, largest first. LTV is printed at the end of each pair."""
    rows = sorted(rows, key=lambda r: -r["outstanding"])[:12]
    fig, ax = plt.subplots(figsize=(COL, 0.21 * len(rows) + 0.9))
    ax.grid(True, axis="x")
    ax.grid(False, axis="y")
    ys = list(range(len(rows)))
    h = 0.38
    ax.barh([y - h / 2 for y in ys], [r["collateral_value"] / 1e6 for r in rows], height=h, color=BLUE_RAMP[0],
            label="stated collateral value")
    ax.barh([y + h / 2 for y in ys], [r["outstanding"] / 1e6 for r in rows], height=h, color=BLUE,
            label="outstanding principal")
    mx = max(r["collateral_value"] for r in rows) / 1e6
    for y, r in zip(ys, rows):
        ax.text(r["collateral_value"] / 1e6 + mx * 0.015, y, f"LTV {100 * r['ltv']:.0f}%", va="center", fontsize=6.2,
                color=INK)
    labels = [f"{_short(r['borrower'])}  {'/'.join(m for m in r['models'] if m != 'other')[:14]} x{r['units']}"
              for r in rows]
    ax.set_yticks(ys, labels, fontsize=5.8, color=INK)
    ax.set_xlim(0, mx * 1.3)
    ax.set_xlabel("USD m")
    ax.invert_yaxis()
    _legend_top(ax, ncol=2)
    _save(fig, out, "fig_collateral")
