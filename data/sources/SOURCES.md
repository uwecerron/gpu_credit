# Archived sources

Snapshots of every web source cited in the paper, taken 2026-10-26T23:53:01+00:00. Each `.html` is the page as served; each `.txt` is its extracted text. SHA-256 lets anyone check the snapshot was not edited later. Code repositories are pinned to the commit we read.

| Cite key | Source | Supports | Evidence (quote or paraphrase) | Snapshot | SHA-256 (html) |
|---|---|---|---|---|---|
| `bullish2025` | [https://www.pymnts.com/?p=4131576](https://www.pymnts.com/?p=4131576) | USD.AI $100M credit facility from Bullish | "USD.AI Secures $100 Million Credit Facility From Bullish to Power AI Buildout", PYMNTS, 28 Aug 2026 | `bullish2025.html`, `bullish2025.txt` | `e7bc4408109ab745…` |
| `aavearfc` | [https://governance.aave.com/t/arfc-onboard-usdai-susdai-to-aave-v3-arbitrum-instance/23260](https://governance.aave.com/t/arfc-onboard-usdai-susdai-to-aave-v3-arbitrum-instance/23260) | USDai/sUSDai proposed as collateral on Aave | Thread title: "[ARFC] Onboard USDai & sUSDai to Aave V3 Arbitrum Instance" | `aavearfc.html`, `aavearfc.txt` | `548a73eb4071a736…` |
| `architect2026` | [https://www.theblock.co/post/386487](https://www.theblock.co/post/386487) | GPU rental futures being built | The Block, 21 Jan 2026: Architect plans perpetual futures on AX tied to daily GPU rental prices, pending regulatory approval (page blocks automated download; content read via fetch) | `architect2026.txt` (fetch summary; site returned 403 to download) | n/a |
| `friedman2025` | [https://davefriedman.substack.com/p/neoclouds-hold-more-than-20-billion](https://davefriedman.substack.com/p/neoclouds-hold-more-than-20-billion) | >$20B GPU-backed debt; lenders; H100 $7-10 to $2-4 | "There are now more than $20 billion in outstanding loans collateralized by NVIDIA GPUs"; "BlackRock, Blackstone, PIMCO, Carlyle, JP Morgan, and Macquarie are all lenders"; "H100 rental prices have collapsed from $7-10/hour in early 2024 to $2-4/hour by late 2025" (7 Feb 2026) | `friedman2025.html`, `friedman2025.txt` | `614a7adc5acfee0b…` |
| `gokhshtein2026` | [https://gokhshtein.com/news/2026-10-22-neocloud-pricing-power-tests-debt-concerns](https://gokhshtein.com/news/2026-10-22-neocloud-pricing-power-tests-debt-concerns) | CoreWeave CDS at distressed levels | "CoreWeave's five-year credit default swaps reached distressed levels, and its bond yields climbed" (22 Oct 2026) | `gokhshtein2026.html`, `gokhshtein2026.txt` | `2eaeb561bf5dd7f6…` |
| `blockmedia2026` | [https://www.blockmedia.co.kr/archives/1074441](https://www.blockmedia.co.kr/archives/1074441) | $26.82M loan to Crucible Capital, 576 B300 GPUs | Headline: 2,682만 달러 GPU 담보 대출 (body: 2,680만 달러), 엔비디아 B300 GPU 576개 담보, 1MW 클러스터 (7 Apr 2026) | `blockmedia2026.html`, `blockmedia2026.txt` | `5f50625afe976e3a…` |
| `gaib2025` | [https://decrypt.co/310897](https://decrypt.co/310897) | GAIB AID, comparable GPU-backed synthetic dollar | "AID is backed by a portfolio of GPU financing deals, GPU cash flow, a reserve of treasury bills, and other liquid assets" | `gaib2025.html`, `gaib2025.txt` | `6f755a10de922778…` |
| `usdaidocs` | [https://docs.usd.ai/technical-overview/technical-protocol-overview](https://docs.usd.ai/technical-overview/technical-protocol-overview) | Optimistic vs conservative NAV; ERC-4626/7540 design | "Loan positions are valued conservatively with the remaining balance of the loan, or optimistically with the remaining balance of the loan plus the interest accrued since last repayment" | `usdaidocs.html`, `usdaidocs.txt` | `6524dca06397e02e…` |
| `eip4626` | [https://eips.ethereum.org/EIPS/eip-4626](https://eips.ethereum.org/EIPS/eip-4626) | ERC-4626 standard | "ERC-4626: Tokenized Vaults", Final | `eip4626.html`, `eip4626.txt` | `0f3b3abdb9e37ef4…` |
| `eip7540` | [https://eips.ethereum.org/EIPS/eip-7540](https://eips.ethereum.org/EIPS/eip-7540) | ERC-7540 standard | "ERC-7540: Asynchronous ERC-4626 Tokenized Vaults", Final | `eip7540.html`, `eip7540.txt` | `1191348dda76df6e…` |
| `layerzero` | [https://docs.layerzero.network/v2](https://docs.layerzero.network/v2) | OFT bridging | Omnichain Fungible Tokens documentation | `layerzero.html`, `layerzero.txt` | `2f7d35c3ef4b8052…` |
| `goldrush` | [https://goldrush.dev/docs](https://goldrush.dev/docs) | Data source | GoldRush API documentation | `goldrush.html`, `goldrush.txt` | `67d0e3b22a2a1783…` |
| `getdeploying` | [https://getdeploying.com/dataset/gpu-prices](https://getdeploying.com/dataset/gpu-prices) | GPU rental prices | Dataset page; the weekly series used is frozen in data/external/ with its SHA-256 | `getdeploying.html`, `getdeploying.txt` | `d3a306eae4106f40…` |
| `liquidlabor` | [https://liquid-labor.com](https://liquid-labor.com) | Machine-hours framing | Essay index incl. "VI. On Depreciation" | `liquidlabor.html`, `liquidlabor.txt` | `a99a33f3342de968…` |
| `morpho-curation` | [https://data.morpho.org/curation](https://data.morpho.org/curation) | Curator AUC (used in advisory notes, not the paper) | Steakhouse $2.50B, Sentora $1.20B, Gauntlet $981M | `morpho-curation.html`, `morpho-curation.txt` | `56481368e3ad36bd…` |

## Code repositories (pinned)

| Cite key | Repository | Used for | Commit |
|---|---|---|---|
| `usdaisrc` | [https://github.com/metastreet-labs/usdai-contracts](https://github.com/metastreet-labs/usdai-contracts) | Event signatures, migration history | usdai-contracts @ 0c8946fb6b3c041636c058d84fc40bb910a025f4 (2026-09-30); usdai-loan-router-contracts @ 23b06f19b779505b3e71510c80e434bf4a11f97c (2026-10-01) |
| `cerron2026gpu` | [https://github.com/uwecerron/GPU_Depreciation_Research](https://github.com/uwecerron/GPU_Depreciation_Research) | GPU depreciation, GetDeploying file | HEAD f9aa638c69614e36c66a58ffd627865e4233011d |
| `railway2026` | [https://github.com/uwecerron/railway_blockchain_incident](https://github.com/uwecerron/railway_blockchain_incident) | Key-compromise example | HEAD dacba1b333a4c1c5676c65940bd2687943b83e78 |

## Not archived

- `insights.munich-startup.de` ("USD.AI surpasses $100M ... record $34M deal"): returned 404 on retrieval, so it is not cited.
