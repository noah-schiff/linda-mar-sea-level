"""Compute cross-shore shoreline-position time series along the transects
defined by define_transects.py (Phase 3 continued).

Loads the raw CoastSat output already saved by extract_shorelines.py
(coastsat_data/LINDAMAR/LINDAMAR_output.pkl -- not re-extracted), applies
the same cleanup already used for the shoreline geojson (duplicate/
inaccurate-georef removal, reference-shoreline point filter), then uses
CoastSat's compute_intersection_QC to measure cross-shore distance along
each transect for every image date. Saves:
  - data/coastsat_transect_timeseries.csv  (small, tracked in git)
  - console summary: per-transect linear trend (m/yr) and the alongshore-
    mean trend

Not tidally corrected -- see CLAUDE.md Phase 3 notes: extra scatter from
the tidal cycle is layered on top of any real trend, so treat this as a
first, uncorrected pass.

Run from the project root, with the `coastsat` conda environment active:
    conda activate coastsat
    python scripts\\coastsat\\compute_transect_timeseries.py
"""

import pickle
import sys
from pathlib import Path

from osgeo import gdal
gdal.UseExceptions()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COASTSAT_DIR = REPO_ROOT / "external" / "CoastSat"
sys.path.insert(0, str(REPO_ROOT / "scripts" / "coastsat"))
sys.path.insert(0, str(COASTSAT_DIR))

import numpy as np
import pandas as pd
from scipy import stats
from coastsat import SDS_tools, SDS_transects

from extract_shorelines import filter_points_near_reference  # reuse same cleanup

OUTPUT_PKL = REPO_ROOT / "coastsat_data" / "LINDAMAR" / "LINDAMAR_output.pkl"
TRANSECTS_GEOJSON = REPO_ROOT / "data" / "coastsat_transects.geojson"
REF_SL_PATH = REPO_ROOT / "data" / "coastsat_reference_shoreline.npy"
CSV_OUT = REPO_ROOT / "data" / "coastsat_transect_timeseries.csv"

# Same quality-control parameters as CoastSat's own example.py, appropriate
# for a sandy dissipative beach like Linda Mar.
QC_SETTINGS = {
    "along_dist": 25,       # m, alongshore distance used to find points near a transect
    "min_points": 3,        # minimum shoreline points needed for an intersection
    "max_std": 15,          # m, reject if points scatter more than this
    "max_range": 30,        # m, reject if points span more than this
    "min_chainage": -100,   # m, drop points this far landward of the transect origin
    "multiple_inter": "auto",
    "auto_prc": 0.1,
}


def decimal_year(dates):
    return np.array([d.year + (d.timetuple().tm_yday - 1) / 365.2425 for d in dates])


def main() -> None:
    with open(OUTPUT_PKL, "rb") as f:
        output = pickle.load(f)
    print(f"Loaded {len(output['shorelines'])} raw detections from {OUTPUT_PKL}")

    output = SDS_tools.remove_duplicates(output)
    output = SDS_tools.remove_inaccurate_georef(output, 10)

    ref_sl = np.load(REF_SL_PATH)
    output, n_dropped_pts, n_dropped_sl = filter_points_near_reference(
        output, ref_sl, max_dist_m=50,
    )
    print(f"After cleanup: {len(output['shorelines'])} shorelines "
          f"(dropped {n_dropped_pts} stray points, {n_dropped_sl} shorelines "
          f"far from the reference coast).")

    transects = SDS_tools.transects_from_geojson(str(TRANSECTS_GEOJSON))

    cross_distance = SDS_transects.compute_intersection_QC(output, transects, QC_SETTINGS)

    dates = output["dates"]
    years = decimal_year(dates)

    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d %H:%M:%S") for d in dates],
        "decimal_year": years,
        "satname": output["satname"],
    })
    for key in transects:
        df[key] = cross_distance[key]
    df = df.sort_values("decimal_year").reset_index(drop=True)
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(CSV_OUT, index=False)
    print(f"Saved {CSV_OUT}")

    print(f"\n{'Transect':<8}{'n':>6}{'trend (m/yr)':>16}{'p-value':>10}")
    for key in transects:
        y = cross_distance[key]
        mask = ~np.isnan(y)
        if mask.sum() < 10:
            print(f"{key:<8}{int(mask.sum()):>6}{'--':>16}{'--':>10}")
            continue
        res = stats.linregress(years[mask], y[mask])
        print(f"{key:<8}{int(mask.sum()):>6}{res.slope:>16.3f}{res.pvalue:>10.3f}")

    # Alongshore-mean cross-shore distance per date (average across
    # transects with a valid intersection that date), then fit one overall
    # trend across the whole beach.
    all_vals = np.array([cross_distance[key] for key in transects])
    mean_per_date = np.nanmean(all_vals, axis=0)
    mask = ~np.isnan(mean_per_date)
    res = stats.linregress(years[mask], mean_per_date[mask])
    direction = "retreating (erosion)" if res.slope < 0 else "advancing (accretion)"
    print(f"\nAlongshore-mean trend: {res.slope:+.3f} m/yr "
          f"(p={res.pvalue:.3f}, n={int(mask.sum())} dates) -- {direction}")


if __name__ == "__main__":
    main()
