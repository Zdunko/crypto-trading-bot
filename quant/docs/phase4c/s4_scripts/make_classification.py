"""One-off generator of dataset/asset_classification.json from the dev-window symbol listing.

Every symbol seen in the development window gets an EXPLICIT class. Non-asset lists below (by base) are the
curated review result (ticker semantics; evidence level 'curated-unverified': not checked against
exchange announcements, which are unreachable here). The instrument type is a static product
property known at listing, so the class applies from the first candle ('inception'); no future
market information is used. Name patterns are alarms only (see quantlab.pit_universe.SUSPECT).

    python make_classification.py RAW_LISTING_JSON OUT_JSON
"""

import json
import sys

STABLE = ["AEUR", "BKRW", "BUSD", "DAI", "EURI", "FDUSD", "PAX", "SUSD", "TUSD", "USD1", "USDC", "USDP",
          "USDS", "USDSB", "UST", "USTC", "XUSD"]  # fmt: skip
FIAT = ["AUD", "EUR", "GBP"]
COMMODITY = ["PAXG"]
LEVERAGED = ["1INCHDOWN", "1INCHUP", "AAVEDOWN", "AAVEUP", "ADADOWN", "ADAUP", "BCHDOWN", "BCHUP", "BEAR",
             "BNBBEAR", "BNBBULL", "BNBDOWN", "BNBUP", "BTCDOWN", "BTCUP", "BULL", "DOTDOWN", "DOTUP",
             "EOSBEAR", "EOSBULL", "EOSDOWN", "EOSUP", "ETHBEAR", "ETHBULL", "ETHDOWN", "ETHUP", "FILDOWN",
             "FILUP", "LINKDOWN", "LINKUP", "LTCDOWN", "LTCUP", "SUSHIDOWN", "SUSHIUP", "SXPDOWN", "SXPUP",
             "TRXDOWN", "TRXUP", "UNIDOWN", "UNIUP", "XLMDOWN", "XLMUP", "XRPBEAR", "XRPBULL", "XRPDOWN",
             "XRPUP", "XTZDOWN", "XTZUP", "YFIDOWN", "YFIUP"]  # fmt: skip
NOTES = {
    "SYRUP": "name matches the leveraged-token pattern but is a normal asset (false positive of the old regex)",
    "BULL": "short name that the old regex (length > 4) missed; ticker semantics: bitcoin leveraged token",
    "BEAR": "short name that the old regex (length > 4) missed; ticker semantics: bitcoin leveraged token",
    "UST": "stablecoin until its 2022 depeg; class is the instrument type, applied from inception",
    "USTC": "post-collapse ticker of the same instrument family; treated as stablecoin like UST",
    "AUD": "fiat quote currency traded as a pair; missed by the old S1 list",
    "BKRW": "KRW-pegged stablecoin; missed by the old S1 list",
}
listing = json.load(open(sys.argv[1], encoding="utf-8"))
bases = sorted(s[:-4] for s in listing)
cls: dict = {}
for b in bases:
    c = ("stablecoin" if b in STABLE else "fiat" if b in FIAT else "commodity_token" if b in COMMODITY
         else "leveraged_token" if b in LEVERAGED else "asset")  # fmt: skip
    cls[b + "USDT"] = {
        "class": c,
        "valid_from": "inception",
        **({"note": NOTES[b]} if b in NOTES else {}),
    }
missing = [x for x in STABLE + FIAT + COMMODITY + LEVERAGED if x + "USDT" not in cls]
doc = {
    "id": "S4-asset-classification-v1",
    "authority": "this table; name patterns are alarms only",
    "evidence_level": "curated-unverified (ticker semantics; not checked against exchange announcements)",
    "scope": "USDT symbols with at least one development-window file (months < 2025-07)",
    "listed_but_not_in_dev_window": sorted(set(missing)),
    "symbols": cls,
}
json.dump(
    doc, open(sys.argv[2], "w", encoding="utf-8"), indent=1, sort_keys=True, ensure_ascii=False
)
print(
    len(cls),
    {
        k: sum(1 for v in cls.values() if v["class"] == k)
        for k in sorted({v["class"] for v in cls.values()})
    },
    missing,
)
