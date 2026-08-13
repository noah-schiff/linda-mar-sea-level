"""Single summary figure combining all three project phases.

Left: the Phase 2 elevation map with projected high-tide reach (today, and
NOAA 2022 Intermediate/High by 2100). Right, stacked: the Phase 1 San
Francisco sea level record, and the Phase 3 satellite-derived shoreline
position at Linda Mar Beach. A stat row across the top carries the three
headline numbers.

Runs in the project's regular `.venv` (like the other plot_*.py scripts) --
reads the transect time series and transects geojson as plain CSV/JSON, so
no geopandas or the separate `coastsat` conda env needed.

    .\\.venv\\Scripts\\python.exe scripts\\plot_summary.py
"""

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import tifffile
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from scipy import stats
from scipy.ndimage import gaussian_filter

from plot_sea_level import TREND_START_YEAR, fit_trend, load_data

ROOT = Path(__file__).resolve().parent.parent
DEM_PATH = ROOT / "data" / "linda_mar_dem.tif"
META_PATH = ROOT / "data" / "linda_mar_dem.meta.json"
TIMESERIES_PATH = ROOT / "data" / "coastsat_transect_timeseries.csv"
OUTPUT_PATH = ROOT / "output" / "linda_mar_summary.png"

M_TO_FT = 3.28084
MHHW_NAVD88_M = 1.798
SLR_INT_2100 = 0.911   # NOAA 2022 Intermediate, 50th pct, SF (PSMSL 10)
SLR_HIGH_2100 = 1.958  # NOAA 2022 High, 50th pct

# --- Palette -----------------------------------------------------------------
# dataviz reference palette. The two time-series panels share one visual
# grammar so the reader learns it once: muted gray = raw noisy observations,
# categorical slot 1 (blue) = the smoothed signal, slot 2 (orange) = the
# fitted linear trend. Validated (adjacent, light, surface #fcfcfb): CVD
# dE 24.7, normal-vision dE 33.6, both marks >= 3:1 -- all checks pass.
COLOR_RAW = "#c3c2b7"
COLOR_SIGNAL = "#2a78d6"
COLOR_TREND = "#eb6834"

# Flood extent is an AREA, not a line -- so the map fills nested zones rather
# than drawing thin contours (three near-coincident lines over a diverging
# basemap were nearly unreadable at this size). The zones are ORDERED (already
# wet today < added by 2100 Intermediate < added by 2100 High), so they take a
# one-hue ordinal ramp (blue 650/450/250) rather than arbitrary categorical
# hues: darkest = water already here, lightest = only under the High scenario.
# Validated with the ordinal checks -- monotone lightness, all step gaps
# >= 0.06, light end 2.06:1 vs surface, hue spread 3deg.
FLOOD_TODAY = "#104281"
FLOOD_INT_2100 = "#2a78d6"
FLOOD_HIGH_2100 = "#86b6ef"

# The terrain underneath is context, not data -- a recessive light-gray ramp,
# so the only loud thing on the map is the water. (The Phase 2 deliverable
# keeps its LSU purple/gold diverging scale; that map's job is elevation
# itself, where the color IS the data.)
COLOR_LAND_LOW = "#f2f1ec"
COLOR_LAND_HIGH = "#b0aea4"

COLOR_INK = "#0b0b0b"
COLOR_SECONDARY_INK = "#52514e"
COLOR_MUTED = "#898781"
COLOR_GRID = "#e1e0d9"
COLOR_SURFACE = "#fcfcfb"

plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans", "sans-serif"]


def style_axes(ax):
    """Recessive chrome: hairline solid grid, no top/right spines."""
    ax.set_facecolor(COLOR_SURFACE)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(COLOR_GRID)
    ax.grid(True, axis="y", color=COLOR_GRID, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    ax.tick_params(colors=COLOR_MUTED, labelsize=8.5)


def panel_sea_level(ax):
    df = load_data()
    df["rolling_12mo"] = df["height_mm"].rolling(window=12, center=True, min_periods=12).mean()
    slope, intercept, trend_x, trend_y = fit_trend(df, TREND_START_YEAR)

    # Center on the trend-period mean so the axis reads as change, not as the
    # RLR datum's ~7000 mm offset. Centering shifts the intercept only -- the
    # slope (the actual Phase 1 result) is unaffected.
    baseline = df.loc[df["year"] >= TREND_START_YEAR, "height_mm"].mean()

    ax.plot(df["year"], df["height_mm"] - baseline, color=COLOR_RAW, linewidth=0.7,
            label="Monthly mean", zorder=1)
    ax.plot(df["year"], df["rolling_12mo"] - baseline, color=COLOR_SIGNAL, linewidth=1.6,
            label="12-month rolling average", zorder=2)
    ax.plot(trend_x, trend_y - baseline, color=COLOR_TREND, linewidth=2,
            solid_capstyle="round", label=f"Linear trend: {slope:.2f} mm/yr", zorder=3)

    ax.set_title("① Sea level is rising — San Francisco tide gauge, 1854–present",
                 fontsize=11.5, color=COLOR_INK, fontweight="bold", loc="left", pad=8)
    ax.set_ylabel("Sea level (mm, relative to\n1897–present mean)", fontsize=8.5,
                  color=COLOR_MUTED)
    style_axes(ax)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=COLOR_SECONDARY_INK)

    # No direct end-label here: the rate already appears in the legend and in
    # the stat tile above, and a third copy sat on top of the trend line.
    return slope


def panel_shoreline(ax):
    df = pd.read_csv(TIMESERIES_PATH)
    transect_cols = [c for c in df.columns
                     if c not in ("date", "decimal_year", "satname")]

    mean_series = df[transect_cols].mean(axis=1, skipna=True)
    mask = ~mean_series.isna()
    years = df["decimal_year"].values
    # Plot as anomaly about the record mean: the question is whether the beach
    # moved, not how far it sits from an arbitrary transect origin.
    baseline = mean_series[mask].mean()
    anomaly = mean_series - baseline

    res = stats.linregress(years[mask], anomaly[mask])

    ax.axhline(0, color=COLOR_GRID, linewidth=1, zorder=0)
    ax.scatter(years[mask], anomaly[mask], s=7, color=COLOR_RAW, alpha=0.75,
               linewidths=0, label="Individual satellite passes", zorder=1)

    # Annual median = the smoothed signal, same role blue plays in panel 1.
    annual = pd.DataFrame({"year": np.floor(years[mask]), "v": anomaly[mask]})
    annual = annual.groupby("year")["v"].median()
    ax.plot(annual.index + 0.5, annual.values, color=COLOR_SIGNAL, linewidth=1.6,
            label="Annual median", zorder=2)

    xline = np.array([years[mask].min(), years[mask].max()])
    ax.plot(xline, res.intercept + res.slope * xline, color=COLOR_TREND, linewidth=2,
            solid_capstyle="round", label=f"Linear trend: {res.slope:+.2f} m/yr", zorder=3)

    ax.set_title("② …and the beach is holding — shoreline position, 1984–2026",
                 fontsize=11.5, color=COLOR_INK, fontweight="bold", loc="left", pad=8)
    ax.set_ylabel("Shoreline position (m,\nrelative to record mean)", fontsize=8.5,
                  color=COLOR_MUTED)
    ax.set_xlabel("Year", fontsize=8.5, color=COLOR_MUTED)
    style_axes(ax)
    # 99.3% of passes fall inside +/-45 m; capping the axis here keeps the
    # trend legible instead of letting 7 outliers set the scale. The count is
    # stated on the panel rather than silently dropped.
    n_outside = int((anomaly[mask].abs() > 50).sum())
    ax.set_ylim(-50, 50)
    ax.legend(loc="upper left", frameon=False, fontsize=8.5, ncol=1,
              labelcolor=COLOR_SECONDARY_INK)
    ax.annotate("seaward →", xy=(0.995, 0.93), xycoords="axes fraction", ha="right",
                fontsize=8, color=COLOR_MUTED)
    ax.annotate("← landward", xy=(0.995, 0.04), xycoords="axes fraction", ha="right",
                fontsize=8, color=COLOR_MUTED)
    ax.annotate(f"axis capped at ±50 m ({n_outside} of {int(mask.sum())} passes fall outside)",
                xy=(0.995, 0.135), xycoords="axes fraction", ha="right",
                fontsize=7.5, color=COLOR_MUTED, style="italic")
    return res.slope, res.pvalue


def panel_map(ax, fig):
    arr = gaussian_filter(tifffile.imread(DEM_PATH), sigma=6)
    meta = json.loads(META_PATH.read_text())
    x_min, y_min = meta["x_min"], meta["y_min"]
    extent = [0, (meta["x_max"] - x_min) / 1000, 0, (meta["y_max"] - y_min) / 1000]

    t_today = MHHW_NAVD88_M
    t_int = MHHW_NAVD88_M + SLR_INT_2100
    t_high = MHHW_NAVD88_M + SLR_HIGH_2100

    # Recessive terrain context. Starts at the highest flood threshold so the
    # gray ramp never competes with the blue zones drawn over it.
    land = LinearSegmentedColormap.from_list("land", [COLOR_LAND_LOW, COLOR_LAND_HIGH])
    ax.imshow(arr, extent=extent, origin="upper", cmap=land,
              vmin=t_high, vmax=60)

    # Nested filled flood zones, drawn in one pass so the boundaries share
    # edges exactly (no seams, no stacked translucency).
    zones = [
        ("Already reached at today's high tide", t_today, FLOOD_TODAY),
        ("Added by 2100 · NOAA Intermediate", t_int, FLOOD_INT_2100),
        ("Added by 2100 · NOAA High", t_high, FLOOD_HIGH_2100),
    ]
    ax.contourf(arr, levels=[np.nanmin(arr), t_today, t_int, t_high],
                colors=[FLOOD_TODAY, FLOOD_INT_2100, FLOOD_HIGH_2100],
                extent=extent, origin="upper")

    ax.set_title("③ But the high-tide line still moves inland — projected reach by 2100",
                 fontsize=11.5, color=COLOR_INK, fontweight="bold", loc="left", pad=8)
    ax.set_xlabel("Kilometers east", fontsize=8.5, color=COLOR_MUTED)
    ax.set_ylabel("Kilometers north", fontsize=8.5, color=COLOR_MUTED)
    ax.set_aspect("equal")
    ax.tick_params(colors=COLOR_MUTED, labelsize=8.5)
    for spine in ax.spines.values():
        spine.set_color(COLOR_GRID)

    # Orientation cues, so the reader can find the beach and the floodplain.
    ax.annotate("Linda Mar\nBeach", xy=(0.30, 0.85), fontsize=8.5, color=COLOR_INK,
                ha="left", va="center", fontweight="bold")
    ax.annotate("San Pedro Creek\nfloodplain", xy=(1.18, 2.06), fontsize=8.5,
                color=COLOR_INK, ha="left", va="center", fontweight="bold")
    ax.annotate("Pacific Ocean", xy=(0.08, 3.15), fontsize=8.5, color="white",
                ha="left", va="center", style="italic")

    handles = [
        Line2D([0], [0], marker="s", linestyle="none", markersize=9,
               markerfacecolor=c, markeredgecolor=COLOR_SURFACE, markeredgewidth=0.8,
               label=f"{lbl}  ·  below {lv:.2f} m / {lv * M_TO_FT:.1f} ft")
        for lbl, lv, c in zones
    ]
    handles.append(Line2D([0], [0], marker="s", linestyle="none", markersize=9,
                          markerfacecolor=COLOR_LAND_HIGH,
                          markeredgecolor=COLOR_SURFACE, markeredgewidth=0.8,
                          label="Higher ground (darker = higher)"))
    ax.legend(handles=handles, loc="lower right", frameon=True, framealpha=0.94,
              edgecolor=COLOR_GRID, fontsize=8, labelcolor=COLOR_SECONDARY_INK,
              borderpad=0.7, handletextpad=0.7)


def stat_row(fig, sl_slope, shoreline_slope, shoreline_p):
    """Three headline numbers. Equal weight -- no single hero figure."""
    # Order matches the panel order below (① sea level, ② shoreline, ③ flooding).
    tiles = [
        ("① Sea level rise, 1897–present", f"{sl_slope:.2f} mm/yr",
         "San Francisco tide gauge (PSMSL 10)"),
        ("② Shoreline change, 1984–2026", f"{shoreline_slope:+.2f} m/yr",
         f"CoastSat, 16 transects (p={shoreline_p:.3f})"),
        # SLR scenario values are relative to a YEAR-2000 baseline, not to
        # today -- the map legend carries the unambiguous absolute NAVD88
        # elevations that this rise implies.
        ("③ Projected sea level rise by 2100", f"+{SLR_INT_2100:.2f} m",
         "NOAA 2022 Intermediate, vs. 2000 baseline"),
    ]
    for i, (label, value, sub) in enumerate(tiles):
        x = 0.035 + i * 0.322
        fig.text(x, 0.919, label, fontsize=9, color=COLOR_SECONDARY_INK, ha="left")
        # Value in primary ink, never the series color -- identity comes from
        # the panel it sits above, not from coloring the text.
        fig.text(x, 0.877, value, fontsize=21, color=COLOR_INK, ha="left",
                 fontweight="bold")
        fig.text(x, 0.855, sub, fontsize=7.8, color=COLOR_MUTED, ha="left")


def main() -> None:
    fig = plt.figure(figsize=(17, 11), dpi=150)
    fig.patch.set_facecolor(COLOR_SURFACE)

    # Reading order carries the argument: the two observed histories stack on
    # the left (① rising sea level, ② a beach that has held), and the
    # projection they lead to gets the tall right-hand panel (③).
    gs = fig.add_gridspec(
        2, 2, width_ratios=[1.32, 1], height_ratios=[1, 1],
        left=0.045, right=0.985, top=0.822, bottom=0.075, wspace=0.13, hspace=0.30,
    )
    ax_sl = fig.add_subplot(gs[0, 0])
    ax_sc = fig.add_subplot(gs[1, 0])
    ax_map = fig.add_subplot(gs[:, 1])

    sl_slope = panel_sea_level(ax_sl)
    shoreline_slope, shoreline_p = panel_shoreline(ax_sc)
    panel_map(ax_map, fig)
    stat_row(fig, sl_slope, shoreline_slope, shoreline_p)

    fig.suptitle("Linda Mar Beach, Pacifica — Sea Level, Flooding, and Shoreline Change",
                 fontsize=17, color=COLOR_INK, x=0.035, y=0.984, ha="left",
                 fontweight="bold")
    fig.text(0.035, 0.953,
             "Sea level at the gauge has risen steadily for a century and the beach has so "
             "far held its ground — but projections still push the high-tide line well "
             "inland across the San Pedro Creek floodplain.",
             fontsize=10.5, color=COLOR_SECONDARY_INK, ha="left")

    fig.text(0.035, 0.022,
             "Sources: PSMSL station 10 (monthly mean sea level, RLR datum) · NOAA 2022 "
             "Interagency SLR scenarios, 50th percentile · USGS 3DEP 2 m elevation (NAVD88) · "
             "CoastSat (Landsat 5/7/8/9 + Sentinel-2, 1,051 shorelines).",
             fontsize=7.8, color=COLOR_MUTED, ha="left")
    fig.text(0.035, 0.006,
             "Flood extents are a static \"bathtub\" screening model — no storm surge, wave "
             "run-up, or drainage connectivity. Shoreline positions are not tidally corrected.",
             fontsize=7.8, color=COLOR_MUTED, ha="left")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=COLOR_SURFACE)
    print(f"Saved {OUTPUT_PATH}")
    print(f"  Phase 1 sea level trend:   {sl_slope:.3f} mm/yr")
    print(f"  Phase 2 Intermediate 2100: {MHHW_NAVD88_M + SLR_INT_2100:.3f} m NAVD88")
    print(f"  Phase 3 shoreline trend:   {shoreline_slope:+.3f} m/yr (p={shoreline_p:.3f})")


if __name__ == "__main__":
    main()
