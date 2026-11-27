# S9 — Data licensing: what is needed from the owner

Facts: the only verified text is the Binance Vision Dataset Terms (research / personal non-production backtesting only). In S8, twelve primary URLs were **not reachable** from this environment (host not resolvable). They are **not retried**; nothing below is assumed or fetched. No commercial usage right is assumed for any source.

## A. Decision needed first
Which venue will the paper-trading and any later live account use? Only that venue's terms plus the terms of whatever historical data source is used for research and re-validation matter. Everything else can be skipped.

## B. Documents required (the exact primary sources; URLs are best-known and must be confirmed by the owner from the live page)
| # | Document | Where | Question it answers |
|---|---|---|---|
| 1 | Terms of Use / User Agreement of the **intended trading venue** (owner's own account version) | the venue's legal page in the owner's jurisdiction | may an automated strategy trade the owner's own account; API limits |
| 2 | The venue's **API / market-data terms** | e.g. Binance: terms linked from `developers.binance.com`; Kraken: `https://www.kraken.com/legal`; Coinbase: `https://www.coinbase.com/legal/market_data_terms`; OKX: `https://www.okx.com/help/okx-api-agreement`; Bitstamp: `https://www.bitstamp.net/terms-and-conditions/` | may public market data be stored and used to fit models for own-account trading; is that "commercial" |
| 3 | The venue's **historical-data download terms** | Kraken: `https://support.kraken.com/hc/en-us/articles/360047124832-Downloadable-historical-OHLCVT-Open-High-Low-Close-Volume-Trades-data`; Binance Vision: already read, research only | may such history be used to validate a strategy that will trade live |
| 4 | Terms of any **aggregate data source** considered for longer history | e.g. FRED `https://fred.stlouisfed.org/legal/` and the series page `https://fred.stlouisfed.org/series/CBBTCUSD` | redistribution and derivative-use rights, since they inherit exchange terms |
| 5 | Written answers to the six questions of `s5_production_data_licensing_roadmap.md` | sent by the owner to the venue | explicit permission, in writing |
| 6 | Regulatory / tax advice for the owner's jurisdiction | qualified counsel | outside data licensing; not investigated |

## C. Minimum owner actions (choose one per document; cost EUR 0)
1. **Paste the text** into a file under `quant/docs/legal/<venue>_<document>_<date>.txt` (I then hash and summarise it), **or**
2. **Authorise the exact hosts** in the environment network settings (a Settings decision; I can propose it via the environment tool, which asks you for approval): `www.binance.com`, `developers.binance.com`, `www.kraken.com`, `support.kraken.com`, `www.coinbase.com`, `docs.cdp.coinbase.com`, `www.okx.com`, `www.bitstamp.net`, `docs.bitfinex.com`, `fred.stlouisfed.org`. Authorise only the venue(s) from section A to keep the surface small.
3. Send the written questions (item 5) and paste the reply verbatim.

## D. What stays blocked until this is done
L4 (forward paper trading on a licence-cleared feed), any claim about commercial deployability, and re-validation of any research result on licence-cleared data. L1-L3 on the existing research-only data are allowed but never imply commercial usability.
