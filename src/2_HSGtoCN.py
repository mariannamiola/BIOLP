#!/usr/bin/env python3

import os
import sys
import pandas as pd
import numpy as np

from termcolor import colored


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



################################
### Computing CURVE NUMBER (CN) for different areas by using Land Cover and Hydrological Soil Group (HSG)
### starting from a CLC-CN lookuptable (CLC_CN.xls). The file links CLC with CN values according to HSG.
### A contract form (only for the III Corine Level) is the file IIICLC_CN_light.csv


######################################################
### Function: compute Curve Number from HSG-CLC correspondence
def computeCN(df, hsg, clc, use_hc, hc):
    """
    Compute Curve Number from HSG-CLC correspondence

    Parameters:
    - df: DataFrame with CLC-CN lookup table
    - hsg: Hydrological Soil Group ('A', 'B', 'C', 'D')
    - clc: CLC code (string)
    - use_hc: enable hydrologic condition filter
    - hc: hydrologic condition (string: poor/fair/good)

    Returns:
    - avg_cn: Average CN value
    - max_cn: Maximum CN value
    - min_cn: Minimum CN value
    """

    # Mapping HSG to column index
    hsg_map = {'A': 'CN_HSG_A_VALUE', 'B': 'CN_HSG_B_VALUE', 'C': 'CN_HSG_C_VALUE', 'D': 'CN_HSG_D_VALUE'}

    if hsg not in hsg_map:
        raise ValueError(f"Invalid HSG value: {hsg}. Must be 'A', 'B', 'C', or 'D'")

    hsg_col = hsg_map[hsg]

    ##############################################
    ##Considerare hydrologic condition
    #use_hc = True        # oppure False
    #hc = 'Poor'
    print(f'Flag HC (Hydrologic Condition) is set on: ', use_hc)
    if use_hc:
        print(f'Filtering on: ', hc, ' hydrologic condition scenario')


    ##############################################
    ##Inizialize lists
    cn = []
    error = []
    j = 0
    l=len(clc) ##lunghezza stringa passata (l <=3)


    # -------------------------------------------------
    # Verifica se HC fissata esiste per questo CLC
    # -------------------------------------------------
    hc_exists = False
    if use_hc:
        for i in range(df.shape[0]):
            clc_lev3 = str(df.iloc[i, 0])
            if clc_lev3[:l] != clc:
                continue
            if str(df.iloc[i, 3]) == hc:
                hc_exists = True
                break
        print(f'HC "{hc}" exists for CLC {clc}:', hc_exists)
    
    ## Ciclo sul df (lookuptable - IIICLC_CN_light.csv)
    for i in range(df.shape[0]):
        clc_lev3=str(df.iloc[i,0])
        clc_lev3_descr=str(df.iloc[i,1]) ##colonna 2: CLC_LEV3_NAME

        ##Filtro su clc
        if (clc_lev3[:l] != clc):
            continue

        ##Filtro su HC
        if use_hc and hc_exists:
            hc_table = str(df.iloc[i,3]) ##4: colonna hydrologic condition
            if (hc_table != hc):
                continue

        ##Se la stringa clc_lev3 fino a lunghezza l è uguale a clc, prende il valore CN corrispondente all'HSG
        ##clc_lev3 sarà sicuramente composta da 3 caratteri poichè l'analisi è impostata per un clc di III livello

        j = j+1
        val = df.loc[i, hsg_col]
        if use_hc and hc_exists:
            print(f'Row {i} | CLC match: {clc_lev3} -- {clc_lev3_descr} | HC match: {hc_table} | CN raw value:', val)
        else:
            print(f'Row {i} | CLC match: {clc_lev3} -- {clc_lev3_descr} | CN raw value:', val)

        if (np.isnan(val) == False):
            cn.append(int(val))
            print(f'  -> appended CN:', int(val))
        else:
            ##cn.append(int(-1))
            error.append([int(clc),-1])
            print(f'# CN not available (NaN) for selected HSG={hsg} in CLC-CN lookuptable. CN = {cn}') ##Errore tipo -1
            print('  -> skipped (NaN)')

    print('\nCN list BEFORE averaging:', cn)

    ##Se non trovo alcun CLC uguale al CLCIII: ERRORE tipo -2
    if j == 0:
        ##cn.append(int(-2))
        error.append([int(clc),-2])
        print('# CLCi not found in CLC-CN lookuptable. CN = ', cn)
        return None, None, None

    if (len(cn) == 0):
        print(colored('# Error on CN length.', 'red'))
        return None, None, None

    avg_cn=sum(cn)/len(cn)
    max_cn=max(cn)
    min_cn=min(cn)

    print(f'# Average CN: {round(avg_cn, 2)}, Max: {max_cn}, Min: {min_cn}')

    return round(avg_cn,2), max_cn, min_cn



######################################################
### NUOVA FUNZIONE: Calcola CN con media pesata quando HSG mancante
def computeCN_weighted(df, clc, use_hc, hc):
    """
    Calcola CN usando media pesata di tutti gli HSG disponibili

    Parameters:
    - df: DataFrame with CLC-CN lookup table
    - clc: CLC code (string)
    - hc: hydrologic condition (string)

    Returns:
    - avg_cn: Weighted average CN value
    - max_cn: Maximum CN value across all HSG
    - min_cn: Minimum CN value across all HSG
    """
    print(colored('\n--- Computing WEIGHTED AVERAGE CN (HSG missing) ---', 'cyan'))

    # Pesi che favoriscono condizioni intermedie (B e C più comuni in natura)
    weights = {'A': 0.15, 'B': 0.35, 'C': 0.35, 'D': 0.15}

    cn_weighted = []
    all_cn_values = []

    for hsg, weight in weights.items():
        print(f'\n  Processing HSG {hsg} (weight={weight})...')
        try:
            avg_cn, max_cn, min_cn = computeCN(df, hsg, clc, use_hc, hc)

            if avg_cn is not None:
                cn_weighted.append((avg_cn, weight))
                all_cn_values.append(avg_cn)
                print(f'HSG {hsg}: CN_avg={avg_cn}')
            else:
                print(f'HSG {hsg}: No valid CN found')
        except Exception as e:
            print(f'HSG {hsg}: Error - {e}')

    if not cn_weighted:
        print(colored('\n# ERROR: No valid CN found for any HSG type', 'red'))
        return None, None, None

    # Calcolo media pesata
    weighted_avg = sum(cn * w for cn, w in cn_weighted) / sum(w for _, w in cn_weighted)

    print(colored(f'\nWEIGHTED AVERAGE CN: {round(weighted_avg, 2)}', 'green', attrs=['bold']))
    print(f'   Based on {len(cn_weighted)}/4 valid HSG types')
    print(f'   Range: [{round(min(all_cn_values), 2)} - {round(max(all_cn_values), 2)}]')

    return round(weighted_avg, 2), round(max(all_cn_values), 2), round(min(all_cn_values), 2)


def computeCN_missing_strategy(df, clc, policy, fixed_hsg, use_hc, hc):
    """
    Gestisce il calcolo del CN quando HSG è mancante
    """

    if policy == 'original':
        print(colored('=== Missing HSG: keeping original behavior (-9999)', 'yellow'))
        return -9999, -9999, -9999

    elif policy == 'weighted':
        print(colored('=== Missing HSG: using WEIGHTED average', 'cyan'))
        return computeCN_weighted(df, clc, use_hc, hc)

    elif policy == 'fixed':
        print(colored(f'=== Missing HSG: forcing case HSG={fixed_hsg}', 'magenta'))
        return computeCN(df, fixed_hsg, clc, use_hc, hc)

    elif policy == 'nearest':
        # HSG gaps are expected to have already been filled upstream (nearest-neighbour
        # fill in 1_vimport.py). Reaching this point means a polygon is still empty after
        # that fill, so fall back to the same behavior as 'original' instead of crashing.
        print(colored(
            '=== Missing HSG: nearest-neighbour fill left this polygon empty, falling back to -9999',
            'red'
        ))
        return -9999, -9999, -9999

    else:
        raise RuntimeError("Unhandled CN missing policy")




######################################################
######################################################
###### MAIN

print('=== Computing Curve Number ...')

######################################################
### Read CSV file
HSGCLCtab_filename=sys.argv[1] ##HSG-CLC overlay table (e.g. hsg_CLC_overlay.csv)
CNHSGtab_filename=sys.argv[2] ##CLC-CN lookup table (e.g. CLC_HC_CN_descr.csv)

if not os.path.exists(HSGCLCtab_filename):
    print(f"ERROR: file not found -> {HSGCLCtab_filename}")
    sys.exit(1)

if not os.path.exists(CNHSGtab_filename):
    print(f"ERROR: file not found -> {CNHSGtab_filename}")
    sys.exit(1)

### Directories definition
script_dir=os.path.dirname(os.path.realpath(__file__))
data_dir=script_dir+'/../data'
#out_dir=script_dir+'/../out'
out_dir=sys.argv[3]

cn_missing_policy=sys.argv[5].lower() #'original', 'weighted', 'fixed'
if cn_missing_policy not in ['original', 'weighted', 'fixed', 'nearest']:
    raise ValueError("CN_MISSING_POLICY must be one of: original, weighted, fixed, nearest")

## Set hydrologic condition as a filter for curve number
use_hc=sys.argv[6]
use_hc=parse_bool(use_hc)
hc=sys.argv[7]
if use_hc:
    print("use_hc parsed:", use_hc, type(use_hc), "; set on: ", hc)

## Set hsg for missing_policy = fixed
fixed_hsg=sys.argv[8]

##Import table HSG-CLC (resulting from vector overlaying in GRASS)
ucs_field=sys.argv[4] ##nome della colonna che contiene il codice CLC
df0 = pd.read_csv(HSGCLCtab_filename, sep=',', dtype={ucs_field: str}) ##, header=None)
print('=== Read file: ', HSGCLCtab_filename)

df = pd.read_csv(CNHSGtab_filename, sep=';') ##, header=None)
print('=== Read CLC-CN lookuptable: ', CNHSGtab_filename)
print()

CLC_LEVEL=3
print('=== CLC_LEVEL is set to:', CLC_LEVEL)

error=[]
array_cn=[]
array_cn_max=[]
array_cn_min=[]
array_cat=[]

missing_hsg_count = 0
hsg_name = sys.argv[9]

for i in range(df0.shape[0]):
    array_cat.append(df0.iloc[i]['cat']) ##ID area

    if df0.iloc[i][hsg_name] in ['A','B','C','D']:
        hsg = df0.iloc[i][hsg_name] ##HSG - nome della colonna che contiene l'HSG
    else:
        hsg = ''

    clc = df0.iloc[i][ucs_field]
    clc=str(clc).strip() ##converti clc in stringa
    print('#####################################################')
    if(clc[-1]=='0'): ##verifico se l'ultimo carattere della stringa CLC è 0: se così, livello inferiore di III
        if(clc[-2]=='0'): ##verifico se l'ultimo carattere della stringa CLC è 0: se così, livello inferiore di II
            print('# row:', i, ' | HSG: ' , hsg, ' | CLC: ', clc, colored('|| Warning: a CLC_1_LEVEL is detected!', 'yellow'))
        else:
            print('# row:', i, ' | HSG: ' , hsg, ' | CLC: ', clc, colored('|| Warning: a CLC_2_LEVEL is detected!', 'yellow'))
    elif(len(clc) > CLC_LEVEL):
        print('# row:', i, ' | HSG: ' , hsg, ' | CLC: ', clc, colored('|| Warning: a CLC_4_LEVEL is detected!', 'yellow'))
    else:
        print('# row:', i, ' | HSG: ' , hsg, ' | CLC: ', clc)


    clc = clc[:CLC_LEVEL]

    level1_detected = False
    if(clc[-1]=='0'):
        clc=clc[:len(clc)-1]
        if(clc[-1]=='0'):
            clc=clc[:len(clc)-1]
            print('# Breaking CLC to level I: ', clc)
            level1_detected = True
        else:
            print('# Breaking CLC to level II: ', clc)
    
    # Check CLC missing
    if clc == "" or clc.lower() in ["none", "nan"]:
        print(colored(f'=== WARNING: Missing CLC at row {i}. Assigning -9999 for CN.', 'yellow'))
        cn, cn_max, cn_min = -9999, -9999, -9999
    else:
        if ( hsg != '' ):
            cn, cn_max, cn_min = computeCN(df,hsg,clc,use_hc, hc)
        else:
            print(colored(f'=== WARNING - Missing HSG value at row {i}.','yellow'))

            if level1_detected:
                cn, cn_max, cn_min = computeCN_missing_strategy(df, clc, 'fixed', 'D', use_hc, hc)
            else:
                cn, cn_max, cn_min = computeCN_missing_strategy(df, clc, cn_missing_policy, fixed_hsg, use_hc, hc)
                missing_hsg_count += 1  # incremento contatore

            if cn is None:
                cn = -9999
                cn_max = -9999
                cn_min = -9999
                error.append([int(clc),-9999])
                print(colored('=== ERROR - Could not compute CN even with weighted average.','red'))

    print('# Computing CN_avg: ', cn)
    print('# Computing CN_max: ', cn_max)
    print('# Computing CN_min: ', cn_min)
    print()
    array_cn.append(cn)
    array_cn_max.append(cn_max)
    array_cn_min.append(cn_min)

print(f"=== # of missing HSG: {missing_hsg_count}")

array_cn = np.array(array_cn)
array_cn = np.transpose(array_cn)

array_cn_max = np.array(array_cn_max)
array_cn_max = np.transpose(array_cn_max)

array_cn_min = np.array(array_cn_min)
array_cn_min = np.transpose(array_cn_min)

array_cat = np.array(array_cat)
array_cat = np.transpose(array_cat)

s = set()
for item in error:
    s.add(tuple(item))

np.savetxt(out_dir+'/cat_column.csv', array_cat, header='cat', comments='', fmt='%1.0f')
np.savetxt(out_dir+'/CN_column.csv', array_cn, header='CN', comments='', fmt='%1.2f')
np.savetxt(out_dir+'/CN_max_column.csv', array_cn_max, header='CN', comments='', fmt='%1.2f')
np.savetxt(out_dir+'/CN_min_column.csv', array_cn_min, header='CN', comments='', fmt='%1.2f')

print('=== Saving CN_avg ... COMPLETED.')
print('=== Saving CN_max ... COMPLETED.')
print('=== Saving CN_min ... COMPLETED.')
print()
