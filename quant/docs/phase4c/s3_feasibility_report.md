# S3 - Data Feasibility Gate: report

Scope: data feasibility only. No returns evaluated, no strategy, no backtest, no market replay, no parameter choice, no dataset builder, **no holdout access** (see 7). Audit date 2026-11-26.
Data (c) Binance, CC BY-NC-SA 4.0, attribution "Binance Vision"; this repository contains only hashes, scripts and aggregate counts derived from it.
Pre-registration: GO/NO-GO criteria `s3_criteria.json` were committed (`325aa33`) **before** any file was downloaded or analysed; the evaluation code reads thresholds from that file.

## 1. Verdict
**CONDITIONAL GO for Binance Vision (development period 2017-2025-06) as a research dataset**, i.e. all 12 pre-registered gates pass, but only after documented exclusions/quarantine that a later builder must implement (identity-flagged assets, 3 defective daily files, 2 defective hourly files). It is **NO-GO for any use beyond personal, non-commercial, non-production research** (licence) and **not an answer to the statistical-power problem** (one cycle). Full gate table in 3; recommendation in 9.

## 2. What was done (reproducible)
Scratch directory `RAW` (not committed, 185 MB for 22 k files).
```bash
cd quant/docs/phase4c/s3_scripts
python fetch.py RAW 1d all                          # 21 616 requested symbol-months, S1 symbol list, months < 2025-07 only
python analyze.py sample RAW sample.json            # seeded (20261126) hourly stratified sample -> 369 files
python fetch.py RAW 1h sample sample.json           # 369 files; 738 requests in 17 s = 43.4 req/s
python analyze.py RAW result.json pins.tsv.gz 43.4 [true]   # deterministic; run twice and cmp
```
Committed outputs: `s3_audit_result.json` (sha256 `c1c714250f7d65a2f754aea760a703ce4aa0d924cbd22fbe528a25844813fc96`), `s3_pin_manifest.tsv.gz` (sha256 `3d02e9d77f4da45c0dd393338a6aa96b4cde4c2e766d3a703c84179c1358ccb3`; interval, symbol, month, HTTP status, sha256, size of **every** file, 21 616 daily + 369 hourly lines), `s3_hourly_sample.json`. Primitives: `quantlab/data_audit.py` (pure functions) with 15 synthetic tests (`tests/test_data_audit.py`): every defect class, microsecond timestamps, partial months, point-in-time no-lookahead (mutating data at/after the date changes nothing), holdout guard, and every gate can fail (each criterion flips the verdict to NO_GO when broken).
Reproducibility (P1): two independent full analysis runs produced byte-identical JSON and pin manifest (`analysis_hash a068efe9...`).
Scope of what a free-standing "dataset builder" would add (explicitly **not** built): resumable download with rate limiting, epoch splitting, quarantine application, hash-pinned storage.

## 3. Pre-registered gates and measured results
| Gate | Criterion | Measured | Result |
|---|---|---|---|
| L1 | licence read from primary source; backtesting for personal non-production research permitted | Vision Dataset Terms v1.0 read (4.1); see licensing findings | pass (manual determination) |
| L2 | paper/live use of derived signals | not permitted or not covered (4.1-4.4) | constraint (reported) |
| I1 | sha256 = published .CHECKSUM >= 0.999 | **1.0000** (21 518 daily + 369 hourly files all match; 98 requested months are absent = coverage breaks, 0 checksum fetch failures) | pass |
| Q1 | daily files quarantined <= 2 % | **3 of 21 518 = 0.014 %** (AUDUSDT 2020-11 `ohlc_inconsistent`; BTTUSDT 2019-01 and 2019-02 `negative_volume`) | pass |
| Q2 | hourly fatal-defect rate, 95 % Wilson upper bound <= 10 % | 2 of 369 (BCCUSDT, NEOUSDT 2018-02, `misaligned_timestamp`: 43 candles offset by ~28 min (1 696 s) from the hourly grid inside the month); upper bound **1.95 %** | pass |
| U1 | >= 30 PIT-eligible at 1 M USDT at 100 % of month starts 2021-01..2025-06 (54 dates) | min **84** (2021-01); 301 at 2025-06 | pass |
| U2 | >= 30 at 5 M at >= 80 % of dates | **100 %** of dates; min 40 (2021-01), 54 at 2023-01 | pass |
| U3 | U1 after removing identity-flagged assets | min **83** (flags remove at most 9 assets at any date) | pass |
| S1 | delisted symbols retained | 252 of 252 delisted symbols with dev data present and checked (share 1.0) | pass |
| S2 | survivorship reported | see 5 | reported |
| R1 | each regime label >= 6 month starts with >= 30 eligible | bull 27, sideways 18, bear 9 | pass |
| P1 | identical output of two runs; every file pinned | identical; 21 985 requests pinned (21 518 + 369 files with sha256, 98 absent months with HTTP 404) | pass |
| C1 | 1h storage of the 1 M-eligible universe <= 2 GB and download <= 3 h | **0.43 GB**, 13 181 symbol-months, 26 362 requests = **0.17 h** at the measured 43 req/s | pass |
| T1 | time dimension (info) | years with >= 30 eligible at all month starts: 2021-2025 (5 years); regime episodes in 5 | reported |
Verdict by the pre-registered rule: all gates pass, exclusions required -> **CONDITIONAL GO**.

## 4. Data quality findings (detail)
- **Daily**: 21 518 files, 593 symbols. Fatal defects 3 files (above). Non-fatal: 9 files with internal gaps (missing candles share inside first..last candle **0.0073 %**), 4 zero-volume files, 4 files with flat zero-volume candles. After correcting my first draft (leading/trailing absence inside a listing/delisting month had been counted as a gap, inflating gaps to 783 files), the audit counts only gaps *between* the first and last candle; partial months are reported separately (`leading_missing`, `trailing_missing`).
- **Hourly sample** (369 files, stratified 44 per year 2018-2025, 17 in 2017 = all available pairs; the sample size is 369 not the 400 preregistered because 2017 has only 17 files): 2 fatal (above); 82 files have gaps (missing candles inside span **0.24 %**, of which 24 files lose >= 24 candles, i.e. exchange downtime/maintenance days), 39 files with zero-volume and flat candles. The S1 defect class "whole file repeated 4x" (JUVUSDT) did not occur in this sample; it is detected by the `repeated_block` check (synthetic test), and S1's 1-in-23 should be read as small-sample noise, not a rate. Microsecond timestamps (2025-01..06) were present in the sample and handled.
- **Out-of-order / duplicate / malformed**: none occurred in the audited files; all classes are covered by synthetic tests, so absence is a measurement, not a blind spot (the detectors are proven to fire).
- **Alignment**: daily candles aligned to UTC midnight in all but the files flagged; the 2018 hourly files show the only misalignment.
- **Limits**: hourly quality was sampled, not scanned in full (369 sampled files); the bound in Q2 is statistical. A full hourly scan belongs to the builder stage.

## 5. Universe, identity, survivorship, regimes
- **PIT liquidity eligibility** (S1 rule, only candles strictly before the date, no look-ahead; leveraged tokens/stable/fiat bases excluded by S1's name rule):

| Month start | >= 1 M | after identity exclusions | >= 5 M | after exclusions |
|---|---|---|---|---|
| 2021-01 | 84 | 83 | 40 | 40 |
| 2021-07 | 213 | 207 | 176 | 172 |
| 2022-01 | 266 | 258 | 186 | 181 |
| 2022-07 | 267 | 259 | 120 | 116 |
| 2023-01 | 170 | 167 | 54 | 53 |
| 2023-07 | 189 | 187 | 67 | 67 |
| 2024-01 | 267 | 263 | 112 | 110 |
| 2024-07 | 367 | 361 | 125 | 123 |
| 2025-01 | 352 | 345 | 169 | 165 |
| 2025-06 | 301 | 297 | 109 | 109 |
These reproduce S1's counts exactly (84/266/170/267/352), which is an independent consistency check of two separately written implementations. Liquidity is **volume-only** (no order book, spread or depth).
- **Identity/migration flags** (data-derived rules: >= 2 missing consecutive months, or a close-to-close daily ratio >= 10x or <= 0.1x): 10 assets flagged among eligible-type assets, plus 26 leveraged/stable symbols (not assets by the S1 rule). The flags are *candidates*; no announcement source was reachable, so none is verified:
BNX (2023-02-22, x0.009), COCOS (2021-01-23, x1295), CVC (coverage gap 2022-12..2023-05), DREP (2021-04-02, x108), FTT (gap 2022-11..2023-09), LUNA (2022-05-11/12 collapse and 2022-05-31 x177 400: ticker reuse), QUICK (2023-07-21, x0.0008), SUN (2021-06-18, x0.0012), VEN (gap 2018-07..2018-10 and 2018-10-19 x5.5e-5), VIDT (2022-11-09, x0.05).
The detector catches the known cases (LUNA ticker reuse, FTT gap, VEN migration) and several redenomination-like jumps, so it is useful as an alarm; it **cannot resolve** whether a jump is a crash, redenomination or migration. **Important bias note:** excluding these assets for the whole sample uses future information (an event in 2023 removes the asset in 2021). That is acceptable for this *feasibility* gate (it only shows depth survives the exclusion) but a builder must instead split identities into epochs and apply a flag only **from the event date forward** (point-in-time), otherwise the exclusion itself introduces look-ahead and survivorship bias.
- **Leveraged-token name rule false positive**: S1's regex `(UP|DOWN|BULL|BEAR)$` (base length > 4) wrongly excludes SYRUP (a real asset). The audit lists the 49 excluded bases (`lev_regex_excluded_bases_with_dev_data`); 48 are leveraged tokens. The rule is kept unchanged to keep S1 comparability; a builder needs an explicit exclusion list instead of a regex.
- **Survivorship** (delisted by 2026-10 among the PIT-eligible at 1 M): 2021-01 22/84 (26 %), 2022-01 119/266 (45 %), 2023-01 49/170 (29 %), 2024-01 88/267 (33 %), 2025-01 94/352 (27 %). The archive keeps delisted symbols, so a survivorship-free universe is reconstructable; any universe built only from currently listed assets would be strongly biased. Residual selection bias: Binance chooses what to list and delist.
- **Regimes** (descriptive rule fixed in the criteria; BTC trailing 180-day return >= +30 % bull, <= -20 % bear): month starts bull 27, sideways 18, bear 9 (all with >= 30 eligible assets). Episodes: bull 5, sideways 7, **bear only 2** (1 month and 8 months). The coverage gate passes, but the number of independent bear episodes is 2, so regime-conditional claims will have extremely low power.

## 6. Provenance, integrity, resources
- Every file pinned (sha256 plus the published `.CHECKSUM`, which matched in 100 % of cases). Pins detect later upstream replacement (README states files may be replaced); they cannot prove the archive itself is correct.
- Zip sizes: 1h mean 32.6 kB per symbol-month; daily files a few kB. Whole 1d dev scan: 21.6 k files, 185 MB local, tens of minutes of wall time with 32 download threads; analysis single core, about a minute. 1h data of the 1 M-eligible universe: 0.43 GB (estimate = eligible assets per month start x mean file size; labelled estimate). Bandwidth measured 43 req/s (small files, latency-bound), 0.17 h estimated. No GPU, no paid service, EUR 0.
- Dependencies: standard library + project environment (`numpy` not needed by the audit). Network: only the Binance S3 endpoint (the other hosts are unreachable here).

## 7. Holdout compliance
- All requests were built from the S1 symbol table with `min(last_month, 2025-06)`; `fetch.py` raises on any month >= 2025-07 (`guard`, unit-tested); `data_audit.assert_dev_month` likewise. No file name or content from 2025-07 onward was requested, listed, downloaded or parsed in S3.
- S3 reused the S1 coverage table, which records only last month of existence per symbol (S1, accepted). This is availability metadata used for the survivorship report (is a symbol still present in 2026-10); no candle, price or volume from the holdout period was read. This is the one place holdout-era *existence* information enters the audit; it influences reporting only, never eligibility or selection.
- Development-period prices and volumes were read for data quality, eligibility and descriptive regime labels only; no return or performance of any strategy was computed (BTC trailing return is used only to label coverage). Ledger entry S3 added via amendment A6 (counts toward N: no).

## 8. Licensing summary (details: `s3_licensing_findings.md`)
Primary text read (Binance Vision Dataset Terms v1.0, 2026-08-26, sha256 `99c4921d...`): historical research and "algorithmic historical backtesting for purely personal non-production research" **permitted**; live trading, automated commercial order generation, commercial products/bots, signal distribution, redistribution of feeds **prohibited**; derived data are "strictly governed" by the same terms; paper trading is not in the closed list of permitted uses -> treat as not permitted/unclear. The Binance Terms of Use and all alternative sources' terms could not be read from this environment, so no alternative is verified; none is recommended.

## 9. Unresolved risks
1. **Licence ceiling**: the whole project may only ever use this data for non-commercial, personal, non-production research. Paper/live trading or sharing signals needs a separate licence decision (and probably another source).
2. **Identity**: no announcement-based identity table; data-derived flags are candidates only, and whole-sample exclusion is look-ahead (epoch-splitting needed).
3. **Liquidity realism**: volume-only; no order book; slippage of 1-5 M USDT/day assets stays an assumption.
4. **Time dimension**: effectively one cycle (2021-2025), only 2 bear episodes; the data work cannot enlarge it. Power problems of Family A style tests persist.
5. **Hourly quality** sampled (369 files), not exhaustively scanned; defect classes seen only in 2018 samples; micro-timestamp era only partly sampled.
6. **Archive mutability and withdrawal** (terms 5.3, README update log): pins detect change, not availability.
7. **Single venue and Binance-selected listings**; the earlier frozen dataset (OKX) is a different venue and not comparable.
8. **Alternatives unverifiable** from this environment.
9. **Heuristic rules inherited from S1**: leveraged-token regex false positives (SYRUP); regime rule is a descriptive convention.
10. Legal reading is an engineering reading, not legal advice; Terms of Use unread.

## 10. GO / NO-GO
- **GO (conditional)**: build, as a separately approved next stage, a hash-pinned, rate-limited, resumable **dataset builder with identity epochs, quarantine application and a full-universe hourly quality scan**, restricted to the development period, non-commercial. Preconditions: owner acceptance of the licence ceiling (8) and of one-cycle statistical limits (9.4).
- **NO-GO** until further approval: Family B (also needs the identity table, full hourly scan and a feasibility/power gate with correlated-trade adjustment), any market evaluation, any holdout access, any paper/live use of the data, any change to risk parameters or T1-T10.
- The risk-layer integration (S3-4) is design-only (`s3_risk_integration_plan.md`) and awaits its own approval; it needs no market data.
