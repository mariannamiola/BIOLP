#!/usr/bin/env python3

import os
import sys
import grass.script as gs
import grass.script.setup as gsetup

def parse_bool(x):
    if isinstance(x, bool):
        return x

    if isinstance(x, str):
        x = x.strip().lower()
        if x in ("true", "1", "yes", "y"):
            return True
        if x in ("false", "0", "no", "n", ""):
            return False

    if isinstance(x, (int, float)):
        return bool(x)

    if x is None:
        return False

    raise ValueError(f"Invalid boolean value: {x} (type={type(x)})")


def main():
# ----------------------------------------------------------------
# init GRASS GIS
# ----------------------------------------------------------------

    dir = sys.argv[1]
    gisdb = dir + "/" + sys.argv[2]     # Cartella del database
    location = sys.argv[3]              # Nome della location
    mapset = sys.argv[4]                # Nome del mapset

    os.environ["GISDBASE"] = gisdb
    os.environ["LOCATION_NAME"] = location
    os.environ["MAPSET"] = mapset

    grass_configpath = sys.argv[5]
    sys.path.append(grass_configpath)
    gsetup.init(gisdb, location, mapset)

# ----------------------------------------------------------------
# setup directories
# ----------------------------------------------------------------

    script_dir=os.path.dirname(os.path.realpath(__file__))

    data_dir=sys.argv[12] ##script_dir+"/../data"
    in_dir=data_dir+"/in"

    out_dir=sys.argv[6] ##data_dir+"../out"

# ----------------------------------------------------------------
# setup the data processing pipelines
# ----------------------------------------------------------------

    print('\033[1;32m=== Building Curve Number raster map ... \033[0m')

    print('=== Importing CN database ... ')
    cn_file=sys.argv[7]
    if not os.path.exists(cn_file):
        print(f"ERROR: {cn_file} not exist!")
        sys.exit(1)

    cn_filename=os.path.basename(cn_file)
    cn_basename=os.path.splitext(cn_filename)[0]

    gs.run_command('db.in.ogr', input=cn_file, overwrite=True)
        
    # Parameters definition
    map_name = sys.argv[9] ##"hsg_CLC_overlay"
    column_join = "cat"
    cn_table = cn_basename + "_csv"
    raster_out=map_name+'_out'
    cn_column_text = "x_CN"
    cn_column_numeric = "x_CN_numeric"
                             
    sql_addcolumn="ALTER TABLE "+cn_table+" ADD COLUMN "+cn_column_numeric+" double precision"
    gs.run_command('db.execute', sql=sql_addcolumn)
    
    sql_castvalue="UPDATE "+cn_table+" SET "+cn_column_numeric+" = CAST("+cn_column_text+" AS double precision)"
    gs.run_command('db.execute', sql=sql_castvalue)
        
    print("=== Joining table to map database ...")
    print("=== Map: ", map_name)
    print("=== Table: ", cn_table)
    gs.run_command('v.db.join', map=map_name, column=column_join, other_table=cn_table, other_column=column_join, overwrite=True)
    
    describe_output = gs.parse_command('db.describe', table=map_name)
    print("=== Database description ...")
    for key, value in describe_output.items():
        print(f"{key}: {value}")
        
    print("=== Converting to raster ...")
    gs.run_command('v.to.rast', input=map_name, output=raster_out, use='attr', attribute_column=cn_column_numeric, overwrite=True)

    ### Export CN raster in ASC format (ESRI ASCII GRID)
    format_out='AAIGrid'
    ext_out='.asc'
    hsg_CLC_overlay_CN_out=out_dir+'/'+map_name+'_'+cn_basename+ext_out

    gs.run_command('r.null', map=raster_out, null=-9999)

    ### DTM mask
    set_clip_dtm = sys.argv[10] ##set to True if you want to clip DTM with a smaller mask, False otherwise
    mask_file = in_dir+'/'+sys.argv[11]
    print('=== Set clip DTM: ', set_clip_dtm)
    set_clip_dtm=parse_bool(set_clip_dtm)

    if set_clip_dtm:
        print('=== Clipping DTM with mask ...')
        print('=== Mask file: ', mask_file)
        gs.run_command('v.import', input=mask_file, output='dtm_mask_vect', overwrite=True)
        gs.run_command('v.to.rast', input='dtm_mask_vect', output='mask_rast', use='val', value=1, overwrite=True)
        
        gs.run_command('r.mapcalc',
        expression=f'{raster_out}_masked = if(isnull(mask_rast), null(), {raster_out})',
        overwrite=True)
        gs.run_command('g.region', vector='dtm_mask_vect', flags='p')
        gs.run_command('r.out.gdal', input=f'{raster_out}_masked', output=hsg_CLC_overlay_CN_out, format=format_out, nodata=-9999, overwrite=True, createopt='FORCE_CELLSIZE=TRUE')
    else:
        gs.run_command('r.out.gdal', input=raster_out, output=hsg_CLC_overlay_CN_out, format=format_out, nodata=-9999, overwrite=True, createopt='FORCE_CELLSIZE=TRUE')
    print()



if __name__ == '__main__':
    main()
