"""Dict-backed fake of the Binance Vision S3 endpoint (objects, .CHECKSUM, listings)."""

from __future__ import annotations

import hashlib
import io
import re
import zipfile

from quantlab import pit_fetch as pf


def zip_bytes(name: str, text: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr(name, text)
    return b.getvalue()


class FakeS3:
    """Dict-backed archive: GET object, GET .CHECKSUM, ListObjects with prefix/delimiter."""

    def __init__(
        self,
        objects: dict[str, bytes],
        fail_after: int | None = None,
        corrupt: set[str] | None = None,
    ):
        self.objects, self.n, self.fail_after, self.corrupt = (
            dict(objects),
            0,
            fail_after,
            corrupt or set(),
        )
        self.log: list[str] = []

    def get(self, url: str):
        self.n += 1
        self.log.append(url)
        if self.fail_after is not None and self.n > self.fail_after:
            return 0, b""  # network down
        if "?" in url:
            found = re.search(r"prefix=([^&]*)", url)
            prefix = found.group(1) if found else ""
            if prefix == pf.KLINES:
                dirs = sorted({k[len(prefix) :].split("/")[0] for k in self.objects})
                return 200, "".join(
                    f"<CommonPrefixes><Prefix>{prefix}{d}/</Prefix></CommonPrefixes>" for d in dirs
                ).encode()
            keys = sorted(k for k in self.objects if k.startswith(prefix))
            return 200, "".join(f"<Contents><Key>{k}</Key></Contents>" for k in keys).encode()
        key = url[len(pf.BASE) + 1 :]
        if key.endswith(".CHECKSUM"):
            base = key[: -len(".CHECKSUM")]
            if base not in self.objects:
                return 404, b""
            h = "0" * 64 if base in self.corrupt else hashlib.sha256(self.objects[base]).hexdigest()
            return 200, f"{h}  {base.rsplit('/', 1)[-1]}\n".encode()
        if key in self.objects:
            return 200, self.objects[key]
        return 404, b""


def key(sym, itv, ym):
    return f"{pf.KLINES}{sym}/{itv}/{sym}-{itv}-{ym}.zip"
