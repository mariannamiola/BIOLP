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

To let someone with their own copy of LANDPLANER plug it in, this is the exact command-line interface `main.py` expects from it (see `src/main.py`, `--step landplaner`):

```bash
Rscript <landplaner.version>.r --args \
  -wd <output folder> \
  -dem <dtm name>.asc \
  -slope slope.asc \
  -acc accumulation.asc \
  -drain drainage_abs.asc \
  -cn <computecn.clc_hsg>_<CN variant>.asc \
  -ba basin.asc \
  -outfolder <landplaner.out_dir>_<CN variant>
```
where `<CN variant>` is each of `CN_min`, `CN`, `CN_max` in turn, and every `.asc` file referenced above is produced by `1_vimport.py`/`3_CNmap.py` in the same output folder. Anyone holding a separate copy of LANDPLANER only needs a script that accepts these arguments to slot into this pipeline unmodified.

## 6. Interfacing with MUSE (private — available on request)

MUSE is a stochastic, vegetation-based tool that produces hydrologically-conditioned CN maps as an alternative (or complement) to the deterministic SCS-CN branch implemented in `src/`. It is **not distributed in this repository**; for methodological details and results, please refer to:

- **Thesis**: [Cognome, Titolo della tesi, Anno, Ateneo] — *placeholder, to be completed*
- **Poster**: [Titolo del poster, Conferenza/Venue, Anno, link] — *placeholder, to be completed*

If you would like access to the MUSE code for research purposes, please contact the corresponding author (see the README's [Contributor](../README.md#contributor) section).

MUSE-derived CN rasters are meant to be fed into the same LANDPLANER step described in §5, alongside the deterministic `CN_min`/`CN`/`CN_max` rasters produced by this pipeline — LANDPLANER's interface does not distinguish between the two sources. `main.py` provides an explicit hook for this: set `muse.enabled: True` and `muse.cn_raster` (see §3) to the path of a MUSE-produced CN raster, and the `landplaner` step will run LANDPLANER once more using it, writing its output to `<landplaner.out_dir>_MUSE`. This only runs if `landplaner.enabled: True` as well — a MUSE CN raster still needs LANDPLANER itself to turn it into an erosion estimate.

## 7. Validating the stochastic vegetation simulation (`validation/`)

`validation/` contains the accuracy assessment of MUSE's simulated vegetation classification against an independent ground-truth vegetation map. This validates MUSE's stochastic vegetation output specifically — it is independent of, and not required to reproduce, the deterministic CN/erosion pipeline in `src/`.

> **Status**: `validation/vegetation_accuracy_assessment.py` is a working version, still being refined.

### Purpose
MUSE simulates vegetation classes from a set of sample points; this script quantifies how well the simulated map reproduces an independently mapped ground truth, and how sensitive the result is to the **sampling design** used to condition the simulation. Three configurations are compared:

| Configuration | Description |
|---|---|
| `Random` | Sample points placed at random locations |
| `Grid 100x100` | Regular grid, 100 m spacing |
| `Grid 200x200` | Regular grid, 200 m spacing |

Sample-point layouts and pre-computed example outputs are not shipped in this
repository (ground truth and MUSE simulation output are private); running the
script against your own data (see below) regenerates them.

### Requirements
```bash
pip install geopandas pandas numpy scipy scikit-learn matplotlib seaborn
```

### Expected inputs
The script (edit the `CONFIGURATION` block at the top of the file to point at your own data):

- **Ground truth** (`GROUND_TRUTH_PATH`, default `data/ground_truth_clip.gpkg`): any vector format readable by `geopandas`, with a geometry column and a string class column (`GT_CLASS_COLUMN`, default `vege`).
- **Simulation output**, one CSV per sampling configuration (`CONFIGS`, default `results_sis/sis_random.csv`, `sis_grid100.csv`, `sis_grid200.csv`): columns `x`, `y`, `best_guess` (integer class code) and one probability column per class (`PROB_COLS`, e.g. `pdf_cat1` … `pdf_cat9`), as produced by MUSE.
- **Class map** (`CLASS_MAP`): integer → string label, must match the ground truth's class labels. The nine classes currently configured are: `castanea`, `altre latifoglie`, `macchia a leccio`, `macchia a sughera`, `bosco misto di pino e castagno`, `pineta`, `formazione di pino post incendio`, `formazioni di macchia post incendio`, `agricolo / altre superf. non boscate`.

Both `data/` and `results_sis/` are expected as subfolders of `validation/` (i.e. `validation/data/ground_truth_clip.gpkg`, `validation/results_sis/sis_random.csv`, ...) unless you edit the paths to point elsewhere.

### What it computes
For each configuration, after spatially joining every simulated point to the ground-truth polygon it falls within:

- **Overall Accuracy (OA)** and **Cohen's Kappa** (`sklearn.metrics.accuracy_score`, `cohen_kappa_score`);
- **Per-class Producer's Accuracy** (recall), **User's Accuracy** (precision), **F1-score**, **Omission error** (`1 - recall`), **Commission error** (`1 - precision`) and support, via `sklearn.metrics.classification_report`;
- a **normalised confusion matrix** heatmap (`confmat_<config>.png`);
- a **Shannon-entropy uncertainty map** (bits) computed per point from its class-probability vector, as a spatial measure of classification confidence (`entropy_<config>.png`), together with diagnostics: the theoretical maximum entropy (`log2(n_classes)`), the correlation between entropy and the top predicted probability (expected negative), mean entropy grouped by correct/incorrect classification, and accuracy across entropy quintile bins (printed to console).

### Outputs
Running `python3 vegetation_accuracy_assessment.py` (from `validation/`) writes to `output_accuracy/`:
- `summary_accuracy.csv` / `.tex` — OA and kappa per configuration;
- `perclass_accuracy.csv` / `.tex` — producer's/user's accuracy, F1-score, omission/commission error, support per class per configuration;
- `confmat_<config>.png` — normalised confusion matrix;
- `entropy_<config>.png` — spatial uncertainty map.
