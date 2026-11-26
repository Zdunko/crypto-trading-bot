import sys, re, json, io, zipfile, os, statistics

sys.path.insert(0, ".")
from lib import *
import numpy as np

idx = json.load(open("usdt_1d_index.json"))
os.makedirs("cache", exist_ok=True)
DATES = ["2018-07", "2019-01", "2020-01", "2021-01", "2022-01", "2023-01", "2024-01", "2025-01"]


def shift(ym, k):
    y, m = map(int, ym.split("-"))
    t = y * 12 + m - 1 + k
    return f"{t // 12}-{t % 12 + 1:02d}"


STABLE = {
    "USDC",
    "TUSD",
    "BUSD",
    "PAX",
    "USDP",
    "FDUSD",
    "DAI",
    "USDS",
    "AEUR",
    "EUR",
    "GBP",
    "TRY",
    "UST",
    "USTC",
    "SUSD",
    "UST",
    "USDSB",
    "VAI",
    "EURI",
    "USD1",
    "XUSD",
    "BFUSD",
    "RLUSD",
    "PAXG",
}


def is_asset(s):
    b = s[:-4]
    if b in STABLE:
        return False
    if re.search(r"(UP|DOWN|BULL|BEAR)$", b) and len(b) > 4:
        return False
    return True


def fetch(sym, ym):
    f = f"cache/{sym}-{ym}.csv"
    if os.path.exists(f):
        return open(f).read()
    z = get(f"{BASE}/data/spot/monthly/klines/{sym}/1d/{sym}-1d-{ym}.zip")
    if z is None:
        return None
    try:
        t = (
            zipfile.ZipFile(io.BytesIO(z))
            .read(zipfile.ZipFile(io.BytesIO(z)).namelist()[0])
            .decode()
        )
    except Exception:
        return None
    open(f, "w").write(t)
    return t


def qvols(sym, months):
    out = []
    for ym in months:
        t = fetch(sym, ym)
        if t is None:
            return None
        for ln in t.strip().splitlines():
            p = ln.split(",")
            if p[0].isalpha():
                continue
            out.append(float(p[7]))
    return out


def at(T):
    months = [shift(T, -3), shift(T, -2), shift(T, -1)]
    cand = [
        s
        for s, v in idx.items()
        if v["months"] and is_asset(s) and all(m in v["months"] for m in months)
    ]

    def f(s):
        q = qvols(s, months)
        return s, (None if not q else (len(q), float(np.median(q[-90:]))))

    with ThreadPoolExecutor(8) as ex:
        res = dict(ex.map(f, cand))
    return res


if __name__ == "__main__":
    out = {}
    for T in DATES:
        r = at(T)
        out[T] = r
        vals = [v for v in r.values() if v]
        row = {th: sum(1 for n, m in vals if n >= 60 and m >= th) for th in (250e3, 1e6, 5e6, 25e6)}
        later_del = {
            th: sum(
                1
                for s, (v) in r.items()
                if v and v[0] >= 60 and v[1] >= th and idx[s]["months"][-1] < "2026-10"
            )
            for th in (250e3, 1e6, 5e6, 25e6)
        }
        print(
            T,
            "candidates",
            len(r),
            "valid",
            len(vals),
            "eligible by threshold",
            row,
            "of which delisted by 2026-10",
            later_del,
            flush=True,
        )
    json.dump(out, open("elig.json", "w"))
