#!/usr/bin/env python3

import os
import sys
import subprocess
from pathlib import Path
import zipfile
import logging
import shutil
from datetime import datetime
import argparse
import json
import getpass
import yaml


print()
print("=============================================================")
print("=== BIOLP: Biodiversity for LANDPLANER", flush=True)
print("=== Version: 0.0")
print("=== Python executable:", sys.executable)
print("=== Python version:", sys.version)
print("=============================================================")
print()


# ============================================================
# ARGUMENT PARSER
# ============================================================
parser = argparse.ArgumentParser(description="BIOLP Workflow Runner")
parser.add_argument(
    '--step',
    type=str,
    default="all",
    choices=["all", "import", "hsgtocn", "cnmap", "landplaner"],
    help="Which step to run: all, import, hsgtocn, cnmap, landplaner"
)
parser.add_argument(
    "--config",
    type=str,
    default="../config.yml",
    help="Path to configuration file"
)
args = parser.parse_args()
step_to_run = args.step.lower()


# ============================================================
# LOAD CONFIG FILE
# ============================================================

config_path = Path(args.config)
if not config_path.exists():
    logging.error(f"Config file not found: {config_path}")
    sys.exit(1)

with open(config_path) as f:
    CONFIG = yaml.safe_load(f)


# ============================================================
# CHECK GRASS GIS PRESENCE (block immediately if missing)
# ============================================================
## Use the path from config.yml (grass.bin) if provided, otherwise auto-detect via PATH
GRASS_BIN = CONFIG.get("grass", {}).get("bin") or shutil.which("grass") or ""
if not GRASS_BIN:
    print()
    print("=============================================================")
    print("=== ERROR: GRASS GIS not found.")
    print("=== This pipeline requires GRASS GIS to run.")
    print("=== Install it and make sure 'grass' is on your PATH, or set")
    print("=== 'grass.bin' in config.yml to its full executable path.")
    print("=== Download GRASS GIS: https://grass.osgeo.org/download/")
    print("=============================================================")
    print()
    sys.exit(1)


# ============================================================
# GLOBAL CONSTANTS (from config)
# ============================================================
SCRIPT_DIR = Path(__file__).resolve().parent  ##cartella dove sta il main.py (src/)
ROOT_DIR = SCRIPT_DIR.parent

### Setup directory di lavoro
## paths.data_dir is optional (defaults to "data"); it lets a config point the
## pipeline at a different dataset (e.g. demo/data for the synthetic demo)
## without moving/overwriting the real data/ folder.
DATA_DIR = (ROOT_DIR / CONFIG.get("paths", {}).get("data_dir", "data")).resolve()
R_DIR = ROOT_DIR / "external"

print("=== Source directory: ", SCRIPT_DIR)
print("=== Data directory: ", DATA_DIR)
print("=== External directory: ", R_DIR)


# Setup logging
LOG_DIR = ROOT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

log_filename = LOG_DIR / f"main_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)

print()
print("=============================================================")
print()
logging.info("=== Script started")


def run_step(cmd, step_name):
    """Run a pipeline sub-script; stop the whole run if it failed, since later
    steps depend on the files it's supposed to produce."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    logging.info(result.stdout)
    if result.returncode != 0:
        logging.error(f"{step_name} failed (exit code {result.returncode}):")
        logging.error(result.stderr)
        sys.exit(1)
    elif result.stderr:
        logging.warning(f"{step_name} produced stderr output (non-fatal):")
        logging.warning(result.stderr)
    return result


def combine_cat_cn(catcol, cncol, out_path):
    """Combine cat_column.csv + <variant>_column.csv into the CN CSV consumed
    by 3_CNmap.py. Both inputs are produced by 2_HSGtoCN.py (the 'hsgtocn'
    step) -- fail clearly if it hasn't run yet, instead of silently writing
    an empty/malformed CN CSV whose only symptom is a confusing GRASS import
    error later on."""
    for f in (catcol, cncol):
        if not f.exists():
            logging.error(f"{f} not found -- run --step hsgtocn (or all) first.")
            sys.exit(1)
    with open(out_path, 'w') as out_csv:
        subprocess.run(['paste', '-d', ';', str(catcol), str(cncol)], stdout=out_csv, text=True)
    logging.info(f"Combined {catcol} and {cncol} into {out_path}")


def run_landplaner(wd, dem_prefix, cn_path, out_suffix):
    """Run LANDPLANER once, for a single CN raster.

    `cn_path` may be a bare filename (resolved by LANDPLANER relative to
    `wd`, e.g. a CN_min/CN/CN_max raster produced by 3_CNmap.py) or an
    absolute path (e.g. an externally-produced MUSE CN raster) -- LANDPLANER
    reads it with R's `scan()`, which honors absolute paths regardless of its
    own working directory. Non-fatal: logs and continues on failure, so one
    failing CN variant doesn't stop the others.
    """
    print(f"=== START LANDPLANER EXECUTION for CN_MAP = {cn_path}")
    result = subprocess.run([
        "Rscript", f"{LANDPLANER}.r", "--args",
        "-wd", str(wd),
        "-dem", dem_prefix + DTM_NAME + ".asc",
        "-slope", dem_prefix + "slope.asc",
        "-acc", dem_prefix + "accumulation.asc",
        "-drain", dem_prefix + "drainage_abs.asc",
        "-cn", str(cn_path),
        "-ba", dem_prefix + "basin.asc",
        "-outfolder", f"{RES_DIR_NAME}_{out_suffix}"
    ], capture_output=True, text=True)
    logging.info(result.stdout)

    if result.returncode != 0:
        logging.error("LANDPLANER exited with an error:")
        logging.error(result.stderr)
    elif result.stderr:
        logging.warning("LANDPLANER produced stderr output (non-fatal):")
        logging.warning(result.stderr)

    logging.info("### END LANDPLANER EXECUTION.")


def run_landplaner_step(wd, dem_prefix):
    """Run the whole landplaner step (all CN variants + optional MUSE raster)
    for one output folder, honoring landplaner.enabled/muse.enabled."""
    if not LANDPLANER_ENABLED:
        msg = "=== LANDPLANER step skipped (landplaner.enabled: False in config.yml)"
        print(msg)
        logging.info(msg)
        return

    print("=== Running LANDPLANER ...")
    os.chdir(R_DIR)

    print("=== LANDPLANER version: ", LANDPLANER)
    print("=== Output directory: ", RES_DIR_NAME)

    ##Check if the output directory exists starting as RES_DIR_NAME; if true, removes it
    for name in os.listdir(wd):
        full_path = os.path.join(wd, name)
        if name.startswith(RES_DIR_NAME) and os.path.isdir(full_path):
            print(f"=== Directory '{full_path}' exists! Removing it ...")
            shutil.rmtree(full_path)

    print("=== Looping on Curve Number maps (i.e., CNmean, CNmax, CNmin) ...")
    for n in names:
        run_landplaner(wd, dem_prefix, f"{HSGCLCoverlay_filename}_{n}.asc", n)

    if MUSE_ENABLED:
        if MUSE_CN_RASTER:
            print("=== Running LANDPLANER with the MUSE-derived CN raster ...")
            run_landplaner(wd, dem_prefix, MUSE_CN_RASTER, "MUSE")
        else:
            logging.warning("muse.enabled is True but muse.cn_raster is empty in config.yml -- skipping the MUSE LANDPLANER run.")


## GRASS setup: location
logging.info(f"=== GRASS bin location: {GRASS_BIN}")


# Check GRASS version
try:
    version_check = subprocess.run(
        [GRASS_BIN, '--version'],
        capture_output=True, text=True, check=True
    )
    print("=== GRASS version:", version_check.stdout.strip())
    logging.info(f"GRASS version: {version_check.stdout.strip()}")
except subprocess.CalledProcessError as e:
    logging.error(f"Error checking GRASS version: {e}")
    print("Unable to check GRASS version. Make sure GRASS is correctly installed.")


print()
print("=============================================================")
print()


# ============================================================
# DEFAULT CONFIG TEMPLATE
# ============================================================

default_config = {}

default_config["run_info"] = {
    "timestamp": datetime.now().isoformat(),
    "user": getpass.getuser(),
    "script": os.path.basename(__file__)
}

# Merge CONFIG with defaults (CONFIG overrides default)
full_config = {**default_config, **CONFIG}




############################################################
## Set GRASS project and variables
DB = CONFIG["grass"]["db"] ##"grassdata"
LOC = CONFIG["grass"]["loc"] ##"mp_v1_dtmclip"
MAPSET = CONFIG["grass"]["mapset"] ##"PERMANENT"

DTM_RES = str(CONFIG["dtm"]["res"]) ##"10"
DTM_NAME = CONFIG["dtm"]["name"] ##"dtm_clip"
DTM_EXT = CONFIG["dtm"]["ext"] ##"tif"
SET_CLIP = CONFIG["dtm"]["set_clip"] ##True
MASK = CONFIG["dtm"]["mask"] ##"mask.gpkg"

OUT_DIR = ROOT_DIR / "out" / f"{LOC}_{DTM_RES}"


## Extract data folder: unzip if the folder not exist
if not DATA_DIR.exists():
    logging.info(f"The folder {DATA_DIR} does not exist. Unzipping...")
    zip_path = str(DATA_DIR) + ".zip"
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(ROOT_DIR)
        logging.info(f"Unzipped {zip_path} successfully.")
    except Exception as e:
        logging.error(f"Error unzipping {zip_path}: {e}")
        sys.exit(1)
else:
    logging.info(f"The folder {DATA_DIR} already exists!")


## Create a GRASS location if not exist according to DTM
DTM_FILENAME = DTM_NAME+"."+DTM_EXT

grass_location_path = Path.home() / DB / LOC
DIR_MAPSET = grass_location_path / MAPSET

print()
print("=============================================================")
print()

## The GRASS location is (re)created only when the "import" step actually runs,
## so that re-running later steps (e.g. --step cnmap/landplaner) does not
## wipe out the location built by a previous "import" run.
if step_to_run in ["all", "import"]:
    if grass_location_path.exists():
        logging.info(f"Location {grass_location_path} exists. Deleting...")
        shutil.rmtree(grass_location_path)
        logging.info("Deleted existing location.")

    print("=== Creating GRASS project ...")
    print("=== Importing DTM ...")
    logging.info(f"Creating GRASS location at {grass_location_path}")

    dtm_path = (DATA_DIR / CONFIG["dtm"]["path"] / DTM_FILENAME).resolve()

    # Creating GRASS location from DTM
    result = subprocess.run([
        GRASS_BIN,
        '-c', str(dtm_path),
        str(grass_location_path), '-e'
        ], capture_output=True, text=True, check=True)
    logging.info(result.stdout)
    if result.stderr:
        logging.error(result.stderr)
else:
    if not grass_location_path.exists():
        logging.error(
            f"GRASS location {grass_location_path} not found. Run with --step import (or all) first."
        )
        sys.exit(1)
    logging.info(f"Reusing existing GRASS location at {grass_location_path}")

print()
print("=============================================================")
print()

## Hydrologic soil group
print("=== Importing Hydrologic Soil Group database ...") ##rif. database pedologico
DBPED_NAME = CONFIG["hsg"]["name"]
DBPED_EXT = CONFIG["hsg"]["ext"]
DBPED_FILENAME = f"{DBPED_NAME}.{DBPED_EXT}"
DBPED_HSG = (DATA_DIR / CONFIG["hsg"]["dir"] / DBPED_FILENAME).resolve()
print("=== HSG database file: ", DBPED_HSG)
DBPED_HSG_LAYER = CONFIG["hsg"]["layer"]
HSG_FIELD_NAME = CONFIG["hsg"]["field"] #gi
HSG_FIELD_LABEL = CONFIG["hsg"]["field_label"] ##"b_" ##"a_"
HSG_FIELD_NAME_LABEL = HSG_FIELD_LABEL + HSG_FIELD_NAME
print("=== HSG field name: ", HSG_FIELD_NAME)
print("=== HSG field label: ", HSG_FIELD_LABEL)
print()


## Activate CORINE LAND COVER
print("=== Importing Land Cover ...")
CORINE = CONFIG["corine"]["enabled"]
CORINE_DIR = (DATA_DIR / CONFIG["corine"]["dir"]).resolve()
CORINE_NAME = CONFIG["corine"]["pattern"]
CLC_FIELD_LABEL = CONFIG["corine"]["field_label"] ##"a_" ##"b_" 
CLC_FIELD_NAME = CONFIG["corine"]["field"] ##"ucs" ##"clc"
USOSUOLO = (DATA_DIR / CONFIG["corine"]["single_file"]).resolve()
print("=== CLC file: ", USOSUOLO)
print("=== CLC field name: ", CLC_FIELD_NAME)
print("=== CLC field label: ", CLC_FIELD_LABEL)
print()


## For curve number computation
HSGCLCoverlay_filename = CONFIG["computecn"]["clc_hsg"]
HSGCN = (DATA_DIR / CONFIG["computecn"]["lookuptable"]).resolve()
USE_HC = CONFIG["computecn"]["enabled_hc"]
HC = CONFIG["computecn"]["set_hc"]
HSG_MISSING_POLICY = CONFIG["computecn"]["hsg_missing_policy"] ##"original"
FIXED_HSG = CONFIG["computecn"]["fixed_hsg"]

## Curve Number variants produced by 2_HSGtoCN.py / 3_CNmap.py for each run (mean, max, min)
names = ["CN_min", "CN", "CN_max"]

## For erosion modeling in landplaner
LANDPLANER_ENABLED = CONFIG["landplaner"].get("enabled", True)
LANDPLANER = CONFIG["landplaner"]["version"] ##"version"
RES_DIR_NAME = CONFIG["landplaner"]["out_dir"] ##"synth_noroot"

## MUSE produces its own stochastic, vegetation-based CN maps entirely
## separately (not run from this script); if enabled, its CN raster is fed
## into the same LANDPLANER step as an extra scenario, alongside CN_min/CN/CN_max.
MUSE_ENABLED = CONFIG.get("muse", {}).get("enabled", False)
MUSE_CN_RASTER = CONFIG.get("muse", {}).get("cn_raster", "")
if MUSE_ENABLED and MUSE_CN_RASTER:
    MUSE_CN_RASTER = str((DATA_DIR / MUSE_CN_RASTER).resolve())


if CORINE:
    logging.info("Reading Corine Land Cover ...")

    if not CORINE_DIR.exists():
        logging.error(f"Directory {CORINE_DIR} not found!")
        sys.exit(1)

    print("=== Looping on CLC files ...")
    for clcfile in CORINE_DIR.glob(CORINE_NAME):
        suffix = clcfile.stem.replace("clc", "")
        logging.info(f"Found: {clcfile.name}, clc date: {suffix}")
        print("=== CLC file: ", clcfile)

        USOSUOLO = clcfile
        current_out_dir = ROOT_DIR / "out" / f"{LOC}_{DTM_RES}_{suffix}"
        current_out_dir.mkdir(parents=True, exist_ok=True)

        ##Saving config
        out_json = os.path.join(current_out_dir, "run_config.json")
        with open(out_json, "w") as f:
            json.dump(full_config, f, indent=2)
        print(f"Saved run configuration to: {out_json}")

        # Run 1_vimport.py
        print()
        print("=============================================================")
        print()

        if step_to_run in ["all", "import"]:
            print("=== Running 1_vimport.py ...")
            print("=== Output folder: ", current_out_dir)
            run_step([
                GRASS_BIN, str(DIR_MAPSET), '-f', '--exec',
                'python3', str(SCRIPT_DIR / '1_vimport.py'),
                str(Path.home()), DB, LOC, MAPSET,
                GRASS_BIN, str(DATA_DIR), str(current_out_dir),
                DTM_FILENAME, DTM_RES, DBPED_HSG, DBPED_HSG_LAYER,
                str(USOSUOLO), HSGCLCoverlay_filename, HSG_FIELD_NAME, HSG_MISSING_POLICY,
                str(SET_CLIP), MASK, CLC_FIELD_LABEL, CLC_FIELD_NAME, HSG_FIELD_LABEL
            ], "1_vimport.py")

        print()
        print("=============================================================")
        print()

        CATcol = current_out_dir / "cat_column.csv"

        # Run 2_HSGtoCN.py
        if step_to_run in ["all", "hsgtocn"]:
            print("=== Running 2_HSGtoCN.py ...")
            HSGCLCoverlay = current_out_dir / f"{HSGCLCoverlay_filename}.csv"
            UCS_FIELD = CLC_FIELD_LABEL + f"{CLC_FIELD_NAME}{suffix}"

            run_step([
                'python3', str(SCRIPT_DIR / '2_HSGtoCN.py'),
                str(HSGCLCoverlay), str(HSGCN),
                str(current_out_dir), UCS_FIELD, HSG_MISSING_POLICY, str(USE_HC), HC, FIXED_HSG, HSG_FIELD_NAME_LABEL
            ], "2_HSGtoCN.py")

        print()
        print("=============================================================")
        print()

        # Run 3_CNmap.py
        if step_to_run in ["all", "cnmap"]:
            print("=== Looping on Curve Number (i.e., mean, max, min) ...")
            for n in names:
                CNcol = current_out_dir / f"{n}_column.csv"
                CN = current_out_dir / f"{n}.csv"
                print("=== Curve Number: ", n)

                combine_cat_cn(CATcol, CNcol, CN)

                # Delete the temporary files
                for temp_file in [CNcol]:
                    if temp_file.exists():
                        temp_file.unlink()
                        logging.info(f"Deleted temporary file {temp_file}")

                print("=== Running 3_CNmap.py ...")
                run_step([
                    GRASS_BIN, str(DIR_MAPSET), '-f', '--exec',
                    'python3', str(SCRIPT_DIR / '3_CNmap.py'),
                    str(Path.home()), DB, LOC, MAPSET,
                    GRASS_BIN, str(current_out_dir), str(CN), DTM_RES, HSGCLCoverlay_filename,
                    str(SET_CLIP), MASK, str(DATA_DIR)
                ], "3_CNmap.py")

        print()
        print("=============================================================")
        print()

        # Run R script LANDPLANER
        if step_to_run in ["all", "landplaner"]:
            run_landplaner_step(current_out_dir, dem_prefix="")

else:
    print("=== Specific file for Land Use/Cover ...")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    out_json = os.path.join(OUT_DIR, "run_config.json")
    with open(out_json, "w") as f:
        json.dump(full_config, f, indent=2)
    print(f"Saved run configuration to: {out_json}")

    print()
    print("=============================================================")
    print()

    if step_to_run in ["all", "import"]:
        print("\033[1;33m=== Running 1_vimport.py ...\033[0m")
        print("=== Output folder: ", OUT_DIR)
        run_step([
            GRASS_BIN, str(DIR_MAPSET), '-f', '--exec',
            'python3', str(SCRIPT_DIR / '1_vimport.py'),
            str(Path.home()),
            DB,
            LOC,
            MAPSET,
            GRASS_BIN,
            str(DATA_DIR),
            str(OUT_DIR),
            DTM_FILENAME,
            DTM_RES,
            DBPED_HSG,DBPED_HSG_LAYER,
            str(USOSUOLO), HSGCLCoverlay_filename, HSG_FIELD_NAME, HSG_MISSING_POLICY,
            str(SET_CLIP), MASK,
            CLC_FIELD_LABEL, CLC_FIELD_NAME, HSG_FIELD_LABEL
        ], "1_vimport.py")

    print()
    print("=============================================================")
    print()


    info_file = OUT_DIR / "vimport_info.json"
    with open(info_file) as f:
        vimport_info = json.load(f)

    ucs_fields = vimport_info["ucs_fields"]
    print("=== ucs_fields:", ucs_fields)

    # HSGCLCoverlay, and the per-UCS-field folder scaffolding, are needed by
    # hsgtocn/cnmap/landplaner alike, so they live outside any single step's
    # guard -- this lets each step be (re-)run independently via --step,
    # rather than only as part of "all" or nested under "hsgtocn".
    HSGCLCoverlay = OUT_DIR / f"{HSGCLCoverlay_filename}.csv"
    for UCS_FIELD in ucs_fields:
        UCS_DIR = OUT_DIR / UCS_FIELD
        UCS_DIR.mkdir(exist_ok=True)
        CATcol = UCS_DIR / "cat_column.csv"
        bUCS = CLC_FIELD_LABEL + UCS_FIELD

        # Run 2_HSGtoCN.py
        if step_to_run in ["all", "hsgtocn"]:
            print("\033[1;33m=== Running 2_HSGtoCN.py ...\033[0m")
            print(f"=== Running 2_HSGtoCN for UCS={UCS_FIELD}")
            print(f"--- Output folder for {UCS_FIELD}: {UCS_DIR}")

            run_step([
                'python3', str(SCRIPT_DIR / '2_HSGtoCN.py'),
                str(HSGCLCoverlay),
                str(HSGCN),
                str(UCS_DIR),
                bUCS,
                HSG_MISSING_POLICY, str(USE_HC), HC, FIXED_HSG, HSG_FIELD_NAME_LABEL
            ], "2_HSGtoCN.py")

            print()
            print("=============================================================")
            print()

        # Run 3_CNmap.py
        if step_to_run in ["all", "cnmap"]:
            print("\033[1;33m=== Looping on Curve Number (i.e., mean, max, min) ...\033[0m")
            for n in names:
                CNcol = UCS_DIR / f"{n}_column.csv"
                CN = UCS_DIR / f"{n}.csv"

                combine_cat_cn(CATcol, CNcol, CN)

                # Delete the temporary files
                for temp_file in [CNcol]:
                    if temp_file.exists():
                        temp_file.unlink()
                        logging.info(f"Deleted temporary file {temp_file}")

                run_step([
                    GRASS_BIN, str(DIR_MAPSET), '-f', '--exec',
                    'python3', str(SCRIPT_DIR / '3_CNmap.py'),
                    str(Path.home()), DB, LOC, MAPSET,
                    GRASS_BIN, str(UCS_DIR), str(CN), DTM_RES, HSGCLCoverlay_filename,
                    str(SET_CLIP), MASK, str(DATA_DIR)
                ], "3_CNmap.py")

            print()
            print("=============================================================")
            print()

        # Run R-LANDPLANER
        if step_to_run in ["all", "landplaner"]:
            run_landplaner_step(UCS_DIR, dem_prefix="../")
            print()


logging.info("=== Script ended")


print()
print("=============================================================")
print()
