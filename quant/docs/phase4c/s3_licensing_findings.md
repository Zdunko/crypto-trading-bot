# S3-3: Licensing verification (Binance Vision and alternatives)

Not legal advice; a technical reading of primary texts by an engineering agent. Audit date 2026-11-26.

## 1. Primary sources actually read
| Source | How read | Fingerprint |
|---|---|---|
| `binance/binance-public-data` `TERMS_AND_CONDITIONS.md` ("BINANCE VISION DATASET TERMS", v1.0, last updated 2026-08-26) | `raw.githubusercontent.com/binance/binance-public-data/master/TERMS_AND_CONDITIONS.md` (the README's "Dataset Terms" link) | sha256 `99c4921dbe023cd68c1a447775707d621453cc78aec6ac0bfe2e6c06a5114ee0` (9807 bytes) |
| same repo `README.md` (dataset description, CHECKSUM, update log, "Licence: MIT") | same host | sha256 `2e133d9945a9263a02781369078e72805eff074680f305cd5460016471c6caad` |
| Binance Terms of Use (`binance.com/en/about-legal/terms`), incorporated by reference (clause 1.2) | **not readable**: host unreachable from this environment (also for a delegated fetch: DNS failure) | - |

The terms text is the authoritative statement and is more specific than S1's summary. Where the two differ, this document governs. The README's "Licence: MIT" refers to the repository's scripts; the **data** are under CC BY-NC-SA 4.0 via the dataset terms (clause 3.1). The Terms of Use could not be read; clause 1.5 says the dataset terms prevail on conflict "with respect to the services contemplated", so the unread text is unlikely to widen the permissions, but that is an inference.

## 2. Clause readings (quotations are short, from the file above)
- 3.1/3.2: data are provided under **CC BY-NC-SA 4.0**; agreement is deemed upon "downloading, caching, querying, or otherwise utilizing". 3.3: where both impose obligations "the stricter obligation shall apply". 3.4: "Commercial licensing is strictly excluded ... any commercial utilization requires a separate, written enterprise data license agreement".
- 4.1: permitted non-commercial uses are "**limited to** academic research, non-monetized open educational projects, algorithmic historical backtesting for purely personal non-production research, and non-commercial open-source data science evaluations".
- 4.2: no "live proprietary trading execution, automated commercial order generation, or signal distribution to third parties for direct or indirect compensation".
- 4.3: no licensing, sale, hosting or commercial exploitation of the Datasets "or any derivative real-time or historical data feeds". 4.4: no integration into commercial financial products, hedge-fund tools, paid newsletters, "commercial trading bot platforms". 4.5: redistributed derivative works need attribution to Binance Vision and the identical CC BY-NC-SA 4.0 licence.
- 2.4: "any data derived from, calculated with, or extracted from the Datasets (including charts, models, and derivative analytical indicators) is strictly governed by these Vision Dataset Terms" - so derived signals are **not** outside the terms.
- 1.4: Binance may amend at any time; an amendment applies prospectively to Datasets made available afterwards and "does not affect your rights to Datasets already downloaded under the terms in effect at the time of download".
- 5.3: Binance may modify, redact or discontinue any pair, dataset or endpoint without notice (availability/reproducibility risk; pin and archive hashes).
- 7.1/7.2: abide by rate limits; no scripts "designed to circumvent rate restrictions". The S3 audit used 32-48 parallel connections to the public S3 endpoint with retry back-off; it does not circumvent any published limit (none is published in the terms), but a production builder should be rate-limited, resumable and cache-first.
- 8.2/8.3: no implication of Binance sponsorship; do not use the Binance names to market applications or signals.

## 3. Use-case classification
| Use | Assessment | Basis |
|---|---|---|
| Historical research (non-commercial, personal) | **Permitted** | 4.1 (academic/personal research, open data-science evaluation) |
| Backtesting, personal, non-production | **Permitted** | 4.1 names "algorithmic historical backtesting for purely personal non-production research" |
| Public repository with *aggregate* results, hashes, scripts, attribution | **Permitted with conditions** | 4.5: derivatives need attribution and the same licence; do not commit raw or reconstructable candle data; committed aggregates carry the attribution line |
| Derived signals used for **non-production** research output | Permitted (they are research output) | 2.4 + 4.1 |
| Derived signals **distributed** to others, or used to run an automated order generator, or bots | **Prohibited if for compensation or commercial; not covered otherwise** | 4.2, 4.4, 3.4 |
| **Paper trading** (simulated orders forward in time) fed by Binance Vision data | **Not listed in 4.1 (a closed list) -> treat as not permitted/unclear**. Note also that Vision is an archive (daily/monthly files) so a live paper loop would need another real-time source anyway | 4.1 "limited to" |
| **Commercial use** (any) | **Prohibited** without a separate written enterprise licence | 3.4, 4.3, 4.4 |
| **Live trading** (own money or not) with signals/models derived from the data | **Not permitted** as "live proprietary trading execution" (and as "production") | 4.2, 4.1 "non-production" |
Consequence for the project (owner's own rule: simulated capital, dry_run only, no live, no paid services) is compatible with 4.1 **as long as the work stays personal, non-commercial and non-production**. Any step toward paper trading with these data, live trading, or sharing signals needs a fresh licence decision by the owner (and probably a different data source). A model fitted on Binance Vision data and later used live is *derived from* the Datasets; whether the use of such a derived model is covered is not answerable from the text (2.4 says derived items are "strictly governed"; 4.2 prohibits live execution) -> treat as prohibited until the owner obtains a written answer from Binance.

## 4. Alternatives
None of the alternatives could be read from this environment (their hosts do not resolve; a delegated fetch failed the same way), so **no licence statement about them is verified**; the table is therefore documentation-level and labelled.
| Source | Status | Observation |
|---|---|---|
| OKX public API/candles (already used for the frozen 8-pair dataset) | terms **not read** | No listing/delisting history; cannot give a point-in-time universe; terms must be checked by the owner before any use beyond personal research |
| Kraken OHLCVT archive | terms **not read** | prior S1 reading: documentation-level only |
| Coinbase, Bitstamp, Bitfinex, Bybit public data, CoinGecko/CoinPaprika/CryptoCompare free tiers | **not reachable, not read** | S1: free tiers lack depth or are non-commercial |
| Binance Vision (this audit) | **read** | Only source with hands-on verification; CC BY-NC-SA 4.0 non-commercial |
Rule adopted: publicly downloadable is not assumed unrestricted; no alternative is recommended until its terms are read. To read them the owner would have to allow the corresponding hosts for this environment (a Settings decision I have not requested), or paste the relevant texts.

## 5. Obligations the project must keep (checklist)
1. Attribute "Binance Vision" in every committed derivative (already done for S1/S3 aggregates).
2. Never commit raw klines; commit only hashes, scripts, aggregates.
3. Keep the pin manifest (sha256 + published CHECKSUM) of every file, since terms apply as of download date (1.4) and archive files can be changed or withdrawn (5.3).
4. No live/paper/commercial use of the data or models derived from it without a new licence review.
5. Download politely (rate-limited, cache-first) in any later builder (7.1).
6. Do not describe the project as endorsed by Binance (8.2).
