"""Build a CoastSat reference shoreline from the Phase 2 elevation DEM,
instead of hand-digitizing one (CoastSat's normal method, via an
interactive click tool).

Extracts the MHHW-elevation contour line from data/linda_mar_dem.tif (the
same "today's high tide" reference used throughout Phase 2). The coastline
can split into multiple disconnected contour pieces (e.g. the sandy beach
and the rockier point north of it break separately) -- every piece that
meaningfully overlaps our CoastSat ROI is combined into one reference.
Saved as a plain .npy array of (x, y) points in EPSG:32610, for use as
settings['reference_shoreline'] in extract_shorelines.py.

Run with the `coastsat` conda environment active (needs GDAL + scikit-image):
    conda activate coastsat
    python scripts\\coastsat\\build_reference_shoreline.py
"""

import json
import sys
from pathlib import Path

import numpy as np
from osgeo import gdal
from pyproj import Transformer
from skimage import measure

gdal.UseExceptions()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "coastsat"))
DEM_PATH = REPO_ROOT / "data" / "linda_mar_dem.tif"
META_PATH = REPO_ROOT / "data" / "linda_mar_dem.meta.json"
OUT_PATH = REPO_ROOT / "data" / "coastsat_reference_shoreline.npy"

MHHW_NAVD88_M = 1.798  # same reference elevation used throughout Phase 2


def main() -> None:
    ds = gdal.Open(str(DEM_PATH))
    arr = ds.ReadAsArray()
    meta = json.loads(META_PATH.read_text())
    x_min, y_max = meta["x_min"], meta["y_max"]
    res = meta["resolution_m"]

    contours = measure.find_contours(arr, level=MHHW_NAVD88_M)
    print(f"Found {len(contours)} contour pieces at {MHHW_NAVD88_M} m NAVD88 "
          f"(lengths: {sorted((len(c) for c in contours), reverse=True)}).")

    # The DEM covers more coastline than our CoastSat ROI (it also includes
    # the rockier coast/harbor area further north) -- the *longest* contour
    # isn't necessarily the one for Linda Mar Beach itself. Pick whichever
    # contour has the most points actually inside our download ROI, in the
    # same UTM 32610 CRS the DEM/contours are in.
    from download_imagery import polygon as roi_polygon
    lons = [pt[0] for pt in roi_polygon[0]]
    lats = [pt[1] for pt in roi_polygon[0]]
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32610", always_xy=True)
    roi_x, roi_y = transformer.transform(lons, lats)
    roi_x_min, roi_x_max = min(roi_x), max(roi_x)
    roi_y_min, roi_y_max = min(roi_y), max(roi_y)

    # The coastline can break into multiple disconnected contour pieces
    # (e.g. the sandy beach and the rockier point north of it, split where
    # the shape changes sharply) -- combine every piece with meaningful
    # overlap with our ROI, rather than keeping only the single best one.
    kept_points = []
    for i, c in enumerate(contours):
        rows, cols = c[:, 0], c[:, 1]
        xs = x_min + cols * res
        ys = y_max - rows * res
        in_roi = (
            (xs >= roi_x_min) & (xs <= roi_x_max) &
            (ys >= roi_y_min) & (ys <= roi_y_max)
        )
        frac = in_roi.mean()
        print(f"  contour {i}: {len(c)} points, {in_roi.sum()} inside ROI ({frac:.0%})")
        if in_roi.sum() > 20 or frac > 0.3:
            kept_points.append(np.column_stack([xs, ys])[in_roi])

    ref_sl = np.concatenate(kept_points, axis=0)
    print(f"Combined reference shoreline from {len(kept_points)} contour piece(s): "
          f"{len(ref_sl)} points total.")

    np.save(OUT_PATH, ref_sl)
    print(f"Saved reference shoreline ({len(ref_sl)} points) to {OUT_PATH}")
    print(f"Extent: x [{ref_sl[:,0].min():.0f}, {ref_sl[:,0].max():.0f}], "
          f"y [{ref_sl[:,1].min():.0f}, {ref_sl[:,1].max():.0f}]")


if __name__ == "__main__":
    main()
