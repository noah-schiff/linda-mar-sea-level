"""Map Linda Mar Beach elevation and mark where NOAA's 2022 projected high
tides would reach in 2050 and 2100.

Reads the DEM downloaded by download_dem.py and overlays contour lines: the
elevation that today's high tide (MHHW) plus each year's projected sea
level rise would reach, under the NOAA 2022 Interagency Low, Intermediate,
and High scenarios. Any land at or below a contour is land the tide would
regularly reach by that year, under a simple "bathtub" assumption (no storm
surge, waves, or drainage effects included -- see CLAUDE.md for caveats,
and for a comparison against USGS CoSMoS's more sophisticated wave/storm
modeling for this same stretch of coast).

Elevation is NAVD88 (meters), the same vertical datum used for the tide
thresholds below, so the two are directly comparable.
"""

import json
from pathlib import Path

import matplotlib.patheffects as pe
import matplotlib.pyplot as plt
import numpy as np
import tifffile
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm
from matplotlib.lines import Line2D
from pyproj import Transformer
from scipy.ndimage import gaussian_filter

ROOT = Path(__file__).resolve().parent.parent
DEM_PATH = ROOT / "data" / "linda_mar_dem.tif"
META_PATH = ROOT / "data" / "linda_mar_dem.meta.json"
OUTPUT_PATH = ROOT / "output" / "linda_mar_elevation_map.png"

# --- Tide + sea-level-rise reference values ---------------------------------
# MHHW (Mean Higher High Water) relative to NAVD88 at the San Francisco tide
# gauge (NOAA station 9414290), from NOAA CO-OPS datums API
# (api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/9414290/datums.json):
#   MHHW = 3.602 m and NAVD88 = 1.804 m, both relative to the station datum
#   -> MHHW relative to NAVD88 = 3.602 - 1.804 = 1.798 m
MHHW_NAVD88_M = 1.798

# NOAA 2022 Interagency sea level rise scenarios (50th/median percentile),
# relative to a year-2000 baseline, for San Francisco (PSMSL station 10) --
# from the interagency report's own supplementary dataset
# (TR_local_projections.nc, Zenodo record 5951626; extracted in full,
# all scenarios/years/percentiles, by extract_slr_scenarios.py into
# data/sf_slr_scenarios.csv).
M_TO_FT = 3.28084
THRESHOLD_TODAY = MHHW_NAVD88_M

SCENARIOS = {
    # label: (SLR 2050 m, SLR 2100 m, line color)
    # Drawn in this order so Low ends up on top where scenarios overlap
    # spatially (they're close together in the near term).
    "High":         (0.367, 1.958, "#e34948"),  # red
    "Intermediate": (0.233, 0.911, "#1a1a1a"),  # ink/black
    "Low":          (0.145, 0.277, "#2a78d6"),  # blue
}
YEARS = [2050, 2100]
LINESTYLES = {2050: "-", 2100: "--"}

COLOR_INK = "#1a1a1a"

# LSU purple/gold theme, as a diverging scale centered on TODAY's high tide
# (MHHW): purple = land already reached by today's high tide, cream = right
# at today's high tide line, gold = dry land above it. The scenario contour
# lines then show how far inland that same boundary is projected to move.
COLOR_PURPLE_DARK = "#2c1150"
COLOR_NEUTRAL = "#f0efec"
COLOR_GOLD = "#FDD023"

LANDMARK_LON, LANDMARK_LAT = -122.5051, 37.5946  # Linda Mar Beach parking lot


def main() -> None:
    arr = tifffile.imread(DEM_PATH)
    # Lightly smooth before mapping/contouring. The raw 2 m lidar DEM
    # resolves individual curbs, driveways, and small yard grading in the
    # developed neighborhood -- fine for engineering work, but it makes a
    # screening-level "bathtub" contour zigzag across every tiny bump
    # instead of tracing the broad landform. sigma=3 px ~= 6 m real-world
    # smoothing radius.
    arr = gaussian_filter(arr, sigma=6)
    meta = json.loads(META_PATH.read_text())
    # Plot in kilometers from the map's own southwest corner, rather than
    # raw UTM easting/northing -- easier to read, no 1e6-style axis offset.
    x_min, y_min = meta["x_min"], meta["y_min"]
    extent = [
        0, (meta["x_max"] - x_min) / 1000,
        0, (meta["y_max"] - y_min) / 1000,
    ]

    fig, ax = plt.subplots(figsize=(10, 12), dpi=150)
    fig.patch.set_facecolor("#fcfcfb")
    ax.set_facecolor("#fcfcfb")

    cmap = LinearSegmentedColormap.from_list(
        "lsu_elevation", [COLOR_PURPLE_DARK, COLOR_NEUTRAL, COLOR_GOLD],
    )
    norm = TwoSlopeNorm(vmin=-3, vcenter=THRESHOLD_TODAY, vmax=8)
    im = ax.imshow(arr, extent=extent, origin="upper", cmap=cmap, norm=norm)

    # For each scenario, draw its 2050/2100 threshold as a white line
    # underneath + colored line on top -- a manual "stroke" effect that
    # reads clearly against both the purple and gold halves of the map.
    # Color = scenario, linestyle = year, so all six lines stay legible.
    thresholds = {}
    for scen_label, (slr_2050, slr_2100, color) in SCENARIOS.items():
        levels = [MHHW_NAVD88_M + slr_2050, MHHW_NAVD88_M + slr_2100]
        thresholds[scen_label] = dict(zip(YEARS, levels))
        linestyles = [LINESTYLES[y] for y in YEARS]
        ax.contour(arr, levels=levels, extent=extent, origin="upper",
                   colors="white", linewidths=3.5, linestyles=linestyles)
        ax.contour(arr, levels=levels, extent=extent, origin="upper",
                   colors=color, linewidths=1.6, linestyles=linestyles)

    transformer = Transformer.from_crs("EPSG:4326", meta["crs"], always_xy=True)
    lx, ly = transformer.transform(LANDMARK_LON, LANDMARK_LAT)
    lx_km, ly_km = (lx - x_min) / 1000, (ly - y_min) / 1000
    ax.plot(lx_km, ly_km, marker="o", markersize=7, color="white",
            markeredgecolor=COLOR_INK, markeredgewidth=1.2, zorder=5)
    ax.annotate(
        "Linda Mar Beach", (lx_km, ly_km), xytext=(10, 10), textcoords="offset points",
        fontsize=10, color=COLOR_INK, fontweight="bold",
        path_effects=[pe.withStroke(linewidth=3, foreground="white")],
    )

    fig.suptitle(
        "Linda Mar Beach, Pacifica — Elevation vs. Projected High Tide",
        fontsize=14, color=COLOR_INK, x=0.02, y=0.98, ha="left", fontweight="bold",
    )
    fig.text(
        0.02, 0.953,
        "NOAA 2022 Low/Intermediate/High scenarios, San Francisco tide gauge "
        "(PSMSL 10) — USGS 3DEP 2 m elevation model",
        fontsize=9.5, color="#52514e", ha="left",
    )

    ax.set_xlabel("Kilometers east", fontsize=9, color="#52514e")
    ax.set_ylabel("Kilometers north", fontsize=9, color="#52514e")
    ax.tick_params(labelsize=8, colors="#52514e")
    ax.set_aspect("equal")

    cbar = fig.colorbar(im, ax=ax, shrink=0.6, pad=0.02)
    cbar.set_label("Elevation (m, NAVD88)", fontsize=9, color="#52514e")
    cbar.ax.tick_params(labelsize=8, colors="#52514e")

    legend_elements = []
    for scen_label in ["Low", "Intermediate", "High"]:
        _, _, color = SCENARIOS[scen_label]
        for year in YEARS:
            elev_m = thresholds[scen_label][year]
            elev_ft = elev_m * M_TO_FT
            legend_elements.append(Line2D(
                [0], [0], color=color, lw=1.8, linestyle=LINESTYLES[year],
                label=f"{scen_label} {year} ({elev_m:.2f} m / {elev_ft:.1f} ft NAVD88)",
            ))
    ax.legend(handles=legend_elements, loc="lower left", frameon=True,
              framealpha=0.9, fontsize=7.8, title="Projected high tide reach",
              title_fontsize=8.5)

    fig.tight_layout(rect=[0, 0, 1, 0.92])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=fig.get_facecolor())
    print(f"Saved {OUTPUT_PATH}")
    print(f"Today's MHHW: {THRESHOLD_TODAY:.3f} m NAVD88 ({THRESHOLD_TODAY*M_TO_FT:.2f} ft)")
    for scen_label in ["Low", "Intermediate", "High"]:
        for year in YEARS:
            elev_m = thresholds[scen_label][year]
            print(f"{scen_label} {year}: {elev_m:.3f} m NAVD88 ({elev_m*M_TO_FT:.2f} ft)")


if __name__ == "__main__":
    main()
