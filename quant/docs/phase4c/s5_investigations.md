# S5-P3 / P4: volume discrepancy (X1) and identity-epoch review

Development window only; descriptive; no returns; the frozen S4 files were not modified. Scripts: `s5_scripts/x1_investigation.py`, `s5_scripts/identity_review.py`; results `s5_x1_investigation.json`, `s5_identity_review.json`.

## 1. X1: daily volume versus the sum of hourly volumes (1 029 of 21 508 symbol-months)
**Classification (exclusive, by the worst day of the month; counts sum to 1 029):**
| Class | Months | Meaning |
|---|---|---|
| `full_day_hourly_smaller` | 589 | a day with all 24 hourly candles whose hourly sum is smaller than the daily volume |
| `full_day_hourly_greater` | 219 | all 24 hourly candles present, hourly sum greater than the daily volume |
| `explained_by_hourly_gaps` | 219 | the mismatching days have missing hourly candles and the hourly sum is smaller (expected) |
| `day_missing_in_hourly` / `day_missing_in_daily` | 1 / 1 | a day present in only one interval |
**Where:** concentrated in five months: 2020-12 (219), 2021-01 (219), 2021-04 (253), 2021-12 (249), 2022-04 (86), plus 3 single months; 342 symbols affected; zero in 2017-2019, 2023, 2025. Magnitude on full-24-candle days (1 047 days of 638 456): median -0.13 %, 5th/95th percentile -5.9 % / +1.4 %, extremes -26.0 % / +7.6 %; 21 % of them hourly greater, 79 % smaller. 4 395 days have hourly gaps.
**Hypothesis (not proven):** the clustering matches periods in which the Binance public-data README log (update of 2022-08-08, "Fixed inconsistent data") corrected many daily-file klines (2021-04: 858 files, 2021-12: 658, 2022-03: 1 159, 2022-04: 193 for the 1h/1d daily archives). The log lists only the *daily* archive files; our monthly files are not named in it, so whether a monthly file was corrected or not, and which of the two intervals is right, is **unknown**. 2020-12 and 2021-01 are not in that log.
**Impact on liquidity eligibility (measured):** the S4 membership was recomputed with each daily quote volume replaced by the hourly-derived value (variant A: clean 24-candle days, 1 047 volumes actually changed; variant B: every hourly day incl. gaps, 1 266 changed). **Decisions changed: 0 of 21 139 in both variants** (max change in member count per date: 0). Reason: the changes are small relative to the distance of a 60-day median from the 1 M / 5 M thresholds. Eligibility is robust to this discrepancy on the observed data; the frozen dataset needs no change.
**Impact on execution (not claimed to be bounded):** the Stage 0 engine takes its liquidity budget from hourly base volumes (10 % of the median of the previous 24 completed hourly candles). The daily/hourly disagreement does not alter the hourly numbers it uses, but it shows that at least one of the two sources is wrong on up to ~800 symbol-months. Day-level errors reach -26 % / +7.6 %; the median over 24 candles dampens a single-day error but the effect on a given budget cannot be bounded from this data. Direction: hourly smaller than daily (79 %) means the engine's budget is conservative if the daily number is right; hourly greater (21 %) means it could overstate liquidity. Hourly gaps (4 395 days) trigger the engine's existing fail-closed rule (fewer than 24 valid candles = no liquidity). Execution realism therefore remains an assumption; no correction of data was made.
**Decision:** no change to the frozen dataset; X1 stays a limitation (L-X1 in the register) and any future execution study must report liquidity results with and without the affected months.

## 2. Identity epochs: crashes versus migrations and redenominations
43 breaks (gap 8, jump_down 14, jump_up 21); 12 on assets, 28 on leveraged tokens, 3 on stablecoins. Candle-only evidence per event (price ratio, mean base-volume ratio and quote-volume ratio over 7 days after/before): a **rescale signature** = quote volume roughly continuous (0.2-5x) while base volume moves inversely to price (redenomination/split/migration-like); a **crash signature** = base volume explodes with a price collapse.
| Asset event | Evidence | Reading (unverified) |
|---|---|---|
| COCOS 2021-01-23 up x1 295 | base volume x0.0009, quote x1.25 | rescale signature |
| QUICK 2023-07-21 down x0.0008 | base x1 879, quote x1.3 | rescale signature |
| SUN 2021-06-18 down x0.0012 | base x2 170, quote x2.3 | rescale signature |
| DREP 2021-04-02 up x108 | base x0.06, quote x7.2 | rescale with volume surge |
| LUNA 2022-05-11 and 2022-05-12 down | base x5 026 / x531, quote x3.4 / x1.0 | genuine collapse |
| LUNA 2022-05-31 up (new asset on the old ticker) | no pre-event candles | ticker reuse, not decidable from candles |
| BNX 2023-02-22 down x0.009 | base x549, quote x5 | crash-like (possibly a rescale; not decidable) |
| VIDT 2022-11-09 down | insufficient neighbours | undecided |
| CVC, FTT, VEN gaps | no prices across the gap | unresolved (FTT collapse and VEN->VET migration are known events outside the data) |
Totals over all 43 events: rescale signature 24, volume surge 3, other/insufficient 16.
**Cost of the conservative rule (every break restarts the 60-of-90-day history):** a counterfactual with price-jump breaks disabled adds only **15 of 21 139 membership decisions (0.07 %)**, 5 symbols (LUNA 4, SUN 4, BNX 3, VIDT 2, DREP 2). So the rule does not materially shrink the universe. Two directional effects exist and are small but real: (i) genuine crashes (LUNA, BNX) leave the eligible set for the history-rebuilding period, a mild optimistic selection of the opportunity set; (ii) redenominated assets (COCOS, QUICK, SUN) are treated as new identities, which is right for price-based features but loses the link to the earlier history.
**Conclusion:** the handling is conservative and cheap; candle-only evidence can often flag a rescale (24 of 43) but cannot be trusted to decide per event without announcements, so it must not replace the break. **No change to the frozen S4**; a possible v2 (separately pre-registered) could keep history across crash-signature events while still restarting it for rescale-signature events, and would need an announcement-based identity table to be trustworthy.
