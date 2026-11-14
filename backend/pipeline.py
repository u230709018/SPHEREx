"""
End-to-end job: target -> SPHEREx frames (per epoch x detector) + spectrum + light curve.

Parts of this file were written with the assistance of an AI coding assistant
(Claude, Anthropic) and reviewed by the team. See README "Use of AI".
"""
from __future__ import annotations

import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor
import time
from collections import OrderedDict

import numpy as np
from astropy.time import Time

import catalogs as cat
import spherex_core as sx

RESULTS_DIR = sx.ROOT / "data" / "results"
_CUTOUT_LRU: "OrderedDict[str, list[sx.Cutout]]" = OrderedDict()
_LRU_LOCK = threading.Lock()
PIPELINE_VERSION = 6


def job_key(p: dict) -> str:
    sig = json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in sorted(p.items())}
                     | {"v": PIPELINE_VERSION})
    return hashlib.sha1(sig.encode()).hexdigest()[:16]


def cached_result(key: str) -> dict | None:
    f = RESULTS_DIR / f"{key}.json"
    return json.loads(f.read_text()) if f.exists() else None


def _remember(key: str, cutouts: list[sx.Cutout]):
    with _LRU_LOCK:
        _CUTOUT_LRU[key] = cutouts
        _CUTOUT_LRU.move_to_end(key)
        while len(_CUTOUT_LRU) > 4:
            _CUTOUT_LRU.popitem(last=False)


def cutouts_for(key: str, params: dict) -> list[sx.Cutout]:
    """Cutouts of a finished job (memory, else re-read from the disk cache)."""
    with _LRU_LOCK:
        if key in _CUTOUT_LRU:
            return _CUTOUT_LRU[key]
    res = cached_result(key)
    if not res:
        return []
    ra0, dec0, size = res["grid"]["crval"][0], res["grid"]["crval"][1], res["fov_arcmin"] / 60
    cutouts = []
    for im in res["images"]:
        rec = sx.ImageRecord(uri=im["uri"], mjd=im["mjd"], det=im["det"], epoch=im["epoch"])
        path = sx.fetch_cutout(sx.cutout_url(rec, ra0, dec0, size))
        c = sx.load_cutout(rec, path) if path else None
        if c is not None:
            cutouts.append(c)
    _remember(key, cutouts)
    return cutouts


def target_track(p: dict, mjds: list[float]) -> list[tuple[float, float]]:
    return [cat.propagate(p["ra"], p["dec"], p.get("pmra", 0), p.get("pmdec", 0),
                          p.get("ref_epoch", 2000.0), cat.mjd_to_jyear(m)) for m in mjds]


_GAIA: "OrderedDict[str, dict]" = OrderedDict()


def gaia_neighbors(key: str, ra0: float, dec0: float, fov_arcmin: float, ep_meta: list[dict]) -> dict:
    """Gaia DR3 positions in the field, propagated to every visit: {epoch: [(ra, dec), ...]}.
    Used to deblend the target's PSF photometry from known neighbours."""
    with _LRU_LOCK:
        if key in _GAIA:
            return _GAIA[key]
    out: dict = {}
    try:
        g = cat.gaia_sources(ra0, dec0, fov_arcmin / 60 * 0.75, [e["jyear"] for e in ep_meta], gmax=20.5)
        out = {e["epoch"]: [s["positions"][i] for s in g["sources"]] for i, e in enumerate(ep_meta)}
    except Exception:
        out = {}
    with _LRU_LOCK:
        _GAIA[key] = out
        while len(_GAIA) > 8:
            _GAIA.popitem(last=False)
    return out


def spectrum_and_lightcurve(cutouts, positions_by_epoch=None, ra=None, dec=None,
                            neighbors_by_epoch=None, method: str = "aperture") -> dict:
    """Photometry at a fixed (ra, dec) or at a moving target position per epoch."""
    pts = []
    for c in cutouts:
        if positions_by_epoch is not None:
            r, d = positions_by_epoch[c.rec.epoch]
        else:
            r, d = ra, dec
        nb = None
        if neighbors_by_epoch and neighbors_by_epoch.get(c.rec.epoch):
            arr = np.asarray(neighbors_by_epoch[c.rec.epoch], dtype=float)
            sep = np.hypot((arr[:, 0] - r) * np.cos(np.radians(d)), arr[:, 1] - d) * 3600
            nb = arr[(sep > 6.0) & (sep < 36.0)]
        ph = sx.photometry_at(c, r, d, neighbors=nb, method=method)
        if ph is not None:
            pts.append(ph)
    pts.sort(key=lambda q: (q["wavelength_um"] or 0))
    # light curve: robust median per (epoch, detector)
    lc = []
    cells: dict = {}
    for q in pts:
        if q["good"]:
            cells.setdefault((q["epoch"], q["det"]), []).append(q)
    for (ep, det), qs in sorted(cells.items()):
        f = np.array([q["flux_mjy"] for q in qs])
        lc.append({"epoch": ep, "det": det, "mjd": float(np.mean([q["mjd"] for q in qs])),
                   "flux_mjy": float(np.median(f)),
                   "err_mjy": float(1.253 * np.std(f) / np.sqrt(len(f))) if len(f) > 1 else None,
                   "n": len(qs)})
    return {"points": pts, "lightcurve": lc}


PREVIEW_PER_CELL = 3                         # images per (visit, detector) in the first preview
KEY_EXCLUDE = ("name", "priority_dets")      # request fields that do not change the final result


def _epoch_meta(cutouts, records) -> list[dict]:
    out = []
    for ep in sorted({c.rec.epoch for c in cutouts}):
        cs = [c for c in cutouts if c.rec.epoch == ep]
        mjds = [c.rec.mjd for c in cs]
        out.append({"epoch": ep, "mjd": float(np.mean(mjds)),
                    "jyear": cat.mjd_to_jyear(float(np.mean(mjds))),
                    "date_start": Time(min(mjds), format="mjd").iso[:10],
                    "date_end": Time(max(mjds), format="mjd").iso[:10],
                    "n_images": len(cs),
                    "n_available": sum(1 for r in records if r.epoch == ep),
                    "dets": sorted({c.rec.det for c in cs})})
    return out


def run_frames_job(p: dict, progress, publish=None) -> dict:
    """p: ra, dec, pmra, pmdec, ref_epoch, fov_arcmin, max_per_cell, budget, name, priority_dets.

    Work is done in three groups so the browser can start blinking early (publish(partial)):
      1. "preview": the detectors on screen (priority_dets), first and last visit only
      2. "visits":  the same detectors, every other visit
      3. final:     the remaining detectors, then the spectrum and light curve
    Each (visit, detector) frame belongs to exactly one group, so frames are built once."""
    t0 = time.time()
    key = job_key({k: v for k, v in p.items() if k not in KEY_EXCLUDE})
    size_deg = p["fov_arcmin"] / 60.0

    # Centre the field on the target's position in the middle of the SPHEREx data range.
    progress("query", 0, 1, "Finding SPHEREx images of this position...")
    ra_mid, dec_mid = cat.propagate(p["ra"], p["dec"], p.get("pmra", 0), p.get("pmdec", 0),
                                    p.get("ref_epoch", 2000.0), 2025.9)
    records = sx.find_images(ra_mid, dec_mid)
    if not records:
        raise RuntimeError("No SPHEREx images cover this position yet.")
    epochs = sx.group_epochs(records)
    n_total = len(records)
    chosen = sx.budget_select(records, p.get("max_per_cell", 8), p.get("budget", 260))
    progress("query", 1, 1, f"{n_total} images in {len(epochs)} visits; downloading {len(chosen)}")
    grid, shape = sx.make_grid(ra_mid, dec_mid, size_deg)

    prio = [d for d in (p.get("priority_dets") or []) if d in sx.DETECTORS] or ["D5", "D6"]
    ep_ids = sorted({r.epoch for r in chosen})
    # first and last visit that the on-screen detectors actually cover (a field near the edge of the
    # focal plane can be seen by only some detectors in a visit)
    ep_prio = sorted({r.epoch for r in chosen if r.det in prio}) or ep_ids
    ends = {ep_prio[0], ep_prio[-1]}
    # Preview: at most PREVIEW_PER_CELL images (spread in time) of each on-screen detector in the
    # first and last visit; the rest of those cells is added in the "visits" stage.
    preview = []
    for ep in sorted(ends):
        for det in prio:
            cell = [r for r in chosen if r.epoch == ep and r.det == det]
            idx = sorted(set(np.linspace(0, len(cell) - 1, min(PREVIEW_PER_CELL, len(cell))).round().astype(int))) if cell else []
            preview += [cell[i] for i in idx]
    in_preview = {id(r) for r in preview}
    groups = [g for g in (
        ("preview", preview),
        ("visits", [r for r in chosen if r.det in prio and id(r) not in in_preview]),
        ("final", [r for r in chosen if r.det not in prio])) if g[1]]

    def assemble(cutouts, frames, phot=None, partial=None):
        ep_meta = _epoch_meta(cutouts, records)
        track = target_track(p, [e["mjd"] for e in ep_meta])
        res = {
            "key": key, "name": p.get("name"),
            "target": {k: p.get(k) for k in ("ra", "dec", "pmra", "pmdec", "ref_epoch")},
            "fov_arcmin": p["fov_arcmin"],
            "quality": {"max_per_cell": p.get("max_per_cell", 8), "budget": p.get("budget", 260)},
            "grid": {"crval": [ra_mid, dec_mid], "crpix": list(grid.wcs.crpix), "cdelt": list(grid.wcs.cdelt),
                     "shape": list(shape)},
            "epochs": [e | {"target_ra": t[0], "target_dec": t[1]} for e, t in zip(ep_meta, track)],
            "frames": [{"epoch": ep, "det": det, "n": n, "data": sx.b64f32(arr)}
                       for (ep, det), (arr, n) in sorted(frames.items())],
            "images": [{"uri": c.rec.uri, "mjd": c.rec.mjd, "det": c.rec.det, "epoch": c.rec.epoch,
                        "obs_id": c.rec.obs_id} for c in cutouts],
            "stats": {"n_total": n_total, "n_downloaded": len(chosen), "n_used": len(cutouts),
                      "rejected": dict(rejected), "seconds": round(time.time() - t0, 1)},
            **(phot or {"points": [], "lightcurve": []}),
        }
        if partial:
            res["partial"] = partial
            res["visits_total"] = len(ep_ids)
        return res, ep_meta, track

    # The preview downloads alone (on a small server the CPU is the bottleneck, so anything running
    # beside it only delays the first frames); the later groups are queued together right after it,
    # in priority order, and download while earlier groups are processed.
    cutouts, frames, rejected = [], {}, {"failed": 0, "transient": 0}
    by_cell: dict = {}
    n_done = [0]
    done_lock = threading.Lock()

    def fetch(rec):
        path = sx.fetch_cutout(sx.cutout_url(rec, ra_mid, dec_mid, size_deg))
        with done_lock:
            n_done[0] += 1
            k = n_done[0]
        progress("download", k, len(chosen), f"Downloading cutouts {k}/{len(chosen)}")
        return path

    pool = ThreadPoolExecutor(max_workers=24)
    futures = [(groups[0][0], [(rec, pool.submit(fetch, rec)) for rec in groups[0][1]])]
    for gi, (label, items) in enumerate(futures):
        new = []
        for rec, fut in items:
            path = fut.result()
            c = sx.load_cutout(rec, path) if path else None
            if c is None:
                rejected["failed"] += 1
            elif c.n_transient > sx.MAX_TRANSIENT_PIXELS:
                rejected["transient"] += 1
            else:
                new.append(c)
        cutouts += new
        touched = set()
        for c in new:
            by_cell.setdefault((c.rec.epoch, c.rec.det), []).append(c)
            touched.add((c.rec.epoch, c.rec.det))
        if touched:                       # rebuild only the frames that got new images
            frames.update(sx.build_frames([c for k in touched for c in by_cell[k]], grid, shape))
        if publish and label != "final" and frames:
            try:
                publish(assemble(cutouts, frames, partial=label)[0])
            except Exception:
                pass                        # a preview must never break the job
        if gi == 0:                       # preview on screen: queue everything else now
            futures += [(lb, [(rec, pool.submit(fetch, rec)) for rec in grp]) for lb, grp in groups[1:]]
    pool.shutdown(wait=False)
    if not cutouts:
        raise RuntimeError("All cutouts failed to download; the archive may be overloaded. Try again shortly.")
    _remember(key, cutouts)

    progress("process", 1, 1, "Measuring the spectrum and light curve (PSF fit, Gaia-deblended)...")
    ep_meta = _epoch_meta(cutouts, records)
    track = target_track(p, [e["mjd"] for e in ep_meta])
    pos_by_epoch = {e["epoch"]: t for e, t in zip(ep_meta, track)}
    nbrs = gaia_neighbors(key, ra_mid, dec_mid, p["fov_arcmin"], ep_meta)
    phot = spectrum_and_lightcurve(cutouts, positions_by_epoch=pos_by_epoch,
                                   neighbors_by_epoch=nbrs, method="psf")
    result = assemble(cutouts, frames, phot=phot)[0]
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / f"{key}.json").write_text(json.dumps(result))
    return result
