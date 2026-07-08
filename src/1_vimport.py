#!/usr/bin/env python3

import os
import sys
import grass.script as gs
import grass.script.setup as gsetup
import json

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

    base_dir = sys.argv[1]
    gisdb = base_dir + "/" + sys.argv[2]     # Cartella del database
    location = sys.argv[3]              # Nome della location
    mapset = sys.argv[4]                # Nome del mapset

    os.environ["GISDBASE"] = gisdb
    os.environ["LOCATION_NAME"] = location
    os.environ["MAPSET"] = mapset

    ##sys.path.append("/opt/local/lib/grass84") ###grass --config path ###DA MODIFICARE!!! gestire in bash?
    ##sys.path.append("/usr/lib/grass83") ###grass --config path

    grass_configpath = sys.argv[5]
    sys.path.append(grass_configpath)
    gsetup.init(gisdb, location, mapset)

# ----------------------------------------------------------------
# setup directories
# ----------------------------------------------------------------
    script_dir=os.path.dirname(os.path.realpath(__file__))

    data_dir=sys.argv[6] ##script_dir+"/../data"
    in_dir=data_dir+"/in"

    out_dir=sys.argv[7] ##data_dir+"../out"
    print()

# ----------------------------------------------------------------
# setup the data processing pipelines
# ----------------------------------------------------------------

    ###### DTM
    print('=== Importing DTM ... ')
    dtm_filename=sys.argv[8]
    dtm_file=in_dir+'/'+dtm_filename
    if not os.path.exists(dtm_file):
        print(f"ERROR: {dtm_file} not exist!")
        sys.exit(1)

    dtm_filename=os.path.basename(dtm_file)
    dtm_basename=os.path.splitext(dtm_filename)[0]
    print('=== Loading DTM file: ', dtm_file)

    format_out='AAIGrid'
    ext_out='.asc'
    dtm_out=out_dir+'/'+dtm_basename+ext_out

    ### Import DTM as raster
    gs.run_command('r.import', input=dtm_file, output='dtm_out', overwrite=True)

    ### Set the active region and resolution
    ##Modifying resolution 
    resol=sys.argv[9]
    print('=== Modifying DTM resolution ... ')
    region = gs.parse_command("g.region", raster="dtm_out", flags="g")
    print(region)

    res_dtm_original_ns = float(region['nsres'])
    res_dtm_original_ew = float(region['ewres'])
    print(f"=== Original DTM resolution: NS={res_dtm_original_ns}, EW={res_dtm_original_ew}")
    print(f"=== Requested resolution: {resol}")
    tol = 1e-6

    USE_REGION = abs(res_dtm_original_ns - float(resol)) > tol or abs(res_dtm_original_ew - float(resol)) > tol

    if USE_REGION:
        print('=== Use g.region to adapt the fixed resolution ...')
        gs.run_command('g.region', raster='dtm_out', res=resol, flags='p')

    ###### GENERATE ACCUMULATION AND DRAINAGE DIRECTION
    print('\033[1;32m=== WATERSHED ANALYSIS: Generate accumulation and drainage direction from DTM ... \033[0m')
    
    thresh='10' ##for dtm=100m: 10; for dtm=10m: 1000
    if resol == "100":
        thresh = "10"
    elif resol == "10":
        thresh = "1000"
    else:
        thresh = "100"
    print('=== (Automatic) Threshold set equal to ', thresh)
    print()

    ## Computing: accumulation, drainage, basin (bacini idrografici raster), stream raster (reticolo idrografico - raster binario con pixel fluviali)
    gs.run_command('r.watershed', elevation='dtm_out', accumulation='accumulation', drainage='drainage', basin='basin', stream='stream_raster', threshold=thresh, flags='sab', overwrite=True)
    gs.run_command('r.mapcalc', expression='drainage_abs = abs(drainage)', overwrite=True)


    ## Output paths for accumulation/drainage/basin (exported later, once the target region/mask is finalized)
    accum_out=out_dir+'/accumulation'+ext_out
    drainabs_out=out_dir+'/drainage_abs'+ext_out
    basin_out=out_dir+'/basin'+ext_out

    ###### GENERATE SLOPE FROM DTM
    print()
    print('\033[1;32m=== Generating slope from DTM ... \033[0m')
    gs.run_command('r.slope.aspect', elevation='dtm_out', slope='slope', overwrite=True)

    slope_out=out_dir+'/slope'+ext_out

    ### DTM mask
    set_clip_dtm = sys.argv[16] ##set to True if you want to clip DTM with a smaller mask, False otherwise
    mask_file = in_dir+'/'+sys.argv[17]
    print('=== Set clip DTM: ', set_clip_dtm)
    set_clip_dtm=parse_bool(set_clip_dtm)
    if set_clip_dtm:
        print('=== Clipping DTM with mask ...')
        print('=== Mask file: ', mask_file)
        gs.run_command('v.import', input=mask_file, output='dtm_mask_vect', overwrite=True)
        gs.run_command('v.to.rast', input='dtm_mask_vect', output='mask_rast', use='val', value=1, overwrite=True)
    print()

    ### Export DTM in ASC format (ESRII ARCGIS FILE)
    if USE_REGION:
        print('=== Use g.region to adapt the fixed resolution ...')
        #gs.run_command('g.region', raster='dtm_out', res=resol, flags='p') ##uncomment to define resolution different from res_dtm_original
        gs.run_command('g.region', raster='accumulation', res=resol, overwrite=True)
        gs.run_command('g.region', raster='drainage_abs', res=resol, overwrite=True)
        gs.run_command('g.region', raster='basin', res=resol, overwrite=True)
        gs.run_command('g.region', raster='slope', res=resol, overwrite=True)

    if set_clip_dtm:
        # Applica maschera esplicita su ogni raster PRIMA dell'export
        print('=== Applying explicit mask to rasters before export ...')
        for rname in ['dtm_out', 'slope', 'accumulation', 'drainage_abs', 'basin']:
            gs.run_command('r.mapcalc',
                expression=f'{rname}_masked = if(isnull(mask_rast), null(), {rname})',
                overwrite=True)
        gs.run_command('g.region', vector='dtm_mask_vect', flags='p')

    def raster_name(base):
        return f'{base}_masked' if set_clip_dtm else base
        
    print('=== Exporting rasters in .asc format ... ')
    gs.run_command('r.out.gdal', input=raster_name('dtm_out'), output=dtm_out, format=format_out, nodata=-9999, overwrite=True, type='Float64', createopt='FORCE_CELLSIZE=TRUE')       
    gs.run_command('r.out.gdal', input=raster_name('accumulation'), output=accum_out, format=format_out, nodata=-9999, type='Float64', overwrite=True, createopt='FORCE_CELLSIZE=TRUE')
    gs.run_command('r.out.gdal', input=raster_name('drainage_abs'), output=drainabs_out, format=format_out, nodata=-9999, type='Int16',overwrite=True, createopt='FORCE_CELLSIZE=TRUE')
    gs.run_command('r.out.gdal', input=raster_name('basin'), output=basin_out, format=format_out, nodata=-9999, type='Float32', overwrite=True, createopt='FORCE_CELLSIZE=TRUE')
    gs.run_command('r.out.gdal', input=raster_name('slope'), output=slope_out, format=format_out, nodata=-9999, type='Float32', overwrite=True, createopt='FORCE_CELLSIZE=TRUE')




    ###### OVERLAY VECTORS
    print()
    print('\033[1;32m=== Overlaying vector files ... \033[0m')

    ###### Import vector files: gruppo idrologico usda (HSG)
    hsg_file=sys.argv[10]
    hsg_layer=sys.argv[11]
    if not os.path.exists(hsg_file):
        print("ERROR: {hsg_file} not exist!")
        sys.exit(1)

    print('=== First vector file (PEDOLOGICAL DATABASE): ', hsg_file)
    gs.run_command('v.import', input=hsg_file, layer=hsg_layer, output='hsg_raw', overwrite=True)
    if set_clip_dtm:
        gs.run_command('v.clip', input='hsg_raw', clip='dtm_mask_vect', output='hsg_out', overwrite=True)
    else:
        gs.run_command('g.rename', vector='hsg_raw,hsg_out')

    ###### Import vector files: Corine Land Cover CLC (or land use)
    CLC_file=sys.argv[12]
    if not os.path.exists(CLC_file):
        print(f"ERROR: {CLC_file} not exist!")
        sys.exit(1)

    print('=== Second vector file (CORINE LAND COVER): ', CLC_file)
    gs.run_command('v.import', input=CLC_file, output='CLC_raw', overwrite=True)
    if set_clip_dtm:
        gs.run_command('v.clip', input='CLC_raw', clip='dtm_mask_vect', output='CLC_out', overwrite=True)
    else:
        gs.run_command('g.rename', vector='CLC_raw,CLC_out')

    ###### Reading fields related to CLC_file
    info = gs.read_command('v.info', map='CLC_out', flags='c')

    # Ogni riga è: layer|column_name|type|length
    lines = info.strip().split("\n")
    fields = [l.split("|")[1] for l in lines]

    CLC_FIELD_LABEL=sys.argv[18] ##'a_' ##'b_'
    CLC_FIELD_NAME=sys.argv[19] ##ucs
    print(f"=== (Automatic) searching UCS fields | starting with: {CLC_FIELD_NAME} ...")
    ucs_fields = [f for f in fields if f.lower().startswith(CLC_FIELD_NAME.lower())]
    num_ucs = len(ucs_fields)

    print(f"Found UCS fields: {ucs_fields}")
    print(f"UCS fields number = {num_ucs}")

    output_info = {
        "ucs_fields": ucs_fields
    }
    with open(f"{out_dir}/vimport_info.json", "w") as f:
        json.dump(output_info, f)
    

    ###### Overlay vector files: HSG/CLC
    clc_hsg=sys.argv[13] ##'CLC_hsg_overlay'
    gs.run_command('v.overlay', ainput='CLC_out', binput='hsg_out', operator='and', output=clc_hsg, overwrite=True)


    ## Filling HSG for empty polygons
    HSG_FIELD_NAME=sys.argv[14]
    HSG_FIELD_LABEL=sys.argv[20] ##'b_' ##'a_'
    HSG_FIELD_NAME_LABEL=HSG_FIELD_LABEL+HSG_FIELD_NAME
    HSG_POLICY=sys.argv[15]
    where_clause_null = f'{HSG_FIELD_NAME_LABEL} IS NULL'
    where_clause_notnull = f'{HSG_FIELD_NAME_LABEL} IS NOT NULL'


    # Conta tutti i poligoni
    info = gs.parse_command('v.info', map=clc_hsg, flags='t')
    total_count = int(info.get('areas', 0))

    # Conta vuoti con v.db.select
    empty_rows = gs.read_command(
        'v.db.select',
        map=clc_hsg,
        where=where_clause_null,
        columns='cat'
    ).strip().splitlines()
    empty_count = len(empty_rows) -1 if empty_rows else 0
    print(f"=== Empty HSG polygons: {empty_count} / {total_count}")

    if HSG_POLICY == 'nearest':
        if empty_count == 0:
            print('=== No empty polygons found, skipping fill.')
        else:
            print(f'=== Missing HSG: nearest neighbour algorithm - filling {empty_count} polygons...')

            print("==================== FILLING EMPTY POLYGONS with nearest HSG ...")
            gs.run_command('v.db.addcolumn', map=clc_hsg, columns='hsg_nn TEXT')
            gs.run_command('v.extract', input=clc_hsg, where=where_clause_null, output='polys_empty')
            gs.run_command('v.extract', input=clc_hsg, where=where_clause_notnull, output='polys')

            gs.run_command('v.to.points', input='polys_empty', type='centroid', output='centroids_polys_empty')
            gs.run_command('v.to.points', input='polys', type='centroid', output='centroids_polys')

            gs.run_command('v.distance', from_='centroids_polys_empty', to='centroids_polys', upload='to_attr', column='hsg_nn', to_column=HSG_FIELD_NAME_LABEL)

            gs.run_command('v.db.addcolumn', map='centroids_polys_empty', columns="cat_pol INTEGER")

            gs.run_command('v.what.vect', map='centroids_polys_empty', column='cat_pol', query_map=clc_hsg, query_column='cat')

            gs.run_command('v.db.join', map=clc_hsg, column='cat', other_table='centroids_polys_empty_1', other_column='cat_pol', subset_columns='hsg_nn')

            gs.run_command('v.db.update', map=clc_hsg, column=HSG_FIELD_NAME_LABEL, query_column='hsg_nn', where=where_clause_null)
            print("==================== FILLING EMPTY POLYGONS with nearest HSG ... END.")

            # Verifica post-fill (senza flags='c')
            empty_after_rows = gs.read_command(
                'v.db.select',
                map=clc_hsg,
                where=where_clause_null,
                columns='cat'
            ).strip().splitlines()
            empty_after = len(empty_after_rows) -1 if empty_after_rows else 0

            if empty_after == 0:
                print('=== Fill completed: no empty polygons remaining.')
            else:
                print(f'\033[1;31m=== WARNING: {empty_after} polygons still empty after fill!\033[0m')
    else:
        if empty_count > 0:
            print(f'\033[1;33m=== WARNING: HSG_POLICY != nearest, {empty_count} empty polygons NOT filled!\033[0m')
        else:
            print('=== No empty polygons found.')

    print()
    print('\033[1;32m=== Extracting vector overlay (intersecting hsg-clc) ...\033[0m')
    hsg_CLC_overlay_out_vector=out_dir+'/'+clc_hsg+'_out.gpkg'
    gs.run_command('v.out.ogr', input=clc_hsg, output=hsg_CLC_overlay_out_vector, overwrite=True)
    print(f"=== Saved filled vector overlay: {hsg_CLC_overlay_out_vector}")
    
    print()
    print('\033[1;32m=== Extracting vector database ...\033[0m')
    hsg_CLC_out=out_dir+'/'+clc_hsg+'.csv'
    gs.run_command('v.db.select', map=clc_hsg, format='csv', file=hsg_CLC_out, overwrite=True)
    print(f"=== Saved vector database: {hsg_CLC_out}")


if __name__ == '__main__':
    main()
