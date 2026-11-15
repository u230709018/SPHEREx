"""
Read SPHEREx Level-2 cutouts straight from the public AWS copy of the archive
(s3://nasa-irsa-spherex, mirrored by NASA/IPAC IRSA), without the IRSA cutout service.

The Level-2 images are uncompressed FITS, so a cutout is a handful of HTTP range requests:
the extension headers, the rows that cover the requested box, one ePSF zone and the spectral
WCS table. The result is written as a FITS file identical in layout to an IRSA (IBE) cutout,
so the rest of the pipeline cannot tell the two sources apart.

Parts of this file were written with the assistance of an AI coding assistant
(Claude, Anthropic) and reviewed by the team. See README "Use of AI".
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS

S3_BASE = "https://nasa-irsa-spherex.s3.us-east-1.amazonaws.com/"
BLOCK = 2880
PIXEL_SCALE_ARCSEC = 6.15
_local = threading.local()


def _session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = _local.s = requests.Session()
        s.mount("https://", requests.adapters.HTTPAdapter(pool_connections=4, pool_maxsize=4))
    return s


def _get(key: str, start: int, length: int) -> bytes:
    last = None
    for attempt in range(4):
        try:
            r = _session().get(S3_BASE + key, headers={"Range": f"bytes={start}-{start + length - 1}"}, timeout=30)
            if r.status_code in (200, 206):
                return r.content
            if r.status_code in (403, 404, 416):
                raise FileNotFoundError(f"{key}: HTTP {r.status_code}")
            last = RuntimeError(f"HTTP {r.status_code}")
        except FileNotFoundError:
            raise
        except Exception as err:      # timeouts, connection resets
            last = err
        time.sleep(0.5 * 2 ** attempt)
    raise RuntimeError(f"S3 read failed for {key}: {last}")


def _header(key: str, start: int, first: bytes | None = None) -> tuple[fits.Header, int, bytes]:
    """Header starting at byte `start`; returns (header, data offset, bytes read after the header)."""
    buf = first if first is not None else b""
    while True:
        # FITS cards are 80 bytes; END is always at a card boundary
        for i in range(0, len(buf) - 79, 80):
            if buf[i:i + 8] == b"END     ":
                hlen = (i // BLOCK + 1) * BLOCK
                return fits.Header.fromstring(buf[:i + 80].decode("ascii")), start + hlen, buf[hlen:]
        buf += _get(key, start + len(buf), 12 * BLOCK)


def _data_size(h: fits.Header) -> int:
    n = abs(h["BITPIX"]) // 8
    for i in range(1, h.get("NAXIS", 0) + 1):
        n *= h[f"NAXIS{i}"]
    n += h.get("PCOUNT", 0)
    return -(-n // BLOCK) * BLOCK if n else 0


def _rows(key, h, data_start, ya, yb, xa, xb, dtype):
    nx = h["NAXIS1"]
    item = abs(h["BITPIX"]) // 8
    raw = _get(key, data_start + ya * nx * item, (yb - ya) * nx * item)
    return np.frombuffer(raw, dtype=dtype).reshape(yb - ya, nx)[:, xa:xb].copy()


def _compressed_rows(key, h, data_start, ya, yb, xa, xb):
    """Rows of a tile-compressed image stored one row per tile (ZTILE2 = 1, RICE_1)."""
    from astropy.io.fits.hdu.compressed._codecs import Rice1
    if h.get("ZTILE2", 1) != 1 or h.get("ZCMPTYPE") != "RICE_1" or h["ZTILE1"] != h["ZNAXIS1"]:
        raise RuntimeError(f"{key}: unsupported compression {h.get('ZCMPTYPE')} {h.get('ZTILE1')}x{h.get('ZTILE2')}")
    rowlen = h["NAXIS1"]                      # one descriptor per tile: (nbytes, heap offset)
    table = np.frombuffer(_get(key, data_start + ya * rowlen, (yb - ya) * rowlen), dtype=">i4").reshape(yb - ya, -1)
    nbytes, offs = table[:, 0].astype(np.int64), table[:, 1].astype(np.int64)
    heap0 = data_start + h.get("THEAP", h["NAXIS1"] * h["NAXIS2"])
    lo, hi = int(offs.min()), int((offs + nbytes).max())
    heap = _get(key, heap0 + lo, hi - lo)
    par = {str(h.get(f"ZNAME{i}", "")).upper(): h.get(f"ZVAL{i}") for i in range(1, 5)}
    bytepix = int(par.get("BYTEPIX", abs(h["ZBITPIX"]) // 8))
    codec = Rice1(blocksize=int(par.get("BLOCKSIZE", 32)), bytepix=bytepix, tilesize=h["ZTILE1"])
    dt = {1: "u1", 2: "i2", 4: "i4", 8: "i8"}[bytepix]
    out = np.empty((yb - ya, h["ZNAXIS1"]), dtype=">" + dt if bytepix > 1 else dt)
    for i, (n, o) in enumerate(zip(nbytes, offs)):
        out[i] = np.frombuffer(codec.decode(np.frombuffer(heap, dtype=np.uint8, count=int(n), offset=int(o - lo))), dtype=dt)[:h["ZNAXIS1"]]
    return out[:, xa:xb].copy()


def _image_header(h: fits.Header) -> fits.Header:
    """Plain image header from a tile-compressed one (ZBITPIX/ZNAXISn -> BITPIX/NAXISn)."""
    from astropy.io.fits.hdu.compressed.header import _bintable_header_to_image_header
    return _bintable_header_to_image_header(h)


def _shift(h: fits.Header, xa: int, ya: int, nx: int, ny: int) -> fits.Header:
    h = h.copy()                      # the original still gives the size of the data on disk
    h["NAXIS1"], h["NAXIS2"] = nx, ny
    for suffix in ("", "A", "W"):
        if f"CRPIX1{suffix}" in h:
            h[f"CRPIX1{suffix}"] = h[f"CRPIX1{suffix}"] - xa
        if f"CRPIX2{suffix}" in h:
            h[f"CRPIX2{suffix}"] = h[f"CRPIX2{suffix}"] - ya
    return h


def s3_key(uri: str) -> str:
    """IRSA uri ('ibe/data/spherex/dr1/level2/...') -> S3 key ('dr1/level2/...')."""
    return uri.split("ibe/data/spherex/", 1)[-1]


def cutout(key: str, ra: float, dec: float, size_deg: float, out: Path) -> Path | None:
    """Write an IBE-style cutout of `key` centred on (ra, dec) to `out`. None if it does not overlap."""
    first = _get(key, 0, 14 * BLOCK)
    h0, off, rest = _header(key, 0, first)
    hi, d_img, _ = _header(key, off, rest)
    ny, nx = hi["NAXIS2"], hi["NAXIS1"]
    with np.errstate(all="ignore"):
        px, py = WCS(hi).all_world2pix([[ra, dec]], 0, quiet=True)[0]
    if not (np.isfinite(px) and np.isfinite(py)):
        return None
    if not (-0.5 <= px <= nx - 0.5 and -0.5 <= py <= ny - 0.5):
        return None        # same rule as IRSA's CONTAINS(point, footprint): the centre must be on the image
    n = int(np.ceil(size_deg * 3600 / PIXEL_SCALE_ARCSEC))
    x0, y0 = int(round(px - (n - 1) / 2)), int(round(py - (n - 1) / 2))
    xa, xb, ya, yb = max(0, x0), min(nx, x0 + n), max(0, y0), min(ny, y0 + n)
    if xa >= xb or ya >= yb:
        return None

    hdus = [fits.PrimaryHDU(header=h0)]
    hdus.append(fits.ImageHDU(_rows(key, hi, d_img, ya, yb, xa, xb, ">f4"), _shift(hi, xa, ya, xb - xa, yb - ya)))
    pos = d_img + _data_size(hi)
    for name, dtype in (("FLAGS", ">i4"), ("VARIANCE", ">f4"), ("ZODI", ">f4")):
        h, d, _ = _header(key, pos)
        if h.get("EXTNAME") != name:
            raise RuntimeError(f"{key}: expected {name}, found {h.get('EXTNAME')}")
        if h.get("ZIMAGE"):
            data, hh = _compressed_rows(key, h, d, ya, yb, xa, xb), _image_header(h)
        else:
            dt = {8: ">u1", 16: ">i2", 32: ">i4", -32: ">f4", -64: ">f8"}[h["BITPIX"]]
            data, hh = _rows(key, h, d, ya, yb, xa, xb, dt), h
        hdus.append(fits.ImageHDU(data, _shift(hh, xa, ya, xb - xa, yb - ya)))
        pos = d + _data_size(h)

    # ePSF: a uniform grid of zones over the active pixels ("x-fast then y"); the grid differs per
    # detector, so read the first zone to learn the tile size, then fetch only the zone under the
    # cutout centre (the same zone IRSA's nearest-centre choice gives).
    h, d, _ = _header(key, pos)
    pos = d + _data_size(h)
    if h.get("EXTNAME") == "EPSF":
        rowlen, nrow = h["NAXIS1"], h["NAXIS2"]
        def table(raw, nr=1):
            h1 = h.copy()
            h1["NAXIS2"] = nr
            return fits.BinTableHDU.fromstring(h1.tostring().encode() + raw + b"\0" * (-len(raw) % BLOCK))
        z0 = table(_get(key, d, rowlen)).data[0]
        wx, wy = float(z0["XWIDTH"]), float(z0["YWIDTH"])
        x_start, y_start = float(z0["XCENTER"]) - wx / 2, float(z0["YCENTER"]) - wy / 2
        nzx = max(1, int(round((nx - 2 * (x_start + 0.5)) / wx))) if wx > 0 else 1
        nzy = nrow // nzx
        cx, cy = 1 + (xa + xb - 1) / 2 - 1, 1 + (ya + yb - 1) / 2 - 1   # 0-based parent pixel of the centre
        ix = int(np.clip(np.floor((cx - x_start) / wx), 0, nzx - 1))
        iy = int(np.clip(np.floor((cy - y_start) / wy), 0, nzy - 1))
        k = min(nrow - 1, iy * nzx + ix)
        hdus.append(table(_get(key, d + k * rowlen, rowlen)))
        h, d, _ = _header(key, pos)
    if h.get("EXTNAME") == "WCS-WAVE":
        raw = _get(key, d, max(BLOCK, _data_size(h)))
        hdus.append(fits.BinTableHDU.fromstring(h.tostring().encode() + raw[:_data_size(h)]))

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".s3part")
    fits.HDUList(hdus).writeto(tmp, overwrite=True, output_verify="ignore")   # headers come from valid files
    tmp.replace(out)
    return out
