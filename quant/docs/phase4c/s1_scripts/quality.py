import sys, re, json, io, zipfile, hashlib

sys.path.insert(0, ".")
from lib import *
import numpy as np

el = json.load(open("elig.json"))
idx = json.load(open("usdt_1d_index.json"))
r = el["2022-01"]
ok = sorted(s for s, v in r.items() if v and v[0] >= 60 and v[1] >= 1e6)
dead = [s for s in ok if idx[s]["months"][-1] < "2026-10"]
alive = [s for s in ok if idx[s]["months"][-1] >= "2026-10"]
pick = dead[:: max(1, len(dead) // 12)][:12] + alive[:: max(1, len(alive) // 12)][:12]


def one(s):
    ym = "2022-03"
    z = get(f"{BASE}/data/spot/monthly/klines/{s}/1h/{s}-1h-{ym}.zip")
    if z is None:
        return s, None
    zf = zipfile.ZipFile(io.BytesIO(z))
    t = zf.read(zf.namelist()[0]).decode().strip().splitlines()
    rows = [ln.split(",") for ln in t if not ln[0].isalpha()]
    ts = [int(x[0]) for x in rows]
    unit = len(str(ts[0]))
    step = 3600000 if unit == 13 else 3600000000
    d = np.diff(ts)
    gaps = int(((d // step) - 1).clip(min=0).sum())
    dup = int((d == 0).sum())
    non = int((d < 0).sum())
    o, h, l, c, v = [np.array([float(x[i]) for x in rows]) for i in (1, 2, 3, 4, 5)]
    bad = int(((h < np.maximum(o, c) - 1e-12) | (l > np.minimum(o, c) + 1e-12)).sum())
    return s, {
        "rows": len(rows),
        "expected": 744,
        "gaps_missing_hours": gaps,
        "dups": dup,
        "nonmono": non,
        "zero_vol_share": float((v == 0).mean()),
        "ohlc_bad": bad,
        "ts_digits": unit,
        "size": len(z),
        "dead": s in dead,
    }


with ThreadPoolExecutor(6) as ex:
    res = dict(ex.map(one, pick))
json.dump(res, open("quality.json", "w"))
for s, v in res.items():
    print(s, v)


# 1h listing sizes for storage estimate
def size(s):
    p, o, okk = list_prefix(f"data/spot/monthly/klines/{s}/1h/")
    return (
        s,
        sum(z for k, z in o if k.endswith(".zip")),
        len([1 for k, z in o if k.endswith(".zip")]),
    )


with ThreadPoolExecutor(6) as ex:
    sz = list(ex.map(size, pick))
print(
    "1h zip bytes per symbol-month (mean):",
    sum(b for _, b, _ in sz) / max(1, sum(n for *_, n in sz)),
)
# timestamp unit in 2025 and checksum
z = get(f"{BASE}/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2025-03.zip")
t = (
    zipfile.ZipFile(io.BytesIO(z))
    .read("BTCUSDT-1d-2025-03.csv")
    .decode()
    .splitlines()[0]
    .split(",")[0]
)
print("BTCUSDT 1d 2025-03 first open_time digits:", len(t), t)
t2 = (
    zipfile.ZipFile(
        io.BytesIO(get(f"{BASE}/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-03.zip"))
    )
    .read("BTCUSDT-1d-2024-03.csv")
    .decode()
    .splitlines()[0]
    .split(",")[0]
)
print("BTCUSDT 1d 2024-03 first open_time digits:", len(t2), t2)
zz = get(f"{BASE}/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-03.zip")
cs = get(f"{BASE}/data/spot/monthly/klines/BTCUSDT/1d/BTCUSDT-1d-2024-03.zip.CHECKSUM")
print(
    "checksum file:",
    cs.decode().strip()[:80],
    "match:",
    hashlib.sha256(zz).hexdigest() in cs.decode(),
)
