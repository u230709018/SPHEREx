"""
Build our own footprint index of every SPHEREx Level-2 image, straight from the public AWS copy.

SPHEREx observes the same sky with D1+D4, D2+D5 and D3+D6 (a dichroic splits the beam), and
D1, D2, D3 sit side by side. So one header per exposure is enough: we read the pointing (TAN WCS)
of one reference detector and derive the other two footprints from fixed focal-plane offsets
measured here once ("calibrate"). Only ~9 kB of each 65 MB file is read.

Output: data/index/spherex_index.npz
  centre unit vectors (x, y, z) of the reference detector, its TAN WCS, MJD, file naming parts.

Usage:  python scripts/list_s3.py                (list the bucket, all releases)
        python scripts/build_index.py            (resumes if interrupted; exposures already in
                                                  the existing index are not read again)

Written with the assistance of an AI coding assistant (Claude, Anthropic); see README "Use of AI".
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import requests
from astropy.io import fits
from astropy.wcs import WCS

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import s3_source as s3  # noqa: E402

IDX = ROOT / "data" / "index"
PAT = re.compile(r"^(?P<rel>[^/]+)/level2/(?P<week>[^/]+)/(?P<ver>[^/]+)/(?P<det>[1-6])/level2_(?P<obs>.+?)D(?P=det)_spx_(?P=ver)\.fits$")
REF_ORDER = [2, 5, 1, 4, 3, 6]              # prefer the middle array as reference
GROUP = {1: 0, 4: 0, 2: 1, 5: 1, 3: 2, 6: 2}
NPIX = 2040
_local = threading.local()


def session():
    s = getattr(_local, "s", None)
    if s is None:
        s = _local.s = requests.Session()
    return s


def get(key, a, n):
    for attempt in range(6):
        try:
            r = session().get(s3.S3_BASE + key, headers={"Range": f"bytes={a}-{a + n - 1}"}, timeout=40)
            if r.status_code in (200, 206):
                return r.content
            if r.status_code in (403, 404):
                return None
        except Exception:
            pass
        time.sleep(0.5 * 2 ** attempt)
    return None


WANT = ("CRPIX1", "CRPIX2", "CRVAL1", "CRVAL2", "CDELT1", "CDELT2", "PC1_1", "PC1_2", "PC2_1", "PC2_2", "MJD-OBS")


def pointing(key):
    """TAN pointing + MJD from a 9 kB slice of the IMAGE header (full header as fallback)."""
    raw = get(key, 2880 + 9600, 8800)
    vals = {}
    if raw:
        for i in range(0, len(raw) - 79, 80):
            k = raw[i:i + 8].decode("ascii", "replace").strip()
            if k in WANT and k not in vals:
                try:
                    vals[k] = float(raw[i + 10:i + 80].decode("ascii").split("/")[0].strip().strip("'"))
                except ValueError:
                    pass
    if len(vals) < len(WANT):
        try:
            h0, off, rest = s3._header(key, 0)
            h, _, _ = s3._header(key, off, rest)
            vals = {k: float(h.get(k, 1.0 if k in ("PC1_1", "PC2_2") else 0.0)) for k in WANT if k in h or k.startswith("PC")}
        except Exception:
            return None
    return vals if len(vals) == len(WANT) else None


def tan_pix(v, ra, dec):
    """Vectorised gnomonic projection: world -> 0-based pixel in a TAN frame described by v."""
    ra0, dec0 = np.radians(v["CRVAL1"]), np.radians(v["CRVAL2"])
    ra, dec = np.radians(ra), np.radians(dec)
    cosc = np.sin(dec0) * np.sin(dec) + np.cos(dec0) * np.cos(dec) * np.cos(ra - ra0)
    xi = np.cos(dec) * np.sin(ra - ra0) / cosc
    eta = (np.cos(dec0) * np.sin(dec) - np.sin(dec0) * np.cos(dec) * np.cos(ra - ra0)) / cosc
    xi, eta = np.degrees(xi), np.degrees(eta)
    pc = np.array([[v["PC1_1"], v["PC1_2"]], [v["PC2_1"], v["PC2_2"]]]) * np.array([[v["CDELT1"]], [v["CDELT2"]]])
    inv = np.linalg.inv(pc)
    # FITS: (xi, eta) = PC*CDELT @ (p - crpix), xi positive towards +RA (east)
    dx = inv[0, 0] * xi + inv[0, 1] * eta
    dy = inv[1, 0] * xi + inv[1, 1] * eta
    return dx + v["CRPIX1"] - 1, dy + v["CRPIX2"] - 1


def calibrate(exposures, n=24):
    """Affine maps ref-TAN-pixel -> pixel of each other array group, from full headers (with SIP)."""
    full = [e for e in exposures if all(d in e["keys"] for d in range(1, 7))]
    sample = [full[i] for i in np.linspace(0, len(full) - 1, n).astype(int)]
    grid = np.array([[x, y] for x in np.linspace(0, NPIX - 1, 9) for y in np.linspace(0, NPIX - 1, 9)])
    pairs = {}
    for e in sample:
        hdr = {}
        for d in range(1, 7):
            h0, off, rest = s3._header(e["keys"][d], 0)
            hdr[d], _, _ = s3._header(e["keys"][d], off, rest)
        for ref in range(1, 7):
            vref = {k: float(hdr[ref].get(k, 0.0)) for k in WANT if k != "MJD-OBS"}
            for tgt in range(1, 7):
                world = WCS(hdr[tgt]).all_pix2world(grid, 0)
                px, py = tan_pix(vref, world[:, 0], world[:, 1])
                pairs.setdefault((ref, GROUP[tgt]), []).append((np.c_[px, py, np.ones(len(px))], grid))
    maps = {}
    for (ref, g), lst in pairs.items():
        A = np.vstack([a for a, _ in lst]); B = np.vstack([b for _, b in lst])
        M, *_ = np.linalg.lstsq(A, B, rcond=None)
        res = np.abs(A @ M - B).max()
        maps.setdefault(str(ref), {})[str(g)] = M.tolist()
        print(f"ref D{ref} -> group {g}: max residual {res:.1f} px", flush=True)
    return maps


def main():
    files = json.loads((IDX / "s3_files.json").read_text())
    exp = {}
    for k, _ in files:
        m = PAT.match(k)
        if not m:
            continue
        e = exp.setdefault((m["rel"], m["obs"]), {"rel": m["rel"], "week": m["week"], "obs": m["obs"], "vers": {}, "keys": {}})
        e["vers"][int(m["det"])] = m["ver"]
        e["keys"][int(m["det"])] = k
    exposures = sorted(exp.values(), key=lambda e: (e["rel"], e["obs"]))
    print(len(exposures), "exposures", flush=True)

    cal = IDX / "focal_plane.json"
    if not cal.exists():
        cal.write_text(json.dumps(calibrate(exposures)))

    # Exposures already in the existing index are not read again: after a new release only the
    # new files are fetched (minutes instead of hours on a fresh clone).
    known = {}
    old = IDX / "spherex_index.npz"
    if old.exists():
        with np.load(old) as z:      # read each array once (indexing the NpzFile re-reads it every time)
            wcs0, mjd0, ref0, rel0, obs0 = z["wcs"], z["mjd"], z["ref"], z["rel"], z["obs"]
        names = [k for k in WANT if k != "MJD-OBS"]
        for i in range(len(mjd0)):
            v = dict(zip(names, map(float, wcs0[i])), **{"MJD-OBS": float(mjd0[i])})
            known[(str(rel0[i]), str(obs0[i]))] = (int(ref0[i]), v)
        print(len(known), "exposures taken from the existing index", flush=True)
    part = IDX / "pointing_partial.jsonl"
    done = set(known)
    if part.exists():
        for line in part.read_text().splitlines():
            try:
                done.add(tuple(json.loads(line)[:2]))
            except Exception:
                pass
    todo = [e for e in exposures if (e["rel"], e["obs"]) not in done]
    print(len(done), "already done,", len(todo), "to go", flush=True)
    lock = threading.Lock()
    t0 = time.time()

    def work(e):
        ref = next(d for d in REF_ORDER if d in e["keys"])
        return e, ref, pointing(e["keys"][ref])

    with open(part, "a") as fh, ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 96) as pool:
        futs = [pool.submit(work, e) for e in todo]
        for i, f in enumerate(as_completed(futs), 1):
            e, ref, v = f.result()
            with lock:
                fh.write(json.dumps([e["rel"], e["obs"], ref, v]) + "\n")
            if i % 2000 == 0:
                fh.flush()
                rate = i / (time.time() - t0)
                print(f"{i}/{len(todo)}  {rate:.0f}/s  eta {(len(todo) - i) / rate / 60:.1f} min", flush=True)

    # ---- pack
    point = dict(known)
    for line in part.read_text().splitlines():
        rel, obs, ref, v = json.loads(line)
        if v:
            point[(rel, obs)] = (ref, v)
    vers = sorted({v for e in exposures for v in e["vers"].values()})
    vidx = {v: i for i, v in enumerate(vers)}
    rows = [e for e in exposures if (e["rel"], e["obs"]) in point]
    n = len(rows)
    wcs = np.zeros((n, 10)); mjd = np.zeros(n); ref = np.zeros(n, np.int8)
    detver = np.full((n, 6), -1, np.int16)
    for i, e in enumerate(rows):
        r, v = point[(e["rel"], e["obs"])]
        ref[i] = r
        mjd[i] = v["MJD-OBS"]
        wcs[i] = [v[k] for k in WANT if k != "MJD-OBS"]
        for d, ver in e["vers"].items():
            detver[i, d - 1] = vidx[ver]
    ra, dec = np.radians(wcs[:, 2]), np.radians(wcs[:, 3])
    xyz = np.c_[np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)].astype(np.float32)
    np.savez_compressed(IDX / "spherex_index.npz", xyz=xyz, wcs=wcs, mjd=mjd, ref=ref, detver=detver,
                        rel=np.array([e["rel"] for e in rows]), obs=np.array([e["obs"] for e in rows]),
                        week=np.array([e["week"] for e in rows]), versions=np.array(vers),
                        built=np.array(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
    print("index written:", n, "exposures,", int((detver >= 0).sum()), "images", flush=True)


if __name__ == "__main__":
    main()
