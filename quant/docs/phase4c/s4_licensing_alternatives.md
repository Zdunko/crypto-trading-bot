# S4 licensing investigation: legally viable data for eventual paper trading, live trading and production models

Documentation-only. Not legal advice. Date 2026-11-26. **Rule applied: public download or API access is not a grant of rights.**
Evidence levels: **V** = primary text read in full by me (verified); **S** = statement seen only in a web-search result summary (secondary, not verified against the primary page; the hosts are unreachable from this environment); **U** = unresolved / unknown.

## 1. What is verified (V)
Only one text was read in full: the Binance Vision Dataset Terms v1.0 (details and sha256 in `s3_licensing_findings.md`).
- Permitted: academic/personal research and "algorithmic historical backtesting for purely personal non-production research" (4.1, closed list).
- Prohibited: live proprietary trading execution, automated commercial order generation, signal distribution for compensation (4.2); commercial exploitation of the data or derivative feeds (4.3); integration into commercial products/bots (4.4); commercial use needs a separate written enterprise licence (3.4).
- Derived data and models are "strictly governed" by the same terms (2.4).
Consequence: the Vision archive can carry the research phase only. It is **not** a verified basis for paper trading, live trading or a production model.

## 2. Candidate sources and what is (not) known
| Source | Evidence | What was seen | Verdict for paper / live / production |
|---|---|---|---|
| Binance Vision archive | V | see above | research only; derived-model use unresolved (U) |
| Binance public REST/WebSocket market data (own account) | S/U | a Binance developer-forum post says no policy specific to public market data exists (a user's view, not Binance's position); official docs describe real-time and historical market data and say to confirm product requirements before production; the main Binance Terms of Use could not be read | **U**: needs the current Terms of Use / API terms for the owner's jurisdiction read in full and, if in doubt, written confirmation from Binance |
| OKX public market-data endpoints (frozen 8-pair dataset came from here) | S | OKX API Agreement says public market-data endpoints are "subject to this Agreement, the OKX ToS, and the market data restrictions in Section 9"; Section 9 text not retrieved | **U**: Section 9 must be read before any use beyond personal research |
| Coinbase Exchange market data | S | Market Data Terms of Use (version seen dated 2023-02-06): "nonexclusive, nontransferable, non-sublicensable, revocable, limited license"; no altering/misrepresenting data; Coinbase may withdraw data | **U**: licence scope for automated trading and storage not confirmed; fewer pairs |
| Kraken | S | Marketplace Fair Use Policy restricts automated/excessive use and use of marketplace data outside legitimate business within the marketplace; no licence text for OHLCVT archives found | **U** |
| Commercial data vendors: Tardis.dev, CoinAPI, Kaiko, CoinGecko enterprise data licence, Deutsche Boerse/Kaiko | S | Kaiko "display" licence explicitly excludes use as input to trading calculations (a different licence is needed); CoinAPI redistribution rights only at enterprise tier (secondhand); Tardis has terms of service incl. exchange-specific terms; prices quoted by third parties ($199-$1,000+/month) | **U**; also **conflicts with the EUR 0 budget rule** (AGENTS.md rule 6): requires explicit owner approval before any contact or purchase |
| Self-collected data from an exchange where the owner holds an account (record own real-time feed) | U | no text read; would still be governed by that exchange's API/market data terms | **U**; cannot reproduce 2017-2025 history |

## 3. Unresolved legal questions (must be answered in writing before paper/live/production)
1. May a **model or parameters fitted on Binance Vision data** be used to trade live (own account, non-commercial)? Terms 2.4 and 4.2 point against it; no clarification exists. Question for Binance (written).
2. Is **paper trading** with Vision-derived signals "research" (4.1) or not? 4.1 is a closed list and does not name it.
3. What do the **Binance Terms of Use / API terms** allow for real-time public market data used by an automated strategy on the owner's own account (non-commercial)? OKX Section 9 and Coinbase/Kraken equivalents likewise.
4. What is the meaning of "commercial" for the owner's end goal (a "production-capable automated trading system")? If the system trades the owner's own capital only, is that "commercial use" of the data under each source's terms? If it ever manages third-party money or sells signals, every source above needs an enterprise licence.
5. Regulatory side (outside data licensing, unresolved): venue eligibility and onboarding from the owner's jurisdiction, algorithmic-trading and crypto-asset service rules (e.g. MiCA scope), tax treatment. Not investigated.

## 4. Recommended path (documentation only, no action taken)
1. Keep the research phase on Vision data under 4.1 (personal, non-commercial, non-production) - already the project rule.
2. Before any paper trading: obtain written answers to questions 1-4 from the venue(s) the owner would actually trade on; read their full Terms of Use/API/market-data sections (hosts are unreachable from this environment; the owner can paste the texts or allow the hosts).
3. Plan production data as **the trading venue's own real-time API under the owner's account terms** (U, to be confirmed) rather than Vision; treat historical Vision data as research-only and re-validate any strategy on data whose licence covers production before live use (a model validated on research data is not licensed-cleared by that fact).
4. A paid vendor licence is the fallback and needs explicit owner approval (budget rule 6).
5. Record all answers with date and text hash in the repository; no assumption of permission without a written source.
