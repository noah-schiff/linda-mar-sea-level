"""Define shore-normal transects along Linda Mar Beach for Phase 3
cross-shore shoreline-change analysis.

CoastSat measures shoreline change along user-defined transects: cross-
shore distance from a landward origin to where the detected shoreline
crosses each transect, over time. Rather than interactively drawing them
(CoastSat's normal method), this derives transects programmatically from
the same MHHW DEM contour used for the reference shoreline
(build_reference_shoreline.py) -- consistent with how that reference
shoreline was itself built.

Isolates the sandy-beach contour piece specifically (not the rockier
point/cove north of it, which the CoastSat download ROI also covers --
see CLAUDE.md), resamples it at regular alongshore intervals, and for
each sample point builds a transect normal to the local shoreline
tangent. The seaward direction is picked automatically as whichever side
has lower DEM elevation (open coast here has no missing/NaN elevation
data -- min value along this stretch is ~-17 m, clearly water/nearshore
seafloor, not land), rather than assumed from geometry.

Saves:
  - data/coastsat_transects.geojson   (small, tracked in git)
  - output/coastsat_transects_map.png (visual sanity check -- confirms
    origins are landward and transects point out to sea, per CoastSat's
    own recommended check)

Run with the `coastsat` conda environment active (needs GDAL + scikit-image):
    conda activate coastsat
    python scripts\\coastsat\\define_transects.py
"""

import json
import sys
from pathlib import Path

import numpy as np
from osgeo import gdal
from scipy.ndimage import gaussian_filter
from skimage import measure

gdal.UseExceptions()

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "coastsat"))
sys.path.insert(0, str(REPO_ROOT / "external" / "CoastSat"))

from pyproj import Transformer
from coastsat import SDS_tools

DEM_PATH = REPO_ROOT / "data" / "linda_mar_dem.tif"
META_PATH = REPO_ROOT / "data" / "linda_mar_dem.meta.json"
GEOJSON_OUT = REPO_ROOT / "data" / "coastsat_transects.geojson"
MAP_OUT = REPO_ROOT / "output" / "coastsat_transects_map.png"

MHHW_NAVD88_M = 1.798        # same reference as build_reference_shoreline.py
OUTPUT_EPSG = 32610

SPACING_M = 100               # alongshore spacing between transects
OFFSET_LANDWARD_M = 50        # transect origin, landward of the MHHW point
TRANSECT_LENGTH_M = 450       # origin to seaward end
ELEV_SAMPLE_DIST_M = 30       # offset used to test which side is lower (the sea)
MARGIN_M = 150                # keep transects this far from the piece's own endpoints


def elevation_at(arr, meta, x, y):
    row = np.clip(np.round((meta["y_max"] - y) / meta["resolution_m"]).astype(int), 0, arr.shape[0] - 1)
    col = np.clip(np.round((x - meta["x_min"]) / meta["resolution_m"]).astype(int), 0, arr.shape[1] - 1)
    return arr[row, col]


def main() -> None:
    ds = gdal.Open(str(DEM_PATH))
    arr = ds.ReadAsArray()
    meta = json.loads(META_PATH.read_text())
    x_min, y_max, res = meta["x_min"], meta["y_max"], meta["resolution_m"]

    # Smooth before contouring -- same fix as plot_elevation_map.py: the raw
    # 2 m DEM resolves individual curbs/driveways/yard grading, which made
    # the unsmoothed contour jagged enough to throw off local tangent
    # estimates (transects ended up crossing each other instead of fanning
    # smoothly along the beach). sigma=6 px ~= 12 m real-world smoothing.
    arr_smooth = gaussian_filter(arr, sigma=6)
    contours = measure.find_contours(arr_smooth, level=MHHW_NAVD88_M)

    from download_imagery import polygon as roi_polygon
    lons = [pt[0] for pt in roi_polygon[0]]
    lats = [pt[1] for pt in roi_polygon[0]]
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32610", always_xy=True)
    roi_x, roi_y = transformer.transform(lons, lats)
    roi_x_min, roi_x_max = min(roi_x), max(roi_x)
    roi_y_min, roi_y_max = min(roi_y), max(roi_y)

    # Pick the sandy-beach contour piece specifically: the same DEM contour
    # used for the reference shoreline splits into several disconnected
    # pieces (see build_reference_shoreline.py); the open sand beach is
    # almost entirely inside the download ROI (~97%), while the rockier
    # point/cove piece further north is only partly inside (~56%), since it
    # continues past the ROI's northern edge -- so the piece with the
    # highest in-ROI fraction (among pieces with a meaningful number of
    # points) is the beach.
    candidates = []
    for c in contours:
        if len(c) < 300:
            continue
        rows, cols = c[:, 0], c[:, 1]
        xs = x_min + cols * res
        ys = y_max - rows * res
        in_roi = ((xs >= roi_x_min) & (xs <= roi_x_max) &
                  (ys >= roi_y_min) & (ys <= roi_y_max))
        frac = in_roi.mean()
        print(f"  contour: {len(c)} points, {frac:.0%} inside ROI")
        candidates.append((frac, np.column_stack([xs, ys])))

    frac, beach = max(candidates, key=lambda t: t[0])
    print(f"Selected beach piece: {len(beach)} points, {frac:.0%} inside ROI.")

    # Arc length along the ordered contour (find_contours traces a
    # continuous boundary, so points are already in order).
    seg = np.hypot(np.diff(beach[:, 0]), np.diff(beach[:, 1]))
    s = np.concatenate([[0], np.cumsum(seg)])
    total_len = s[-1]
    print(f"Beach piece length: {total_len:.0f} m")

    def point_at(s_query):
        x = np.interp(s_query, s, beach[:, 0])
        y = np.interp(s_query, s, beach[:, 1])
        return np.array([x, y])

    positions = np.arange(MARGIN_M, total_len - MARGIN_M, SPACING_M)
    print(f"Placing {len(positions)} transects every {SPACING_M} m "
          f"(staying {MARGIN_M} m clear of the piece ends).")

    # A per-transect tangent estimated from a small local window turned out
    # to be too sensitive to natural centimeter-to-meter-scale wiggle in the
    # beach edge (even after smoothing the DEM) -- individual transects ended
    # up rotated tens of degrees apart and crossing each other instead of
    # fanning out evenly. Linda Mar Beach itself is close to a straight
    # north-south line (confirmed via PCA: the long axis is >10x the short
    # axis over the transect placement range), so instead fit ONE global
    # shore-normal direction from all the beach points in that range and
    # reuse it for every transect -- only the alongshore origin differs.
    in_range = (s >= MARGIN_M) & (s <= total_len - MARGIN_M)
    pts_c = beach[in_range] - beach[in_range].mean(axis=0)
    _, singular_values, vt = np.linalg.svd(pts_c, full_matrices=False)
    tangent = vt[0]
    if np.dot(tangent, point_at(total_len - MARGIN_M) - point_at(MARGIN_M)) < 0:
        tangent = -tangent
    straightness = singular_values[0] / singular_values[1]
    print(f"Global shore-normal fit: straightness ratio {straightness:.1f}:1 "
          f"(long axis vs. short axis of the beach point cloud -- "
          f"large means genuinely straight)")

    normal = np.array([-tangent[1], tangent[0]])
    p_mid = point_at(total_len / 2)
    elev_a = elevation_at(arr_smooth, meta, *(p_mid + normal * ELEV_SAMPLE_DIST_M))
    elev_b = elevation_at(arr_smooth, meta, *(p_mid - normal * ELEV_SAMPLE_DIST_M))
    seaward = normal if elev_a < elev_b else -normal
    print(f"Seaward direction: {seaward} (elevation {min(elev_a, elev_b):.1f} m that "
          f"side vs. {max(elev_a, elev_b):.1f} m landward, at beach midpoint)")

    transects = {}
    for i, s0 in enumerate(positions):
        p = point_at(s0)
        origin = p - seaward * OFFSET_LANDWARD_M
        end = origin + seaward * TRANSECT_LENGTH_M
        transects[f"T{i:02d}"] = np.array([origin, end])

    gdf = SDS_tools.transects_to_gdf(transects)
    gdf.crs = f"EPSG:{OUTPUT_EPSG}"
    GEOJSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(GEOJSON_OUT, driver="GeoJSON", encoding="utf-8")
    print(f"Saved {len(transects)} transects to {GEOJSON_OUT}")

    _plot_validation(arr_smooth, meta, beach, transects)


def _plot_validation(arr, meta, beach, transects):
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

    x_min, y_min = meta["x_min"], meta["y_min"]
    extent = [0, (meta["x_max"] - x_min) / 1000, 0, (meta["y_max"] - y_min) / 1000]

    fig, ax = plt.subplots(figsize=(10, 12), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")
    cmap = LinearSegmentedColormap.from_list("elevation", ["#2c1150", "#f0efec", "#FDD023"])
    norm = TwoSlopeNorm(vmin=-3, vcenter=MHHW_NAVD88_M, vmax=8)
    ax.imshow(arr, extent=extent, origin="upper", cmap=cmap, norm=norm, alpha=0.85)

    ax.plot((beach[:, 0] - x_min) / 1000, (beach[:, 1] - y_min) / 1000,
            color="#e34948", linewidth=1.2, alpha=0.6, label="Reference shoreline (beach)")

    for key, t in transects.items():
        xs = (t[:, 0] - x_min) / 1000
        ys = (t[:, 1] - y_min) / 1000
        ax.plot(xs, ys, color="#1a1a1a", linewidth=0.9)
        ax.plot(xs[0], ys[0], marker="o", markersize=3, color="#2a78d6")  # landward origin

    ax.set_title("Linda Mar Beach — Shore-Normal Transects", fontsize=13,
                 color="#1a1a1a", fontweight="bold", loc="left", pad=20)
    fig.text(0.02, 0.955,
              f"{len(transects)} transects, {SPACING_M} m spacing "
              f"(blue dot = landward origin)",
              fontsize=9.5, color="#52514e", ha="left")
    ax.set_xlabel("Kilometers east", fontsize=9, color="#52514e")
    ax.set_ylabel("Kilometers north", fontsize=9, color="#52514e")
    ax.tick_params(labelsize=8, colors="#52514e")
    ax.set_aspect("equal")

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    MAP_OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(MAP_OUT, facecolor=fig.get_facecolor())
    print(f"Saved {MAP_OUT}")


if __name__ == "__main__":
    main()
