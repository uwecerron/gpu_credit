"""Event definitions taken verbatim from the audited source repositories, plus
decoding of raw logs. GoldRush returns decoded logs only for ABIs it knows; we
decode everything ourselves from `raw_log_topics` / `raw_log_data` so results do
not depend on third-party ABI coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from Crypto.Hash import keccak
from eth_abi import decode as abi_decode


def topic0(signature: str) -> str:
    k = keccak.new(digest_bits=256)
    k.update(signature.encode())
    return "0x" + k.hexdigest()


@dataclass(frozen=True)
class Event:
    name: str            # unique key used in this codebase
    signature: str       # canonical Solidity signature
    indexed: tuple       # types of topics[1:]
    data: tuple          # types ABI-encoded in data
    fields: tuple        # names, indexed first then data, in order

    @property
    def topic(self) -> str:
        return topic0(self.signature)


LOAN_TERMS_V2 = ("(uint64,address,address,address,(uint16,uint8,int32),(address,bytes),"
                 "uint256[],(address,uint256,uint256)[],(uint8,address,address,bytes)[],address[],bytes)")

EVENTS = [
    # USDai (IUSDai.sol)
    Event("USDai.Deposited", "Deposited(address,address,address,uint256,uint256)",
          ("address", "address"), ("address", "uint256", "uint256"),
          ("caller", "recipient", "deposit_token", "deposit_amount", "mint_amount")),
    Event("USDai.Withdrawn", "Withdrawn(address,address,address,uint256,uint256)",
          ("address", "address"), ("address", "uint256", "uint256"),
          ("caller", "recipient", "withdraw_token", "usdai_amount", "withdraw_amount")),
    Event("USDai.Harvested", "Harvested(uint256)", (), ("uint256",), ("usdai_amount",)),
    # sUSDai (IERC7575 / IERC7540 / IStakedUSDai / position managers)
    Event("sUSDai.Deposit", "Deposit(address,address,uint256,uint256)",
          ("address", "address"), ("uint256", "uint256"), ("sender", "owner", "assets", "shares")),
    Event("sUSDai.Withdraw", "Withdraw(address,address,address,uint256,uint256)",
          ("address", "address", "address"), ("uint256", "uint256"),
          ("sender", "receiver", "owner", "assets", "shares")),
    Event("sUSDai.RedeemRequest", "RedeemRequest(address,address,uint256,address,uint256)",
          ("address", "address", "uint256"), ("address", "uint256"),
          ("controller", "owner", "request_id", "sender", "shares")),
    Event("sUSDai.RedemptionProcessed", "RedemptionProcessed(uint256,address,uint256,uint256,uint256)",
          ("uint256", "address"), ("uint256", "uint256", "uint256"),
          ("redemption_id", "controller", "fulfilled_shares", "amount", "pending_shares")),
    Event("sUSDai.RedemptionsServiced", "RedemptionsServiced(uint256,uint256,bool)",
          (), ("uint256", "uint256", "bool"), ("shares", "amount", "all_serviced")),
    Event("sUSDai.BaseYieldDeposited", "BaseYieldDeposited(uint256,uint256)",
          (), ("uint256", "uint256"), ("deposited_amount", "admin_fee")),
    Event("sUSDai.LoanTimelockDeposited", "LoanTimelockDeposited(bytes32,uint256,uint64)",
          ("bytes32",), ("uint256", "uint64"), ("loan_terms_hash", "usdai_amount", "expiration")),
    Event("sUSDai.LoanTimelockCancelled", "LoanTimelockCancelled(bytes32,uint256)",
          ("bytes32",), ("uint256",), ("loan_terms_hash", "usdai_amount")),
    Event("sUSDai.LoanDepositTimelockDeposited", "LoanDepositTimelockDeposited(bytes32,uint256,uint64)",
          ("bytes32",), ("uint256", "uint64"), ("loan_terms_hash", "usdai_amount", "expiration")),
    Event("sUSDai.LoanDepositTimelockCancelled", "LoanDepositTimelockCancelled(bytes32,uint256)",
          ("bytes32",), ("uint256",), ("loan_terms_hash", "usdai_amount")),
    Event("sUSDai.LoanEscrowTimelockDeposited", "LoanEscrowTimelockDeposited(bytes32,uint256,uint256)",
          ("bytes32",), ("uint256", "uint256"), ("loan_terms_hash", "usdai_amount", "interest_rate")),
    Event("sUSDai.LoanEscrowTimelockWithdrawn", "LoanEscrowTimelockWithdrawn(bytes32,uint256)",
          ("bytes32",), ("uint256",), ("loan_terms_hash", "interest_amount")),
    Event("sUSDai.LoanEscrowTimelockCancelled", "LoanEscrowTimelockCancelled(bytes32,uint256,uint256)",
          ("bytes32",), ("uint256", "uint256"), ("loan_terms_hash", "usdai_amount", "interest_amount")),
    # Loan router V1 (ILoanRouter.sol at commit before 43dd6d5)
    Event("LR1.LoanOriginated", "LoanOriginated(bytes32,address,address,uint256,uint256)",
          ("bytes32", "address", "address"), ("uint256", "uint256"),
          ("loan_terms_hash", "borrower", "currency_token", "principal", "origination_fee")),
    Event("LR1.LoanRepaid", "LoanRepaid(bytes32,address,uint256,uint256,uint256,uint256,bool)",
          ("bytes32", "address"), ("uint256", "uint256", "uint256", "uint256", "bool"),
          ("loan_terms_hash", "borrower", "principal", "interest", "prepayment", "fee", "is_repaid")),
    Event("LR1.LoanCollateralLiquidated", "LoanCollateralLiquidated(bytes32,uint256,uint256,uint256)",
          ("bytes32",), ("uint256", "uint256", "uint256"), ("loan_terms_hash", "proceeds", "fee", "surplus")),
    # Loan router V2 (ILoanRouterV2.sol)
    Event("LR2.LoanOriginated", "LoanOriginated(bytes32,bytes)", ("bytes32",), ("bytes",),
          ("loan_terms_hash", "loan_terms")),
    Event("LR2.LoanRefinanced", "LoanRefinanced(bytes32,bytes32,bytes,uint256,uint256,uint256)",
          ("bytes32", "bytes32"), ("bytes", "uint256", "uint256", "uint256"),
          ("old_loan_terms_hash", "new_loan_terms_hash", "new_loan_terms", "cash_out", "cash_in", "refinance_fee")),
    Event("LR2.LoanRefinanced3", "LoanRefinanced(bytes32,bytes32,bytes)", ("bytes32", "bytes32"), ("bytes",),
          ("old_loan_terms_hash", "new_loan_terms_hash", "new_loan_terms")),   # early V2 variant (devel branch)
    Event("LR2.LoanMigrated", "LoanMigrated(bytes32,bytes32,bytes)", ("bytes32", "bytes32"), ("bytes",),
          ("old_loan_terms_hash", "new_loan_terms_hash", "new_loan_terms")),
    Event("LR2.LiquidationProceedsDeposited", "LiquidationProceedsDeposited(bytes32,uint256,uint256,uint256)",
          ("bytes32",), ("uint256", "uint256", "uint256"), ("loan_terms_hash", "proceeds", "fee", "surplus")),
    Event("LR2.FeePaid", "FeePaid(bytes32,uint8,address,address,uint256)",
          ("bytes32", "uint8", "address"), ("address", "uint256"),
          ("loan_terms_hash", "kind", "recipient", "fee_model", "amount")),
    # Shared V1/V2
    Event("LR.LoanRepaid", "LoanRepaid(bytes32,address,uint256,uint256,uint256,uint256,bool)",
          ("bytes32", "address"), ("uint256", "uint256", "uint256", "uint256", "bool"),
          ("loan_terms_hash", "borrower", "principal", "interest", "prepayment", "fee", "is_repaid")),
    Event("LR.LenderPositionMinted", "LenderPositionMinted(bytes32,address,uint8,uint256)",
          ("bytes32", "address", "uint8"), ("uint256",), ("loan_terms_hash", "lender", "tranche", "token_id")),
    Event("LR.LenderRepaid", "LenderRepaid(bytes32,address,uint8,uint256,uint256,uint256)",
          ("bytes32", "address", "uint8"), ("uint256", "uint256", "uint256"),
          ("loan_terms_hash", "lender", "tranche", "principal", "interest", "prepay")),
    Event("LR.LenderLiquidationRepaid", "LenderLiquidationRepaid(bytes32,address,uint8,uint256,uint256)",
          ("bytes32", "address", "uint8"), ("uint256", "uint256"),
          ("loan_terms_hash", "lender", "tranche", "principal", "interest")),
    Event("LR.LoanLiquidated", "LoanLiquidated(bytes32)", ("bytes32",), (), ("loan_terms_hash",)),
    Event("LR.LoanBreached", "LoanBreached(bytes32)", ("bytes32",), (), ("loan_terms_hash",)),
    # Reserve accounts
    Event("RAF.ReserveAccountCreated", "ReserveAccountCreated(address,address)", ("address", "address"), (),
          ("reserve_account", "borrower")),
    # Base yield escrow
    Event("BYE.Deposited", "Deposited(address,uint256)", ("address",), ("uint256",), ("caller", "amount")),
    Event("BYE.Withdrawn", "Withdrawn(address,uint256)", ("address",), ("uint256",), ("caller", "amount")),
    Event("BYE.Harvested", "Harvested(address,uint256)", ("address",), ("uint256",), ("caller", "amount")),
    # ERC-20
    Event("ERC20.Transfer", "Transfer(address,address,uint256)", ("address", "address"), ("uint256",),
          ("from", "to", "value")),
]

# Duplicate signatures (V1 vs shared LoanRepaid) resolve to the shared name.
_BY_TOPIC: dict[str, Event] = {}
for _e in EVENTS:
    _BY_TOPIC.setdefault(_e.topic, _e)
    if _e.name.startswith("LR."):
        _BY_TOPIC[_e.topic] = _e

BY_NAME = {e.name: e for e in EVENTS}


def _hex(b: str) -> bytes:
    return bytes.fromhex(b[2:] if b.startswith("0x") else b)


def _norm(v):
    if isinstance(v, bytes):
        return "0x" + v.hex()
    if isinstance(v, str) and v.startswith("0x"):
        return v.lower()
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    return v


def decode_log(topics: list[str], data: str | None, only: set[str] | None = None) -> tuple[str, dict] | None:
    """Return (event_name, fields) or None if the log is not one of ours.
    ERC-721 Transfer (tokenId indexed, 4 topics) is rejected by arity."""
    if not topics:
        return None
    ev = _BY_TOPIC.get(topics[0].lower())
    if ev is None or (only and ev.name not in only):
        return None
    if len(topics) - 1 != len(ev.indexed):
        return None
    try:
        idx = [abi_decode([t], _hex(x))[0] for t, x in zip(ev.indexed, topics[1:])]
        dat = list(abi_decode(list(ev.data), _hex(data or "0x"))) if ev.data else []
    except Exception:
        return None
    return ev.name, dict(zip(ev.fields, [_norm(v) for v in idx + dat]))


@lru_cache(maxsize=None)
def _lt2_type():
    return [LOAN_TERMS_V2]


def decode_loan_terms_v2(blob: str) -> dict:
    """Decode the LoanTermsV2 struct carried in V2 LoanOriginated / LoanRefinanced."""
    t = abi_decode(_lt2_type(), _hex(blob))[0]
    return {
        "expiration": t[0], "borrower": t[1].lower(), "currency_token": t[2].lower(),
        "collateral_token": t[3].lower(),
        "repayment": {"total_duration_days": t[4][0], "day": t[4][1], "tz_offset_s": t[4][2]},
        "interest_rate_model": t[5][0].lower(),
        "collateral_token_ids": [str(x) for x in t[6]],
        "tranches": [{"lender": x[0].lower(), "amount": x[1], "rate": x[2]} for x in t[7]],
        "fees": [{"kind": x[0], "recipient": x[1].lower(), "model": x[2].lower()} for x in t[8]],
    }
