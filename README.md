# SPHEREx Time Machine

**Blink the infrared sky. Spot what moves. Read its spectrum.**

**Live tool: https://spherex-time-machine.onrender.com** (free hosting: the first visit after a quiet period can take ~1 minute to wake up).

Try: [WISE 0855 difference](https://spherex-time-machine.onrender.com/#target=wise0855&mode=diff&dets=D5,D6) · [Barnard's Star](https://spherex-time-machine.onrender.com/#target=barnard&dets=D2,D3) · [R Draconis light curve](https://spherex-time-machine.onrender.com/#target=r_dra) · [Interstellar comet 3I/ATLAS](https://spherex-time-machine.onrender.com/#object=3I&fov=4&mode=stack)

A public web tool for the NASA Space Apps Challenge 2026 *"Planet X and SPHEREx"*. Enter a sky position or an object name, and the tool shows a series of NASA SPHEREx images of that patch of sky like a short movie, making moving and variable objects easy to see. Click anywhere to get an on-the-fly 0.75–5 µm spectrum.

## Features

- **Blink** SPHEREx images of any position, one frame per visit (DR1 + QR3 + deep fields, queried live from NASA/IPAC IRSA, so newly released data appears automatically).
- **Six detector arrays** selectable individually or combined; frames are co-added per visit and detector for signal-to-noise.
- **Difference mode**: each visit minus the median of the other visits. Static stars cancel; movers leave a dipole.
- **False-colour mode** (blue = D1+D2, green = D3+D4, red = D5+D6) and **D6−D4 mode**: cold brown dwarfs are bright at 4.5 µm but dark in the 3.3 µm methane band.
- **Proper-motion aware**: named targets are propagated to the SPHEREx epochs. High-proper-motion stars (Barnard's Star moved 4.4′ since J2000; WISE 0855 sits ~2′ from its catalogue position) are found automatically, and the predicted track is drawn on the images.
- **On-the-fly spectrum and light curve** at the target or at any clicked position, coloured by visit, with molecular bands (H₂O, CH₄, CO₂, CO) and emission lines marked. Fluxes come from forced photometry with the SPHEREx effective PSF, fitted simultaneously with neighbouring Gaia DR3 stars so blended light is removed (WISE 0855 sits 8″ from a G = 16 star: after deblending its spectrum is dark below 3.8 µm and matches the published WISE W2 and Spitzer 3.6 µm fluxes).
- **Automatic candidate boxes** on the difference images: *mover?* (positive/negative dipole), *variable?*, and *one visit only* (asteroid, transient or artifact). Hints for human eyes, with cosmic-ray, bright-star and saturation safeguards.
- **Measured proper motion**: per-visit centroids are fitted to measure the target's motion directly from SPHEREx and compare it with the catalogue value.
- **25-year baseline**: archival 2MASS (1997–2001) and AllWISE (2010) images of the same field are fetched from IRSA, reprojected onto the SPHEREx grid and added as extra blink/difference frames (2000 → 2010 → 2025 → 2026). WISE 0855 jumps ~2′ across the field; including the WISE epoch tightens its measured motion to 8.20 ± 0.03″/yr (catalogue 8.15″/yr).
- **Solar System object mode** (IRSA MOST): follow an asteroid or comet through every SPHEREx image, with object-centred frames and a shift-and-add *Stack* mode. Demo: interstellar comet 3I/ATLAS.
- **Overlays**: Gaia DR3 (propagated to each visit from J2016.0, fast movers drawn with motion arrows), known asteroids and comets (JPL Small-Body Identification), target track.
- **"No Gaia counterpart" badge**: a moving source invisible to Gaia is too cold for optical light – the classic brown-dwarf signature used by citizen scientists.
- **Data-quality notes** from SPHEREx pixel flags (ghosts, streaks, cosmic rays, persistence) at the measured position; frames with heavy transient contamination are skipped.
- **Shareable/embeddable URLs**: every setting lives in the URL, e.g. `/#target=wise0855&mode=diff&dets=D5,D6` or `/#ra=269.452&dec=4.693&pmra=-802&pmdec=10362&fov=8`.
- **Links out**: WiseView (13 years of WISE), SIMBAD, CADC SSOIS (other telescopes at this position), Legacy Survey, IRSA SPHEREx Data Explorer.
- Keyboard: Space play/pause · ← → step · B/D/C modes · I invert · + − zoom.

## Running locally

```bash
python3 -m venv .venv
.venv/bin/pip install astropy astroquery numpy reproject fastapi uvicorn
.venv/bin/uvicorn main:app --app-dir backend --port 8000
# open http://localhost:8000
```

Optional – pre-compute the demo targets so they load instantly:

```bash
.venv/bin/python scripts/warm_cache.py 5
```

## How it works

```
Browser (vanilla JS, canvas, Plotly)          FastAPI backend (Python)
  blink / difference / colour rendering  <--   /api/frames   own index -> AWS cutouts -> clean -> reproject -> co-add
  stretch, invert, zoom (instant)              /api/spectrum aperture photometry on every image
  WCS (TAN) for overlays & clicks              /api/gaia     ESA Gaia archive (MAST fallback)
  URL state, keyboard                          /api/asteroids JPL sb_ident
                                               /api/resolve  built-in targets, CDS Sesame
                                               disk cache of cutouts and results
```

- **Finding images – our own index, no database query.** All 1.63 million SPHEREx Level-2 images (273,000 exposures) are indexed by `scripts/build_index.py`, which reads ~9 kB of each 65 MB file in the public AWS copy (`s3://nasa-irsa-spherex`). D1+D4, D2+D5 and D3+D6 see the same sky and D1–D3 sit side by side, so one pointing per exposure plus a fixed focal-plane map describes all six footprints. Each exposure is stored as a 3-D unit vector, so "which images cover this position?" becomes one dot product per exposure (a 3-D search reduced to comparing a single number), followed by a vectorised gnomonic projection of the candidates: a few milliseconds, and it keeps working when the IRSA database is down. The IRSA TAP service (`spherex.artifact`/`spherex.plane`) is the fallback.
- **Cutouts straight from the cloud.** Level-2 images are uncompressed FITS, so a cutout is a handful of HTTP range requests (headers, the rows that cover the box, the row-compressed FLAGS tiles, one ePSF zone, the spectral WCS). The result is pixel-for-pixel identical to an IRSA cutout; the IRSA cutout service is the fallback.
- **Progressive loading.** For a position never loaded before, the detectors on screen are processed first, first and last visit before the others, and each stage is shown as soon as it is ready; the remaining detectors and the spectrum follow in the background while the animation plays. All downloads are queued up front in that order so network and processing overlap. Loaded fields open instantly.
- Cleaning: zodiacal light model (ZODI extension) subtracted; pixels with bad FLAGS bits masked (Explanatory Supplement Table 16); per-image background removed.
- Alignment: every cutout reprojected onto a common north-up TAN grid (6.15″ pixels) with `reproject`.
- Co-addition: one inverse-variance–weighted frame per (visit, detector); the browser normalises and combines detectors on the fly.
- Spectrum: each SPHEREx pixel has its own wavelength (linear variable filter); per-image forced PSF photometry (ePSF extension of each image, weighted by the variance map, fitted together with Gaia DR3 neighbours and a local background) at the target position for that image's date gives one spectral point per image. Saturated stars are measured on their unsaturated PSF wings (relative fluxes only).

## Data and resources

**NASA:** SPHEREx DR1 (DOI 10.26131/IRSA678) and QR3 (DOI 10.26131/IRSA662) spectral images via NASA/IPAC IRSA; SPHEREx Explanatory Supplement; IRSA SPHEREx tutorial notebooks; IRSA MOST; JPL Small-Body Identification API; WiseView (inspiration).
**Space agency partners:** ESA Gaia DR3; Canadian Space Agency NEOSSat tutorial and Canadian Astronomy Data Centre (SSOIS, DSS).
**Other:** CDS Sesame name resolver; astropy, astroquery, reproject, FastAPI, Plotly.js.

### Acknowledgements

This publication makes use of data products from the Spectro-Photometer for the History of the Universe, Epoch of Reionization and Ices Explorer (SPHEREx), which is a joint project of the Jet Propulsion Laboratory and the California Institute of Technology, and is funded by the National Aeronautics and Space Administration. This research has made use of the NASA/IPAC Infrared Science Archive, which is funded by NASA and operated by the California Institute of Technology. This work has made use of data from the European Space Agency (ESA) mission Gaia, processed by the Gaia Data Processing and Analysis Consortium. This research used the facilities of the Canadian Astronomy Data Centre operated by the National Research Council of Canada with the support of the Canadian Space Agency.

This is not an official NASA product and does not imply endorsement by NASA, JPL, Caltech, ESA or CSA.

## Use of AI (Super Intelligence) tools

As required by the NASA Space Apps rules, we disclose that an AI coding assistant (Claude, by Anthropic) was used during the hackathon to help survey the challenge resources and to draft parts of the code (backend pipeline, API server and frontend). Files containing AI-assisted code say so in their header comment. The team chose the challenge, made the design decisions, and reviewed, tested and is responsible for all code and results. No AI-generated images, audio or video are used.

## License

MIT (see LICENSE). Third-party data remain subject to their providers' terms.
