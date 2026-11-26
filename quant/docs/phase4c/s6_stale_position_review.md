# S6 risk review R1: stale held positions (characterisation, nothing in the frozen risk layer changed)

Question: does the frozen S2 risk layer (`RiskManagedStrategy` + `RiskStateMachine`, manifest v6) handle a HELD asset that stops printing candles (delisting, halt, data loss) safely? Method: synthetic engine runs (`tests/test_stale_review.py`, 4 tests), deterministic, no market data.

## Findings (all measured on synthetic fixtures)
1. **Detection works but is counted in candles.** `data_gap_candles = 48` (frozen). On hourly candles a held asset without a candle triggers an `integrity` alarm after 48 candles (47-50 measured) -> SHUTDOWN, `safety_disqualified` set permanently, flatten orders for every position, no new entries afterwards. **On daily candles the same alarm needs 48 days** (measured 47-50 days): the frozen thresholds are not time-based. A daily strategy therefore detects a delisted holding about seven weeks late.
2. **The dead position cannot be sold.** The engine cannot trade without a candle; a halt liquidation never expires, so it waits forever. The healthy asset is sold, the stale one stays in `state.positions`. This is safe in the sense that nothing new is bought and nothing is double-sold, but the position remains.
3. **Valuation is optimistic.** The engine values a position without candles at its last close less one exit cost. Reported equity (and every drawdown, tier and floor test computed from it) therefore **does not show the loss** of an asset that is in fact worthless. The risk layer cannot trigger on a loss it cannot see; the floor/HWM protections are blind to delisting losses. The same holds for benchmarks that hold a delisted asset (test: equity constant after the asset ends).
4. **The universe guard is entry-only by design.** It blocks buys of non-members/stale assets and never sells; the risk layer's liquidation path is the only exit and it needs a candle.
5. **Unified conclusion:** the layers fail *safe for new risk* (no new entries, permanent shutdown) but *not safe for reporting* (a stuck position is valued at its last close).

## What was done / not done
- Done: tests that pin this behaviour, `benchmarks.stuck_positions` to list held positions without recent candles (for reports), the limitation recorded (L-STALEPOS in the register).
- **Not done (needs approval, would be a new risk-layer version):** time-based stale thresholds, a conservative stale valuation (for example a haircut after N days), an exit policy for assets without candles. S2 parameters and code are frozen and were not touched.

## Mitigations available inside the approved scope
- Evaluations must report stuck positions and run a **sensitivity line** in which stuck positions are marked at zero after a stated number of days; a result that depends on that valuation is not credible.
- Pre-registered strategies must declare the monitoring candle (hourly monitoring even for daily decisions) so that the 48-candle threshold means 48 hours.
- The point-in-time universe (S4) already removes assets from membership when their candles stop, which prevents *new* exposure to stale assets.
