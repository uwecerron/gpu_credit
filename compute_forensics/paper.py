"""Write paper/generated/{numbers.tex, tab_*.tex} from the analysis results."""
from __future__ import annotations

from pathlib import Path

from . import registry as R


def usd_m(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else f"\\${x / 1e6:,.{nd}f}\\,M"


def usd_k(x: float | None) -> str:
    return "n/a" if x is None else f"\\${x / 1e3:,.0f}\\,k"


def pct(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{nd}f}\\%"


def num(x, nd: int = 0) -> str:
    return "n/a" if x is None else f"{x:,.{nd}f}"


def short(a: str) -> str:
    return f"\\texttt{{{a[:6]}\\ldots{{}}{a[-4:]}}}"


def macros(res: dict) -> dict[str, str]:
    ln, v, q, g = res["loans"], res["vault"], res["queue"], res["gpu"]
    hc = res["holders"]["concentration"]
    arb = hc.get(f"{R.HUB}:sUSDai", {})
    s_by = res["holders"]["susdai_supply_by_chain"]
    m = {
        "StudyStart": res["window"]["start"], "StudyEnd": res["window"]["end"],
        "EndBlock": num(res["window"]["end_block"]), "EventsDecoded": num(res["events_decoded"]),
        "NLoans": num(ln["n"]), "NTestLoans": num(ln["n_test"]), "NBorrowers": num(ln["borrowers"]),
        "Originated": usd_m(ln["originated"]), "Outstanding": usd_m(ln["outstanding"]),
        "InterestPaid": usd_m(ln["interest_paid"], 2), "PrincipalRepaid": usd_m(ln["principal_repaid"]),
        "FeesPaid": usd_k(ln["fees_paid"]), "NRepaid": num(ln["repaid"]), "NBreached": num(ln["breached"]),
        "NMigrated": num(ln["migrated"]), "NReserveAccounts": num(ln["reserve_accounts"]),
        "HHIOrig": num(ln["hhi_originated"], 3), "HHIOut": num(ln["hhi_outstanding"], 3),
        "TopOneShare": pct(ln["top1_share"]), "TopThreeShare": pct(ln["top3_share"]),
        "RateMin": pct(ln["rate_min"]), "RateMax": pct(ln["rate_max"]), "RateWavg": pct(ln["rate_wavg_outstanding"], 2),
        "SusdaiFunded": pct(ln["susdai_funded_share"], 2),
        "NavStart": num(v["nav_start"], 4), "NavEnd": num(v["nav_end"], 4), "AnnTotal": pct(v["ann_total"], 2),
        "AnnNinety": pct(v["ann_90d"], 2), "SharesEvents": num(v["shares_from_events"] / 1e6, 1) + "\\,M",
        "SharesHolders": num(v["shares_from_holders"] / 1e6, 1) + "\\,M", "Claims": usd_m(v["claims_usd"]),
        "IdleUSDai": usd_m(v["idle_usdai"]), "LoanBook": usd_m(v["loan_book"]),
        "Unexplained": usd_m(v["unexplained_assets"]), "Accrued": usd_m(v["accrued_total"], 2),
        "CashInterest": usd_m(v["cash"]["loan_interest"], 2), "CashBase": usd_m(v["cash"]["base_yield"], 2),
        "CashFees": usd_k(v["cash"]["fees"]), "CashEscrow": usd_k(v["cash"].get("escrow_interest")), "AdminFee": usd_m(v["admin_fee"], 2),
        "CashCoverage": pct(v["cash_coverage"]),
        "IdleShare": pct(v["idle_usdai"] / v["claims_usd"] if v["claims_usd"] else None),
        "LoanShare": pct(v["loan_book"] / v["claims_usd"] if v["claims_usd"] else None),
        "USDaiMinted": usd_m(res["usdai"]["minted"]), "USDaiBurned": usd_m(res["usdai"]["burned"]),
        "NRedeemRequests": num(q["requests"]), "NRedeemers": num(q["unique_redeemers"]),
        "RequestedShares": num(q["requested_shares"] / 1e6, 1) + "\\,M", "PendingShares": num(q["pending_shares"] / 1e6, 2) + "\\,M",
        "WaitMedian": num(q["wait_days_median"], 1), "WaitPNinety": num(q["wait_days_p90"], 1),
        "WaitMax": num(q["wait_days_max"], 1), "NCompleted": num(q["completed"]),
        "GPUWeeks": num(g["weeks_overlap"]), "RhoLevel": num(g["spearman_level"], 2),
        "RhoChange": num(g["spearman_change"], 2),
        "ArbHolders": num(arb.get("holders")), "ArbTopOne": pct(arb.get("top1")), "ArbTopTen": pct(arb.get("top10")),
        "ArbHHI": num(arb.get("hhi"), 3), "ArbGini": num(arb.get("gini"), 3),
        "SharesArb": num(s_by.get(R.HUB, 0) / 1e6, 1) + "\\,M", "SharesEth": num(s_by.get("eth-mainnet", 0) / 1e6, 1) + "\\,M",
        "SharesBase": num(s_by.get("base-mainnet", 0) / 1e6, 2) + "\\,M",
        "SharesPlasma": num(s_by.get("plasma-mainnet", 0) / 1e6, 1) + "\\,M",
        "NCrossChain": num(len(res["holders"]["cross_chain"])),
        "USDaiMin": num(res["prices"]["USDai"]["min"], 4), "USDaiLast": num((res["prices"]["USDai"]["last"] or {}).get("price"), 4),
        "USDaiLastDate": (res["prices"]["USDai"]["last"] or {}).get("date", "n/a"),
    }
    rc = res.get("reconciliation", {})
    m.update({
        "StateBlock": num(rc.get("block")), "TotalAssets": usd_m(rc.get("total_assets")),
        "TotalShares": num((rc.get("total_shares") or 0) / 1e6, 1) + "\\,M",
        "HubSupply": num((rc.get("hub_supply") or 0) / 1e6, 1) + "\\,M",
        "BridgedSupply": num((rc.get("bridged_supply") or 0) / 1e6, 1) + "\\,M",
        "SpokeSolana": num((rc.get("spoke_plus_solana") or 0) / 1e6, 1) + "\\,M",
        "PendingRedeemShares": num((rc.get("pending_redemption_shares") or 0) / 1e6, 2) + "\\,M",
        "DepositBalance": usd_m(rc.get("deposit_balance")), "DTBalance": usd_m(rc.get("deposit_timelock_balance")),
        "PendingLoanBalance": usd_m(rc.get("pending_loan_balance")),
        "AccruedLoanInterest": usd_m(rc.get("accrued_loan_interest"), 2),
        "BaseYieldAccrued": usd_m(rc.get("base_yield_accrued"), 2),
        "DepositPrice": num(rc.get("deposit_share_price"), 4), "RedemptionPrice": num(rc.get("redemption_share_price"), 4),
        "LoanBookGap": usd_m(abs(rc.get("loan_book_gap") or 0), 2),
        "LoanBookGapPct": pct(abs(rc.get("loan_book_gap") or 0) / (rc.get("pending_loan_balance") or 1), 2),
        "SharesGapPct": pct(abs(rc.get("shares_gap") or 0) / (rc.get("total_shares") or 1), 2),
        "DTShare": pct((rc.get("deposit_timelock_balance") or 0) / (rc.get("total_assets") or 1)),
        "SolanaShares": num(((res.get("solana") or {}).get("sUSDai") or {}).get("ui_amount", 0) / 1e6, 1) + "\\,M",
    })
    es = res.get("escrow", {})
    op = es.get("open", [])
    m.update({"EscrowDeposits": usd_m(es.get("deposits_total")), "NEscrow": num(es.get("n_deposits")),
              "NEscrowClosed": num(es.get("n_closed")), "NEscrowCancelled": num(es.get("n_cancelled")),
              "EscrowOpen": usd_m(sum(x["usd"] for x in op)), "NEscrowOpen": num(len(op)),
              "EscrowAPR": pct(max((x["apr"] for x in op), default=None), 1)})
    lp = res.get("livepeer", {})
    m.update({"LPUSD": usd_m(lp.get("usd_total"), 2), "LPETH": num(lp.get("eth_total"), 0),
              "LPTickets": num(lp.get("tickets")), "LPGateways": num(lp.get("gateways")),
              "LPOrchestrators": num(lp.get("orchestrators")), "LPTopGateway": pct(lp.get("top_gateway_share")),
              "LPTopThree": pct(lp.get("top3_gateway_share")), "LPHHIG": num(lp.get("hhi_gateways"), 3),
              "LPHHIO": num(lp.get("hhi_orchestrators"), 3)})
    ak = res.get("akash", {})
    mods = ak.get("models", {})
    m.update({"AKUSD": usd_m(ak.get("usd_window"), 2), "AKAllTime": usd_m(ak.get("usd_all_time"), 1),
              "AKGPUMin": num(ak.get("active_gpu_min")), "AKGPUMax": num(ak.get("active_gpu_max")),
              "AKGPUNow": num(ak.get("active_gpu_now")), "AKGPUTotal": num(ak.get("gpu_total_now")),
              "AKProviders": num(ak.get("providers_now")),
              "AKHundred": "\\$" + num((mods.get("h100-80Gi") or {}).get("price_med"), 2),
              "AKAHundred": "\\$" + num((mods.get("a100-80Gi") or {}).get("price_med"), 2),
              "CentralH": "\\$" + num(res.get("h100_central_last"), 2),
              "AKRetrieved": (ak.get("retrieved_at") or "n/a")[:10]})
    if (mods.get("h100-80Gi") or {}).get("price_med") and res.get("h100_central_last"):
        m["AKDiscount"] = pct(1 - mods["h100-80Gi"]["price_med"] / res["h100_central_last"])
    eh = res.get("eth_holder_history", {})
    ks = sorted(k for k, v in eh.items() if v.get("holders"))
    if ks:
        m.update({"EthHistFirst": ks[0], "EthHistLast": ks[-1], "EthHoldersFirst": num(eh[ks[0]]["holders"]),
                  "EthHoldersLast": num(eh[ks[-1]]["holders"]), "EthTopFirst": pct(eh[ks[0]]["top1"]),
                  "EthTopLast": pct(eh[ks[-1]]["top1"]),
                  "EthSupplyJune": num(eh.get("2026-06-01", {}).get("supply", 0) / 1e6, 1) + "\\,M",
                  "EthSupplyLast": num(eh[ks[-1]]["supply"] / 1e6, 1) + "\\,M"})
    real_compute = (ak.get("usd_window") or 0) + (lp.get("usd_total") or 0)
    m["ComputeSpend"] = usd_m(real_compute, 2)
    m["CreditMultiple"] = num(ln["originated"] / real_compute, 0) if real_compute else "n/a"
    st = res.get("activity_stats", {})
    m.update({"ActBorrowers": num(st.get("borrowers")), "BorrChainsMin": num(st.get("borrower_chains_min")),
              "BorrChainsMax": num(st.get("borrower_chains_max")), "BorrChainsMed": num(st.get("borrower_chains_median")),
              "ActHolders": num(st.get("holders")), "HoldChainsMin": num(st.get("holder_chains_min")),
              "HoldChainsMax": num(st.get("holder_chains_max")), "HoldChainsMed": num(st.get("holder_chains_median"))})
    eth_top = res["holders"]["top"].get("eth-mainnet:sUSDai", [])
    m["EthTopTwo"] = pct(sum(t["share"] for t in eth_top[:2]))
    m["EthMorpho"] = pct(next((t["share"] for t in eth_top if t["address"] == "0xbbbbbbbbbb9cc5e90e3b3af64bdaf62c37eeffcb"), None))
    bs = v.get("base_yield_sources", {})
    m["CashBasePYUSD"] = usd_m(bs.get("pyusd_harvest"), 2)
    m["CashBaseWM"] = usd_m(bs.get("wm"), 2)
    m["CashBaseOther"] = usd_m(bs.get("other", 0.0), 2)
    rr = res.get("usdai_pyusd_ratio_min") or {}
    m["USDaiRatioMin"] = num(rr.get("ratio"), 3)
    m["USDaiRatioMinDate"] = rr.get("date", "n/a")
    m["EscrowAccrued"] = usd_m(rc.get("escrow_interest_accrued"), 2)
    m["CrossChainMin"] = "100{,}000"
    m["VaultInterestShare"] = pct(ln["lender_interest"].get(R.SUSDAI, 0.0) / ln["interest_paid"] if ln["interest_paid"] else None)
    bh = res.get("book_health", {})
    my = bh.get("outstanding_by_maturity_year", {})
    m.update({"NActive": num(bh.get("active")), "TermMin": num((bh.get("term_days_min") or 0) / 365.25, 1),
              "TermMax": num((bh.get("term_days_max") or 0) / 365.25, 1),
              "YearsToMaturity": num(bh.get("weighted_years_to_maturity"), 1),
              "MatTwentyEight": usd_m(my.get("2028", 0.0)), "MatTwentyNine": usd_m(my.get("2029", 0.0)),
              "MaxDaysSincePayment": num(bh.get("max_days_since_payment")),
              "NLate": num(len(bh.get("late_over_45d", [])) + len(bh.get("never_paid_older_than_45d", []))),
              "KappaBorrowers": pct(v.get("cash_coverage_borrowers_only"))})
    ven = res["holders"]["venues"]
    m["PendleArb"] = pct(ven.get(f"{R.HUB}:sUSDai", {}).get("Pendle"))
    m["PendlePlasmaUSDai"] = pct(ven.get("plasma-mainnet:USDai", {}).get("Pendle"))
    m["VaultPlasmaUSDai"] = pct(ven.get("plasma-mainnet:USDai", {}).get("Vault/strategy"))
    st_ = res.get("stress", {})
    m.update({"TopOneOut": pct(st_.get("top1_outstanding_share")), "TopThreeOut": pct(st_.get("top3_outstanding_share")),
              "IdleOverPending": num(st_.get("idle_over_pending"), 0)})
    for row in st_.get("rows", []):
        tag = {"largest borrower": "One", "three largest borrowers": "Three", "every borrower": "All"}.get(row["who"])
        if tag and abs(row["recovery"] - 0.4) < 1e-9:
            m[f"Stress{tag}Loss"] = usd_m(row["loss"])
            m[f"Stress{tag}Pct"] = pct(row["loss_pct_assets"])
            m[f"Stress{tag}NAV"] = num(row["nav_after"], 3)
        if row["who"].startswith("every borrower, and"):
            m["StressWorstPct"] = pct(row["loss_pct_assets"])
            m["StressWorstNAV"] = num(row["nav_after"], 3)
    ic = res.get("implied_compute", {})
    by_p = {round(c["price"], 2): c for c in ic.get("curve", [])}
    m.update({"DebtService": usd_m(ic.get("annual_debt_service")), "DebtInterest": usd_m(ic.get("annual_interest")),
              "DebtAmort": usd_m(ic.get("annual_amortization")),
              "GPUsAkashPrice": num(by_p.get(2.56, {}).get("gpus")), "GPUhAkashPrice": num(by_p.get(2.56, {}).get("gpu_hours_per_year", 0) / 1e6, 1),
              "MWAkashPrice": num(by_p.get(2.56, {}).get("mw"), 1),
              "GPUsCentralPrice": num(by_p.get(3.36, {}).get("gpus")), "MWCentralPrice": num(by_p.get(3.36, {}).get("mw"), 1),
              "GPUsLowPrice": num(by_p.get(1.5, {}).get("gpus")), "MWLowPrice": num(by_p.get(1.5, {}).get("mw"), 1),
              "BridgedShare": pct((rc.get("bridged_supply") or 0) / (rc.get("total_shares") or 1))})
    co = res.get("collateral") or {}
    be = res.get("breakeven") or {}
    unp = co.get("unpledged") or []
    big = unp[0] if unp else {}
    m.update({"CollValue": usd_m(co.get("active_collateral_value")), "BookLTV": pct(co.get("book_ltv")),
              "LTVMin": pct(co.get("ltv_min"), 0), "LTVMax": pct(co.get("ltv_max"), 0),
              "CollUnits": num(co.get("active_units")), "CollGPUs": num(co.get("active_gpus")),
              "CollRecords": num(co.get("n_records")), "CollRetrieved": (co.get("retrieved_at") or "n/a")[:10],
              "UsefulLife": " and ".join(str(x) for x in co.get("useful_life_days", [])),
              "Breakeven": "\\$" + num(be.get("breakeven_price"), 2), "BreakevenFull": "\\$" + num(be.get("price_full_utilization"), 2),
              "MWPledged": num(be.get("mw_pledged"), 1),
              "UnpledgedValue": usd_m(co.get("unpledged_value")), "UnpledgedName": (big.get("name") or "n/a").replace("[", "(").replace("]", ")"),
              "UnpledgedUnits": num(big.get("units")), "UnpledgedPrior": usd_m((big.get("previously_secured") or {}).get("principal"))})
    li = ln["lender_interest"]
    m["InterestToVault"] = usd_m(li.get(R.SUSDAI, 0.0), 2)
    other = {k: val for k, val in li.items() if k != R.SUSDAI}
    m["InterestToOthers"] = usd_k(sum(other.values()))
    return m


def write_generated(res: dict, loans: dict, btab: list[dict], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    lines = ["% Generated by compute_forensics.paper. Do not edit by hand."]
    allm = macros(res)
    allm.update(write_verification(res.get("verification"), out))
    for k, v in allm.items():
        lines.append(f"\\newcommand{{\\{k}}}{{{v}}}")
    (out / "numbers.tex").write_text("\n".join(lines) + "\n")

    # Borrower table
    rows = ["\\begin{tabular}{@{}lrrrr@{}}", "\\toprule",
            "Borrower & Loans & Originated & Outstanding & Interest paid \\\\", "\\midrule"]
    for r in btab:
        rows.append(f"{short(r['borrower'])} & {r['loans']} & {usd_m(r['originated'], 2)} & "
                    f"{usd_m(r['outstanding'], 2)} & {usd_k(r['interest'])} \\\\")
    rows += ["\\bottomrule", "\\end{tabular}"]
    (out / "tab_borrowers.tex").write_text("\n".join(rows) + "\n")

    # Holders table (sUSDai, all chains)
    rows = ["\\begin{tabular}{@{}lrrrrr@{}}", "\\toprule",
            "Chain & Holders & Supply & Top-1 & Top-10 & HHI \\\\", "\\midrule"]
    for key, c in res["holders"]["concentration"].items():
        ch, sym = key.split(":")
        if sym != "sUSDai" or not c.get("holders"):
            continue
        rows.append(f"{ {'eth': 'Ethereum'}.get(ch.split('-')[0], ch.split('-')[0].capitalize()) } & {c['holders']:,} & {c['total'] / 1e6:,.1f}\\,M & "
                    f"{pct(c['top1'])} & {pct(c['top10'])} & {c['hhi']:.3f} \\\\")
    rows += ["\\bottomrule", "\\end{tabular}"]
    (out / "tab_holders.tex").write_text("\n".join(rows) + "\n")

    # Top holders on the hub
    rows = ["\\begin{tabular}{@{}lrrl@{}}", "\\toprule", "Holder & sUSDai & Share & Label \\\\", "\\midrule"]
    for t in res["holders"]["top"].get(f"{R.HUB}:sUSDai", [])[:8]:
        nm = (t["names"][0] if t["names"] else t["label"]).replace("_", "\\_").replace("&", "\\&")[:28]
        rows.append(f"{short(t['address'])} & {t['balance'] / 1e6:,.2f}\\,M & {pct(t['share'])} & {nm} \\\\")
    rows += ["\\bottomrule", "\\end{tabular}"]
    (out / "tab_topholders.tex").write_text("\n".join(rows) + "\n")
    write_extra_tables(res, out)
    write_usdai_table(res, out)
    write_stress_table(res, out)
    write_collateral_table(res, out)


ROLE = {
    R.SUSDAI: "sUSDai vault", R.USDAI: "USDai contract",
    "0x844bb7b6223f6af028189bb34d6341a5733d6286": "escrow facility",
    "0x11687ca5235d669e8d52d7946b1605826cf521b1": "PYUSD hub",
    "0xf845a0a05cbd91ac15c3e59d126de5dfbc2aabb7": "off-ramp A",
    "0x264bd8291fae1d75db2c5f573b07faa6715997b5": "service wallet B",
    "0x5f0bc72fb5952b2f3f2e11404398ed507b25841f": "fee recipient",
    "0x64447901dc34bd610ac562b2c612784a9954d39d": "borrower 1",
    "0x034d28a39c5c48aaca4d87e7775fe202f6cbfc6b": "multisig submitter",
}


def _who(a: str) -> str:
    return f"{ROLE[a]} ({short(a)})" if a in ROLE else short(a)


def write_extra_tables(res: dict, out: Path) -> None:
    es = res.get("escrow", {})
    flows = es.get("flows", {})
    rows = ["\\begin{tabular}{@{}llr@{}}", "\\toprule", "From $\\rightarrow$ To & Asset & USD \\\\", "\\midrule"]
    picks = []
    for a, f in flows.items():
        for sym, b, v in f["out"]:
            if v >= 1e6 and a != b:
                picks.append((a, b, sym, v))
    vault_in = sum(v for sym, b, v in flows.get("0x844bb7b6223f6af028189bb34d6341a5733d6286", {}).get("in", [])
                   if b == R.SUSDAI)
    rows.append(f"{_who(R.SUSDAI)} $\\rightarrow$ escrow facility & USDai & {usd_m(vault_in)} \\\\")
    for a, b, sym, v in sorted(picks, key=lambda x: -x[3])[:9]:
        sym = "PYUSD (redeemed)" if "redemption" in sym else sym
        rows.append(f"{_who(a)} $\\rightarrow$ {_who(b)} & {sym} & {usd_m(v)} \\\\")
    rows += ["\\bottomrule", "\\end{tabular}"]
    (out / "tab_escrow.tex").write_text("\n".join(rows) + "\n")

    ln, lp, ak = res["loans"], res.get("livepeer", {}), res.get("akash", {})
    rows = ["\\begin{tabular}{@{}lrrr@{}}", "\\toprule",
            "Metric (study window) & USD.AI & Akash & Livepeer \\\\", "\\midrule",
            f"USD volume & {usd_m(ln['originated'])} lent & {usd_m(ak.get('usd_window'), 2)} spent & "
            f"{usd_m(lp.get('usd_total'), 2)} paid \\\\",
            f"Revenue to capital/providers & {usd_m(ln['interest_paid'], 2)} interest & {usd_m(ak.get('usd_window'), 2)} & "
            f"{usd_m(lp.get('usd_total'), 2)} \\\\",
            f"Demand-side counterparties & {ln['borrowers']} borrowers & n/a & {lp.get('gateways', 'n/a')} gateways \\\\",
            f"Supply-side counterparties & {len(ln['lender_interest'])} tranche lenders & {ak.get('providers_now', 'n/a')} providers & "
            f"{lp.get('orchestrators', 'n/a')} orchestrators \\\\",
            f"Top-1 share & {pct(ln['top1_share'])} & n/a & {pct(lp.get('top_gateway_share'))} \\\\",
            "Data source & GoldRush (Arbitrum) & Akash Console API & GoldRush (Arbitrum) \\\\",
            "\\bottomrule", "\\end{tabular}"]
    (out / "tab_markets.tex").write_text("\n".join(rows) + "\n")


def write_collateral_table(res: dict, out: Path) -> None:
    co = res.get("collateral") or {}
    rows = ["\\begin{tabular}{@{}llrrrr@{}}", "\\toprule",
            "Borrower & Hardware (units) & GPUs & Stated value & Outstanding & LTV \\\\", "\\midrule"]
    act = sorted((r for r in co.get("per_loan", []) if r["status"] == "active" and r["collateral_value"]),
                 key=lambda r: -r["outstanding"])
    for r in act[:13]:
        hw = "/".join(x for x in r["models"] if x != "other") or "mixed"
        rows.append(f"{short(r['borrower'])} & {hw} ({r['units']}) & {num(r['gpus']) if r['gpus'] else 'n/a'} & "
                    f"{usd_m(r['collateral_value'])} & {usd_m(r['outstanding'])} & {pct(r['ltv'], 0)} \\\\")
    if len(act) > 13:
        rest = act[13:]
        rows.append(f"{len(rest)} smaller loans & mixed ({sum(r['units'] for r in rest)}) & n/a & "
                    f"{usd_m(sum(r['collateral_value'] for r in rest), 2)} & {usd_m(sum(r['outstanding'] for r in rest), 2)} & "
                    f"{pct(sum(r['outstanding'] for r in rest) / max(sum(r['collateral_value'] for r in rest), 1), 0)} \\\\")
    rows += ["\\midrule", f"All active & ({co.get('active_units', 0)}) & {num(co.get('active_gpus'))} & "
             f"{usd_m(co.get('active_collateral_value'))} & {usd_m(co.get('active_outstanding_with_collateral'))} & "
             f"{pct(co.get('book_ltv'), 0)} \\\\", "\\bottomrule", "\\end{tabular}"]
    (out / "tab_collateral.tex").write_text("\n".join(rows) + "\n")


def write_stress_table(res: dict, out: Path) -> None:
    rows = ["\\begin{tabular}{@{}llrrr@{}}", "\\toprule",
            "Defaults & Recovery & Loss & Share of assets & NAV after \\\\", "\\midrule"]
    for r in res.get("stress", {}).get("rows", []):
        who = r["who"].replace("every borrower, and the open escrow is not returned", "every borrower; escrow not returned")
        rows.append(f"{who} & {100 * r['recovery']:.0f}\\% & {usd_m(r['loss'])} & {pct(r['loss_pct_assets'])} & "
                    f"{r['nav_after']:.3f} \\\\")
    rows += ["\\bottomrule", "\\end{tabular}"]
    (out / "tab_stress.tex").write_text("\n".join(rows) + "\n")


def write_usdai_table(res: dict, out: Path) -> None:
    rows = ["\\begin{tabular}{@{}lrr@{}}", "\\toprule", "Backing asset & Minted & Redeemed \\\\", "\\midrule"]
    names = {R.PYUSD_ARB: "PYUSD", R.USDC_ARB: "USDC", "0x437cc33344a0b27a429f795ff6b469c72698b291": "wM (M\\textsuperscript{0})",
             "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": "USDT"}
    for a, v in sorted(res["usdai"]["by_token"].items(), key=lambda kv: -kv[1]["mint_usd"]):
        if v["mint_usd"] < 1 and v["burn_usd"] < 1:
            continue
        sym = names.get(a, short(a))
        rows.append(f"{sym} & {usd_m(v['mint_usd'], 2)} & {usd_m(v['burn_usd'], 2)} \\\\")
    rows += ["\\midrule", f"Total & {usd_m(res['usdai']['minted'])} & {usd_m(res['usdai']['burned'])} \\\\",
             "\\bottomrule", "\\end{tabular}"]
    (out / "tab_usdai.tex").write_text("\n".join(rows) + "\n")


def write_verification(ver: dict | None, out: Path) -> dict[str, str]:
    """Table of GoldRush-vs-chain checks, plus macros. Returns the macros."""
    if not ver:
        (out / "tab_verify.tex").write_text("% no verification run\n")
        return {"NVerify": "0", "NVerifyMatch": "0"}
    rows = ["\\begin{tabular}{@{}lrrc@{}}", "\\toprule", "Event (Arbitrum) & RPC logs & GoldRush logs & Same \\\\",
            "\\midrule"]
    for r in ver["event_checks"]:
        ok = "yes" if r["match"] else f"{r['only_rpc']} missing"
        rows.append(f"{r['check']} & {r['rpc_count']:,} & {r['goldrush_count']:,} & {ok} \\\\")
    rows += ["\\midrule", "\\multicolumn{4}{@{}l}{\\emph{sUSDai supply: \\texttt{totalSupply} vs.\\ sum of GoldRush holders}} \\\\"]
    for s in ver["supply_checks"]:
        if s["rpc_total_supply"] is None:
            continue
        at = "same block" if s["rpc_block"] not in (None, "latest") else "latest block"
        nm = {'eth': 'Ethereum'}.get(s['chain'].split('-')[0], s['chain'].split('-')[0].capitalize())
        rows.append(f"{nm} ({at}) & {s['rpc_total_supply'] / 1e6:,.2f}\\,M & "
                    f"{s['goldrush_holder_sum'] / 1e6:,.2f}\\,M & {s['diff_pct']:+.2f}\\% \\\\")
    rows += ["\\bottomrule", "\\end{tabular}"]
    (out / "tab_verify.tex").write_text("\n".join(rows) + "\n")
    ev = ver["event_checks"]
    lp = next((r for r in ev if r["check"].startswith("Livepeer")), {})
    bk = ver.get("usdai_backing") or {}
    sup = (bk.get("usdai_hub_supply") or 0) + sum((bk.get("usdai_spoke_supply") or {}).values())
    resv = sum((bk.get("reserves_at_usdai_contract") or {}).values())
    return {"NVerify": str(len(ev)), "NVerifyMatch": str(sum(r["match"] for r in ev)),
            "BackingBlock": num(bk.get("block")), "USDaiSupplyNow": usd_m(sup), "USDaiReserves": usd_m(resv),
            "USDaiPYUSD": usd_m((bk.get("reserves_at_usdai_contract") or {}).get("PYUSD")),
            "USDaiCoverage": pct(bk.get("coverage"), 2),
            "NVerifyLogs": f"{sum(r['rpc_count'] for r in ev):,}",
            "LPMissing": str(lp.get("only_rpc", 0)),
            "LPMissingETH": f"{sum(x['eth'] for x in lp.get('missing_from_goldrush', [])):.4f}"}
