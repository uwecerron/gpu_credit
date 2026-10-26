"""Offline tests: event decoding, loan stitching, vault math, holder metrics."""
import unittest

from eth_abi import encode

from compute_forensics import goldrush as G
from compute_forensics import registry as R
from compute_forensics.abi import BY_NAME, LOAN_TERMS_V2, decode_log, decode_loan_terms_v2, topic0
from compute_forensics.events import Ev
from compute_forensics.holders import classify_name, concentration, cross_chain_addresses
from compute_forensics.loans import apr_from_rate, build_loans, hhi
from compute_forensics.vault import annualized, nav_series, redemption_queue, spearman, supply_series

BORROWER = "0x" + "b0" * 20
RESERVE = "0x" + "ee" * 20
H1, H2 = "0x" + "11" * 32, "0x" + "22" * 32


def _t(addr):  # address as a 32-byte topic
    return "0x" + "00" * 12 + addr[2:]


def _log(name, indexed, data):
    ev = BY_NAME[name]
    topics = [ev.topic] + [("0x" + encode([t], [v]).hex()) for t, v in zip(ev.indexed, indexed)]
    return topics, "0x" + encode(list(ev.data), data).hex() if ev.data else "0x"


def _ev(i, name, f, t="2026-03-01T00:00:00Z", tx_from=""):
    return Ev(i, 0, t, f"0x{i:064x}", "", tx_from, name, f)


class AbiTests(unittest.TestCase):
    def test_known_topics(self):
        self.assertEqual(topic0("Transfer(address,address,uint256)"),
                         "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef")
        self.assertEqual(BY_NAME["sUSDai.Deposit"].topic,
                         "0xdcbc1c05240f31ff3ad067ef1ee35ce4997762752e3a095284754544f4c709d7")

    def test_roundtrip_v1_origination(self):
        topics, data = _log("LR1.LoanOriginated", [bytes.fromhex(H1[2:]), BORROWER, R.PYUSD_ARB], [5_000_000, 1])
        name, f = decode_log(topics, data)
        self.assertEqual(name, "LR1.LoanOriginated")
        self.assertEqual(f["borrower"], BORROWER)
        self.assertEqual(f["principal"], 5_000_000)

    def test_erc721_transfer_rejected(self):
        ev = BY_NAME["ERC20.Transfer"]
        topics = [ev.topic, _t(BORROWER), _t(RESERVE), "0x" + "00" * 31 + "07"]
        self.assertIsNone(decode_log(topics, "0x"))

    def test_loan_terms_v2_decode(self):
        terms = (123, RESERVE, R.USDAI, "0x" + "c0" * 20, (1095, 1, 0), ("0x" + "a1" * 20, b""), [7],
                 [(R.SUSDAI, 10 * 10 ** 18, 2695332318)], [], [], b"")
        blob = "0x" + encode([LOAN_TERMS_V2], [terms]).hex()
        d = decode_loan_terms_v2(blob)
        self.assertEqual(d["borrower"], RESERVE)
        self.assertEqual(d["tranches"][0]["lender"], R.SUSDAI)
        self.assertAlmostEqual(apr_from_rate(2695332318), 0.085, places=3)


class LoanStitchTests(unittest.TestCase):
    def test_migration_maps_reserve_account_and_repayments(self):
        terms = (0, RESERVE, R.USDAI, "0x" + "c0" * 20, (960, 1, 0), ("0x" + "a1" * 20, b""), [1],
                 [(R.SUSDAI, 900_000 * 10 ** 18, 3805175038)], [], [], b"")
        blob = "0x" + encode([LOAN_TERMS_V2], [terms]).hex()
        events = [
            _ev(1, "RAF.ReserveAccountCreated", {"reserve_account": RESERVE, "borrower": BORROWER}),
            _ev(2, "LR1.LoanOriginated", {"loan_terms_hash": H1, "borrower": BORROWER,
                                          "currency_token": R.PYUSD_ARB, "principal": 1_000_000 * 10 ** 6,
                                          "origination_fee": 0}),
            _ev(3, "LR.LoanRepaid", {"loan_terms_hash": H1, "borrower": BORROWER, "principal": 100_000 * 10 ** 6,
                                     "interest": 10_000 * 10 ** 6, "prepayment": 0, "fee": 0, "is_repaid": False}),
            _ev(4, "LR2.LoanMigrated", {"old_loan_terms_hash": H1, "new_loan_terms_hash": H2,
                                        "new_loan_terms": blob}),
            _ev(5, "LR.LoanRepaid", {"loan_terms_hash": H2, "borrower": RESERVE, "principal": 50_000 * 10 ** 18,
                                     "interest": 9_000 * 10 ** 18, "prepayment": 0, "fee": 0, "is_repaid": False}),
        ]
        loans, meta = build_loans(events)
        self.assertEqual(len(loans), 1)
        ln = loans[H1]
        self.assertEqual(ln.borrower, BORROWER)
        self.assertAlmostEqual(ln.interest_paid, 19_000)          # 6- and 18-decimal legs both scaled
        self.assertAlmostEqual(ln.outstanding, 850_000)           # 900k migrated minus 50k repaid since
        self.assertEqual(meta["stray_events"], 0)

    def test_hhi(self):
        self.assertAlmostEqual(hhi([50, 50]), 0.5)
        self.assertAlmostEqual(hhi([100]), 1.0)


class VaultTests(unittest.TestCase):
    def test_nav_supply_and_annualized(self):
        ev = [_ev(1, "sUSDai.Deposit", {"sender": BORROWER, "owner": BORROWER, "assets": 100 * 10 ** 18,
                                        "shares": 100 * 10 ** 18}, t="2026-01-01T00:00:00Z"),
              _ev(2, "sUSDai.Deposit", {"sender": BORROWER, "owner": BORROWER, "assets": 110 * 10 ** 18,
                                        "shares": 100 * 10 ** 18}, t="2027-01-01T00:00:00Z"),
              _ev(3, "sUSDai.RedeemRequest", {"controller": BORROWER, "owner": BORROWER, "request_id": 1,
                                              "sender": BORROWER, "shares": 50 * 10 ** 18}, t="2027-01-02T00:00:00Z")]
        nav = nav_series(ev)
        self.assertAlmostEqual(annualized(nav, "2026-01-01", "2027-01-01"), 0.10, places=6)
        self.assertAlmostEqual(supply_series(ev)["2027-01-02"], 150.0)

    def test_queue_wait(self):
        ev = [_ev(1, "sUSDai.RedeemRequest", {"controller": BORROWER, "owner": BORROWER, "request_id": 7,
                                              "sender": BORROWER, "shares": 10 * 10 ** 18}, t="2026-01-01T00:00:00Z"),
              _ev(2, "sUSDai.RedemptionProcessed", {"redemption_id": 7, "controller": BORROWER,
                                                    "fulfilled_shares": 10 * 10 ** 18, "amount": 11 * 10 ** 18,
                                                    "pending_shares": 0}, t="2026-01-31T00:00:00Z")]
        q = redemption_queue(ev)
        self.assertEqual(q["completed"], 1)
        self.assertAlmostEqual(q["wait_days_median"], 30.0)
        self.assertAlmostEqual(q["pending_shares"], 0.0)

    def test_spearman(self):
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(spearman([1, 2, 3, 4], [4, 3, 2, 1]), -1.0)


class HolderTests(unittest.TestCase):
    def test_concentration(self):
        c = concentration([10 ** 18 * x for x in (50, 30, 20)])
        self.assertAlmostEqual(c["top1"], 0.5)
        self.assertAlmostEqual(c["hhi"], 0.25 + 0.09 + 0.04)

    def test_labels(self):
        self.assertEqual(classify_name(["SY Staked USDai"]), "Pendle")
        self.assertEqual(classify_name(["Morpho Blue"]), "Morpho")
        self.assertEqual(classify_name(["something"]), "unlabeled")

    def test_cross_chain(self):
        a = "0x" + "aa" * 20
        h = {"x": {"sUSDai": {"rows": [{"address": a, "balance": str(2 * 10 ** 23)}]}},
             "y": {"sUSDai": {"rows": [{"address": a, "balance": str(3 * 10 ** 23)}]}}}
        self.assertEqual(cross_chain_addresses(h, "sUSDai"), {a: ["x", "y"]})


class WindowTests(unittest.TestCase):
    def test_windows_cover_range_without_overlap(self):
        w = G.windows(100, 2_600_099, span=1_000_000)
        self.assertEqual(w[0], (100, 1_000_099))
        self.assertEqual(w[-1][1], 2_600_099)
        self.assertTrue(all(b[0] == a[1] + 1 for a, b in zip(w, w[1:])))


if __name__ == "__main__":
    unittest.main()
