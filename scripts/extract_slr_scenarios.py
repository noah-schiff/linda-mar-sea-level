"""Extract the NOAA 2022 Interagency sea level rise scenarios for the San
Francisco tide gauge (PSMSL station 10) and save them as a CSV.

Source: the supplementary dataset released alongside "Global and Regional
Sea Level Rise Scenarios for the United States" (NOAA-NOS-TR01, Feb 2022),
archived at Zenodo record 5951626 (https://zenodo.org/records/5951626).
`TR_local_projections.nc` holds projections at individual tide-gauge
locations, keyed by PSMSL ID -- station 10 is San Francisco.

Values are relative sea level rise in meters, relative to a year-2000
baseline, at the 17th/50th/83rd percentiles ("likely range") of each of the
five scenarios (Low, Intermediate-Low, Intermediate, Intermediate-High,
High). To compare against elevation (NAVD88), add the local MHHW-NAVD88
offset -- see plot_elevation_map.py.

Usage:
    python scripts/extract_slr_scenarios.py
"""

import csv
from pathlib import Path

import netCDF4 as nc
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
NC_PATH = ROOT / "data" / "slr_scenarios" / "Results" / "TR_local_projections.nc"
OUT_PATH = ROOT / "data" / "sf_slr_scenarios.csv"

PSMSL_STATION_ID = 10
SCENARIOS = ["Low", "IntLow", "Int", "IntHigh", "High"]
SCENARIO_LABELS = {
    "Low": "Low", "IntLow": "Intermediate-Low", "Int": "Intermediate",
    "IntHigh": "Intermediate-High", "High": "High",
}
REPORT_YEARS = [2020, 2030, 2040, 2050, 2060, 2070, 2080, 2090, 2100, 2150]


def main() -> None:
    ds = nc.Dataset(NC_PATH)
    psmsl_ids = ds.variables["PSMSL_id"][:]
    station_idx = int(np.where(psmsl_ids == PSMSL_STATION_ID)[0][0])
    station_name = str(ds.variables["tg"][station_idx])

    years = ds.variables["years"][:]
    year_indices = {y: int(np.where(years == y)[0][0]) for y in REPORT_YEARS}
    percentiles = ds.variables["percentiles"][:]  # [17, 50, 83]

    rows = []
    for scen in SCENARIOS:
        var = ds.variables[f"rsl_total_{scen}"]  # (percentiles, years, tg)
        for year in REPORT_YEARS:
            yi = year_indices[year]
            values_mm = var[:, yi, station_idx]
            row = {
                "scenario": SCENARIO_LABELS[scen],
                "year": year,
                "rsl_17th_pct_m": round(float(values_mm[0]) / 1000, 3),
                "rsl_median_m": round(float(values_mm[1]) / 1000, 3),
                "rsl_83rd_pct_m": round(float(values_mm[2]) / 1000, 3),
            }
            rows.append(row)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Station: {station_name} (PSMSL {PSMSL_STATION_ID})")
    print(f"Saved {len(rows)} rows to {OUT_PATH}")
    print("\nMedian projections (meters, relative to year-2000 baseline):")
    print(f"{'Scenario':<20}{'2050':>10}{'2100':>10}")
    for scen in SCENARIOS:
        var = ds.variables[f"rsl_total_{scen}"]
        v2050 = var[1, year_indices[2050], station_idx] / 1000
        v2100 = var[1, year_indices[2100], station_idx] / 1000
        print(f"{SCENARIO_LABELS[scen]:<20}{v2050:>9.2f}m{v2100:>9.2f}m")


if __name__ == "__main__":
    main()
