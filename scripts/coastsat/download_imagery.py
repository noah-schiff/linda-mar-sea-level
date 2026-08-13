"""Define the Linda Mar Beach region of interest and pull satellite imagery
via CoastSat/Google Earth Engine.

Originally a small 2-year/Sentinel-2-only validation batch (see CLAUDE.md);
now extended to the full historical record -- 1984-present, Landsat 5/7/8/9
plus Sentinel-2 -- now that the extraction pipeline has been validated
against that first batch. Re-running this is safe: CoastSat's
retrieve_images() skips images already downloaded, so the validated 2023-25
Sentinel-2 batch won't be re-fetched.

Run from the project root, with the `coastsat` conda environment active:
    conda activate coastsat
    python scripts\\coastsat\\download_imagery.py
"""

import sys
from pathlib import Path

from osgeo import gdal
gdal.UseExceptions()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "external" / "CoastSat"))

from coastsat import SDS_download, SDS_tools

PROJECT_ID = "linda-mar-coastsat"

# Region of interest (WGS84 lon/lat), a tight box around the sandy beach
# and surf zone itself -- from the ocean side of the shoreline back to
# just past the dunes/parking/Highway 1, spanning the full ~2 km length
# of Linda Mar Beach from near Mori Point (south) to the rocky point near
# Pedro Point (north). Derived from the Phase 2 elevation map's visible
# shoreline extent (see output/linda_mar_elevation_map.png).
polygon = [[
    [-122.5205, 37.5785],
    [-122.5205, 37.6015],
    [-122.5025, 37.6015],
    [-122.5025, 37.5785],
    [-122.5205, 37.5785],
]]
polygon = SDS_tools.smallest_rectangle(polygon)

# Full historical record: every Landsat mission with usable imagery over
# this site, plus Sentinel-2. Same sitename as the validation batch --
# retrieve_images() skips images already on disk, so this won't re-fetch
# the 129 Sentinel-2 images from the first batch.
dates = ["1984-01-01", "2026-08-13"]
sat_list = ["L5", "L7", "L8", "L9", "S2"]
sitename = "LINDAMAR"

# Downloaded imagery is large and fully reproducible -- gitignored.
filepath_data = str(REPO_ROOT / "coastsat_data")

inputs = {
    "polygon": polygon,
    "dates": dates,
    "sat_list": sat_list,
    "sitename": sitename,
    "filepath": filepath_data,
}

if __name__ == "__main__":
    SDS_download.authenticate_and_initialize(PROJECT_ID)

    print("Region of interest (rectangle, WGS84):")
    for pt in polygon[0]:
        print(f"  {pt}")

    print("\nChecking image availability...")
    SDS_download.check_images_available(inputs)

    print("\nRetrieving images...")
    metadata = SDS_download.retrieve_images(inputs)
    print("\nDone. Metadata:", metadata)
