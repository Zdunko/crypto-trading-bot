# Production-readiness roadmap (documentation only; nothing here is authorised or started)

Goal: a legally compliant, operationally safe, statistically honest automated system. Every stage ends with a measurable exit criterion and an explicit owner gate. All numbers marked (proposal) are for the owner to set; no money, order, credential, paid service or paper/live run exists today. The research-only status of the current dataset (Binance Vision, non-commercial) is a hard ceiling until stage 1 is cleared.

## Stage 1: legally permitted data
- Actions: read the full primary texts (venue terms of use, API and market-data terms, vendor licences); written answers to the question list in `s5_production_data_licensing_roadmap.md`; choose the production data path (venue real-time API under the owner's account terms, forward self-collection, or a licensed vendor; any spend needs separate approval).
- Exit: a dated, hashed legal memo stating for each of historical research, backtesting, derived signals, paper trading, live trading and commercial use what is permitted and by which clause; unresolved questions listed. No stage 2+ work on a source without it.
- Risk if skipped: licence breach; research results unusable for production.

## Stage 2: exchange integration (read-only first)
- Venue eligibility and onboarding in the owner's jurisdiction checked first (regulatory, tax: outside this repository's scope, counsel recommended).
- Integration layer behind an interface, tested on a mocked exchange and then on the venue's test network if one exists; API keys with least privilege (read-only first, trade later, **never withdrawal**), IP allow-list, key rotation, rate-limit compliance, server time synchronisation, idempotent client order ids, spot only, no margin.
- Exit: contract tests pass on the mock; testnet connectivity proven; no key, token or webhook in the repository (existing safety policy and secret scan stay green).

## Stage 3: execution reconciliation
- Order state machine (new, partial, filled, cancelled, rejected, expired) with persistence; after every cycle reconcile exchange balances, open orders and fills against the internal book; the S6 plan scenarios I6-I8 and I14-I15 become mandatory tests.
- Fail-closed rules: a mismatch above tolerance for two consecutive cycles, an unknown order, or a missing fill report puts the system in the S2/V3 SHUTDOWN state; reconciliation tolerances are set from arithmetic (fees, lot size), not from data, and frozen first.
- Exit (proposal): 100 % of simulated-fault scenarios end in the intended state; zero unexplained difference over a full dry run.

## Stage 4: independent out-of-sample validation
- Only a specification that passed a (possibly v2) feasibility gate, was frozen, and has an explicit owner approval for its exact hash.
- Evidence sources allowed: the single-use holdout under its existing rules, and forward paper trading on a frozen specification (minimum 6 months and 200 episodes, whichever later, no parameter edits). Statistics per `protocol_v4_stats.json` (Holm, DSR with the ledger N, bootstrap on the realised path).
- Independent review: a second implementation or an independent code review of the signal and the execution path; reproducibility from a clean checkout and pinned data.
- Honest limit (measured arithmetic): effects below an information ratio of about 1.2 cannot be demonstrated on 4.5 years, and IR 0.5 would need about 25 years; the system cannot rely on a claimed significant alpha unless the effect is large.
- Exit: pre-registered criteria met on forward data, or the family is declared rejected.

## Stage 5: paper trading (dry run on licensed live data)
- Same code path as live except order submission; simulated fills use the venue's live book/volumes; measured slippage and fee model compared with the cost model (BASE 0.15 % per side).
- Exit (proposal): minimum 6 months; realised slippage within the stress scenario; reconciliation breaks zero unresolved; no unplanned SHUTDOWN; risk layer V3 behaves as specified (no false stale alarms beyond a pre-set rate, real halts detected within 48 h).

## Stage 6: operational monitoring
- Heartbeat and data-freshness alarms (elapsed-time based, as in risk layer V3); drawdown vs the 20 % limit on the conservative valuation; daily reconciliation report; hash-chained state and decision log with off-host copies; alert channel with secrets only in the environment; runbooks for each alarm; capacity and clock checks; a documented monthly review.
- Exit: every alarm has an owner, a test that fires it and a runbook entry.

## Stage 7: security and emergency shutdown
- Secrets management (no secrets in git, CI or logs), dependency pinning and review, CI hardening (already zizmor-checked), separate environments, least-privilege keys without withdrawal, two independent kill paths (manual file/flag and automatic on integrity breach, plus a dead-man switch if the process stops reporting), documented incident response, offline backup of the risk state and recovery drill.
- Exit: kill-switch drills succeed from every state of the machine in under a stated time (proposal: one monitoring cycle); a restore from backup reproduces the state hash.

## Stage 8: eventual limited-capital live deployment (not authorised)
All of the following, each evidenced in the repository and approved in writing by the owner: (1) stage 1 legal memo covers live trading with this data and these models; (2) stages 2-7 exit criteria met; (3) the family passed stage 4 on forward data; (4) risk layer V3 (or a later version) adopted with the 20 % drawdown limit unchanged; (5) a hard capital cap set by the owner (proposal: an amount whose total loss is acceptable, ramped in steps with minimum durations, for example 5 % -> 25 % -> 100 % of the cap with at least one month each and an automatic return to the previous step after any SHUTDOWN); (6) written go/no-go review after each step; (7) tax and regulatory position confirmed; (8) automatic permanent stop at the drawdown limit with manual re-authorisation only (S2 authorisation protocol).
Nothing in this document starts any of it; each stage needs a separate approval.
