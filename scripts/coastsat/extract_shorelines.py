"""Extract shoreline positions from the downloaded Linda Mar Beach imagery.

Reads the imagery already downloaded by download_imagery.py (does not
re-download anything), runs CoastSat's automated shoreline detection on
each image, and saves:
  - coastsat_data/LINDAMAR/LINDAMAR_output.pkl   (CoastSat's native output)
  - data/coastsat_shorelines.geojson             (small, tracked in git --
    just line geometries + dates, not imagery -- for the plotting script)

Runs fully automated (check_detection/adjust_detection off), so it does
not pop up any interactive GUI windows -- suitable for a first validation
pass. Uses a reference shoreline (see build_reference_shoreline.py) to
reject detections far from the real coast -- built programmatically from
the Phase 2 DEM instead of interactively digitizing one, CoastSat's normal
method.

Run from the project root, with the `coastsat` conda environment active:
    conda activate coastsat
    python scripts\\coastsat\\extract_shorelines.py
"""

import os
import sys
from pathlib import Path

from osgeo import gdal
gdal.UseExceptions()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COASTSAT_DIR = REPO_ROOT / "external" / "CoastSat"
sys.path.insert(0, str(COASTSAT_DIR))

import numpy as np
from pyproj import CRS
from coastsat import SDS_download, SDS_shoreline, SDS_tools

from download_imagery import PROJECT_ID, inputs, sitename  # reuse same ROI/dates/sitename

# SDS_shoreline.py locates its classifier models via os.path.join(os.getcwd(),
# 'classification', 'models') -- i.e. it assumes CoastSat's own repo is the
# working directory, not a path relative to the coastsat package itself.
os.chdir(COASTSAT_DIR)

OUTPUT_EPSG = 32610  # UTM zone 10N -- same CRS used for the Phase 2 DEM
GEOJSON_OUT = REPO_ROOT / "data" / "coastsat_shorelines.geojson"

settings = {
    "cloud_thresh": 0.1,
    "dist_clouds": 300,
    "output_epsg": OUTPUT_EPSG,
    "check_detection": False,   # no interactive validation GUI
    "adjust_detection": False,  # no interactive threshold-adjustment GUI
    "save_figure": True,        # still saves a PNG per image for spot-checking
    "min_beach_area": 1000,
    "min_length_sl": 500,
    "cloud_mask_issue": False,
    "sand_color": "default",
    "pan_off": False,
    "s2cloudless_prob": 40,
    "inputs": inputs,
}

REF_SL_PATH = REPO_ROOT / "data" / "coastsat_reference_shoreline.npy"
if REF_SL_PATH.exists():
    settings["reference_shoreline"] = np.load(REF_SL_PATH)
    settings["max_dist_ref"] = 100  # meters -- reject detections farther than this

def filter_points_near_reference(output, ref_sl, max_dist_m=50):
    """Drop individual shoreline points farther than max_dist_m from the
    reference shoreline, and drop any shoreline left with under 2 points.

    The in-extraction buffer (settings['max_dist_ref']) already does this
    per-image at 100 m, but a handful of spurious detections (likely
    fog/heavy-cloud images producing a false whole-image split) still slip
    through with a few points anchored near the coast and the rest cutting
    straight across the ROI -- this is a tighter, final cleanup pass.
    """
    from scipy.spatial import cKDTree
    tree = cKDTree(ref_sl)

    n_points = len(output["shorelines"])
    keep_shoreline = [False] * n_points
    filtered_shorelines = [None] * n_points
    n_dropped_points = 0
    for i, sl in enumerate(output["shorelines"]):
        dist, _ = tree.query(sl)
        point_keep = dist <= max_dist_m
        n_dropped_points += int((~point_keep).sum())
        if point_keep.sum() >= 2:
            keep_shoreline[i] = True
            filtered_shorelines[i] = sl[point_keep]

    n_dropped_shorelines = n_points - sum(keep_shoreline)
    new_output = {}
    for key, values in output.items():
        if key == "shorelines":
            new_output[key] = [
                sl for sl, keep in zip(filtered_shorelines, keep_shoreline) if keep
            ]
        elif isinstance(values, list) and len(values) == n_points:
            new_output[key] = [v for v, keep in zip(values, keep_shoreline) if keep]
        else:
            new_output[key] = values
    return new_output, n_dropped_points, n_dropped_shorelines


def output_to_gdf_split_on_gaps(output, gap_m=50):
    """Replacement for SDS_tools.output_to_gdf(output, 'lines').

    That function builds one LineString per date by connecting every point
    in output['shorelines'][i] in array order -- with no check for gaps.
    CoastSat's contour tracer can return several genuinely disconnected
    coastline pieces for one image (e.g. the sand beach and a separate
    small rocky-point piece), concatenated into a single array; connecting
    them naively draws a spurious straight "connector" segment jumping
    between two otherwise-valid, real, near-coast detections -- exactly
    the diagonal spikes seen in the validation plot, which the point-to-
    reference-distance filter above can't catch (both endpoints of the
    jump are individually near real coastline, just not near each other).

    Splits each date's points into separate LineStrings wherever the gap
    between consecutive points exceeds gap_m (real traced contour points
    are normally a few meters apart at most), and emits a MultiLineString
    per date so genuinely separate pieces stay visually and geometrically
    disconnected.
    """
    import geopandas as gpd
    from shapely import geometry

    rows = []
    for i, sl in enumerate(output["shorelines"]):
        if len(sl) < 2:
            continue
        gaps = np.hypot(np.diff(sl[:, 0]), np.diff(sl[:, 1]))
        split_idx = np.where(gaps > gap_m)[0] + 1
        pieces = [p for p in np.split(sl, split_idx) if len(p) >= 2]
        if not pieces:
            continue
        geom = (geometry.LineString(pieces[0]) if len(pieces) == 1
                else geometry.MultiLineString([list(map(tuple, p)) for p in pieces]))
        rows.append({
            "geometry": geom,
            "date": output["dates"][i].strftime("%Y-%m-%d %H:%M:%S"),
            "satname": output["satname"][i],
        })
    return gpd.GeoDataFrame(rows) if rows else None


if __name__ == "__main__":
    SDS_download.authenticate_and_initialize(PROJECT_ID)

    metadata = SDS_download.get_metadata(inputs)
    print("Loaded metadata for", {k: len(v["dates"]) for k, v in metadata.items()})

    output = SDS_shoreline.extract_shorelines(metadata, settings)
    output = SDS_tools.remove_duplicates(output)
    output = SDS_tools.remove_inaccurate_georef(output, 10)
    print(f"\nExtracted {len(output['shorelines'])} shorelines "
          f"(after removing duplicates/inaccurate georeferencing).")

    if REF_SL_PATH.exists():
        output, n_dropped_pts, n_dropped_sl = filter_points_near_reference(
            output, settings["reference_shoreline"], max_dist_m=50,
        )
        print(f"Reference-distance cleanup: dropped {n_dropped_pts} stray points, "
              f"{n_dropped_sl} shorelines with too few points remaining "
              f"-> {len(output['shorelines'])} shorelines kept.")

    gdf = output_to_gdf_split_on_gaps(output, gap_m=50)
    if gdf is None:
        raise RuntimeError("No shorelines were mapped -- nothing to save.")
    gdf.crs = CRS(OUTPUT_EPSG)
    GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(GEOJSON_OUT, driver="GeoJSON", encoding="utf-8")
    print(f"Saved {GEOJSON_OUT}")
