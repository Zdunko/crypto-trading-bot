# S4 - Point-in-time dataset builder: report

Scope: development window only (months 2017-08 .. 2025-06, cutoff 2025-06-30). No holdout month was requested, listed, downloaded or parsed. No return, PnL, backtest, strategy signal or parameter choice exists anywhere in S4. Data (c) Binance, CC BY-NC-SA 4.0, attribution "Binance Vision"; non-commercial research use only (see `s3_licensing_findings.md`, `s4_licensing_alternatives.md`).
Pre-registration: `s4_criteria.json` (commit `58ba372`) was committed before any S4 code or download; thresholds are read from it by `pit_run.evaluate` and were not changed.

## 1. Result
**All 16 pre-registered gates pass -> GO** for the dataset as a research dataset (non-commercial, development window). Deterministic dataset hash `462288b14415edeb3aec73c9400fd8af977faf3105c1396f6f96d4fe3d4069be` (two independent builds, separate processes, byte-identical outputs). `quant/dataset/gates.json` has the machine-readable evaluation. Reconciliation notes for S3 (11 gates, 14 criteria; final CI on `1975df7`) are in `s3_addendum.md`.

## 2. What was built (`quant/quantlab/`)
| Module | Role |
|---|---|
| `pit_fetch.py` | Single request choke point (`Client`): holdout URL guard (refuses any month >= 2025-07 and any listing prefix that could contain one, and rejects holdout keys in responses), global token-bucket rate limiter (30 req/s default), retry with back-off, append-only timestamped request log; `Store` with commit-last `.meta.json` markers (interrupted/corrupted files are redone), sha256 of every file against the published `.CHECKSUM` (one refetch, then `checksum_mismatch` quarantine); unresolved failures raise (fail closed) and are never persisted |
| `pit_universe.py` | File scan with closed reason-code set, identity epochs, explicit classification (fail-closed), causal liquidity eligibility, deterministic tables and hashes |
| `pit_run.py` | `build` (tables + manifest), `validate` (causality/perturbation/stability evidence), `evaluate` (gates) |
| `pit_build.py` | CLI: `discover`, `fetch`, `build`, `validate`, `gates` |
| `dataset/` | `asset_classification.json` (input), `dev_window_listing.json` (input: symbol -> months), outputs `files.csv.gz` (every file: status, reasons, rows, missing candles, warnings, sha256, published sha256, size), `epochs.csv.gz`, `membership.csv.gz`, `manifest.json`, `quality_summary.json`, `validation.json`, `gates.json`, `provenance_run.json` |
Reproduce: `python -m quantlab.pit_build fetch RAW` then `build RAW OUT`, `validate RAW OUT`, `gates RAW OUT OTHER_BUILD N_TESTS` (run from `quant/`). Synthetic tests: `tests/test_pit_fetch.py`, `tests/test_pit_universe.py` (25), plus the existing suite.

## 3. Acceptance gates
| Gate | Criterion (short) | Measured | Result |
|---|---|---|---|
| B1 | no holdout request/key | 77 368 logged requests, 0 holdout URLs; all 43 036 stored files/metas are months <= 2025-06 (store audit). Limit: the append-only log started after about 25 min of the run (see 8) | pass |
| B2 | no post-cutoff influence | latest candle open 2025-06-30; synthetic test: a symbol with only post-cutoff data changes no membership | pass |
| F1 | integrity | 43 025 files sha256 == published checksum; 11 quarantined (reason codes below); 0 unresolved fetch failures | pass |
| F2 | resumability | synthetic: interrupted+resumed build identical to clean; real: fetch was killed with SIGKILL and restarted, crashed twice on real defects and resumed; every re-downloaded daily file matches the S3 pins | pass |
| F3 | rate limit <= 1.25 x 30/s | peak 32 requests in any 1-s window (recomputed from the log of all runs), final run 30 | pass |
| Q1 | complete hourly scan | 21 518 daily months -> 21 518 hourly months requested and classified (21 510 ok, 8 quarantined, 0 absent) | pass |
| Q2 | explicit reasons | 0 unreasoned quarantines | pass |
| Q3 | detectors complete | each reason code produced by a synthetic file (test) | pass |
| I1 | epoch tables causal | 8 seeded cutoffs: epochs from truncated data equal the full-data table | pass |
| I2 | no future-dependent exclusion | 12 seeded dates: membership on data truncated at T equals the full-data membership at T | pass |
| I3 | classification explicit | 593 of 593 symbols in the table, 0 unreviewed | pass |
| U1 | causal liquidity | 20 seeded dates x 6 adversarial modes (volume x1000, volume 0, price x1000, delete, duplicate, random) applied to every candle not completed at T: membership identical in all 120 cases | pass |
| U2 | survivorship preserved | 229 epochs ended before 2025-06; 126 of them were 1 M members at some date | pass |
| U3 | depth | min 84 eligible at 1 M (2021-01); min 40 at 5 M; no global exclusions | pass |
| R1 | reproducibility | two builds, separate processes: identical hash and byte-identical files; archive stability: 21 518 of 21 518 re-downloaded daily files have the identical sha256 as the S3 pins | pass |
| M1 | manifest completeness | the dataset hash is recomputed from the files on disk and equals the manifest | pass |
Report-only: X1 (cross-interval): first-candle day agrees for 593/593 symbols; daily volume equals the sum of hourly volume within 1e-6 in 20 479 of 21 508 compared months (95.2 %); the 1 029 inconsistent months (4.8 %) are not explained (hourly gaps are one candidate) and are reported, not filtered.

## 4. Coverage and quality statistics
- 593 USDT symbols with development-window files (776 USDT symbol names were returned by the archive; the 183 without a development-window file never enter), 43 036 files (21 518 daily + 21 518 hourly), 636 identity epochs, 21 139 membership rows (2 thresholds x 94 month starts).
- Quarantine (11 files, 0.026 %): daily 3 (AUDUSDT 2020-11 `ohlc_inconsistent`; BTTUSDT 2019-01 and 2019-02 `negative_volume`); hourly 8 (AUDUSDT 2020-11 `ohlc_inconsistent`; BCC, BNB, BTC, ETH, LTC and NEO 2018-02 `misaligned_timestamp`, i.e. the same Feb-2018 off-grid timestamps for six majors; JUVUSDT 2022-03 `duplicate_timestamp|out_of_order|repeated_block`, the 4x repetition found in S1). The complete 1h scan therefore found a defect class the 369-file S3 sample could not size: one systematic month (2018-02) across the oldest majors.
- Warnings (not fatal): daily 9 files with internal gaps (47 missing candles), 4 zero-volume files; hourly 2 892 files with internal gaps (10 607 missing candles inside spans; 34 files lose >= 24 candles), 1 586 files with zero-volume/flat candles.
- Depth (eligible epochs, causal rule, no global exclusions):

| Month start | S4 >= 1 M | S3 >= 1 M | S4 >= 5 M | S3 >= 5 M |
|---|---|---|---|---|
| 2021-01 | 84 | 84 | 40 | 40 |
| 2021-07 | 211 | 213 | 174 | 176 |
| 2022-01 | 265 | 266 | 185 | 186 |
| 2022-07 | 265 | 267 | 118 | 120 |
| 2023-01 | 168 | 170 | 53 | 54 |
| 2023-07 | 188 | 189 | 66 | 67 |
| 2024-01 | 267 | 267 | 112 | 112 |
| 2024-07 | 367 | 367 | 125 | 125 |
| 2025-01 | 352 | 352 | 169 | 169 |
| 2025-06 | 301 | 301 | 109 | 109 |
The small differences (at most 2) come from the corrected classification (BULL, BEAR, AUD, BKRW were treated as assets in S1/S3) and from epoch restarts that S3 did not apply.
- Survivorship at 1 M, share of members that had ended before 2025-06: 2021-01 16/84, 2022-01 85/265, 2023-01 32/168, 2024-01 53/267, 2025-01 37/352. Membership exposes `days_since_last_candle`; the S1/S3 rule (60 of the last 90 days) keeps an ended asset eligible for up to about 30 days after its last candle, so consumers must apply their own tradability recency rule.

## 5. Identity epochs (historically available information only)
Rules (fixed in the criteria): a new epoch starts at the first candle after >= 2 whole calendar months without a candle, or at a close-to-close ratio >= 10 or <= 0.1 versus the previous candle; each break uses only candles up to the breaking one, and eligibility history never crosses an epoch boundary (a new epoch must earn a fresh 60-of-90-day history). No whole-sample exclusion exists; the S3 global exclusion (a 2023 event removing an asset in 2021) is gone, and I1/I2 test exactly that property.
Events: 43 breaks (gap 8, jump_down 14, jump_up 21). Among assets (not leveraged/stable): BNX 2023-02-22 down, COCOS 2021-01-23 up, CVC gap to 2023-05-12, DREP 2021-04-02 up, FTT gap to 2023-09-22, LUNA 2022-05-11 and 2022-05-12 down and 2022-05-31 up (collapse then ticker reuse), QUICK 2023-07-21 down, SUN 2021-06-18 down, VEN gap to 2018-10-19, VIDT 2022-11-09 down. 28 breaks belong to leveraged tokens (26 jumps, 2 gaps) and 3 gaps to stablecoins.
What this does **not** do: it cannot tell a crash from a redenomination or a migration (all become a new epoch, conservatively), it cannot link the old and new epoch of one economic asset (no announcement source reachable), and it is blind to ticker reuse without a price jump or gap. A true identity table from announcements remains unresolved.
Classification: explicit table keyed by symbol (593 entries: 522 asset, 50 leveraged_token, 17 stablecoin, 3 fiat, 1 commodity_token). It replaces the regex; the regex survives only as an alarm (JUP and SYRUP match it and are explicitly reviewed as assets). Evidence level `curated-unverified` (ticker semantics, not checked against exchange announcements). Corrections to S1/S3: BULL and BEAR (short leveraged names the old length rule missed), AUD and BKRW (fiat/stable pairs missed) are now excluded; SYRUP was wrongly excluded and is now an asset.

## 6. Causality evidence
The membership function sees only candles with `open + 1 day <= T` of the epoch containing the latest such candle. Evidence: (a) property tests on seeded random markets (gaps, jumps, zero volume): prefix invariance and six adversarial future modes, 8 seeded markets x 3 dates x 6 modes = 144 perturbed recomputations, plus epoch-prefix checks on 12 seeded markets x 3 cutoffs; (b) the same on the real data: I1 (8 cutoffs), I2 (12 dates), U1 (20 dates x 6 modes = 120 perturbed recomputations of the whole universe), all identical; (c) a symbol with only post-cutoff data cannot change membership; (d) the candle opening exactly at T is not counted.

## 7. Licensing (documentation only; `s4_licensing_alternatives.md`)
Verified from a primary text: only the Binance Vision Dataset Terms (research and personal non-production backtesting permitted; live, commercial, signal distribution prohibited; derived models "strictly governed"). Everything about Binance public API terms, OKX (Section 9 market-data restrictions exist, text unread), Coinbase (limited revocable licence), Kraken and commercial vendors is search-summary level or unknown and is listed as unresolved questions (model fitted on Vision data used live; paper trading; commercial meaning for the end goal; regulatory side). No source other than Binance Vision is cleared for paper, live or production use.

## 8. Limitations and unresolved risks
1. **Licence ceiling** (unchanged): this dataset supports research only; the production-capable end goal needs a licence-cleared data path, not yet identified.
2. **Identity**: no announcement-based table; epochs are conservative and cannot link economic identity.
3. **Liquidity** is volume-only; no order book, spread or depth; slippage remains an assumption.
4. **One cycle** (2021-2025, 2 bear episodes); the dataset cannot enlarge it.
5. **B1 evidence gap**: requests made before the append-only log existed (symbol discovery and about the first quarter of the downloads) are not in the log. Evidence for them is the unit-tested URL guard plus the store audit (every stored month <= 2025-06) and the fact that no holdout file name was ever constructed (listing prefixes are year/month-bounded). Not provable after the fact request by request.
6. **Classification** is curated and unverified; new bases fail the build until reviewed.
7. **Fetch code revisions**: the download phase ran partly on earlier revisions of `pit_fetch.py`/`pit_build.py` (transport error handling, request logging); build, validate and gates ran on the final code (manifest `code_sha256`). Content integrity does not depend on it (every file is hash-checked against the published checksum and matches the S3 pins).
8. **Archive mutability**: pins detect later replacement only.
9. **X1**: 4.8 % of months show daily/hourly volume mismatch, unexplained.
10. Single venue and Binance-selected listings; Binance may withdraw or alter files (terms 5.3).
11. The root listing revealed the **names** of 183 symbols that exist only after 2025-06 (no keys, dates, sizes or bytes); they never entered any table, and the builder's candidate set is by construction limited to symbols with a development-window file.

## 9. Recommendation
**GO** (research-only): use `quant/dataset/` as the point-in-time universe/quality layer for the next stage. **Not cleared**: any market evaluation, Family B, holdout access, paper/live use or production data path; each needs its own approval, and the data path for production needs the written licence answers listed in `s4_licensing_alternatives.md` first.
