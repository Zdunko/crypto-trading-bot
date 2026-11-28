# S9 — Three signal hypotheses (L1, cross-sectional) and the selection

Nothing here was computed on market data. Scores: `s9_selection.json` (assigned before the simulation). Power: `s9_signal_power_results.json` (**synthetic**; 400 replications per cell, 1,642 days, HAC lag 10). The three hypotheses are distinct mechanisms (behavioural, supply/novelty, liquidity compensation). None is momentum, trend, mean-reversion-by-RSI/Bollinger, breakout, a risk overlay or Family A; the closest relative of H1 is short-term reversal, so H1 carries an explicit disguise check (below). The economic literature behind each mechanism is **not verified in this environment**; each is a hypothesis.

Common to all three: universe = point-in-time eligible USDT spot assets (S4 rule: median 90-day quote volume >= 5 M USDT, >= 60 daily candles, completed candles only, delisted symbols included); signal at the close of day t, fills at the next candle open (engine rule); evaluation 2021-01-01 to 2025-06-30 (breadth N >= 40 exists from 2021; the holdout from 2025-07-01 is not touched); sub-periods fixed ex ante: 2021-01..2022-12 and 2023-01..2025-06; null: mean cross-sectional rank IC <= 0; test: mean daily Spearman IC with Newey-West standard error (lag 2h for an h-day forward return), Holm across the registered horizons.

## H1 — Lottery-demand avoidance (MAX effect)
- **Rationale.** Retail demand for lottery-like payoffs overprices coins with extreme recent single-day gains, which then earn less; avoiding them is spot-implementable (long-only).
- **Signal.** r_{i,tau} = C_{i,tau}/C_{i,tau-1} - 1 on completed daily closes; MAX3_{i,t} = mean of the 3 largest r_{i,tau} over tau in {t-27..t}; S_{i,t} = -MAX3_{i,t}; the daily cross-sectional rank of S is the signal (higher = less lottery-like). One fixed scalar: window 28.
- **PIT data.** daily closes only; listing/delisting epochs.
- **Horizon / configurations.** 7-day and 28-day forward returns (open t+1 to open t+1+h): **2 configurations**, N would go 43 -> 45.
- **Turnover (assumption).** weekly rebalance of the least-lottery quintile: about 12 one-way turns per year.
- **Cost sensitivity.** break-even IC 0.0035 (gross active return about 3.6 %/year at 2x margin); 3x cost stress: 0.0106. Moderate-to-high sensitivity.
- **Regime dependence.** lottery demand is likely strongest in retail-driven bull phases; skill may vanish in bear phases (simulated as regime-dependent skill).
- **Lookahead/survivorship.** signal uses closes up to day t only (test: truncating the data after t leaves S_t unchanged); delisted coins stay in the cross-section (a coin that crashed to delisting is the case the signal is meant to avoid, so excluding delistings would inflate it); exchange-specific listing dates limit the earliest valid window.
- **Disguise check (L1 failure rule).** mean daily cross-sectional rank correlation of S with the trailing 7-day and 28-day returns > 0.7 in absolute value => treated as a disguised rejected style and terminated.
- **Rejection criteria (pre-registered at L1).** Holm-adjusted p > 0.05 for both horizons; OR IC not positive in both sub-periods; OR disguise check fails; OR a lookahead/prefix test fails.
- **Estimated power (synthetic).** at N = 40 and daily-IC 0.005 / 0.01 / 0.02: 0.27-0.34 / 0.67-0.69 / 0.96-1.00 across the three dependence scenarios; at N = 100: 0.53-0.56 / 0.93-0.98 / 0.995-1.00. Detectable IC at 80 % power: about 0.014 (N = 40), 0.008 (N = 100), not reached for N = 10.

## H2 — Post-listing hype decay (age filter)
- **Rationale.** Newly listed coins attract attention and are overpriced; the premium decays with age. The signal acts mostly as a universe filter.
- **Signal.** a_{i,t} = days since the first valid daily candle of asset i (point-in-time listing epoch); S_{i,t} = min(a_{i,t}, 365); rank of S. One fixed scalar: cap 365.
- **PIT data.** listing epochs only (no prices).
- **Horizon.** 28-day forward returns (1 configuration).
- **Turnover (assumption).** about 1.5 one-way turns per year.
- **Cost sensitivity.** break-even IC 0.0004 (about 0.5 %/year gross); nearly cost-insensitive.
- **Regime dependence.** probably tied to listing waves (bull markets).
- **Lookahead/survivorship.** age uses the Binance listing date, not the coin's true age; age proxies size, liquidity and survival, so any result is confounded; low cross-sectional breadth of young coins.
- **Rejection criteria.** as H1, plus failure if the effect disappears after cross-sectionally controlling for trailing 90-day median volume (pre-registered control).
- **Estimated power.** same simulated table as H1, but the real effective N is the number of young assets (about 10-30), so the simulated N = 10 row applies: detectable IC not reached on the grid (power 0.12-0.15 at IC 0.005, 0.21-0.26 at 0.01, 0.52-0.65 at 0.02).

## H3 — Illiquidity compensation (Amihud)
- **Rationale.** Investors demand compensation for bearing assets that are costly to trade.
- **Signal.** ILLIQ_{i,t} = mean over tau in {t-59..t} of |r_{i,tau}| / V_{i,tau}, V = daily quote volume in USDT; S_{i,t} = +ILLIQ_{i,t}; rank. One fixed scalar: window 60.
- **PIT data.** daily close and quote volume.
- **Horizon.** 28-day forward returns (1 configuration); monthly rebalance.
- **Turnover (assumption).** about 3 one-way turns per year.
- **Cost sensitivity.** break-even IC 0.0009 at the base cost but the signal selects the least liquid quintile, where real slippage, capacity, minimum notional and delisting risk are worst; the base cost is most likely understated.
- **Regime dependence.** the premium may rise in stress (when liquidity is scarce) and be offset by delisting losses.
- **Lookahead/survivorship.** volume and returns up to day t only; delisted coins included (illiquid coins delist more often, so exclusion would bias upward); V3 untradeable-asset handling matters.
- **Rejection criteria.** as H1, plus failure if the 2x-cost net result at L2 turns negative.
- **Estimated power.** same simulated table as H1 (N = 40-100).

## Multiple testing and degrees of freedom (all three)
Holm over the registered horizons of the selected family only; one fixed formula and one scalar per configuration; the window, sub-periods, universe rule, lag and stop rule are fixed here and in the pre-registration; no asset, period or horizon is dropped or added after results; a hypothesis not rejected at L1 terminates with no variant search.

## Selection (pre-registered rubric, scores from reasons only)
| Rank | Hypothesis | Plausibility (0.35) | Feasibility (0.25) | Simplicity (0.20) | Practical value (0.20) | Score |
|---|---|---|---|---|---|---|
| 1 | **H1 lottery-demand avoidance** | 4 | 3 | 4 | 3 | **3.55** |
| 2 | H3 illiquidity compensation | 4 | 3 | 4 | 2 | 3.35 |
| 3 | H2 listing-age decay | 3 | 2 | 5 | 3 | 3.15 |

**Recommended candidate: H1, exactly one.** The ranking was fixed before the simulation and did not use any market performance. H3 is the runner-up mainly because its premium sits where costs are least certain; H2 is last because its effective cross-section is small and it behaves like a filter.

## Honest reading of the power numbers
For every hypothesis the break-even IC (0.0004-0.0035) lies **below** the smallest detectable IC (about 0.008-0.014), so none is "powered" at its break-even effect (pre-registered definition): an L1 test is a screen for effects 2-4x larger than break-even, and a non-rejection cannot exclude a small viable effect. Under the pre-registered stop rule a non-rejection terminates the hypothesis anyway, because an effect too small to detect cannot be validated or operated with confidence (same conclusion as S8). A rejection at L1 would still be only L1: it says nothing about costs, robustness or T1-T10.
