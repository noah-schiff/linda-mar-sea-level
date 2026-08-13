"""Plot CoastSat's extracted shoreline positions over the Phase 2 elevation
map, as a visual sanity check that the detected shorelines actually trace
the real coastline at Linda Mar Beach.

Reads data/coastsat_shorelines.geojson directly with the stdlib json
module (not geopandas -- that's only in the separate `coastsat` conda
env; this script runs in the project's regular .venv, alongside the
Phase 1/2 scripts, since all it needs is coordinates + dates).
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import tifffile
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

ROOT = Path(__file__).resolve().parent.parent
DEM_PATH = ROOT / "data" / "linda_mar_dem.tif"
META_PATH = ROOT / "data" / "linda_mar_dem.meta.json"
GEOJSON_PATH = ROOT / "data" / "coastsat_shorelines.geojson"
OUTPUT_PATH = ROOT / "output" / "coastsat_shoreline_validation.png"

MHHW_NAVD88_M = 1.798  # same reference as plot_elevation_map.py


def main() -> None:
    arr = tifffile.imread(DEM_PATH)
    meta = json.loads(META_PATH.read_text())
    x_min, y_min = meta["x_min"], meta["y_min"]
    extent = [
        0, (meta["x_max"] - x_min) / 1000,
        0, (meta["y_max"] - y_min) / 1000,
    ]

    geojson = json.loads(GEOJSON_PATH.read_text())
    features = geojson["features"]
    dates = sorted(f["properties"].get("date", "") for f in features)
    satnames = sorted({f["properties"].get("satname", "?") for f in features})
    print(f"Loaded {len(features)} shoreline detections ({', '.join(satnames)}), "
          f"{dates[0]} to {dates[-1]}" if dates else "Loaded 0 shorelines")

    fig, ax = plt.subplots(figsize=(10, 12), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    cmap = LinearSegmentedColormap.from_list(
        "elevation", ["#2c1150", "#f0efec", "#FDD023"],
    )
    norm = TwoSlopeNorm(vmin=-3, vcenter=MHHW_NAVD88_M, vmax=8)
    ax.imshow(arr, extent=extent, origin="upper", cmap=cmap, norm=norm, alpha=0.85)

    n_plotted = 0
    for feat in features:
        coords = feat["geometry"]["coordinates"]
        # LineString -> [[x,y],...]; MultiLineString -> [[[x,y],...],...]
        lines = coords if isinstance(coords[0][0], (int, float)) else coords
        if isinstance(coords[0][0], (int, float)):
            lines = [coords]
        for line in lines:
            xs = [(pt[0] - x_min) / 1000 for pt in line]
            ys = [(pt[1] - y_min) / 1000 for pt in line]
            ax.plot(xs, ys, color="#e34948", linewidth=0.6, alpha=0.35, zorder=5)
            n_plotted += 1

    ax.set_title(
        "CoastSat Extracted Shorelines vs. Elevation — Linda Mar Beach",
        fontsize=13, color="#1a1a1a", fontweight="bold", loc="left", pad=30,
    )
    fig.text(
        0.02, 0.955,
        f"{len(features)} detections ({', '.join(satnames)}), {dates[0]} to {dates[-1]} "
        f"(not tidally corrected)" if dates else "",
        fontsize=9.5, color="#52514e", ha="left",
    )
    ax.set_xlabel("Kilometers east", fontsize=9, color="#52514e")
    ax.set_ylabel("Kilometers north", fontsize=9, color="#52514e")
    ax.tick_params(labelsize=8, colors="#52514e")
    ax.set_aspect("equal")

    fig.tight_layout(rect=[0, 0, 1, 0.93])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())
    print(f"Plotted {n_plotted} shoreline lines. Saved {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
