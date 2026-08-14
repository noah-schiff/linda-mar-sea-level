"""Generate the data payload for the Phase 4 interactive site.

Reads the Phase 1-3 source data and writes compact binary + JSON into
site/data/, plus vendors three.js into site/vendor/. The site's HTML/CSS/JS
are hand-authored files -- this script only produces what they load, so no
markup lives inside Python strings here.

Outputs (all committed, so GitHub Pages works without running the build):
  site/data/terrain.bin      Int16 heights in centimetres, row-major, south-up
  site/data/terrain.json     grid dimensions + georeferencing
  site/data/shorelines.bin   Int16 quantised XY for every satellite pass
  site/data/shorelines.json  per-year index + annual median shorelines
  site/data/sealevel.json    Phase 1 series and fitted trend
  site/data/summary.json     headline numbers + per-step flood areas

    .\\.venv\\Scripts\\python.exe scripts\\build_site.py
"""

import argparse
import json
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import tifffile
from scipy import stats

from plot_sea_level import TREND_START_YEAR, fit_trend, load_data

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DATA_OUT = SITE / "data"
VENDOR_OUT = SITE / "vendor"

DEM_PATH = ROOT / "data" / "linda_mar_dem.tif"
META_PATH = ROOT / "data" / "linda_mar_dem.meta.json"
SHORELINES_PATH = ROOT / "data" / "coastsat_shorelines.geojson"
TRANSECTS_PATH = ROOT / "data" / "coastsat_transects.geojson"
TIMESERIES_PATH = ROOT / "data" / "coastsat_transect_timeseries.csv"

M_TO_FT = 3.28084
MHHW_NAVD88_M = 1.798
SLR_INT_2100 = 0.911
SLR_HIGH_2100 = 1.958
LEVEL_INT_2100 = MHHW_NAVD88_M + SLR_INT_2100
LEVEL_HIGH_2100 = MHHW_NAVD88_M + SLR_HIGH_2100

# 2x decimation -> 891x613 verts (~1.1M triangles). Comfortable for WebGL and
# still 4 m posts, well inside the DEM's own 2 m resolution.
DOWNSAMPLE = 2
BASELINE_YEARS = (1984, 1989)  # the "ghost" reference shoreline

THREE_VERSION = "0.169.0"
VENDOR_FILES = {
    "three.module.min.js": f"https://unpkg.com/three@{THREE_VERSION}/build/three.module.min.js",
    "OrbitControls.js":
        f"https://unpkg.com/three@{THREE_VERSION}/examples/jsm/controls/OrbitControls.js",
}


def write_terrain(meta):
    """DEM -> Int16 centimetres, row 0 = SOUTH edge so the JS can build the
    mesh with x=east, z=north and no flips."""
    arr = tifffile.imread(DEM_PATH).astype("float64")
    dec = arr[::DOWNSAMPLE, ::DOWNSAMPLE]
    dec = np.flipud(dec)  # DEM row 0 is north; the site wants row 0 = south

    cm = np.rint(dec * 100.0)
    assert cm.min() >= np.iinfo(np.int16).min and cm.max() <= np.iinfo(np.int16).max, (
        f"heights {cm.min()}..{cm.max()} cm overflow Int16")
    cm = cm.astype("<i2")

    rows, cols = cm.shape
    (DATA_OUT / "terrain.bin").write_bytes(cm.tobytes())
    spacing = meta["resolution_m"] * DOWNSAMPLE
    terrain_meta = {
        "rows": rows, "cols": cols,
        "spacing_m": spacing,
        "height_scale": 0.01,          # Int16 units -> metres
        "x0_utm": meta["x_min"], "y0_utm": meta["y_min"],
        "width_m": (cols - 1) * spacing, "depth_m": (rows - 1) * spacing,
        "min_m": float(dec.min()), "max_m": float(dec.max()),
        "crs": meta["crs"],
    }
    (DATA_OUT / "terrain.json").write_text(json.dumps(terrain_meta, indent=2))
    print(f"  terrain.bin   {rows}x{cols} = {rows*cols:,} verts, "
          f"{rows*cols*2/1e6:.2f} MB, {dec.min():.1f}..{dec.max():.1f} m")
    return arr, terrain_meta


def annual_median_shorelines():
    """Rebuild a shoreline per year from the 16 transect medians -- the same
    numbers the +0.131 m/yr trend is fitted to.

    Transects with no observation in a given year are skipped rather than
    interpolated, so the line never invents a position it doesn't have.
    """
    tj = json.loads(TRANSECTS_PATH.read_text())
    transects = {}
    for feat in tj["features"]:
        coords = np.array(feat["geometry"]["coordinates"], dtype="float64")
        origin = coords[0]
        direction = coords[-1] - coords[0]
        transects[feat["properties"]["name"]] = (origin, direction / np.linalg.norm(direction))

    df = pd.read_csv(TIMESERIES_PATH)
    names = sorted(transects)
    df["year"] = df["decimal_year"].astype(int)

    per_year, coverage = {}, {}
    for year, grp in df.groupby("year"):
        med = grp[names].median()
        pts = []
        for name in names:
            if pd.notna(med[name]):
                origin, unit = transects[name]
                pts.append((origin + unit * float(med[name])).tolist())
        per_year[int(year)] = pts
        coverage[int(year)] = len(pts)
    return per_year, coverage, len(names)


def write_shorelines(per_year_median, coverage, n_transects):
    """Every satellite pass, quantised to Int16 over the shorelines' own bbox."""
    gj = json.loads(SHORELINES_PATH.read_text())

    # Group each pass's polyline parts by year.
    by_year = {}
    for feat in gj["features"]:
        year = int(feat["properties"]["date"][:4])
        geom = feat["geometry"]
        parts = ([geom["coordinates"]] if geom["type"] == "LineString"
                 else geom["coordinates"])
        by_year.setdefault(year, []).append(parts)

    every = np.array([pt for yr in by_year.values() for parts in yr
                      for part in parts for pt in part], dtype="float64")
    x_min, y_min = every[:, 0].min(), every[:, 1].min()
    x_max, y_max = every[:, 0].max(), every[:, 1].max()
    span_x, span_y = x_max - x_min, y_max - y_min

    def quantise(points):
        arr = np.asarray(points, dtype="float64")
        qx = np.rint((arr[:, 0] - x_min) / span_x * 65535.0) - 32768.0
        qy = np.rint((arr[:, 1] - y_min) / span_y * 65535.0) - 32768.0
        return np.column_stack([qx, qy]).astype("<i2")

    chunks, part_index, year_index, passes_by_year = [], [], {}, {}
    offset = 0  # in coordinate PAIRS, not bytes
    for year in sorted(by_year):
        first_part = len(part_index)
        for parts in by_year[year]:
            for part in parts:
                if len(part) < 2:
                    continue
                chunks.append(quantise(part))
                part_index.append([offset, len(part)])
                offset += len(part)
        year_index[str(year)] = [first_part, len(part_index) - first_part]
        # Distinct satellite passes, which is NOT the part count -- one pass is
        # usually a MultiLineString of several disconnected coastline pieces.
        passes_by_year[str(year)] = len(by_year[year])

    packed = np.concatenate(chunks, axis=0)
    (DATA_OUT / "shorelines.bin").write_bytes(packed.tobytes())

    years = sorted(per_year_median)
    lo, hi = BASELINE_YEARS
    baseline_src = [per_year_median[y] for y in years if lo <= y <= hi]
    n_pts = min(len(p) for p in baseline_src)
    baseline = np.mean([np.array(p[:n_pts]) for p in baseline_src], axis=0).tolist()

    index = {
        "quantisation": {"x_min": x_min, "y_min": y_min,
                         "span_x": span_x, "span_y": span_y,
                         "int16_offset": -32768.0, "int16_range": 65535.0},
        "parts": part_index,
        "years": year_index,
        "passes_by_year": passes_by_year,
        "median_by_year": {str(y): per_year_median[y] for y in years},
        "coverage_by_year": {str(y): coverage[y] for y in years},
        "n_transects": n_transects,
        "baseline_years": list(BASELINE_YEARS),
        "baseline": baseline,
    }
    (DATA_OUT / "shorelines.json").write_text(json.dumps(index, separators=(",", ":")))

    partial = {y: c for y, c in coverage.items() if c < n_transects}
    print(f"  shorelines.bin {offset:,} pts, {len(part_index):,} parts, "
          f"{offset*4/1e6:.2f} MB")
    print(f"  shorelines.json {len(year_index)} years "
          f"({min(by_year)}-{max(by_year)}), partial coverage: {partial}")
    return sorted(by_year)


def write_sealevel():
    df = load_data()
    df["rolling_12mo"] = df["height_mm"].rolling(window=12, center=True,
                                                 min_periods=12).mean()
    slope, intercept, trend_x, trend_y = fit_trend(df, TREND_START_YEAR)
    baseline = df.loc[df["year"] >= TREND_START_YEAR, "height_mm"].mean()

    def clean(series):
        return [None if pd.isna(v) else round(float(v) - baseline, 1) for v in series]

    payload = {
        "year": [round(float(v), 4) for v in df["year"]],
        "monthly_mm": clean(df["height_mm"]),
        "rolling_mm": clean(df["rolling_12mo"]),
        "trend": {"x": [float(trend_x[0]), float(trend_x[-1])],
                  "y": [round(float(trend_y[0] - baseline), 1),
                        round(float(trend_y[-1] - baseline), 1)],
                  "slope_mm_per_yr": round(float(slope), 3),
                  "start_year": TREND_START_YEAR},
        "baseline_note": f"relative to the {TREND_START_YEAR}-present mean",
    }
    (DATA_OUT / "sealevel.json").write_text(json.dumps(payload, separators=(",", ":")))
    print(f"  sealevel.json {len(payload['year']):,} months, "
          f"trend {slope:.3f} mm/yr")
    return slope


def water_levels():
    lo = np.linspace(MHHW_NAVD88_M, LEVEL_INT_2100, 10)
    hi = np.linspace(LEVEL_INT_2100, LEVEL_HIGH_2100, 11)
    return sorted({round(float(v), 3) for v in np.concatenate([lo, hi])})


def write_summary(arr_full, res, sl_slope):
    """Flood areas come from the FULL-resolution DEM, never the decimated
    display grid, so the readout doesn't inherit decimation error."""
    dry_today = arr_full > MHHW_NAVD88_M
    px_ha = (res * res) / 10_000.0

    steps = []
    for level in water_levels():
        newly_ha = float(np.count_nonzero(dry_today & (arr_full <= level)) * px_ha)
        label = f"{level:.2f}"
        if abs(level - MHHW_NAVD88_M) < 1e-6:
            label = "Today"
        elif abs(level - LEVEL_INT_2100) < 1e-6:
            label = "2100 Int"
        elif abs(level - LEVEL_HIGH_2100) < 1e-6:
            label = "2100 High"
        steps.append({"level_m": level, "level_ft": round(level * M_TO_FT, 2),
                      "rise_m": round(level - MHHW_NAVD88_M, 3),
                      "newly_flooded_ha": round(newly_ha, 1), "label": label})

    df = pd.read_csv(TIMESERIES_PATH)
    cols = [c for c in df.columns if c not in ("date", "decimal_year", "satname")]
    mean_series = df[cols].mean(axis=1, skipna=True)
    mask = ~mean_series.isna()
    res_fit = stats.linregress(df["decimal_year"].values[mask], mean_series.values[mask])

    payload = {
        "headline": [
            {"n": "1", "label": "Sea level rise, 1897-present",
             "value": f"{sl_slope:.2f} mm/yr",
             "sub": "San Francisco tide gauge (PSMSL 10)"},
            {"n": "2", "label": "Shoreline change, 1984-2026",
             "value": f"{res_fit.slope:+.2f} m/yr",
             "sub": f"CoastSat, {len(cols)} transects (p={res_fit.pvalue:.3f})"},
            {"n": "3", "label": "Projected sea level rise by 2100",
             "value": f"+{SLR_INT_2100:.2f} m",
             "sub": "NOAA 2022 Intermediate, vs. 2000 baseline"},
        ],
        "mhhw_m": MHHW_NAVD88_M,
        "level_int_2100_m": round(LEVEL_INT_2100, 3),
        "level_high_2100_m": round(LEVEL_HIGH_2100, 3),
        "water_steps": steps,
        "shoreline_trend_m_per_yr": round(float(res_fit.slope), 3),
        "shoreline_trend_p": round(float(res_fit.pvalue), 4),
        "dem_max_m": round(float(arr_full.max()), 1),
        "dem_resolution_m": res,
    }
    (DATA_OUT / "summary.json").write_text(json.dumps(payload, indent=2))
    print(f"  summary.json {len(steps)} water steps, "
          f"{steps[0]['newly_flooded_ha']:.1f} -> {steps[-1]['newly_flooded_ha']:.1f} ha")
    return payload


def vendor(force=False):
    VENDOR_OUT.mkdir(parents=True, exist_ok=True)
    for name, url in VENDOR_FILES.items():
        dest = VENDOR_OUT / name
        if dest.exists() and not force:
            print(f"  {name} already vendored ({dest.stat().st_size/1024:.0f} KB)")
            continue
        with urllib.request.urlopen(url, timeout=60) as resp:
            dest.write_bytes(resp.read())
        print(f"  {name} downloaded ({dest.stat().st_size/1024:.0f} KB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh-vendor", action="store_true",
                    help="re-download three.js even if already present")
    args = ap.parse_args()

    DATA_OUT.mkdir(parents=True, exist_ok=True)
    meta = json.loads(META_PATH.read_text())

    print("Vendoring three.js:")
    vendor(force=args.refresh_vendor)

    print("Building site data:")
    arr_full, _ = write_terrain(meta)
    medians, coverage, n_transects = annual_median_shorelines()
    years = write_shorelines(medians, coverage, n_transects)
    sl_slope = write_sealevel()
    summary = write_summary(arr_full, meta["resolution_m"], sl_slope)

    missing = sorted(set(range(min(years), max(years) + 1)) - set(years))
    assert not missing, f"years with no shoreline data: {missing}"
    assert set(medians) == set(years), "median years and pass years disagree"
    print(f"\nOK -- {len(years)} continuous years {min(years)}-{max(years)}, "
          f"{len(summary['water_steps'])} water levels.")
    total = sum(p.stat().st_size for p in DATA_OUT.iterdir())
    print(f"site/data total: {total/1e6:.2f} MB")


if __name__ == "__main__":
    main()
