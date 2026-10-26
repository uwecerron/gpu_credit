# Research ledger

Every number in the paper, where it comes from, how it was computed and how it was checked. Values are the ones in `paper/generated/numbers.tex`, which the code writes; nothing in the paper is typed by hand.

## Headline numbers

| Claim | Value | Result field | Method | Independent check |
|---|---|---|---|---|
| Loans / borrowers | 39, 13 | `results.json loans.n, loans.borrowers` | LoanOriginated (V1+V2) stitched through migrations and refinances | 22/22 event sets identical to an Arbitrum node (data/verification) |
| Originated | $290.1 M | `loans.originated` | sum of root principal, test loans < $1k excluded | Same; independent reviewer recomputed from loans.csv |
| Outstanding | $182.2 M | `loans.outstanding` | current principal minus principal repaid per terms hash | Matches vault pendingLoanBalance within 0.22% (eth_call) |
| Largest borrower share, HHI | 45.6%, 0.273 | `loans.top1_share, hhi_originated` | from borrowers.csv | Reviewer recomputed |
| NAV growth | 8.18% | `vault.ann_total` | median assets/shares of sUSDai Deposit events per day | Deposit/redemption share price read by eth_call |
| Cash coverage | 93.8%, 28.5% | `vault.cash_coverage, cash_coverage_borrowers_only` | cash (interest, base yield, fees, escrow interest) / NAV-accrued yield | Reviewer recomputed; base-yield split by tx peers |
| Escrow with no loan | $128.9 M, 23.2% | `reconciliation.deposit_timelock_balance; escrow.open` | eth_call depositTimelockBalance vs open escrow deposits | Sum of two open deposits = balance to the cent; live re-read by reviewer |
| Escrow fund path | `paper/generated/tab_escrow.tex` | `escrow.flows` | decoded ERC-20 transfers + USDai Withdrawn, 2 hops | Redemption receipt re-read from node (onchain_checks.json escrow_receipts) |
| Collateral, LTV | 4,560, 66.8% | `collateral.*` | tokenURI by eth_call -> USD.AI metadata records | Crucible loan: press says 576 B300 GPUs; record says 72 servers x 8 = 576 |
| USDai backing | 100.00% | `verification.usdai_backing` | USDai totalSupply (hub + spokes) vs stablecoins held by the USDai contract | eth_call, two separate runs |
| Median redemption wait | 13.0 days | `queue.wait_days_median` | RedeemRequest matched to RedemptionProcessed by id | Event sets identical to node |
| Stress table | `paper/generated/tab_stress.tex` | `stress.rows` | arithmetic on reconciled state; recovery assumed | Not a model; assumptions stated in paper |
| Implied GPUs, breakeven | 5,724, $3.21 | `implied_compute, breakeven` | debt service / price / (8760 x utilization) | Assumptions: 70% utilization, 1.5 kW per GPU |
| Livepeer spend | $1.01 M | `livepeer.usd_total` | WinningTicketTransfer x daily WETH price | 194,377 logs identical to node after boundary fix |
| Akash spend | $3.46 M | `akash.usd_window` | Akash Console API, summed by day | Not on an EVM chain; API only |

## Data provenance

| File | Source | What it holds |
|---|---|---|
| `data/frozen/protocol_txs.json.gz` | GoldRush `transactions_v3` | Full decoded history of the 9 lending contracts |
| `data/frozen/hub_events.json.gz` | GoldRush `events/topics` | 15 vault and USDai event types over 182 block windows, plus window-end patch |
| `data/frozen/holders.json.gz` | GoldRush `token_holders_v2` | Holder lists, 2 tokens x 4 chains |
| `data/frozen/prices.json.gz` | GoldRush pricing | Daily prices of sUSDai, USDai, PYUSD |
| `data/frozen/accounts.json.gz` | GoldRush summaries and histories | Borrower and top-holder activity |
| `data/frozen/escrow_trace.json.gz` | GoldRush `transactions_v3`, `balances_v2` | Escrow facility and downstream wallets |
| `data/frozen/extras.json.gz` | GoldRush activity, holders at block | Cross-chain activity, monthly Ethereum holders |
| `data/frozen/livepeer.json.gz` | GoldRush `events/topics` | Livepeer TicketBroker payments, WETH prices |
| `data/frozen/state.json.gz` | Public Arbitrum node, `eth_call` | Vault accounting views at one block |
| `data/frozen/collateral.json.gz` | Arbitrum node `tokenURI`/`ownerOf` + USD.AI metadata host | Hardware-token records behind each loan |
| `data/frozen/solana.json.gz` | Public Solana node | sUSDai and USDai supply on Solana |
| `data/frozen/akash.json.gz` | Akash Console API | Spend, GPUs, providers, prices |
| `data/external/getdeploying_weekly.json` | GetDeploying, CC BY 4.0 | Weekly H100 rental median |
| `data/verification/onchain_checks.json` | Public RPC nodes, no GoldRush | Log-by-log check of 22 event sets, supply checks, escrow receipt, USDai backing |

`data/frozen/MANIFEST.sha256` hashes every frozen file; `reproduce.py` refuses to run if any hash differs.

## Verification runs

- Last chain check: 2026-10-24T15:28:05+00:00, block range 335,730,936 to 517,064,905.
- Event sets matched: 22 of 22, 246,176 logs.
- USDai backing at block 517,877,817: coverage 100.00%.
- One problem found and fixed: GoldRush `events/topics` treats `ending-block` as exclusive. The first scan skipped the last block of each 1M-block window; the patch added 2 Livepeer logs and no USD.AI logs.
- GoldRush sometimes numbers logs inside a transaction differently from the node, so logs are matched and deduplicated by transaction hash, topics and data, never by index.

## Independent review

A separate agent that had not seen the analysis recomputed the headline figures from the frozen data and live chain reads, and listed 15 issues. All were fixed. The most important:

- Base yield is not only PYUSD incentives: $8.72M of the $15.08M came from M^0's wM. The paper now splits the two.
- "Two orders of magnitude" was wrong; the credit-to-compute ratio is about 65x.
- The escrow facility is a Gnosis Safe operated by the protocol's own signers. Now disclosed.
- The USDai low of 0.889 was a price-feed artifact; replaced by the USDai/PYUSD ratio (min 0.975).
- Escrow cancellations were not decoded at first (`LoanEscrowTimelockCancelled`). Added from the contract source; one escrow that looked open was in fact cancelled.

## External sources

| Source | Supports |
|---|---|
| USD.AI docs and contract source (MetaStreet / USD.AI repos) | Protocol design, event signatures, migration history |
| [Block Media, 7 Apr 2026](https://www.blockmedia.co.kr/archives/1074441) | Crucible Capital loan: $26.82M, 576 NVIDIA B300 GPUs. Matches loan `0xaae6fe82` and its 72-server collateral record |
| [Friedman, neocloud GPU debt](https://davefriedman.substack.com/p/neoclouds-hold-more-than-20-billion) | >$20B GPU-backed debt, lenders, H100 rental price decline |
| [Gokhshtein, 22 Oct 2026](https://gokhshtein.com/news/2026-10-22-neocloud-pricing-power-tests-debt-concerns) | CoreWeave CDS at distressed levels |
| [Decrypt, GAIB AID](https://decrypt.co/310897) | Comparable GPU-backed synthetic dollar |
| [GetDeploying](https://getdeploying.com) | H100 rental price series |
| [Cerron 2026, SSRN 7549859](https://github.com/uwecerron/GPU_Depreciation_Research) | GPU economic life and depreciation |
| [Liquid Labor](https://liquid-labor.com) | Machine-hours framing used for implied compute |
| [Railway trace](https://github.com/uwecerron/railway_blockchain_incident) | Key-compromise risk example |
| Bullish, Aave ARFC, Architect (The Block), EIP-4626, EIP-7540, LayerZero | Context; full citations in `paper/refs.bib` |

## What is assumed, not measured

- Eight GPUs per B200, B300 and H200 server (confirmed for one loan by press).
- 70% utilization and 1.5 kW per GPU in the implied-compute section.
- Recovery rates of 60%, 40% and 20% in the stress table.
- Collateral values are USD.AI's own stated values, not appraisals.
- Wallet roles (off-ramp, service wallet) are inferred from on-chain behaviour only. No wallet is attributed to a company.
