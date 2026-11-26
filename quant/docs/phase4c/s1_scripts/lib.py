import subprocess, re, json, time
from concurrent.futures import ThreadPoolExecutor

BASE = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"


def get(url, tries=3):
    for k in range(tries):
        r = subprocess.run(["curl", "-s", "-m", "40", "-f", url], capture_output=True)
        if r.returncode == 0:
            return r.stdout
        time.sleep(1 + k)
    return None


def list_prefix(prefix, delimiter="/", marker=""):
    out_pref, out_obj = [], []
    while True:
        u = f"{BASE}?delimiter={delimiter}&prefix={prefix}&max-keys=1000" + (
            f"&marker={marker}" if marker else ""
        )
        x = get(u)
        if x is None:
            return out_pref, out_obj, False
        t = x.decode()
        out_pref += re.findall(r"<CommonPrefixes><Prefix>([^<]+)</Prefix>", t)
        for m in re.finditer(r"<Contents><Key>([^<]+)</Key>.*?<Size>(\d+)</Size>", t, re.S):
            out_obj.append((m.group(1), int(m.group(2))))
        if "<IsTruncated>true</IsTruncated>" in t:
            nm = re.search(r"<NextMarker>([^<]+)</NextMarker>", t)
            marker = (
                nm.group(1)
                if nm
                else (out_obj[-1][0] if out_obj else (out_pref[-1] if out_pref else ""))
            )
            if not nm and not out_obj:
                marker = out_pref[-1]
        else:
            return out_pref, out_obj, True
