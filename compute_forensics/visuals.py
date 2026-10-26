"""Build visuals/index.html: a single self-contained page (figures embedded as
base64) that walks through every finding. Opens offline in any browser."""
from __future__ import annotations

import base64
import csv
import html
import json
from pathlib import Path

SECTIONS = [
    ("1. Where the money goes", [
        ("fig_originations", "GPU loans originated each month, by borrower. The four largest borrowers have their own colors."),
    ]),
    ("1a. What the collateral is", [
        ("fig_collateral", "Stated collateral value against outstanding principal, from the protocol's own hardware-token "
                           "records. Book LTV is 67% on a three-year useful life."),
    ]),
    ("2. Where the yield comes from", [
        ("fig_yield", "Cash that reached the vault each month, against the yield credited to holders (black line). "
                      "Base yield from stablecoin issuers is the largest cash source."),
        ("fig_nav", "sUSDai NAV per share from vault deposits, with 7-day medians of the market prices GoldRush reports."),
    ]),
    ("3. The vault's own balance sheet", [
        ("fig_balance_sheet", "Read with eth_call at one block. The orange segment is escrow for loans that do not exist "
                              "on-chain: 23% of reported assets."),
        ("fig_escrow_flow", "Where the escrowed USDai went. Arrow width is proportional to USD. Wallets are labeled by "
                            "on-chain role only."),
    ]),
    ("4. Who holds it, and where", [
        ("fig_supply", "sUSDai shares by chain."),
        ("fig_concentration", "Share of each chain's supply held by the largest holder and the ten largest."),
        ("fig_eth_holders", "sUSDai on Ethereum, from holder lists at the first block of each month."),
        ("fig_activity", "Every chain each borrower and top holder has used (GoldRush cross-chain activity endpoint)."),
    ]),
    ("5. Exits", [
        ("fig_queue", "Weekly redemption requests and the batches that cleared the queue."),
        ("fig_redemptions", "Redemption requests and the H100 rental price on the same time axis. They do not move together."),
    ]),
    ("6. GPU credit vs. compute bought on-chain", [
        ("fig_markets", "Monthly USD on a log scale: USD.AI lending and cash yield next to Akash and Livepeer spending."),
        ("fig_akash", "Akash leased GPUs and monthly spend (Akash Console API)."),
        ("fig_gpu_prices", "GPU rental prices on Akash and on centralized clouds (GetDeploying)."),
        ("fig_lorenz_markets", "How concentrated each side is: Livepeer gateways and orchestrators, and USD.AI borrowers."),
        ("fig_implied_gpus", "H100s that must run at 70% utilization to service the outstanding debt from rental "
                             "income alone, by rental price. The whole Akash network is the grey line."),
    ]),
]

CSS = """
:root{--bg:#fbfaf7;--fg:#1d2430;--muted:#5b6474;--card:#ffffff;--line:#e3e1db;--accent:#0b0b0b;--warn:#c4501f}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--fg:#e8e6e1;--muted:#a0a7b4;--card:#1d2229;--line:#2e343d;--accent:#f0efec;--warn:#f08a5d}
 img.fig{background:#fff;border-radius:6px}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 Inter,system-ui,-apple-system,'Segoe UI',sans-serif}
main{max-width:980px;margin:0 auto;padding:32px 16px 80px}
h1{font-size:1.9rem;line-height:1.2;margin:0 0 6px}h2{font-size:1.25rem;margin:44px 0 12px;border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{color:var(--muted);margin:0 0 24px;font-size:.95rem}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:18px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
.tile b{display:block;font:600 1.45rem/1.2 system-ui,sans-serif;color:var(--accent)}.tile span{font-size:.82rem;color:var(--muted)}
.tile.warn b{color:var(--warn)}
figure{margin:14px 0 22px;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px}
img.fig{width:100%;max-width:640px;height:auto;display:block;margin:0 auto}img.wide{max-width:100%}figcaption{font-size:.88rem;color:var(--muted);margin-top:8px}
table{border-collapse:collapse;width:100%;font:13px/1.4 system-ui,sans-serif}th,td{padding:6px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{cursor:pointer;user-select:none;color:var(--muted);font-weight:600}td:first-child,th:first-child{text-align:left}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:8px}
code{font-size:.85em}.note{font-size:.88rem;color:var(--muted)}a{color:var(--accent)}
"""

JS = """
document.querySelectorAll('table.sort').forEach(t=>{t.querySelectorAll('th').forEach((th,i)=>{th.onclick=()=>{
 const rows=[...t.tBodies[0].rows],asc=th.dataset.asc!=='1';th.dataset.asc=asc?'1':'0';
 const v=r=>{const s=r.cells[i].dataset.v??r.cells[i].textContent;const n=parseFloat(s);return isNaN(n)?s:n};
 rows.sort((a,b)=>(v(a)>v(b)?1:v(a)<v(b)?-1:0)*(asc?1:-1));rows.forEach(r=>t.tBodies[0].appendChild(r))}})});
"""


def _img(figdir: Path, name: str) -> str:
    p = figdir / f"{name}.png"
    if not p.exists():
        return ""
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def _m(x: float | None) -> str:
    return "n/a" if x is None else f"${x / 1e6:,.1f}M"


def build(results: Path, figdir: Path, out: Path) -> Path:
    res = json.loads((results / "results.json").read_text())
    ln, v, rc, es = res["loans"], res["vault"], res.get("reconciliation", {}), res.get("escrow", {})
    open_esc = sum(x["usd"] for x in es.get("open", []))
    tiles = [
        (_m(ln["originated"]), "GPU loans originated", ""),
        (_m(ln["outstanding"]), "outstanding", ""),
        (str(ln["borrowers"]), "borrowers", ""),
        (f"{100 * ln['top1_share']:.0f}%", "largest borrower's share", ""),
        (f"{100 * (v['ann_total'] or 0):.1f}%", "annualized NAV growth", ""),
        (f"{100 * (v['cash_coverage'] or 0):.0f}%", "of NAV yield received as cash", ""),
        (_m(rc.get("total_assets")), "vault assets (eth_call)", ""),
        (_m(open_esc), "escrow pre-funding with no loan on-chain", "warn"),
        (f"{res['queue']['wait_days_median']:.0f} days", "median redemption wait", ""),
        (_m((res.get("akash", {}).get("usd_window") or 0) + (res.get("livepeer", {}).get("usd_total") or 0)),
         "Akash + Livepeer compute spend, same window", ""),
    ]
    parts = [f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
             f"<title>Following the Compute Money</title><style>{CSS}</style></head><body><main>",
             "<h1>Following the Compute Money</h1>",
             f"<p class='sub'>An on-chain forensic look at GPU-backed credit (USD.AI) and decentralized compute markets "
             f"(Akash, Livepeer). Window {res['window']['start']} to {res['window']['end']}. Every number here is generated "
             f"by the code in this repository from the frozen dataset. Chain data: Covalent GoldRush API.</p>",
             "<div class='tiles'>" + "".join(f"<div class='tile {c}'><b>{html.escape(a)}</b><span>{html.escape(b)}</span></div>"
                                             for a, b, c in tiles) + "</div>"]
    for title, figs in SECTIONS:
        parts.append(f"<h2>{html.escape(title)}</h2>")
        for name, cap in figs:
            src = _img(figdir, name)
            if src:
                wide = " wide" if name in ("fig_escrow_flow", "fig_activity", "fig_balance_sheet") else ""
                parts.append(f"<figure><img class='fig{wide}' loading='lazy' alt='{html.escape(cap)}' src='{src}'>"
                             f"<figcaption>{html.escape(cap)}</figcaption></figure>")
    ver = res.get("verification")
    if ver:
        parts.append("<h2>Checked against the chain</h2><p class='note'>Every event set below was pulled twice: once from "
                     "GoldRush and once straight from a public Arbitrum node with eth_getLogs. Logs are matched by "
                     "transaction hash, topics and data.</p><div class='scroll'><table><thead><tr><th>Event</th>"
                     "<th>Node</th><th>GoldRush</th><th>Same</th></tr></thead><tbody>")
        for r in ver["event_checks"]:
            parts.append(f"<tr><td>{html.escape(r['check'])}</td><td>{r['rpc_count']:,}</td>"
                         f"<td>{r['goldrush_count']:,}</td><td>{'yes' if r['match'] else 'no'}</td></tr>")
        parts.append("</tbody></table></div>")
    loans = list(csv.DictReader((results / "loans.csv").open()))
    parts.append("<h2>Every loan (click a column to sort)</h2><div class='scroll'><table class='sort'><thead><tr>"
                 "<th>Originated</th><th>Borrower</th><th>Ccy</th><th>Principal</th><th>Outstanding</th>"
                 "<th>Interest paid</th><th>APR</th><th>Status</th><th>V</th></tr></thead><tbody>")
    for r in loans:
        if r["test_loan"] == "True":
            continue
        apr = f"{100 * float(r['rate_apr']):.1f}%" if r["rate_apr"] else ""
        parts.append(
            f"<tr><td>{r['originated'][:10]}</td><td><code>{r['borrower'][:8]}…{r['borrower'][-4:]}</code></td>"
            f"<td>{r['currency']}</td><td data-v='{r['principal']}'>{float(r['principal']):,.0f}</td>"
            f"<td data-v='{r['outstanding']}'>{float(r['outstanding']):,.0f}</td>"
            f"<td data-v='{r['interest_paid']}'>{float(r['interest_paid']):,.0f}</td>"
            f"<td data-v='{r['rate_apr'] or 0}'>{apr}</td><td>{r['status']}</td><td>{r['version']}</td></tr>")
    parts.append("</tbody></table></div>")
    parts.append("<p class='note'>Addresses are shown by prefix and labeled only by on-chain role. Nothing here identifies "
                 "an off-chain entity or claims misuse of funds. Akash data comes from the Akash Console API and vault "
                 "state from the public Arbitrum RPC; everything else is GoldRush.</p>")
    parts.append(f"<script>{JS}</script></main></body></html>")
    out.mkdir(parents=True, exist_ok=True)
    page = out / "index.html"
    page.write_text("\n".join(parts))
    return page
