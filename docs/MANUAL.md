# BIOLP — User Manual

This manual complements the [README](../README.md) with:
1. a full walkthrough of running the deterministic CN pipeline (`src/`) through `config.yml`;
2. how the pipeline's output interfaces with **LANDPLANER** and **MUSE** — both private, not distributed in this repository;
3. how to reproduce the accuracy validation of MUSE's stochastic vegetation simulation (`validation/`).

## 1. Pipeline overview

```
DTM + Hydrologic Soil Group + Land Cover  ──▶  src/main.py  ──▶  CN rasters + terrain derivatives  ──▶  LANDPLANER (private)
                                                                                                              ▲
                                          MUSE (private) ── stochastic, vegetation-based CN maps ────────────┘
```

`src/main.py` is the only entry point. It is a thin orchestrator: it reads `config.yml`, then calls (via `subprocess`) the three GRASS/Python sub-scripts in order, and optionally LANDPLANER's R script:

1. **`1_vimport.py`** (runs inside a GRASS session) — imports the DTM, computes terrain derivatives (slope, flow accumulation, drainage direction, basins), imports the Hydrologic Soil Group (HSG) and Corine Land Cover (CLC) vectors, overlays them, and fills polygons with missing HSG using a nearest-neighbour rule.
2. **`2_HSGtoCN.py`** (plain Python, no GRASS) — reads the HSG-CLC overlay table and a CLC→CN lookup table, and computes the Curve Number (mean/max/min) for every polygon, following the SCS-CN convention.
3. **`3_CNmap.py`** (runs inside a GRASS session) — joins the computed CN values back onto the vector overlay and rasterizes it to `.asc` (one raster per CN variant).
4. **LANDPLANER** (external, private, optional) — consumes the terrain derivatives and CN rasters produced above to run the erosion model.

Everything that varies between runs (study area, thresholds, input file names, CN policy, etc.) is read from `config.yml` — the scripts themselves should not need editing to point at a different dataset.

## 2. Prerequisites

See the README's [Requirements](../README.md#requirements) section for GRASS GIS, Python and R setup. In short:
```bash
pip install -r requirements.txt
```
and make sure `grass` is on `PATH` (or set `grass.bin` in `config.yml`, see below).

Don't have the real dataset yet? `demo/` ships a small synthetic one to try the pipeline end-to-end in minutes — see [`../demo/README.md`](../demo/README.md).

## 3. Configuration file reference (`config.yml`)

### `paths`
| Key | Type | Meaning |
|---|---|---|
| `data_dir` | str | Folder with the input data, relative to the repository root. Defaults to `data` if omitted. Set to `demo/data` to run against the synthetic demo dataset instead of the real one |

### `grass`
| Key | Type | Meaning |
|---|---|---|
| `db` | str | Name of the GRASS GISDBASE folder, created under your home directory (`~/<db>`) |
| `loc` | str | GRASS location name; also used as a prefix for the output folder name |
| `mapset` | str | GRASS mapset name (typically `PERMANENT`) |
| `bin` | str | Optional full path to the `grass` executable. Leave `""` to auto-detect via `which grass` |

The GRASS location is destroyed and recreated from the DTM every time the `import` (or `all`) step runs. Running `--step hsgtocn/cnmap/landplaner` on its own reuses the existing location instead — `import` must have completed at least once first.

### `dtm`
| Key | Type | Meaning |
|---|---|---|
| `path` | str | Subfolder of `data/` containing the DTM |
| `name`, `ext` | str | DTM file name/extension (file: `data/<path>/<name>.<ext>`) |
| `res` | number | Target resolution in meters. If it differs from the DTM's native resolution, `g.region` resamples the working region to it |
| `set_clip` | bool | If `True`, clip every output raster/vector to `mask` |
| `mask` | str | Mask vector file, expected under `data/in/<mask>` |

### `hsg` (Hydrologic Soil Group)
| Key | Type | Meaning |
|---|---|---|
| `dir`, `name`, `ext` | str | HSG vector file: `data/<dir>/<name>.<ext>` |
| `layer` | str | Layer name to read from the file (relevant for multi-layer formats like GeoPackage) |
| `field` | str | Attribute column holding the HSG class (`A`/`B`/`C`/`D`) |
| `field_label` | str | Prefix GRASS's `v.overlay` adds to the column name after the HSG-CLC overlay (e.g. `field_label: b_` + `field: gi` → column `b_gi` in the overlay output) |

### `corine` (land cover)
| Key | Type | Meaning |
|---|---|---|
| `enabled` | bool | `True`: loop over every file matching `pattern` in `dir` (one full pipeline run per file/date — use this for multi-temporal or multi-scenario land cover); `False`: use `single_file` only, looping instead over every attribute column starting with `field` found in it (use this when one file already holds several land-cover scenarios as separate columns) |
| `dir`, `pattern` | str | Folder and glob pattern used when `enabled: True` (e.g. `clc*.shp`) |
| `single_file` | str | Land cover file used when `enabled: False` |
| `field` | str | Attribute column (or column prefix) holding the land cover code |
| `field_label` | str | Prefix added to `field` after the HSG-CLC overlay, analogous to `hsg.field_label` |

### `computecn`
| Key | Type | Meaning |
|---|---|---|
| `clc_hsg` | str | Base name used for the HSG-CLC overlay vector/table (e.g. `hsg_CLC_overlay`) |
| `lookuptable` | str | CLC→CN lookup table, `data/<lookuptable>` — one row per CLC level-III class, one column per HSG class (`CN_HSG_A_VALUE` … `CN_HSG_D_VALUE`), optionally split by hydrologic condition |
| `enabled_hc` | bool | Whether to filter the lookup table by hydrologic condition |
| `set_hc` | str | Which hydrologic condition to filter on (e.g. `Poor`/`Fair`/`Good`), used only if `enabled_hc: True` |
| `hsg_missing_policy` | str | How to assign a CN when a polygon has no HSG value. One of:<br>• `nearest` — HSG is filled from the nearest polygon with a known HSG value, in GRASS, during `1_vimport.py`. Any polygon still empty afterwards falls back to `-9999`.<br>• `weighted` — weighted average CN across all four HSG classes (weights favor B/C, the most common in nature)<br>• `fixed` — always use `fixed_hsg`<br>• `original` — leave the CN as `-9999` (no attempt to fill) |
| `fixed_hsg` | str | HSG class (`A`/`B`/`C`/`D`) used when `hsg_missing_policy: fixed` |

Regardless of policy, a CLC code truncated to CORINE level I or II (rather than the expected level III) is always treated as `fixed_hsg: D`, since the lookup table is indexed at level III.

### `landplaner`
| Key | Type | Meaning |
|---|---|---|
| `enabled` | bool | Defaults to `True`. Set to `False` to skip the `landplaner` step entirely (e.g. when the private script isn't available — this is why `demo/config_demo.yml` sets it to `False`) instead of attempting to run `Rscript` and failing |
| `version` | str | File name (without `.r`) of the LANDPLANER script expected in `external/` |
| `out_dir` | str | Base name of the output subfolder LANDPLANER writes to; the actual name used is `<out_dir>_<CN variant>` (e.g. `synth_noroot_CN`, `synth_noroot_CN_max`, `synth_noroot_CN_min`) |

### `muse`
| Key | Type | Meaning |
|---|---|---|
| `enabled` | bool | Defaults to `False`. MUSE runs entirely separately from this script (see §6); set to `True` to also feed its output CN raster into the `landplaner` step as an extra scenario, alongside `CN_min`/`CN`/`CN_max` |
| `cn_raster` | str | Path to a MUSE-derived CN raster (`.asc`), relative to `paths.data_dir` or absolute. Ignored unless `muse.enabled: True` |

## 4. Running the pipeline

```bash
cd src
python3 main.py --config ../config.yml --step all
```

`--step` (default `all`) runs a single stage: `import`, `hsgtocn`, `cnmap`, or `landplaner`. A typical iterative workflow, after having run `--step all` once:
```bash
# Tweak computecn.hsg_missing_policy in config.yml, then only recompute CN and its raster:
python3 main.py --config ../config.yml --step hsgtocn
python3 main.py --config ../config.yml --step cnmap
```

Each run writes:
- a copy of the resolved configuration to `<output folder>/run_config.json`, for provenance;
- a timestamped log to `logs/main_<timestamp>.log` at the repository root.

See the README's [Outputs](../README.md#outputs) section for the full output folder layout.

## 5. Interfacing with LANDPLANER (private — available on request)

LANDPLANER (M. Rossi, 2014) is **not distributed in this repository**. `src/main.py` only *calls* it, as an external dependency expected to be placed by the user in `external/<landplaner.version>.r`, with `Rscript` on `PATH`. If you would like access to LANDPLANER for research purposes, please contact the corresponding author (see the README's [Contributor](../README.md#contributor) section).


## 6. Interfacing with MUSE (private — available on request)

MUSE is a stochastic, vegetation-based tool that produces hydrologically-conditioned CN maps as an alternative (or complement) to the deterministic SCS-CN branch implemented in `src/`. It is **not distributed in this repository**; for methodological details and results, please refer to:

- **PhD Thesis**: M. Miola (2025), Increase the knowledge of Natural Systems through the evaluation of the uncertainty of environmental data: operational theory and application
- **Poster**: M. Miola et al. (2022), MUSE: Modeling Uncertainty as a Support for Environment (https://doi.org/10.2312/stag.20221265)

If you would like access to the MUSE code for research purposes, please contact the corresponding author (see the README's [Contributor](../README.md#contributor) section).
