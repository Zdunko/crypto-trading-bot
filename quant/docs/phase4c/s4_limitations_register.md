# S4 limitations register (recorded without changing any acceptance criterion)

Status values: **open** (unresolved), **accepted** (owner accepted for research use), **infrastructure** (outside our code). Nothing here edits `s4_criteria.json` (hash fixed in `protocol/s4_freeze_record.json`).

| ID | Limitation | Evidence | Effect | Status |
|---|---|---|---|---|
| L-CI-MAC | The 6 `macos-15`/`macos-26` upstream test jobs were **cancelled: no runner was ever assigned**, on every recent commit including the frozen `e2d71c6`; the aggregate `Build (3.13)` fails only because of them | job lists of runs 45784252631 and 45847633065 (`runner_name` null, no steps run) | **macOS is untested; these are not passed tests**; Linux and Windows jobs are green | **open, infrastructure** (external runner availability) |
| L-LIC | Binance Vision is research-only; production use not cleared | `s3_licensing_findings.md`, `s4_licensing_alternatives.md` | any production data path is undefined | open (roadmap in `s5_production_data_licensing_roadmap.md`) |
| L-ID | No announcement-based identity table; epochs are conservative and cannot link economic identity | `s5_investigations.md` section 2 | migrations/redenominations appear as new assets; ticker reuse without a jump or gap is invisible | open |
| L-LIQ | Liquidity is volume-only (no order book, spread, depth) | S1/S4 | slippage stays an assumption | open |
| L-CYC | One market cycle (2021-2025), 2 bear episodes | S3 T1 | low power for regime-conditional claims | accepted |
| L-X1 | 4.8 % of symbol-months show daily/hourly volume disagreement, concentrated in 5 months; cause unproven (matches upstream "fixed inconsistent data" periods) | `s5_investigations.md` section 1 | eligibility unaffected on the data (0 of 21 139 decisions change); execution liquidity budgets may be mis-stated for affected months | open |
| L-LOG | The append-only request log began after about the first 25 minutes of the S4 download; symbol discovery and the first fetch passes are not logged | `dataset/provenance_run.json` | B1 cannot be proven request by request for those requests; rests on the unit-tested URL guard and the store audit | open |
| L-NAMES | The S4 root listing returned the **names** of 183 USDT symbols with no development-window file (listed later); S1/S3 also saw post-cutoff file names/sizes and `last_month` values | `s5_holdout_isolation_statement.md` | holdout isolation is of *market observations*, not of all metadata | open |
| L-CLASS | Asset classification is curated from ticker semantics, unverified against announcements | `dataset/asset_classification.json` | possible mislabels (e.g. wrapped/staked tokens kept as assets) | open |
| L-REV | The download phase ran partly on earlier code revisions (transport error handling, logging); build/validate/gates ran on the final code | `provenance_run.json` | no content effect (checksums verified, S3 pins match) | accepted |
| L-MUT | Archive files can be replaced or withdrawn by the provider | README update log, terms 5.3 | pins detect replacement only | accepted |
| L-STALE | Membership keeps an ended asset eligible up to ~30 days after its last candle (S1/S3 60-of-90 rule); consumers must apply a recency rule (S5 loader default: 3 days) | S4 report section 4 | stale members if unfiltered | mitigated in S5 loader |
| L-SINGLE | Single venue, Binance-selected listings; differs from the earlier OKX dataset | S1 | venue and survivorship-by-listing bias | accepted |
| L-FAMA | Family A stays rejected; Family B unapproved; no market evaluation exists for the risk layer | PROJECT_STATUS | no performance claim of any kind | accepted |
| L-S3GATES | S3 report said "12 gates"; correct is 11 gates / 14 criteria | `s3_addendum.md` | wording only | closed |
