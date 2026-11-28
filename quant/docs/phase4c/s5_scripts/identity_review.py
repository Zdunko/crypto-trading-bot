"""S5-P4: review of the 43 S4 epoch breaks with candle evidence, and the cost of conservative handling.

Descriptive review on development data (a retrospective look at already-frozen events; it does NOT feed
back into the frozen S4 tables). Writes s5_identity_review.json.

    python identity_review.py RAW OUT_JSON
"""

import csv
import datetime as dt
import gzip
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from quantlab import pit_universe as pu  # noqa: E402
from quantlab.pit_fetch import Store  # noqa: E402

DAY = pu.DAY
RAW = Path(sys.argv[1])
D = Path(__file__).resolve().parents[3] / "dataset"
classes = pu.load_classification(D / "asset_classification.json")
epochs = list(csv.DictReader(gzip.open(D / "epochs.csv.gz", "rt")))
listing = json.loads((RAW / "listing.json").read_text())
store = Store(RAW / "files")


def load(sym):
    c, vol = [], {}
    for m in listing[sym]:
        rec = store.cached(sym, "1d", m)
        if rec is None or rec.status != "ok":
            continue
        sc = pu.scan_file(rec, store.paths(sym, "1d", m)[0].read_bytes())
        c += sc.candles
        vol.update(sc.day_volume)
    return sorted(set(c)), vol


def mean(a):
    return statistics.fmean(a) if a else float("nan")


events = []
series = {}
for e in epochs:
    if e["k"] == "0":
        continue
    sym = e["symbol"]
    if sym not in series:
        series[sym] = load(sym)
    c, vol = series[sym]
    start = int(e["start_ms"])
    pre = [x for x in c if start - 8 * DAY <= x[0] < start][-7:]
    post = [x for x in c if start <= x[0] < start + 7 * DAY]
    r = post[0][1] / pre[-1][1] if pre and post else float("nan")
    b = (
        mean([vol[x[0]] for x in post]) / mean([vol[x[0]] for x in pre])
        if pre and post
        else float("nan")
    )
    q = mean([x[2] for x in post]) / mean([x[2] for x in pre]) if pre and post else float("nan")
    # rescale signature: quote volume continuous (0.2..5x) and base volume moves inversely to price
    resc = bool(
        pre
        and post
        and 0.2 <= q <= 5
        and abs(math.log(max(b, 1e-12)) + math.log(max(r, 1e-12))) < math.log(3)
    )
    surge = bool(pre and post and q > 5)
    sig = "rescale_signature" if resc else "volume_surge" if surge else "other_or_insufficient"
    events.append({"symbol": sym, "k": int(e["k"]), "reason": e["start_reason"], "class": classes[sym]["class"],
                   "date": dt.datetime.fromtimestamp(start / 1000, dt.UTC).date().isoformat(),
                   "price_ratio": r, "base_volume_ratio_7d": b, "quote_volume_ratio_7d": q, "signature": sig})  # fmt: skip
# ---- cost of conservative handling: membership with price-jump breaks disabled (counterfactual only)
base = {s: v[0] for s, v in series.items()}
allser = {}
for s in sorted(listing):
    allser[s] = base[s] if s in base else load(s)[0]
cls = {s: classes[s] for s in allser}
dates = pu.month_starts()
frozen = {
    (r["date"], r["threshold"], r["epoch_id"].split("#")[0])
    for r in csv.DictReader(gzip.open(D / "membership.csv.gz", "rt"))
}
old = pu.JUMP
pu.JUMP = 1e18
cf = {(r[0], r[1], r[2].split("#")[0]) for r in pu.membership(allser, cls, dates)}
pu.JUMP = old
extra = (
    cf - frozen
)  # decisions the conservative rule removes (asset sat out while rebuilding history)
lost = Counter((x[1]) for x in extra)
by_symbol = Counter(x[2] for x in extra)
asset_events = [x for x in events if x["class"] == "asset"]
rep = {
    "events_total": len(events), "by_reason": dict(Counter(x["reason"] for x in events)),
    "by_class": dict(Counter(x["class"] for x in events)),
    "assets": asset_events,
    "signature_counts_all": dict(Counter(x["signature"] for x in events)),
    "signature_counts_assets": dict(Counter(x["signature"] for x in asset_events)),
    "conservative_handling_cost": {
        "frozen_membership_decisions": len(frozen), "removed_by_epoch_reset_total": len(extra),
        "removed_by_threshold": dict(lost), "share_of_frozen": len(extra) / len(frozen),
        "symbols_affected": len(by_symbol), "top_symbols": by_symbol.most_common(10)},
}  # fmt: skip
Path(sys.argv[2]).write_text(json.dumps(rep, indent=1, sort_keys=True, default=str))
print(
    json.dumps(
        {
            k: rep[k]
            for k in (
                "events_total",
                "by_reason",
                "signature_counts_all",
                "signature_counts_assets",
                "conservative_handling_cost",
            )
        },
        indent=1,
    )
)
for x in asset_events:
    print(
        x["symbol"],
        x["date"],
        x["reason"],
        f"p={x['price_ratio']:.4g} b={x['base_volume_ratio_7d']:.4g} q={x['quote_volume_ratio_7d']:.4g}",
        x["signature"],
    )
