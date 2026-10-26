"""Loan book reconstruction (RQ1, RQ2, RQ4).

A GPU loan can change identity over its life: V1 loans were migrated to V2 on
2026-06-26..07-03 (LoanMigrated) and V2 loans can be refinanced (LoanRefinanced).
Each event carries the old and new `loanTermsHash`; we stitch every hash back to
the root origination so repayments are never orphaned or double counted.
Migrated loans name a per-borrower reserve account as the new "borrower"; the
ReserveAccountFactory event maps it back to the underlying borrower.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from . import registry as R
from .abi import decode_loan_terms_v2
from .events import Ev

SECONDS_PER_YEAR = 365 * 86400
SYMBOL = {R.PYUSD_ARB: "PYUSD", R.USDC_ARB: "USDC", R.USDAI: "USDai"}


def _units(token: str) -> int:
    return 10 ** R.DECIMALS.get(token, 18)


def apr_from_rate(rate: int) -> float:
    """V2 tranche rates are per-second, 1e18-scaled (InterestRateModel convention)."""
    return rate * SECONDS_PER_YEAR / 1e18


@dataclass
class Loan:
    root: str
    version: int
    originated: str
    origin_tx: str
    borrower: str                 # underlying borrower (reserve accounts mapped back)
    currency: str
    principal: float              # at origination, token units ~ USD
    origination_fee: float = 0.0
    current_hash: str = ""
    current_principal: float = 0.0
    principal_repaid: float = 0.0
    principal_repaid_current: float = 0.0
    interest_paid: float = 0.0
    fees_paid: float = 0.0
    payments: int = 0
    status: str = "active"
    lenders: set = field(default_factory=set)
    susdai_share: float | None = None          # share of principal funded by sUSDai (V2 terms)
    rate_apr: float | None = None              # principal-weighted tranche APR (V2 terms)
    duration_days: int | None = None
    collateral_items: int | None = None
    hashes: list = field(default_factory=list)
    reserve_accounts: set = field(default_factory=set)
    first_payment: str | None = None
    last_payment: str | None = None

    @property
    def outstanding(self) -> float:
        if self.status in ("repaid",):
            return 0.0
        return max(self.current_principal - self.principal_repaid_current, 0.0)


def _apply_terms(loan: Loan, terms: dict) -> None:
    unit = _units(terms["currency_token"])
    tr = terms["tranches"]
    total = sum(x["amount"] for x in tr)
    loan.current_principal = total / unit
    loan.principal_repaid_current = 0.0
    loan.susdai_share = (sum(x["amount"] for x in tr if x["lender"] == R.SUSDAI) / total) if total else None
    loan.rate_apr = (sum(apr_from_rate(x["rate"]) * x["amount"] for x in tr) / total) if total else None
    loan.duration_days = terms["repayment"]["total_duration_days"]
    loan.collateral_items = len(terms["collateral_token_ids"])
    loan.lenders |= {x["lender"] for x in tr}


def build_loans(events: list[Ev]) -> tuple[dict[str, Loan], dict]:
    reserve_to_borrower = {e.f["reserve_account"]: e.f["borrower"] for e in events
                           if e.name == "RAF.ReserveAccountCreated"}
    loans: dict[str, Loan] = {}
    hash_root: dict[str, str] = {}
    hash_ccy: dict[str, str] = {}          # currency token of each terms hash (V1 PYUSD/USDC, V2 USDai...)
    lender_interest = defaultdict(float)     # lender -> interest received (USD)
    lender_principal = defaultdict(float)
    fees_by_kind = defaultdict(float)
    monthly = defaultdict(lambda: defaultdict(float))
    stray = 0

    def borrower_of(addr: str, loan: Loan | None = None) -> str:
        if addr in reserve_to_borrower:
            if loan is not None:
                loan.reserve_accounts.add(addr)
            return reserve_to_borrower[addr]
        return addr

    for e in events:
        n, f = e.name, e.f
        if n == "LR1.LoanOriginated":
            unit = _units(f["currency_token"])
            ln = Loan(f["loan_terms_hash"], 1, e.time, e.tx, borrower_of(f["borrower"]), f["currency_token"],
                      f["principal"] / unit, f["origination_fee"] / unit)
            ln.current_hash, ln.current_principal = ln.root, ln.principal
            ln.hashes.append(ln.root)
            loans[ln.root] = ln
            hash_root[ln.root] = ln.root
            hash_ccy[ln.root] = f["currency_token"]
        elif n == "LR2.LoanOriginated":
            terms = decode_loan_terms_v2(f["loan_terms"])
            ln = Loan(f["loan_terms_hash"], 2, e.time, e.tx, "", terms["currency_token"], 0.0)
            ln.borrower = borrower_of(terms["borrower"], ln)
            _apply_terms(ln, terms)
            ln.principal = ln.current_principal
            ln.current_hash = ln.root
            ln.hashes.append(ln.root)
            loans[ln.root] = ln
            hash_root[ln.root] = ln.root
            hash_ccy[ln.root] = terms["currency_token"]
        elif n in ("LR2.LoanMigrated", "LR2.LoanRefinanced", "LR2.LoanRefinanced3"):
            root = hash_root.get(f["old_loan_terms_hash"])
            if root is None:
                stray += 1
                continue
            ln = loans[root]
            terms = decode_loan_terms_v2(f["new_loan_terms"])
            borrower_of(terms["borrower"], ln)
            _apply_terms(ln, terms)
            ln.version = 2
            ln.current_hash = f["new_loan_terms_hash"]
            ln.hashes.append(ln.current_hash)
            hash_root[ln.current_hash] = root
            hash_ccy[ln.current_hash] = terms["currency_token"]
        elif n in ("LR.LoanRepaid",):
            root = hash_root.get(f["loan_terms_hash"])
            if root is None:
                stray += 1
                continue
            ln = loans[root]
            unit = _units(hash_ccy[f["loan_terms_hash"]])
            p, i, pre, fee = (f["principal"] / unit, f["interest"] / unit, f["prepayment"] / unit, f["fee"] / unit)
            ln.principal_repaid += p + pre
            if f["loan_terms_hash"] == ln.current_hash:
                ln.principal_repaid_current += p + pre
            ln.interest_paid += i
            ln.fees_paid += fee
            ln.payments += 1
            ln.first_payment = ln.first_payment or e.time
            ln.last_payment = e.time
            if f["is_repaid"] and f["loan_terms_hash"] == ln.current_hash:
                ln.status = "repaid"
            m = e.time[:7]
            monthly[m]["interest"] += i
            monthly[m]["principal"] += p + pre
        elif n == "LR.LenderRepaid":
            root = hash_root.get(f["loan_terms_hash"])
            if root is None:
                continue
            ln = loans[root]
            unit = _units(hash_ccy[f["loan_terms_hash"]])
            lender_interest[f["lender"]] += f["interest"] / unit
            lender_principal[f["lender"]] += (f["principal"] + f["prepay"]) / unit
            if f["lender"] == R.SUSDAI:
                monthly[e.time[:7]]["interest_to_susdai"] += f["interest"] / unit
        elif n == "LR.LenderPositionMinted":
            root = hash_root.get(f["loan_terms_hash"])
            if root:
                loans[root].lenders.add(f["lender"])
        elif n in ("LR.LoanBreached", "LR.LoanLiquidated"):
            root = hash_root.get(f["loan_terms_hash"])
            if root:
                loans[root].status = n.split(".")[1].replace("Loan", "").lower()
        elif n == "LR2.FeePaid":
            ccy = hash_ccy.get(f["loan_terms_hash"], R.USDAI)
            fees_by_kind[int(f["kind"])] += f["amount"] / _units(ccy)
    meta = {"hash_ccy": hash_ccy, "reserve_accounts": reserve_to_borrower, "lender_interest": dict(lender_interest),
            "lender_principal": dict(lender_principal), "fees_by_kind": dict(fees_by_kind),
            "monthly": {k: dict(v) for k, v in sorted(monthly.items())}, "stray_events": stray}
    return loans, meta


def is_test_loan(ln: Loan, min_principal: float = 1_000.0) -> bool:
    return ln.principal < min_principal


def hhi(values: list[float]) -> float:
    tot = sum(values)
    return sum((v / tot) ** 2 for v in values) if tot else 0.0


def borrower_table(loans: dict[str, Loan]) -> list[dict]:
    agg = defaultdict(lambda: {"loans": 0, "originated": 0.0, "outstanding": 0.0, "interest": 0.0,
                               "first": None, "statuses": set()})
    for ln in loans.values():
        if is_test_loan(ln):
            continue
        a = agg[ln.borrower]
        a["loans"] += 1
        a["originated"] += ln.principal
        a["outstanding"] += ln.outstanding
        a["interest"] += ln.interest_paid
        a["first"] = min(a["first"] or ln.originated, ln.originated)
        a["statuses"].add(ln.status)
    rows = [{"borrower": b, **{k: (sorted(v) if isinstance(v, set) else v) for k, v in a.items()}}
            for b, a in agg.items()]
    return sorted(rows, key=lambda r: -r["originated"])
