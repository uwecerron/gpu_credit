"""Contract registry for the USD.AI protocol.

Sources (retrieved 2026-10-22):
  [D] https://docs.usd.ai/technical-overview/contract-addresses
  [R1] github.com/metastreet-labs/usdai-contracts            deployments/*.json
  [R2] github.com/metastreet-labs/usdai-loan-router-contracts deployments/arbitrum.json
Addresses are lower-cased. Every analysis keys on these constants, so a reader
can audit exactly which contracts were measured.
"""
from __future__ import annotations

HUB = "arbitrum-mainnet"
SPOKES = ("eth-mainnet", "base-mainnet", "plasma-mainnet")

USDAI = "0x0a1a1a107e45b7ced86833863f482bc5f4ed82ef"       # [D][R1] same address on every EVM chain (OFT)
SUSDAI = "0x0b2b2b2076d95dda7817e785989fe353fe955ef9"      # [D][R1] ERC-4626 deposit / ERC-7540 redeem vault
CHIP = "0x0c1c1c109fe34733fca54b82d7b46b75cfb71f6e"        # [D] governance token
PYUSD_ARB = "0x46850ad61c2b7d64d08c9c754f45254596696984"   # observed as USDai deposit/loan currency token
USDC_ARB = "0xaf88d065e77c8cc2239327c5edb3a432268e5831"

# Loan stack. V1 per [D]; V2 per [R2] (deployed 2026-06-26).
LOAN_ROUTER_V1 = "0x0c2ed170f2bb1df1a44292ad621b577b3c9597d1"
DEPOSIT_TIMELOCK_V1 = "0x0d710cc05f34d2ead9fba3c78d53d76a0623c9f8"
LOAN_ROUTER_V2 = "0x1c2ed170de32846316784c4fd58a5e3c7563e12f"
DEPOSIT_TIMELOCK_V2 = "0x1d710cc0c435ba6e27abc82a51dfbca17c41fe3c"
ESCROW_TIMELOCK = "0x1e710cc0b64e1d7572d35e43ad261587789b6438"
COLLATERAL_TIMELOCK = "0x1c710cc0f5562752e88f5a5cc36fa72e73dbea45"
RESERVE_ACCOUNT_FACTORY = "0x12fac720abea21e2954d89c84e1274adb9c3e75c"
BUNDLE_COLLATERAL_WRAPPER = "0x80e3146fb2328fe1b79f92f5a3a6bf35515aee37"
BASE_YIELD_ESCROW = "0x9ddfd49ac4689cf894203794d792dcb38e4b1a9e"

# LayerZero adapters on the hub ([D]); bridged supply on spokes is minted by these.
USDAI_OADAPTER = "0xffa10065ce1d1c42fabc46e06b84ed8ffeb4bae5"
SUSDAI_OADAPTER = "0xffb20098fd7b8e84762eea4609f299d101427f24"

PROTOCOL_CONTRACTS = {
    "LoanRouterV1": LOAN_ROUTER_V1,
    "DepositTimelockV1": DEPOSIT_TIMELOCK_V1,
    "LoanRouterV2": LOAN_ROUTER_V2,
    "DepositTimelockV2": DEPOSIT_TIMELOCK_V2,
    "EscrowTimelock": ESCROW_TIMELOCK,
    "CollateralTimelock": COLLATERAL_TIMELOCK,
    "ReserveAccountFactory": RESERVE_ACCOUNT_FACTORY,
    "BundleCollateralWrapper": BUNDLE_COLLATERAL_WRAPPER,
    "BaseYieldEscrow": BASE_YIELD_ESCROW,
}

PROTOCOL_ADDRESSES = set(PROTOCOL_CONTRACTS.values()) | {USDAI, SUSDAI, USDAI_OADAPTER, SUSDAI_OADAPTER}

DECIMALS = {USDAI: 18, SUSDAI: 18, PYUSD_ARB: 6, USDC_ARB: 6}

# Arbitrum block bounds for the study window (from GoldRush block_v2 by date).
GENESIS_BLOCK = 335_730_936      # 2025-05-12 00:00 UTC
STUDY_END_DATE = "2026-10-22"
