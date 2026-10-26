"""Tests for the escrow, reconciliation, market and paper helpers."""
import unittest

from compute_forensics import goldrush as G
from compute_forensics import registry as R
from compute_forensics.abi import BY_NAME, decode_log
from compute_forensics.events import Ev
from compute_forensics.market_analysis import stable_flows
from compute_forensics.paper import short, usd_m
from compute_forensics.pipeline import _activity_stats
from compute_forensics.vault import LOAN_ROUTER_ADMIN_FEE, cash_yield

from eth_abi import encode


def _log(name, indexed, data):
    ev = BY_NAME[name]
    topics = [ev.topic] + [("0x" + encode([t], [v]).hex()) for t, v in zip(ev.indexed, indexed)]
    return topics, "0x" + encode(list(ev.data), data).hex() if ev.data else "0x"

H = "0x" + "ab" * 32


class EscrowTests(unittest.TestCase):
    def test_cancelled_topic_matches_chain(self):
        # observed on Arbitrum in tx 0xf1e421bc... (2026-08-07)
        self.assertEqual(BY_NAME["sUSDai.LoanEscrowTimelockCancelled"].topic,
                         "0x7a09c02a4912d7fb6670a761309e660d0c58cb28822b27fa5f14dcaa8da05230")

    def test_cancelled_decodes(self):
        tp, d = _log("sUSDai.LoanEscrowTimelockCancelled", [bytes.fromhex(H[2:])], [15 * 10**24, 8 * 10**22])
        name, f = decode_log(tp, d)
        self.assertEqual(name, "sUSDai.LoanEscrowTimelockCancelled")
        self.assertEqual(f["usdai_amount"], 15 * 10**24)

    def test_escrow_interest_counted_net_of_fee(self):
        ev = [Ev(1, 0, "2026-08-07T00:00:00Z", "0x1", "", "", "sUSDai.LoanEscrowTimelockCancelled",
                 {"loan_terms_hash": H, "usdai_amount": 10**24, "interest_amount": 100 * 10**18}),
              Ev(2, 0, "2026-09-03T00:00:00Z", "0x2", "", "", "sUSDai.LoanEscrowTimelockWithdrawn",
                 {"loan_terms_hash": H, "interest_amount": 50 * 10**18})]
        c = cash_yield(ev, {})
        self.assertAlmostEqual(c["2026-08"]["escrow_interest"], 100 * (1 - LOAN_ROUTER_ADMIN_FEE))
        self.assertAlmostEqual(c["2026-09"]["escrow_interest"], 50 * (1 - LOAN_ROUTER_ADMIN_FEE))


class FlowTests(unittest.TestCase):
    def test_stable_flows_in_out_and_mint_excluded(self):
        a, b = "0x" + "aa" * 20, "0x" + "bb" * 20
        zero = "0x" + "00" * 20

        def tr(src, dst, v):
            tp, d = _log("ERC20.Transfer", [src, dst], [v])
            return {"a": R.PYUSD_ARB, "tp": tp, "d": d}
        trace = {"txs": {a: [{"logs": [tr(b, a, 5 * 10**6), tr(a, b, 2 * 10**6), tr(a, zero, 10**6)]}]}}
        f = stable_flows(trace)[a]
        self.assertEqual(f["in"], [("PYUSD", b, 5.0)])
        self.assertEqual(f["out"], [("PYUSD", b, 2.0)])   # burns to zero address are not counterparties


class HelperTests(unittest.TestCase):
    def test_short_is_valid_latex(self):
        s = short("0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9")
        self.assertIn("\\ldots{}cbb9", s)   # \ldotscbb9 would be an undefined control sequence

    def test_usd_m(self):
        self.assertEqual(usd_m(1_234_567), "\\$1.2\\,M")
        self.assertEqual(usd_m(None), "n/a")

    def test_activity_stats(self):
        st = _activity_stats({"b1": ["x", "y"], "b2": ["x"], "h": ["x", "y", "z"]}, ["b1", "b2"])
        self.assertEqual((st["borrower_chains_min"], st["borrower_chains_max"], st["holder_chains_max"]), (1, 2, 3))

    def test_block_at_uses_next_day_range(self):
        seen = {}

        class Api:
            def get(self, path, params=None, **kw):
                seen["path"] = path
                return {"items": [{"height": 42}]}
        self.assertEqual(G.block_at(Api(), "eth-mainnet", "2025-12-31"), 42)
        self.assertEqual(seen["path"], "/v1/eth-mainnet/block_v2/2025-12-31/2026-01-01/")


class GoldRushRangeTests(unittest.TestCase):
    def test_events_by_topic_asks_for_hi_plus_one(self):
        seen = []

        class Api:
            def get(self, path, params=None, **kw):
                seen.append(dict(params))
                return {"items": [], "pagination": {"has_more": False}}
        G.events_by_topic(Api(), "arbitrum-mainnet", "0x" + "00" * 32, "0x" + "11" * 20, 100, 199, final=True)
        self.assertEqual((seen[0]["starting-block"], seen[0]["ending-block"]), (100, 200))  # ending-block is exclusive


class MergeTests(unittest.TestCase):
    def test_same_log_from_two_sources_with_different_offsets_is_kept_once(self):
        from compute_forensics.events import merge
        a = Ev(1, 5, "t", "0xab", "0xc", "", "X", {}, ("0x1",), "0x")
        b = Ev(1, 55, "t", "0xab", "0xc", "", "X", {}, ("0x1",), "0x")
        twin = Ev(1, 6, "t", "0xab", "0xc", "", "X", {}, ("0x1",), "0x")   # identical log repeated in one tx
        self.assertEqual(len(merge([a, twin], [b])), 2)


class CollateralTests(unittest.TestCase):
    def test_model_and_gpu_count(self):
        from compute_forensics.collateral import _model, _record_row
        self.assertEqual(_model("NVIDIA B300 [130]"), "B300")
        self.assertEqual(_model("NVIDIA GB200 NVL72 [32]"), "GB200")
        self.assertEqual(_model("Supermicro NVIDIA RTX 6000 Pro Server"), "RTX 6000")
        rec = {"owner": "0xab", "metadata": {"name": "NVIDIA B200 [96]", "attributes": [
            {"trait_type": "Collateral Value USD", "value": 42734150}, {"trait_type": "Quantity", "value": 96},
            {"trait_type": "Useful Life (days)", "value": 1080}, {"trait_type": "Depreciation Start", "value": "On Borrow"}]}}
        row = _record_row(1004, rec)
        self.assertEqual((row["gpus"], row["value_usd"], row["depreciation_start"]), (768, 42734150.0, "On Borrow"))
        self.assertIsNone(_record_row(1, {"metadata": None}))


if __name__ == "__main__":
    unittest.main()
