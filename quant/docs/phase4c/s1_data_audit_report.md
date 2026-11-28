# S1 - Historical data audit (point-in-time universe) - report

Scope: availability, coverage, quality, licence and reproducibility of free historical crypto data. No strategy, no returns evaluated, no backtest,
no replay, no parameter choice. Only archive file listings and small samples from months before 2025-07 were read; no holdout-period market
observation was downloaded or parsed. Audit date 2026-11-26. Scripts: `quant/docs/phase4c/s1_scripts/` (curl + public S3 endpoint).
Machine-readable results: `s1_binance_usdt_coverage.csv` (775 USDT symbols), `s1_eligibility_counts.json` (aggregate counts). Both derive from
Binance Vision data (c) Binance, CC BY-NC-SA 4.0, attribution "Binance Vision".

## 1. Verdict in one paragraph
A point-in-time, survivorship-aware universe of >= 30 liquid USDT spot assets **can be reconstructed for free from the Binance Vision archive for
dates from 2021-01 onward** (84 eligible at a 1 M USDT median daily volume, 40 at 5 M, using only prior data and including assets delisted later),
and the archive keeps delisted symbols (253 of 775 USDT symbols have no data after 2026-10). It is **not** bias-free: single venue, listing
selection by Binance, ticker reuse and migrations, month-granular listing metadata, volume-only liquidity information (no order book), and a licence
that restricts use to non-commercial research. Before 2021 fewer than 30 assets qualify at 1 M, so the usable sample is still only about one
bull-bear cycle (2021-01 to 2025-06). No other free source was found that is better.

## 2. Source comparison matrix
| Source | Hands-on? | Coverage | Delisted/dead assets | Volume / liquidity | Quality & reproducibility | Licence / cost | Suitability |
|---|---|---|---|---|---|---|---|
| **Binance Vision archive** (S3 endpoint reachable from this environment; main host `data.binance.vision` not resolvable here) | **yes** | 3767 spot symbols, 776 USDT pairs, from 2017-08; klines 1d/1h/... monthly + daily zips | **kept** (BCC, VEN, LEND, BTT, FTT gap, UNFI ... verified); 253/775 USDT symbols end before 2026-10 | candle volume and quote volume, trades count; no order book or spread | `.CHECKSUM` per file (verified for a sample); 22 of 23 sampled 1h files clean; 1 defective file (see 4); files may be replaced upstream so hashes must be pinned at download | **CC BY-NC-SA 4.0**, non-commercial research allowed, EUR 0 | **best available**, with caveats |
| OKX public API (current dataset) | existing | candle history only through the API; no listing/delisting history | not available | volume only | already frozen with sha256; candle limits | free public data | fine as execution-venue data; **cannot** provide a point-in-time universe |
| Kraken OHLCVT archive | docs only (host blocked here) | per pair from first trade to a recent date; only intervals with trades | unconfirmed | volume | quarterly archives, unfilled gaps | Kraken terms (not read) | secondary; fewer assets; delisted unconfirmed |
| CoinGecko API (free/Demo) | docs only | coins ~17k, but free history about 1 year (sources disagree) | listings of dead coins exist but history is paywalled | volume | no archives | free tier is non-commercial; paid from ~USD 129 for long history | **unsuitable** (history depth) |
| CoinMarketCap | docs only | free tier without historical data; weekly historical snapshots page exists | dead coins appear in old snapshots | market cap, volume | terms for scraping not resolved | free tier insufficient | **unsuitable / terms unresolved** (also forbidden to substitute market-cap selection) |
| CoinPaprika free | docs only | 1 year daily, 2000 assets, 20k calls/month | - | - | - | non-commercial | **unsuitable** |
| CryptoCompare / CoinDesk Data free | docs only (host blocked) | personal plan about 365 days daily (unverified) | - | - | - | non-commercial | **unsuitable** |
| Kaggle / third-party dumps | not audited | unknown provenance | unknown | unknown | unknown | per dataset | **not usable** without provenance and survivorship proof |
Notes: most hosts were blocked from this environment (CoinGecko, CoinPaprika, Kraken, Coinbase, CryptoCompare, OKX, the main Binance host); only the Binance S3 endpoint
and GitHub were reachable, so only Binance was audited hands-on; the others rest on their documentation as returned by web search and are labelled accordingly.

## 3. Point-in-time universe reconstruction (Binance, USDT quote)
Rule (stated before looking at any counts; thresholds shown only to expose sensitivity, not selected): asset = USDT pair whose base is not a stablecoin/fiat and not a leveraged token;
eligible at date T if it has >= 60 daily candles in the 90 days before T and median daily quote volume over those days >= threshold. Uses data before T only; assets that are delisted later are
included. Counts (eligible / of which no longer present in 2026-10):

| T | >= 250 k | >= 1 M | >= 5 M | >= 25 M |
|---|---|---|---|---|
| 2018-07 | 8 / 1 | 8 / 1 | 7 / 1 | 4 / 1 |
| 2019-01 | 17 / 3 | 15 / 2 | 10 / 1 | 3 / 0 |
| 2020-01 | 41 / 9 | 27 / 4 | 9 / 1 | 2 / 0 |
| 2021-01 | 127 / 41 | 84 / 22 | 40 / 7 | 13 / 1 |
| 2022-01 | 271 / 120 | 266 / 119 | 186 / 65 | 73 / 10 |
| 2023-01 | 303 / 120 | 170 / 49 | 54 / 6 | 13 / 1 |
| 2024-01 | 345 / 130 | 267 / 88 | 112 / 22 | 31 / 2 |
| 2025-01 | 372 / 105 | 352 / 94 | 169 / 16 | 62 / 2 |
Reading: (a) >= 30 eligible assets exist at >= 1 M from 2021-01 and at >= 5 M from 2021-01 (40), before that the cross-section is too thin; (b) survivorship is large:
26 % of the 2021-01 and 45 % of the 2022-01 eligible set (at 1 M) were gone by 2026-10, versus the 8 frozen pairs which were all survivors; (c) the cross-section thins again
at high thresholds in 2023 (54 at 5 M), so any fixed threshold must be chosen from feasibility only and frozen before returns are looked at.

## 4. Data quality findings
- **Timestamps**: milliseconds (13 digits) up to 2024, **microseconds (16 digits) from 2025-01** for spot (verified: BTCUSDT 1d 2024-03 vs 2025-03; matches the README note). A loader must normalise units per file; mixing is a silent look-ahead/misalignment risk.
- **Integrity**: `.CHECKSUM` present and verified for a sample file; README warns files can be replaced, so reproducibility needs sha256 pinning of every downloaded file at download time (we already do this for OKX).
- **Sample of 23 1h files (2022-03, 11 delisted + 12 live assets)**: 22 complete (744/744 rows, no gaps, no duplicates, OHLC consistent, no zero-volume candles). One defective file: `JUVUSDT-1h-2022-03` has 2976 rows = the same 744 rows repeated 4 times (not caught by a naive duplicate-timestamp check; caught by row-count and monotonicity). Defect rate in the sample ~4 %; every loader needs row-count/monotonic/duplicate-block checks and a quarantine list.
- **Interval coverage**: 1d and 1h month lists matched for the two symbols compared; BTT ends 2022-01 in both. (Sample size is small; a full cross-interval consistency scan is part of a later stage.)
- **Symbol identity**: ticker reuse and migrations are invisible in coverage. `LUNAUSDT` has continuous monthly coverage 2020-08..2026-10 although the asset changed in 2022-05 (collapsed Terra vs the new Terra reusing the ticker; the old asset is `LUNCUSDT` from 2022-09); `FTTUSDT` has a gap 2022-11..2023-09. 9 of 775 symbols have discontinuous coverage. A point-in-time universe therefore needs an asset-identity table (ticker + epoch), built from exchange announcements; announcements could not be retrieved here.
- **Listing/delisting dates**: archive presence gives month granularity (exact first/last candle can be read from the files); official announcement dates are not available; trading may become illiquid or be halted before the last candle.
- **Liquidity**: only volume and trade counts. No order book, spread or depth: the flat 0.05 % slippage assumption cannot be validated for assets with a 1-5 M USDT median daily volume and is likely optimistic for them; the liquidity budget (10 % of median volume) is a volume proxy only.
- **Venue mismatch**: the frozen dataset is OKX; a Binance universe is a different dataset and venue, needs its own freeze, and earlier results are not comparable.

## 5. Licence, storage, computation
- Licence: Dataset Terms (v1.0, updated 2026-08-26) apply CC BY-NC-SA 4.0. Allowed: academic/personal research and "algorithmic historical backtesting for purely personal non-production research". Prohibited: live proprietary trading execution, automated commercial order generation, redistribution/sale of datasets or derived feeds, use in commercial bots or paid signals; derivatives must carry attribution and the same licence.
  Consequences: do not commit raw data to the repository (only hashes, scripts and aggregate counts; the two files committed here carry attribution); keep all use non-commercial; **any move to live execution of signals derived from this data needs a fresh licence review**. The PDF terms host was unreachable here; the text was read from the repository copy of the terms and may differ in detail from the PDF.
- Storage: 1h zipped klines about 32 KB per symbol-month; 30 assets x 66 months about 63 MB; 1d data negligible. Computation: the whole eligibility audit (about 2000 files) ran in minutes on one core; the hard cost is download time and file-hash pinning, not compute.

## 6. Unresolved blockers
1. Asset-identity (ticker reuse, migrations) cannot be resolved from archives alone; needs an announcements-based table - not found in a free machine-readable form here.
2. Single venue and Binance-selected listings: a systematic selection effect remains (assets Binance chose to list; delistings are not random).
3. No order-book data: execution realism for small-cap assets cannot be validated; slippage stays an assumption.
4. Only ~4.5 usable years with >= 30 assets: one cycle; statistical power problems of Family A remain (the data fix does not enlarge the time dimension).
5. Licence is non-commercial and forbids live trading use of the data.
6. Other sources could not be tested hands-on (network); their documentation-only assessment should be re-checked before relying on it.
7. The sample quality scan is small; a full-universe scan is required before any dataset freeze.

## 7. Updated architectural recommendations (risk layer V2 specification addendum, required before S2 implementation)
- **High-water mark is never reset.** Restarts after tier 3 change the permitted exposure, not the reference. T4 is computed exactly as originally defined on whole-run mark-to-market equity.
- **Operational safety disqualification** (new, separate from T4): reported as a distinct flag `SAFETY_DISQUALIFIED` whenever tier 3 triggers (drawdown >= 18 % or integrity breach). It disqualifies promotion independently of T4 and is never described as a breach of the 20 % threshold.
- **Deterministic state machine**: states NORMAL, REDUCED (tier 1), FLAT_COOLDOWN (tier 2), RE-ENTRY(step k), SHUTDOWN (tier 3). Transition precedence evaluated once per candle in fixed order: integrity breach > drawdown >= tier-3 limit > tier 2 > tier 1 > recovery conditions. A single candle can cause at most one transition; transitions are logged with candle time and inputs. Only SHUTDOWN has no automatic exit.
- **Repeated drawdowns during recovery**: any tier-1/2 trigger during RE-ENTRY returns to FLAT_COOLDOWN with a new cooldown and resets the step counter; a counter of consecutive failed re-entries (max 2) escalates to SHUTDOWN, which prevents halt/re-entry loops; cooldown does not shorten.
- **Recovery from a flattened cash portfolio**: with a fixed HWM the cash account cannot rise; therefore re-entry depends on time and signal, not on regaining the peak; the exposure cap during re-entry is limited by the remaining drawdown headroom (limit minus current drawdown) so that a further full-exposure loss cannot exceed the tier-3 limit.
- **Maximum cumulative loss across cycles**: the 18 % tier-3 limit is measured against the never-reset HWM, so cumulative loss across all recovery cycles is capped by construction (except gaps).
- **Gaps, delayed liquidation, no liquidity**: liquidation orders carry priority, never expire, use the shared liquidity budget; if liquidity is unavailable for N consecutive candles an integrity alarm escalates to SHUTDOWN and the open exposure is reported as unliquidated risk; losses beyond the limit due to gaps are reported as overshoot.
- **Persistence across restarts**: the state machine writes an atomic, hash-chained state file after every transition and every candle checkpoint; on start-up an unreadable, missing or inconsistent file means SHUTDOWN (fail closed).
- **Manual authorisation**: a file naming shutdown id, approver, a mandatory exposure cap and the time; any parse error, id mismatch or stale timestamp means no restart.
- **Feasibility gate refinements** (owner request): the gate must count correlated trades and overlapping positions (effective number of independent episodes via a cluster/correlation adjustment, not the raw count), report effective sample size, and propagate uncertainty of estimated volatility, correlation and win rate into a **range** for statistical power; the gate fails if the lower power bound is insufficient; it uses synthetic data and arithmetic only.
- **Ledger rules**: every diagnostic or exploratory experiment is recorded (class, purpose, whether it influenced a decision); an experiment that influenced strategy or parameter selection counts toward N and the research budget. This audit is recorded as a data audit (no returns evaluated, no selection by performance); the eventual universe rule must be frozen from feasibility counts only.

## 8. Family B reassessment (preliminary)
The data barrier is partly removed: a point-in-time cross-section of >= 30 liquid assets exists from 2021-01 on Binance. Remaining objections: one cycle only, survivorship cannot be fully removed, identity issues, high turnover with unverifiable small-cap slippage, a different venue and dataset (new freeze), and the budget/feasibility gate. **Status: still unapproved; conditionally justifiable only after the feasibility gate (with correlated-trade adjustment), an identity table and a full-universe quality scan pass.** A scientifically honest outcome may still be "not testable with credible power".

## 9. CI status (HEAD 1c6beb5, checked 2026-11-26)
Quant CI and zizmor succeeded; upstream Freqtrade CI: 17 jobs succeeded (all Linux, ARM and Windows test jobs, pre-commit, mypy, docs), 6 macOS test jobs cancelled because no runner was assigned, aggregate "Build (3.13)" fails because of them. Unresolved infrastructure item: macOS runner availability (external). The earlier Windows timing flake did not recur.

## 10. GO / NO-GO
- **S2 (risk layer V2 on synthetic scenarios, active-day statistics, reporting fixes): GO**, after you approve the specification addendum in section 7. It needs no market data and no part of the audit result.
- **Family B / any new market evaluation: NO-GO** until the feasibility gate, an identity table and a full-universe quality scan exist.
- **Binance as the future research dataset: conditional GO** for building a dataset builder with hash pinning, identity table and quality quarantine (a later stage, separate approval), accepting the licence and venue caveats.
