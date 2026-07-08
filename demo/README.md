# BIOLP demo (synthetic watershed)

A small hydrologically meaningful synthetic watershed is provided to run the full CN + erosion pipeline in a couple of minutes. Only GRASS GIS is required. 
`landplaner.enabled` is set to `False` in `demo/config_demo.yml`, since the final `landplaner` step
needs a private source code;
 `muse.enabled` is also `False`, since MUSE is a separate, private tool.

## The synthetic watershed
`generate_synthetic_data.py` (GDAL/OGR + numpy, no GRASS needed to run it)
builds a single, closed catchment: 2 km × 2 km, 10 m cells, shaped like an
elongated bowl — ridges on three sides, one outlet at the middle of the
southern edge — so GRASS's watershed delineation converges on one basin and
one outlet, not an arbitrary hilly surface (verified: at 10 m resolution the
whole 200×200 = 40,000-cell domain drains to the outlet, with flow
accumulation reaching ~38,000 cells there).

Land cover and soil are zoned to produce a **deliberate erosion contrast at
comparable slope**, so the demo is actually informative about erosion, not
just about the pipeline's mechanics:

| Zone | Slope position | Land cover | HSG | Resulting CN (HC=Fair) |
|---|---|---|---|---|
| Upper-west | steep (headwaters) | broad-leaved forest (`311`) | A (well-drained) | 36 |
| Upper-east | steep (headwaters) | arable land (`211`) | D (poorly-drained) | 89 |
| Middle-west | mid-slope | coniferous forest (`312`) | B | 56 |
| Middle-east | mid-slope | arable land (`211`) | D | 89 |
| Valley bottom | flat, near the outlet | pastures (`231`) | C (with a small NULL patch, see below) | 79 |

i.e. the west side of the catchment is a protected, well-drained forest, the
east side is poorly-drained arable land at the *same* slope, and the valley
bottom is flat pasture near the outlet. `CLC_HC_CN_descr.csv` is the matching
CLC→CN lookup table (illustrative values, **not an authoritative SCS-CN
reference table**). 
A small square in the valley-bottom HSG layer is left
without a value on purpose, to exercise the `hsg_missing_policy: nearest` fill
in `1_vimport.py` (confirmed working: the one missing polygon gets filled from
its nearest neighbour, `C`, during import).

Because every polygon in this synthetic dataset matches exactly one row of
the lookup table (no averaging across multiple hydrologic-condition rows),
`CN_min`, `CN` (mean) and `CN_max` come out **identical** here — that's
expected for this dataset, not a bug (see `docs/MANUAL.md` for when they'd
actually differ).


## How to run
```bash
cd src
python3 main.py --config ../demo/config_demo.yml --step import
python3 main.py --config ../demo/config_demo.yml --step hsgtocn
python3 main.py --config ../demo/config_demo.yml --step cnmap
python3 main.py --config ../demo/config_demo.yml --step landplaner
```
`demo/config_demo.yml` uses its own GRASS location (`grass.loc: biolp_demo`,
`grass.db: grassdata_demo`) so it never touches a real project's GRASS
database, and points `paths.data_dir` at `demo/data` instead of the real
`data/` folder. `dtm.set_clip` is `False`: the DTM is already a single closed
watershed, so no clipping mask is needed.

`landplaner.enabled` is set to `False` in `demo/config_demo.yml`, so the last
command above prints a one-line "step skipped" message and exits cleanly
instead of trying (and failing) to run a script this repository doesn't
distribute (see
[`../docs/MANUAL.md`](../docs/MANUAL.md#5-interfacing-with-landplaner-private--available-on-request)).
If you have your own copy of LANDPLANER in `external/`, set `landplaner.enabled: True`
in `demo/config_demo.yml` to actually run it (that's how the reference results
below were produced). Running `import`/`hsgtocn`/`cnmap` is enough to exercise
the whole public part of the pipeline (terrain derivatives, HSG-CLC overlay,
Curve Number computation and rasterization).

## Expected output
```
out/biolp_demo_10/
├── run_config.json
├── dtm_demo.asc, slope.asc, accumulation.asc, drainage_abs.asc, basin.asc
├── hsg_CLC_overlay.csv, hsg_CLC_overlay_out.gpkg
└── ucs/
    ├── CN_min.csv, CN.csv, CN_max.csv
    ├── hsg_CLC_overlay_CN_min.asc, hsg_CLC_overlay_CN.asc, hsg_CLC_overlay_CN_max.asc
    └── synth_noroot_CN<_min|_max>_<rainfall_mm>/                                           # LANDPLANER output, if that step was run
```
The whole run (import + hsgtocn + cnmap) takes well under a minute. Slope
ranges from ~2° to ~30°, confirming the intended steep-headwaters /
flat-valley-bottom contrast.

## Reference results (with LANDPLANER)
For anyone who *does* have access to LANDPLANER, here is what running the full
pipeline on this synthetic watershed produces — included so a reviewer without
LANDPLANER can still see what a plausible, sensible outcome looks like, and so
those who do have it can sanity-check their own run against it.

LANDPLANER runs the erosion model once per CN variant and per design rainfall
depth (20 to 140 mm, in its own 20 mm steps), each written to its own
`synth_noroot_CN*_<mm>/` subfolder with LANDPLANER's native output rasters
(`e.asc`, `eout.asc`, `epot.asc`, `qdout.asc`, ...). Zonal averages of `e.asc`
(erosion) at 100 mm rainfall:

| Zone | CN | Mean erosion | Max erosion |
|---|---|---|---|
| Upper-west (forest, HSG A) | 36 | ~0.01 | ~19 |
| Upper-east (arable, HSG D) | 89 | ~14.6 | ~590 |
| Middle-west (forest, HSG B) | 56 | ~0.03 | ~78 |
| Middle-east (arable, HSG D) | 89 | ~35.2 | ~3039 (basin maximum) |
| Valley bottom (pasture, HSG C, flat) | 79 | ~9.0 | ~1739 |

This matches the intended story: at comparable (steep) slope, the arable/
poorly-drained side erodes orders of magnitude more than the forested/
well-drained side — land cover and soil, not just slope, drive the estimated
erosion. The flat valley bottom instead shows a different pattern: low mean
erosion (slope-limited) but locally high peaks near the converging channel,
where accumulated discharge (`qdout.asc`) is highest. Absolute values are an
artifact of this synthetic terrain/rainfall and are not meant to represent a
real erosion rate.
