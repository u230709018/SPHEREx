"""
Archival frames for a long time baseline: 2MASS (1997-2001) and AllWISE (2010) images of the
same field from NASA/IPAC IRSA, reprojected onto the SPHEREx viewer grid so they can be blinked
together with the SPHEREx visits (2025+).

Band mapping to the SPHEREx detectors they overlap:
  2MASS J (1.25 um) -> D2, 2MASS Ks (2.16 um) -> D3, WISE W1 (3.4 um) -> D4, WISE W2 (4.6 um) -> D6

Parts of this file were written with the assistance of an AI coding assistant
(Claude, Anthropic) and reviewed by the team. See README "Use of AI".
"""
from __future__ import annotations

import json
import warnings

import numpy as np
from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.time import Time
from astropy.wcs import WCS
from astroquery.ipac.irsa import Irsa
from reproject import reproject_interp
from scipy.ndimage import gaussian_filter
import astropy.units as u

import catalogs as cat
import pipeline as pl
import spherex_core as sx

SURVEYS = [
    # collection, label, epoch id, {band: (SPHEREx detector, smoothing sigma in pixels)}
    ("twomass_allsky", "2MASS", -2, {"J": ("D2", 2.7), "K": ("D3", 2.7)}),
    ("wise_allwise", "WISE", -1, {"W1": ("D4", 1.5), "W2": ("D6", 1.5)}),
]


def _num(v):
    return None if np.ma.is_masked(v) else float(v)


def _frame(urls: list[str], ra: float, dec: float, size_deg: float, grid: WCS, shape, sigma: float):
    """Mosaic the given images onto the viewer grid (mean of the tiles that cover each pixel)."""
    acc, cnt = np.zeros(shape), np.zeros(shape)
    for url in urls[:6]:
        path = sx.fetch_cutout(f"{url}?center={ra:.6f},{dec:.6f}deg&size={size_deg * 1.6:.5f}deg&gzip=false")
        if path is None:
            continue
        try:
            with fits.open(path, memmap=False) as hdul:
                data = hdul[0].data.astype(np.float64)
                w = WCS(hdul[0].header)
        except Exception:
            continue
        if data.ndim != 2 or data.size < 16:
            continue
        ok = np.isfinite(data)
        if not ok.any():
            continue
        data = np.where(ok, data, np.nanmedian(data))
        data = gaussian_filter(data - np.median(data), sigma)   # roughly match the SPHEREx resolution
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            r, fp = reproject_interp((data, w), grid, shape_out=shape)
        good = np.isfinite(r) & (fp > 0)
        acc[good] += r[good]
        cnt[good] += 1
    if not cnt.any():
        return None, 0
    return np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan).astype(np.float32), int(cnt.max())


def archival_frames(key: str) -> dict:
    cache = pl.RESULTS_DIR / f"arch_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text())
    res = pl.cached_result(key)
    if not res or res.get("mode") == "moving":
        return {"epochs": [], "frames": []}
    ra, dec = res["grid"]["crval"]
    size = res["fov_arcmin"] / 60.0
    grid, shape = sx.make_grid(ra, dec, size)
    coord = SkyCoord(ra, dec, unit="deg")
    out = {"epochs": [], "frames": []}
    for coll, label, eid, bands in SURVEYS:
        try:
            tab = Irsa.query_sia(pos=(coord, size / 2 * u.deg), collection=coll)
        except Exception:
            continue
        sci = [r for r in tab if str(r["dataproduct_subtype"]) == "science"]
        dets, mjds = [], []
        for band, (det, sigma) in bands.items():
            rows = [r for r in sci if str(r["energy_bandpassname"]) == band]
            if not rows:
                continue
            frame, n = _frame([str(r["access_url"]) for r in rows], ra, dec, size, grid, shape, sigma)
            if frame is None:
                continue
            out["frames"].append({"epoch": eid, "det": det, "n": n, "band": band, "data": sx.b64f32(frame)})
            dets.append(det)
            for r in rows:
                a, b = _num(r["t_min"]), _num(r["t_max"])
                if a is not None:
                    mjds.append((a + (b if b is not None else a)) / 2)
        if not dets or not mjds:
            continue
        mjd = float(np.mean(mjds))
        out["epochs"].append({
            "epoch": eid, "archival": True, "label": label,
            "bands": ", ".join(b.replace("K", "Ks") if label == "2MASS" else b for b in bands if bands[b][0] in dets),
            "mjd": mjd, "jyear": cat.mjd_to_jyear(mjd),
            "date_start": Time(min(mjds), format="mjd").iso[:10], "date_end": Time(max(mjds), format="mjd").iso[:10],
            "n_images": len(dets), "n_available": len(dets), "dets": sorted(dets)})
    pl.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(out))
    return out
