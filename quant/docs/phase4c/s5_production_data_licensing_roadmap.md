# Production-data licensing roadmap (separate from research; no purchase, no assumed permission)

Goal: a legally clean data path for paper trading, live trading and production models. Today the **only** verified text is the Binance Vision Dataset Terms (research / personal non-production backtesting only). Nothing below is advice or a permission; every row is a question to be answered in writing.

## Phases and gates
| Phase | Content | Output | Gate (owner decides) | Cost |
|---|---|---|---|---|
| R0 now | research stays on Vision data under its clause 4.1; no paper/live; record the limitation | register entry L-LIC | none | EUR 0 |
| R1 read primary texts | obtain the full current texts: Binance Terms of Use and API/market-data terms for the owner's jurisdiction; OKX API Agreement section 9 and Terms of Service; Coinbase Market Data Terms and Exchange API terms; Kraken API/Terms; each vendor under consideration. The hosts are unreachable from this environment: the owner either pastes the texts or allows the hosts (a Settings decision) | texts stored with date and sha256 under `quant/docs/legal/` | G-L1: texts complete | EUR 0 |
| R2 written answers | send the question list below to the venue/provider (owner as sender) and record answers verbatim | answers with date and hash | G-L2: answers sufficient | EUR 0 |
| R3 choose the production data path | candidates: (a) the trading venue's own real-time API under the owner's account terms; (b) forward self-collection of the venue's feed from the start of paper trading (also subject to the venue's terms); (c) a commercial vendor licence (needs explicit budget approval, prices quoted by third parties USD 199-1 000+/month are unverified) | decision memo | G-L3: owner approval; any spend needs a separate approval | none until approved |
| R4 re-validate | any strategy validated on Vision data must be re-validated on licence-cleared data (same pre-registered criteria) before any paper/live step; the holdout rules stay unchanged | validation report | G-L4 | EUR 0 |

## Questions to put in writing
1. May a model or parameters fitted on Binance Vision data be used to trade live on the owner's own account (non-commercial)? Which clause?
2. Is paper trading driven by Vision-derived signals "research" under clause 4.1?
3. For each venue: may real-time public market data be used by an automated strategy trading the owner's own account? May it be stored and used to fit models? May fitted models be used commercially?
4. What does "commercial" mean when the owner trades only their own capital? Which activities (managing others' funds, selling signals, a bot product) would require an enterprise licence?
5. Retention and derivative-data rules: may derived tables (e.g. universe membership) be published in a repository?
6. Regulatory (outside data licensing): venue eligibility and onboarding in the owner's jurisdiction, algorithmic-trading and crypto-asset service rules, tax. Qualified counsel is recommended; not investigated here.

## Evidence ledger (as of 2026-11-26)
| Source | Level | Note |
|---|---|---|
| Binance Vision Dataset Terms v1.0 | **verified (full text)** | research/personal backtesting only; derived data governed |
| Binance global Terms of Use, API terms | unknown | text not retrievable; forum post says no public-market-data policy (a user's view) |
| OKX API Agreement | search-summary | public endpoints subject to section 9 market-data restrictions (text unread) |
| Coinbase Market Data Terms (2023-02-06) | search-summary | limited, non-transferable, revocable licence |
| Kraken | search-summary | marketplace fair-use policy; no data licence found |
| Vendors (Tardis, CoinAPI, Kaiko, CoinGecko, Deutsche Boerse) | search-summary | display licences exclude trading input; redistribution at enterprise tier; pricing secondhand |
Nothing is purchased, contacted or assumed by this roadmap.
