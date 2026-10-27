# Independent validation of the USD.AI GPU-credit paper (second pass)

Validator run: 2026-10-26. I made no changes to `/home/claude/covalent_onchain_compute`. One exception: a `pytest --collect-only` run created `tests/__pycache__`, and I deleted it straight away. My scripts are in `data/verification/independent/` (loans.py, coll.py, vault.py, misc.py, live.py). The live chain reads are saved in `data/verification/independent/live_checks.json`.

`data/frozen/MANIFEST.sha256` verifies: all 13 files are OK.

## A. Independent recomputation from data/frozen

I wrote my own decoders with `eth_abi` and keccak topic hashes, without the repo's analysis functions. I checked each topic0 against the Solidity signature. Every number below matches `numbers.tex` within 0.5% unless marked.

| Quantity | Mine | numbers.tex | Status |
|---|---|---|---|
| Real loans / test loans / borrowers | 39 / 2 / 13 | 39 / 2 / 13 | match |
| Originated | \$290,117,597 | \$290.1 M | match |
| Outstanding | \$182,235,692 | \$182.2 M | match (exact) |
| Repaid / active | 18 / 21 | 18 / 21 | match |
| Interest, principal (principal + prepayment), repayment fees | \$6.941 M, \$108.15 M, \$515 k | \$6.94 M, \$108.1 M, \$515 k | match. Principal only matches if the `prepayment` field counts as principal: without it the figure is \$79.7 M. |
| Top-1 / top-3 share, HHI on originations | 45.64% / 76.80% / 0.2735 | 45.6% / 76.8% / 0.273 | match |
| HHI and top-1 share on outstanding | 0.1968 / 29.85% | 0.197 / 29.9% | match |
| Rates (active loans, principal-weighted per loan) | 7.0% (repaid 120-day bridge) to 15.0% | 7.0–15.0% | match |
| **Loans "moved from V1 to V2 through migrateLoan()"** | **17** LoanMigrated events, all on real loans | **18** (`NMigrated`) | **MISMATCH** (see D1) |
| Collateral: active units / GPUs / stated value | 630 / 4,560 / \$272,837,420 | 630 / 4,560 / \$272.8 M | match |
| Book LTV, min, max | 66.79%, 43.0%, 80.0% | 66.8%, 43%, 80% | match |
| Useful lives | {1080, 1095} | "1080 and 1095" | match |
| My token-ID mapping (terms + bundle wrapper) vs `by_terms_hash` | identical for all 21 active loans | — | match |
| Deposit-side NAV start/end, annualized | 1.000312 → 1.120137, 8.18% | 1.0003 → 1.1201, 8.18% | match |
| Share supply from events | 476.41 M | 476.4 M | match |
| Accrued yield Y | \$24.436 M | \$24.44 M | match |
| Cash: vault interest / base yield (net) / admin fee / fees to vault / escrow interest net of 10% | \$6.647 M / \$15.080 M / \$1.676 M / \$305.5 k / \$879.7 k | \$6.65 M / \$15.08 M / \$1.68 M / \$305 k / \$880 k | match. The contract source confirms that `BaseYieldDeposited` is emitted net of the fee. |
| κ, borrowers-only κ | 93.76%, 28.45% | 93.8%, 28.5% | match |
| Redemption requests / distinct owners / completed | 2,986 / 2,529 / 2,840 | 2,986 / 2,529 / 2,840 | match |
| Median / p90 / max wait (days), pending shares, requested shares | 13.01 / 26.66 / 127.35, 19.30 M, 349.40 M | 13.0 / 26.6 / 127.3, 19.30 M, 349.4 M | match |
| Escrow deposits: count, total, open | 9, \$223.09 M, 2 open = \$128,895,244.10 | 9, \$223.1 M, \$128.9 M | match |
| Livepeer ETH, tickets, USD | 371.275 ETH, 194,377, \$1.0054 M | 371, 194,377, \$1.01 M | match |
| Livepeer top gateway / top-3 / HHI (USD-weighted) | 49.36% / 83.13% / 0.318 | 49.4% / 83.1% / 0.318 | match. ETH-weighted figures would be 50.9% / 83.4% / 0.328. |
| sUSDai Arbitrum holders, top-1, top-10, HHI | 3,778, 33.3%, 86.7%, 0.209 | same | match |
| Reconciliation: loan-book gap, shares gap, DT share | 0.216%, 0.006%, 23.21% | 0.22%, 0.01%, 23.2% | match |
| Stress rows, breakeven \$3.21 / \$2.25, 6.8 MW, 65× | recomputed arithmetically | same | match |
| Three servicing calls on 2026-03-07 and 2026-04-06 | \$26.81 + \$109.16 + \$80.78 = \$216.75 M | "about \$217 M" | match |

Other facts I checked and found correct:
- The PYUSD hub (0x1168…21b1) was first active on 2026-04-29 and has 56 txs.
- Off-ramp A (0xf845…abb7) is active on 19 chains.
- The hub received \$127.3 M PYUSD from the largest borrower 0x6444… and \$7.35 M from the multisig submitter 0x034d….
- The hub forwarded \$339.6 M to off-ramp A and \$5.5 M to service wallet B.
- The 28%-APR junior tranche and the one-unit fee positions exist.
- Token 1006 secured the largest borrower's \$87.05 M, 120-day, 7% loan, which was repaid on 2026-10-01.
- The oldest active loan dates from 2026-01-28.
- The GetDeploying file's SHA-256 matches the one in the GPU_Depreciation_Research repo.

## B. Live chain spot checks

Block 518,586,254, read 2026-10-26T23:54Z.

- `depositTimelockBalance()`: the selector is `0x37d0a739`. It returns **128,895,244.1 USDai, unchanged**. `totalAssets` is now \$555.997 M, so the share is about 23.2%.
- USDai `totalSupply` on the hub is 265,258,326.8. PYUSD `balanceOf(USDai)` is 266,256,291.6. Adding the EVM spokes (Eth 5,578; Base 125,629; Plasma 866,164) brings supply to about 266.256 M, so **coverage is about 100.0%**, consistent with the paper.
  - Caveat: Solana USDai (590.5 tokens) is left out of the paper's coverage figure. The amount is negligible.
- `ownerOf(1006)` = 0xce242ccca5…7ff2. That is the reserve account that `ReserveAccountCreated` maps to the largest borrower 0x64447901…. This matches `collateral.json.gz` and the "unpledged in the borrower's reserve account" text.
- `tokenURI(1002)` = https://metadata.usd.ai/v1/1002. The live record is "NVIDIA B300 [72]", Collateral Value USD 38,316,634.018552, Quantity 72, life 1080 days. This **matches collateral.json.gz exactly**. Token 1006 also matches (\$140,192,868.97, 288 units).
- The escrow redemption receipt (0x46dc4ae9…, block 508,237,173, 2026-09-23 20:48 UTC) shows, re-read live: 128,895,244.1 USDai burned by the facility, and 128,895,244.10 PYUSD sent from the USDai contract to the hub. Confirmed.
- Metadata record 1012 ("NVIDIA GB200 NVL72 [32]", \$153,063,102.36) exists, and `ownerOf(1012)` reverts (not minted). This confirms results.tex:37.
  - The \$153 M figure is typed into the text by hand. It is not in `collateral.json.gz` or any macro, so it cannot be reproduced from the frozen data.
  - A second unminted record, 1013 ("GB200 NVL72 [32]", \$8.06 M), is now also on the host.

## Discrepancies (file:line → correct value; severity)

**D1. results.tex:15 — "\NMigrated{} [18] loans were moved from V1 to V2 through migrateLoan()". Medium-low.**
`pipeline.py:346` counts loans with more than one terms hash. That count includes one V2-originated loan that was refinanced. The data has exactly 17 `LoanMigrated` events, all on real loans. The correct value is **17**. Alternatively, keep 18 and reword it as "18 loans changed terms hash (17 migrations, 1 V2 refinancing)".

**D2. results.tex:95 — "there we compare against the latest block… and the gaps are below 0.1%". Medium (a false statement in the verification section).**
`data/verification/onchain_checks.json` `supply_checks` shows:
- Arbitrum: RPC 268.99 M vs holder sum 270.82 M, a gap of **0.68%**.
- Ethereum: 102.14 M vs 101.53 M, a gap of **0.60%**.

The correct wording is "gaps of 0.6–0.7%". The text also needs to explain the gap (the latest block is later than the snapshot).

**D3. results.tex:214 — "\$1.50, the low end of 2025 spot pricing~\cite{friedman2025}". Medium.**
The source says "below \$2.00/hour" and never mentions \$1.50. Either find a source for \$1.50 or change it to \$2 (or "below \$2"). This also affects `GPUsLowPrice` / `MWLowPrice`.

**D4. discussion.tex:28 — "drain 231 wallets on 17 chains in about an hour". Medium.**
The cited report gives 19:36 UTC on 21 Oct to 02:32 UTC on 22 Oct, which is **about seven hours**.

**D5. method.tex:7 — "migrateLoan() … executed on-chain between 2026-06-26 and 2026-07-14". Low.**
The `LoanMigrated` events fall on 2026-06-26, 06-30, 07-02 and 07-03. The correct end date is **2026-07-03**, which is also what `loans.py`'s docstring says.

**D6. method.tex:3 — "by KYC'd institutions". Low-medium.**
I found no support for this in the cited docs page or in other docs.usd.ai pages (the docs say users "can mint USDai by depositing PYUSD"). The source has no KYC or whitelist role on `deposit()`. Either cite something or drop it.
- "its hub chain" is not on the cited page.
- method.tex:5 "bad acts" is on docs.usd.ai/borrower/overview, not on the cited technical-overview URL.

**D7. refs.bib metadata. Low.**
- `bullish2025`: published 2026-08-28, so `year` should be 2026.
- `friedman2025`: published 2026-02-07, so `year` should be 2026.
- `eip7540`: the author is Jeroen **Offerijns**, not "Rosenberg".
- `usdaisrc`: the repo now redirects to github.com/usdai-foundation.
- `railway2026`: the title says "22 chains" while the text says 17. Both are true, but it reads as inconsistent.

**D8. method.tex:90 — "The repository has 40 unit tests". Low.**
`pytest --collect-only` reports **41**.

**D9. Escrow-interest composition is not disclosed (results.tex:60 and :106, macro `\CashEscrow`). Medium (interpretation).**
Of the \$977 k gross escrow interest, **\$378,798 (39%) comes from one \$1,000 escrow** (hash 0xfdd957cb…):
- It was opened at 2026-10-02 16:34 and cancelled at 18:34.
- Its rate was 0.0524 per second, about 5.2% per second, against the 6.5% APR the paper states for escrows.
- The cancel transaction (0xeb613f15…, sent by the multisig submitter 0x034d…) moves **\$379,798 USDai from the escrow facility Safe into the vault**. The 10% fee (\$37.9 k) goes to 0x5f0b….

In effect, the protocol-operated Safe paid about \$341 k net into the vault, booked as "escrow interest", one day after the largest borrower's loan was repaid. The cash total is correct, but the paper describes escrow interest as earned at 6.5% and counts this payment toward κ without comment. It should be disclosed.

**D10. method.tex:3 vs results.tex:13 / tab_usdai. Low.**
The background says minting was against "PYUSD, wM and USDC over our window". Table and text also show USDT (\$0.04 M).

**D11. "Largest borrower" means two different addresses. Low (clarity).**
- results.tex:37, 108, 177 and discussion.tex:26 use it for 0x6444… (largest by originations).
- discussion.tex:9 / tab_stress use it for 0x7f12… (largest by outstanding: \$54.4 M, 29.9%).

The two sections should say which ranking they mean.

**D12. RESEARCH.md says logs are "deduplicated by transaction hash, topics and data". Low (documentation).**
Literal content-key deduplication would collapse 219 legitimate sUSDai Deposit logs and 574 USDai Deposited logs. These are identical logs at different indexes in the same transaction: batch deposits.
- The pipeline does not actually do this. Its supply of 476.4 M matches only the non-deduplicated count.
- `verify.py` keeps multiplicity.

The ledger wording is misleading and should say "matched by content key with multiplicity".

## D. Factual sentences without a macro, citation or obvious derivation

| Location | Sentence / fact | Note |
|---|---|---|
| intro:3 | "USD.AI is one of the larger ones." | No size comparison and no source. |
| method:3 | "by KYC'd institutions"; "Arbitrum, its hub chain" | See D6. |
| results:37 | "a further record for 32 GB200 NVL72 racks (\$153 M stated) exists on the metadata host without a minted token" | True live (token 1012), but typed by hand and not in the frozen data. A second record (1013) now exists. |
| results:55 | "a 13-day median wait" | Hard-coded instead of `\WaitMedian`. Correct today. |
| results:62 | "junior tranche priced at 28% APR" | Hard-coded. Verified correct. |
| results:93 | "one ticket payment of 0.0024 ETH" | Hard-coded. Taken from the verification output. |
| results:95 | "0.19% higher on Plasma"; "gaps are below 0.1%" | Hard-coded. The second is wrong (D2). |
| results:108 | Hub "first active on 2026-04-29 and has 56 transactions"; off-ramp "active on 19 chains" | Hard-coded. Verified correct. |
| results:130 | Cross-chain contract has ">8 million Arbitrum transactions", ">95% of supply on Base and Plasma" | Hard-coded. The 95.1% / 97.6% shares are verified; the transaction count was not checked. |
| results:177 | "0.18, the threshold for a highly concentrated market in the 2023 U.S. Merger Guidelines" | Correct (HHI > 1,800) but uncited. |
| results:214 | "B200 and B300 class parts, which rent above H100 rates today" | No price data or citation for B200/B300 rental rates. |
| discussion:28 | "Two days before this paper was finished" | Date claim. The incident was 2026-10-21. |
| discussion:38 | "Payment-stablecoin rules in the United States now distinguish tokens that pay yield from those that do not" | Uncited legal claim (presumably the GENIUS Act). |
| discussion:26 | "with the same collateral and the same borrowers' customers" | Assertion. No evidence about borrowers' customers is presented. |
| method:90 | "40 unit tests… runs them in CI" | 41 tests (D8). CI not verified. |

## Bottom line

The headline numbers all reproduce from the frozen data: loans, principal, concentration, collateral and LTV, NAV, cash coverage, queue, escrow, Livepeer and reconciliation. The live state still matches: the escrow balance is unchanged, USDai is about 100% PYUSD-backed, and tokens 1002 and 1006 match.

The issues to fix are:
- the false "<0.1%" supply-gap statement (D2);
- the unsupported \$1.50 citation (D3);
- "about an hour" in the Railway cite (D4);
- the migrated-loan count (D1);
- the migration end date (D5);
- the undisclosed \$379 k Safe-to-vault "escrow interest" (D9);
- the minor bib and wording items.
