# Licensing: the exact questions and documents (Binance spot as the provisional research venue)

Status: Binance spot is the **provisional research venue only**. Research continues on Binance Vision data strictly within the verified permission (Dataset Terms v1.0: research / personal non-production backtesting). This is **not** approval for commercial deployment, paper trading on a feed, or live trading. Nothing is purchased; no additional usage right is assumed. No blocked host is retried; the owner supplies the texts or authorises the hosts.

## Documents to obtain (primary sources, as the owner's account sees them; store the text with the date under `quant/docs/legal/`)
1. **Binance Terms of Use** (the version applicable to the owner's jurisdiction/account) — automated trading on the owner's own account, API usage limits, prohibited conduct.
2. **Binance API terms / market-data policy** linked from the developer documentation (`developers.binance.com`) — storage and use of public market data, derived data, redistribution.
3. **Binance Vision Dataset Terms** (already read and verified for S3/S4: research only) — re-read the current version once to confirm nothing changed; the text is the authority for everything done so far.
4. **Binance data licence statements for historical downloads** (the licence notice shown on `data.binance.vision` and in the archive's README, if any) — whether CC BY-NC-SA 4.0 or another licence applies and what "non-commercial" excludes.
5. The owner's **account agreement for the venue actually chosen for paper/live** (if not Binance) and that venue's API/market-data terms.

## Exact written questions (send to Binance support/legal as the account owner; record the answer verbatim with date and a sha256)
1. May data downloaded from `data.binance.vision` be used to fit parameters or models, or to validate a signal, that will later drive an automated strategy trading the owner's **own** capital on Binance spot? Which clause?
2. Does "non-commercial/research" in the Dataset Terms exclude using research results derived from this data to make trading decisions with the owner's own money? If yes, what data source may be used instead?
3. May real-time public market data from the Binance API be stored and used to compute signals for the owner's own account (paper first, later live)? Are there retention, rate, or derived-data limits?
4. Which activities would require a commercial or enterprise data licence (managing others' funds, publishing signals, offering a bot, redistributing derived tables)? Is trading only the owner's own capital "commercial" under any of the documents?
5. May derived, non-reconstructible tables (e.g. universe membership, signal ranks) be published in a public code repository? May raw files be redistributed to collaborators?
6. Is there a free, documented historical-data feed whose licence explicitly allows use for validating and operating one's own automated trading?

## What the answers unlock
Answer to 1-2 negative or unclear: every research result so far stays research-only and must be re-validated on licence-cleared data before any paper step (R4 of `s5_production_data_licensing_roadmap.md`). Answer to 3 negative or unclear: L4 (forward paper trading on a live feed) stays blocked. Nothing is assumed in the meantime.
