"""Plot the Phase 3 shoreline-change result: per-transect trend map plus the
alongshore-mean cross-shore distance time series.

Reads data/coastsat_transect_timeseries.csv and data/coastsat_transects.geojson
(both written by the coastsat-env scripts) plus data/linda_mar_dem.tif for the
basemap -- none of that needs geopandas, so (like plot_shoreline_validation.py)
this runs in the project's regular .venv, not the separate `coastsat` conda env.
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
DEM_PATH = ROOT / "data" / "linda_mar_dem.tif"
META_PATH = ROOT / "data" / "linda_mar_dem.meta.json"
TRANSECTS_PATH = ROOT / "data" / "coastsat_transects.geojson"
CSV_PATH = ROOT / "data" / "coastsat_transect_timeseries.csv"
OUTPUT_PATH = ROOT / "output" / "coastsat_transect_trend.png"

MHHW_NAVD88_M = 1.798


def main() -> None:
    df = pd.read_csv(CSV_PATH)
    transect_cols = [c for c in df.columns if c not in ("date", "decimal_year", "satname")]

    trends = {}
    for col in transect_cols:
        y = df[col].values
        mask = ~np.isnan(y)
        if mask.sum() < 10:
            continue
        res = stats.linregress(df["decimal_year"].values[mask], y[mask])
        trends[col] = res.slope

    mean_series = df[transect_cols].mean(axis=1, skipna=True)
    mask = ~mean_series.isna()
    overall = stats.linregress(df["decimal_year"].values[mask], mean_series.values[mask])

    geojson = json.loads(TRANSECTS_PATH.read_text())
    meta = json.loads(META_PATH.read_text())
    arr = tifffile.imread(DEM_PATH)
    x_min, y_min = meta["x_min"], meta["y_min"]
    extent = [0, (meta["x_max"] - x_min) / 1000, 0, (meta["y_max"] - y_min) / 1000]

    fig, (ax_map, ax_ts) = plt.subplots(
        1, 2, figsize=(16, 10), dpi=150, gridspec_kw={"width_ratios": [1, 1.3]},
    )
    fig.patch.set_facecolor("#fcfcfb")

    cmap_elev = LinearSegmentedColormap.from_list("elevation", ["#2c1150", "#f0efec", "#FDD023"])
    norm_elev = TwoSlopeNorm(vmin=-3, vcenter=MHHW_NAVD88_M, vmax=8)
    ax_map.set_facecolor("#fcfcfb")
    ax_map.imshow(arr, extent=extent, origin="upper", cmap=cmap_elev, norm=norm_elev, alpha=0.55)

    max_abs = max(abs(v) for v in trends.values()) if trends else 1
    cmap_trend = LinearSegmentedColormap.from_list("trend", ["#c0392b", "#f0efec", "#1f7a4d"])
    norm_trend = TwoSlopeNorm(vmin=-max_abs, vcenter=0, vmax=max_abs)

    for feat in geojson["features"]:
        name = feat["properties"]["name"]
        coords = feat["geometry"]["coordinates"]
        xs = [(pt[0] - x_min) / 1000 for pt in coords]
        ys = [(pt[1] - y_min) / 1000 for pt in coords]
        slope = trends.get(name)
        color = cmap_trend(norm_trend(slope)) if slope is not None else "#999999"
        ax_map.plot(xs, ys, color=color, linewidth=2.5 if slope is not None else 1)
        ax_map.plot(xs[0], ys[0], marker="o", markersize=3, color="#1a1a1a")

    ax_map.set_title("Trend by transect", fontsize=12, fontweight="bold", loc="left")
    ax_map.set_xlim(-0.3, 0.8)
    ax_map.set_ylim(0, 1.8)
    ax_map.set_xlabel("Kilometers east", fontsize=9, color="#52514e")
    ax_map.set_ylabel("Kilometers north", fontsize=9, color="#52514e")
    ax_map.set_aspect("equal")
    ax_map.tick_params(labelsize=8, colors="#52514e")

    sm = plt.cm.ScalarMappable(cmap=cmap_trend, norm=norm_trend)
    cbar = fig.colorbar(sm, ax=ax_map, shrink=0.5, pad=0.03, orientation="horizontal", location="bottom")
    cbar.set_label("Trend (m/yr) — red = retreating, green = advancing", fontsize=8.5, color="#52514e")

    ax_ts.set_facecolor("#fcfcfb")
    for col in transect_cols:
        ax_ts.scatter(df["decimal_year"], df[col], s=4, alpha=0.06, color="#2a78d6")
    ax_ts.scatter(df["decimal_year"], mean_series, s=10, alpha=0.5, color="#1a1a1a",
                  label="alongshore mean")
    xline = np.array([df["decimal_year"].min(), df["decimal_year"].max()])
    ax_ts.plot(xline, overall.intercept + overall.slope * xline, color="#e34948", linewidth=2.2,
               label=f"trend: {overall.slope:+.2f} m/yr")
    ax_ts.set_title(
        f"Alongshore-mean cross-shore distance — {overall.slope:+.2f} m/yr "
        f"(p={overall.pvalue:.3f})", fontsize=12, fontweight="bold", loc="left",
    )
    ax_ts.set_xlabel("Year", fontsize=9, color="#52514e")
    ax_ts.set_ylabel("Cross-shore distance from transect origin (m)", fontsize=9, color="#52514e")
    ax_ts.tick_params(labelsize=8, colors="#52514e")
    ax_ts.grid(linestyle=":", color="0.8")
    ax_ts.legend(loc="upper left", fontsize=8.5, frameon=True, framealpha=0.9)

    fig.suptitle(
        "Linda Mar Beach — Shoreline Change, 1984–2026 (CoastSat, not tidally corrected)",
        fontsize=14, fontweight="bold", x=0.02, ha="left",
    )
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())
    print(f"Saved {OUTPUT_PATH}")
    print(f"Overall alongshore-mean trend: {overall.slope:+.3f} m/yr (p={overall.pvalue:.3f})")


if __name__ == "__main__":
    main()
