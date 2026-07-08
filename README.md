# BIOLP
Injecting BIOdiversity in Landscape Processes

This repository contains the data-preparation and orchestration code used in the paper to estimate **potential soil erosion** over a study area, following the **SCS Curve Number (CN)** method.

The full research workflow combines several components:

- **GRASS GIS** preprocessing of public geospatial inputs (DTM, CORINE Land Cover, hydrologic soil group) and deterministic estimation of the Curve Number;
- **MUSE**, a stochastic tool for vegetation-based, hydrologically-conditioned CN mapping (not distributed here, private code; M. Miola, 2025);
- **LANDPLANER**, a landslide and erosion modelling tool (not distributed here, private code; M. Rossi, 2014).

**What this repository contains**: the Python/GRASS pipeline (`src/`) that turns a DTM, a land cover map and a hydrologic soil group map into the CN rasters (and terrain derivatives: slope, flow accumulation, drainage direction, basins) that LANDPLANER consumes. MUSE and LANDPLANER themselves are not redistributed here; the code only calls LANDPLANER as an external dependency (`external/`, if available on your machine) so that the full erosion-modelling run can be reproduced by someone who separately holds a license/copy of that tool.

See **[docs/MANUAL.md](docs/MANUAL.md)** for the full user manual: a detailed `config.yml` reference, how the pipeline's output interfaces with LANDPLANER and MUSE (both private, available on request), and how to reproduce the accuracy validation of the stochastic vegetation simulation.

## How to clone
```
git clone https://github.com/mariannamiola/BIOLP.git
```


## Requirements
- **GRASS GIS** ≥ 7.8, with the [`grass`](https://grass.osgeo.org/download/) executable available on `PATH` (or pointed to via `grass.bin` in `config.yml`) ;
- **Python** ≥ 3.9 with the packages in `requirements.txt`:
  ```
  pip install -r requirements.txt
  ```
- Tested on macOS/Linux

## How to run
The pipeline is orchestrated by `src/main.py`, which in turn calls the GRASS sub-scripts and (optionally) LANDPLANER:

```bash
cd src
python3 main.py --config ../demo/config_demo.yml --step all
```

`--step` lets you (re-)run a single stage instead of the whole pipeline:

| Step | Description |
|---|---|
| `import` | GRASS import of DTM/HSG/CLC, terrain derivatives (slope, accumulation, drainage, basins), HSG-CLC overlay (`1_vimport.py`) |
| `hsgtocn` | Compute CN (mean/max/min) per HSG-CLC polygon from the lookup table (`2_HSGtoCN.py`) |
| `cnmap` | Join the CN values back onto the vector overlay and rasterize to `.asc` (`3_CNmap.py`) |
| `landplaner` | Run LANDPLANER (if available in `external/`) on the terrain derivatives + each CN raster |
| `all` (default) | Run every step above, in order |

Notes:
- The GRASS location is only (re)created when the `import` (or `all`) step runs; running a later step on its own reuses the existing location, so `1_vimport.py` must have completed at least once beforehand.
- With `corine.enabled: True`, the whole pipeline is repeated once per CLC file found (one output folder per date/scenario). With `corine.enabled: False`, it runs once per UCS field found in the single land cover file.
- MUSE-derived stochastic CN maps are not produced by this repository; this pipeline covers the deterministic SCS-CN branch only. If you have MUSE output CN rasters, they are meant to be fed into the same LANDPLANER step in place of (or alongside) the deterministic CN rasters produced here.

## Quick demo
To check the pipeline runs, `demo/` provides a small, fully synthetic dataset (tiny DTM, HSG/land-cover grids, CN lookup table) that runs the deterministic CN steps end-to-end in less than a minute, without the need of real regional data or the private LANDPLANER/MUSE code (GRASS GIS is still required). See [`demo/README.md`](demo/README.md).

## Repository content
```
BIOLP/
├── src/
│   ├── main.py           # orchestrator: runs the whole pipeline end-to-end
│   ├── 1_vimport.py      # GRASS: import DTM/HSG/CLC, terrain derivatives, HSG-CLC overlay
│   ├── 2_HSGtoCN.py      # compute Curve Number (mean/max/min) per HSG-CLC polygon
│   └── 3_CNmap.py        # GRASS: join CN values back to the vector overlay and rasterize
├── data/                 # geospatial inputs (not versioned, see "Data" below)
├── demo/                 # small synthetic dataset + config to try the pipeline in minutes
├── external/             # external dependencies (LANDPLANER)
├── validation/           # accuracy assessment of the stochastic simulation (results replicability)
├── out/                  # pipeline outputs, created at runtime (including one folder per run)
├── config.yml            # single configuration file driving the whole run
├── docs/MANUAL.md        # full user manual
└── requirements.txt
```

## Data
To use with real data, place them in a `data/` folder at the repository root (next to this README).

Expected layout (paths are configurable in `config.yml`, defaults shown):
```
data/
├── in/
│   ├── dtm.tif                                    # dtm.{path,name,ext}
│   ├── hydrological_soil_group_map.gpkg           # hsg.{dir,name,ext}
│   └── CLC/
│       └── UCS2007-2019.shp                       # corine.single_file (used if corine.enabled: False; else multiple corine maps)
└── CLC_HC_CN_descr.csv                            # computecn.lookuptable (CLC-HSG-CN correspondence table)
```

## Configuration (`config.yml`)
The whole run is driven by `config.yml`, set as follows.

| Section | Key | Meaning |
|---|---|---|
| `paths` | `data_dir` | Folder with the input data, relative to the repo root (default `data`; e.g. `demo/data` to run the synthetic demo instead) |
| `grass` | `db`, `loc`, `mapset` | GRASS GISDBASE/location/mapset name; the location is (re)created from the DTM at the start of the `import`/`all` steps |
| | `bin` | Optional full path to the `grass` executable; leave empty (`""`) to auto-detect it via `which grass` |
| `dtm` | `path`, `name`, `ext` | Location of the DTM file inside `data/` |
| | `res` | Target resolution (meters); if different from the DTM's native resolution, `g.region` is used to resample |
| | `set_clip`, `mask` | Whether to clip all outputs to a mask vector (`data/in/<mask>`) |
| `hsg` | `dir`, `name`, `ext`, `layer` | Hydrologic Soil Group vector dataset and layer name |
| | `field`, `field_label` | Attribute column holding the HSG class, and the prefix GRASS adds to it after the vector overlay (e.g. `b_` → `b_gi`) |
| `corine` | `enabled` | `True`: loop over every `clc*.shp` file found in `dir` (one run per date/scenario); `False`: use `single_file` only |
| | `dir`, `pattern` | Folder and pattern used when `enabled: True` |
| | `single_file` | Land cover file used when `enabled: False` |
| | `field`, `field_label` | Attribute column holding the land cover code, and its prefix after the overlay |
| `computecn` | `clc_hsg` | Base name for the HSG-CLC overlay layer/table |
| | `lookuptable` | CLC → CN lookup table (CSV, one row per CLC level-III class × HSG × hydrologic condition) |
| | `enabled_hc`, `set_hc` | Whether to filter the lookup table by hydrologic condition (e.g. `Poor`/`Fair`/`Good`), and which one |
| | `hsg_missing_policy` | How to assign a CN when a polygon has no HSG value: `nearest` (fill from the nearest polygon with a known HSG, done in `1_vimport.py`; any polygon still empty afterwards falls back to `-9999`), `weighted` (weighted average across all HSG classes), `fixed` (always use `fixed_hsg`), `original` (leave as `-9999`) |
| | `fixed_hsg` | HSG class used when `hsg_missing_policy: fixed` |
| `landplaner` | `enabled` | Set to `False` to skip the `landplaner` step entirely (e.g. without the private script — this is what `demo/config_demo.yml` does) |
| | `version`, `out_dir` | Filename (without `.r`) of the LANDPLANER script in `external/`, and the output subfolder name it writes to |
| `muse` | `enabled`, `cn_raster` | Set to `True` with a path to feed a MUSE-derived CN raster into the `landplaner` step as an extra scenario (MUSE itself runs separately, see `docs/MANUAL.md`) |

See `docs/MANUAL.md` for the fully annotated version of this table, plus a step-by-step walkthrough of a run.


## Outputs
Each run creates a folder under `out/<loc>_<res>[_<suffix>]/` (one per CLC file/date, or per UCS field, depending on `corine.enabled`) containing:
- `run_config.json`: a snapshot of the configuration used for that run;
- `dtm.asc`, `slope.asc`, `accumulation.asc`, `drainage_abs.asc`, `basin.asc`: terrain derivatives from `1_vimport.py`;
- `hsg_CLC_overlay.csv`, `hsg_CLC_overlay_out.gpkg`: HSG-CLC vector overlay and its attribute table;
- `CN_min.csv`, `CN.csv`, `CN_max.csv` and the corresponding `hsg_CLC_overlay_CN_*.asc` rasters: the three CN variants (min/mean/max, from the lookup table);
- `landplaner.out_dir` as configured: LANDPLANER's own output, one subfolder per CN variant, if the `landplaner` step was run.

All raster outputs are saved in Esri ASCII Grid format (`.asc`) by default.

Log files for each run of `main.py` are written to `logs/` at the repository root.



## Citing us
BIOLP is associated with the following scientific papers: 

- Version submitted to journal (July 2026):
```
@article{miola2026-submitted,
  title={Injecting Stochastic-based Vegetation Model into Hydro-Geomorphological Framework for Potential Erosion Assessment},
  author={Miola, Marianna and Fugacci, Ulderico and Rossi, Mauro},
  year={2026},
  note={submitted at Computer & Geosciences}
}
```

- Preprint published on EarthArXiv:
```
@article{miola2026injecting-preprint,
  title={Injecting vegetation-based spatialization in the hydrogeological framework for erosion modelling},
  author={Miola, Marianna and Fugacci, Ulderico},
  year={2026},
  doi={https://doi.org/10.31223/X5CV1T},
  publisher={EarthArXiv}
}
```

## Acknowledgments
This research is funded under the National Recovery and Resilience Plan (NRRP), Mission 4 Component 2 Investment 1.4 - Call for tender no. 3138 of 16 December 2021, rectified by Decree no. 3175 of 18 December 2021 of Italian Ministry of University and Research funded by the European Union-NextGenerationEU; Award Number: Project code CN 00000033, Concession Decree no. 1034 of 17 June 2022 adopted by the Italian Ministry of University and Research, CUP B83C22002930006, Project title “National Biodiversity Future Center - NBFC”.