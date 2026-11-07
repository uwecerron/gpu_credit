# Research ledger

Every number in the paper, where it comes from, how it was computed and how it was checked. Values are the ones in `paper/generated/numbers.tex`, which the code writes; nothing in the paper is typed by hand. The numbers in this file and in `README.md` are filled from the same macros by `scripts/fill_readme.py`, which `reproduce.py` runs.

## Headline numbers

| Claim | Value | Result field | Method | Independent check |
|---|---|---|---|---|
| Loans / borrowers | <!--n:NLoans-->39<!--/n-->, <!--n:NBorrowers-->13<!--/n--> | `results.json loans.n, loans.borrowers` | LoanOriginated (V1+V2) stitched through migrations and refinances | 22/22 event sets identical to an Arbitrum node (data/verification) |
| Originated | <!--n:Originated-->$290.1M<!--/n--> | `loans.originated` | sum of root principal, test loans < $1k excluded | Same; independent reviewer recomputed from loans.csv |
| Outstanding | <!--n:Outstanding-->$182.2M<!--/n--> | `loans.outstanding` | current principal minus principal repaid per terms hash | Exceeds vault pendingLoanBalance by <!--n:LoanBookGap-->$0.39M<!--/n--> (<!--n:LoanBookGapPct-->0.22%<!--/n-->) at the same block; residual not yet itemized |
| Largest borrower share, HHI | <!--n:TopOneShare-->45.6%<!--/n-->, <!--n:HHIOrig-->0.273<!--/n--> | `loans.top1_share, hhi_originated` | from borrowers.csv | Reviewer recomputed |
| NAV growth | <!--n:AnnTotal-->8.17%<!--/n--> | `vault.ann_total` | median assets/shares of sUSDai Deposit events per day | Deposit/redemption share price read by eth_call |
| Cash coverage | <!--n:CashCoverage-->93.7%<!--/n-->, <!--n:KappaBorrowers-->28.4%<!--/n--> | `vault.cash_coverage, cash_coverage_borrowers_only`, `cash_layers` | cash (interest, base yield, fees, escrow interest) / NAV-accrued yield; six layers in `tab_kappa.tex` | Reviewer recomputed; base-yield split by tx peers; the <!--n:EscrowAnomalous-->$341k<!--/n--> 2026-10-02 transfer is isolated |
| Escrow with no loan | <!--n:EscrowOpen-->$128.9M<!--/n-->, <!--n:DTShare-->23.2%<!--/n--> | `reconciliation.deposit_timelock_balance; escrow.open` | eth_call depositTimelockBalance vs open escrow deposits | Sum of two open deposits = balance to the cent; live re-read by reviewer |
| Escrow fund path | `paper/generated/tab_escrow.tex` | `escrow.flows` | decoded ERC-20 transfers + USDai Withdrawn, 2 hops | Redemption receipt re-read from node (onchain_checks.json escrow_receipts) |
| Collateral, LTV | <!--n:CollGPUs-->4,560<!--/n-->, <!--n:BookLTV-->66.8%<!--/n--> | `collateral.*` | tokenURI by eth_call -> USD.AI metadata records | Crucible loan: press says 576 B300 GPUs; record says 72 servers x 8 = 576 |
| USDai backing | <!--n:USDaiCoverage-->100.00%<!--/n--> | `verification.usdai_backing` | USDai totalSupply (hub + spokes) vs stablecoins held by the USDai contract | eth_call, two separate runs |
| Median redemption wait | <!--n:WaitMedian-->13.0<!--/n--> days (completed requests; <!--n:PendingShares-->20.17M<!--/n--> shares pending, censored) | `queue.wait_days_median` | RedeemRequest matched to RedemptionProcessed by id | Event sets identical to node |
| Stress table | `paper/generated/tab_stress.tex` | `stress.rows` | arithmetic on reconciled state; recovery assumed | Not a model; assumptions stated in paper |
| Implied GPUs, breakeven | <!--n:GPUsAkashPrice-->5,729<!--/n-->, <!--n:Breakeven-->$3.22<!--/n--> | `implied_compute, breakeven` | debt service / price / (8760 x utilization) | Assumptions: 70% utilization, 1.5 kW per GPU |
| Livepeer spend | <!--n:LPUSD-->$1.01M<!--/n--> | `livepeer.usd_total` | WinningTicketTransfer x daily WETH price | 194,377 logs identical to node after boundary fix |
| Akash spend | <!--n:AKUSD-->$3.47M<!--/n--> | `akash.usd_window` | Akash Console API, summed by day | Not on an EVM chain; API only |

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

- Last chain check: <!--n:VerifyRetrieved-->2026-10-27 00:20:42 UTC<!--/n-->, block range <!--n:VerifyBlockStart-->335,730,936<!--/n--> to <!--n:VerifyBlockEnd-->517,316,432<!--/n-->, the same block as the vault-state snapshot.
- Event sets matched: <!--n:NVerifyMatch-->22<!--/n--> of <!--n:NVerify-->22<!--/n-->, <!--n:NVerifyLogs-->246,262<!--/n--> logs.
- USDai backing at block <!--n:BackingBlock-->518,591,558<!--/n-->: coverage <!--n:USDaiCoverage-->100.00%<!--/n-->.
- Independent second pass (own decoders, live reads): `data/verification/VALIDATION.md`.
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
