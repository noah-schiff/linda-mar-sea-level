"""Download a high-resolution elevation model covering Linda Mar Beach, Pacifica, CA.

Source: USGS 3DEP (3D Elevation Program) seamless bare-earth DEM mosaic,
served by the USGS National Map ImageServer. This mosaic serves the best
available resolution at a given location -- along the Pacifica coast that is
1-meter lidar-derived elevation, contributed in part through NOAA Digital
Coast's coastal lidar programs.

Heights are orthometric elevation in meters relative to NAVD88, the same
vertical datum NOAA tidal datums are commonly referenced to -- important
because Phase 2 compares this DEM against tide-gauge-based water levels.

Usage:
    python scripts/download_dem.py
"""

from pathlib import Path

import requests
from pyproj import Transformer

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "linda_mar_dem.tif"

# Bounding box (WGS84 lon/lat) covering Linda Mar Beach, the San Pedro Creek
# floodplain behind it, and enough of surrounding Pacifica for context.
LON_MIN, LON_MAX = -122.520, -122.492
LAT_MIN, LAT_MAX = 37.578, 37.610

# Output projection: UTM zone 10N, so pixels are true square meters (the
# service itself is served in Web Mercator, which distorts distances).
OUTPUT_EPSG = "EPSG:32610"
TARGET_RESOLUTION_M = 2.0  # meters per pixel

SERVICE_URL = (
    "https://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/"
    "ImageServer/exportImage"
)


def main() -> None:
    transformer = Transformer.from_crs("EPSG:4326", OUTPUT_EPSG, always_xy=True)
    x_min, y_min = transformer.transform(LON_MIN, LAT_MIN)
    x_max, y_max = transformer.transform(LON_MAX, LAT_MAX)

    width_m = x_max - x_min
    height_m = y_max - y_min
    cols = round(width_m / TARGET_RESOLUTION_M)
    rows = round(height_m / TARGET_RESOLUTION_M)
    print(f"UTM bbox: ({x_min:.1f}, {y_min:.1f}) to ({x_max:.1f}, {y_max:.1f})")
    print(f"Area: {width_m:.0f} m x {height_m:.0f} m -> {cols} x {rows} px "
          f"at {TARGET_RESOLUTION_M} m/px")

    params = {
        "bbox": f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}",
        "bboxSR": 4326,
        "imageSR": OUTPUT_EPSG.split(":")[1],
        "size": f"{cols},{rows}",
        "format": "tiff",
        "pixelType": "F32",
        "noDataInterpretation": "esriNoDataMatchAny",
        "interpolation": "RSP_BilinearInterpolation",
        "f": "image",
    }
    response = requests.get(SERVICE_URL, params=params, timeout=120)
    response.raise_for_status()
    if response.headers.get("Content-Type", "").startswith("application/json"):
        # The service returns JSON instead of an image on error.
        raise RuntimeError(f"Service returned an error: {response.text[:500]}")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_bytes(response.content)
    print(f"Saved {OUT_PATH} ({len(response.content) / 1e6:.1f} MB)")

    # Save the georeferencing we requested, since we know it exactly and
    # don't need to re-derive it from the GeoTIFF tags later.
    meta_path = OUT_PATH.with_suffix(".meta.json")
    import json
    meta = {
        "crs": OUTPUT_EPSG,
        "x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max,
        "cols": cols, "rows": rows,
        "resolution_m": TARGET_RESOLUTION_M,
        "lon_min": LON_MIN, "lon_max": LON_MAX,
        "lat_min": LAT_MIN, "lat_max": LAT_MAX,
        "vertical_datum": "NAVD88",
        "vertical_units": "meters",
        "source": "USGS 3DEP seamless DEM mosaic (elevation.nationalmap.gov)",
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    print(f"Saved {meta_path}")


if __name__ == "__main__":
    main()
