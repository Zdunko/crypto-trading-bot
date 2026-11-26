# Holdout isolation: what the evidence supports (and what it does not)

Holdout = every market observation on or after 2025-07-01. Statement date 2026-11-26.

## Supported by evidence
1. **S4**: no URL, key, size or byte of a month >= 2025-07 was requested or parsed after the append-only log began (77 368 logged requests, 0 holdout URLs); every stored file and sidecar of the dataset is a month <= 2025-06 (store audit, 43 036 files); the latest candle in any table opens 2025-06-30; the URL guard that refuses holdout months and unbounded listing prefixes is unit-tested.
2. **S3**: downloads were built from month lists capped at 2025-06 and went through a guard (`fetch.py`, unit-tested); the 22 k stored files are months <= 2025-06 (pin manifest).
3. No candle, price or volume value from the holdout period entered any universe rule, threshold, classification or table, and no return of any strategy was computed on it.

## Exposures that exist (not "isolated")
1. **S1** listed archive directories including keys and sizes of months after 2025-06 and produced `s1_binance_usdt_coverage.csv` with `last_month` values up to 2026-10. S1's statement that it read no holdout market observation rests on its report; it ran without a request log or guard.
2. **S3** used that table to define the symbol list (`first_month`) and to *report* survivorship (252 delisted by 2026-10 retained; cohort delisting shares). This is knowledge of post-cutoff delistings; it did not enter eligibility, thresholds or exclusions, but it was used in the S3 conclusions about survivorship.
3. **S4** read the archive root listing: the names of 776 USDT symbols, including 183 that have no development-window file (they never entered any table, but their names were visible to the builder).
4. **Request log gap:** the first ~25 minutes of the S4 download (symbol discovery and about a quarter of the files) are not in the log. For those requests the evidence is the code guard and the store audit, not a record.
5. The owner-level decision that the Binance archive is a viable research source was informed by S1's survivorship picture (including post-cutoff delistings).

## Not claimed
- That no information about the post-cutoff period reached the project (metadata and symbol names did).
- That S1 was guard-protected, or that every S3/S4 request is auditable.
- That decisions made after seeing S1's listing were independent of the future state of the archive.
- Anything about the separate OKX holdout (2025-07-01 .. 2026-11-25) beyond what `PROJECT_STATUS.md` records.
## Operating rule going forward
Any new stage must request only months <= 2025-06 through a guarded, logged client from the first request, must not read post-cutoff listing metadata, and must state these exposures instead of claiming full isolation.
