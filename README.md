# Linda Mar Sea Level

Mapping sea level change and its impact on Linda Mar Beach, Pacifica, CA,
using the San Francisco tide gauge (PSMSL station 10) as the historical
reference record.

![San Francisco sea level trend](output/sf_sea_level_trend.png)
![Linda Mar Beach elevation map](output/linda_mar_elevation_map.png)

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Usage

```powershell
cd scripts
..\.venv\Scripts\python.exe plot_sea_level.py          # Phase 1 chart
..\.venv\Scripts\python.exe download_dem.py             # Phase 2: fetch DEM
..\.venv\Scripts\python.exe extract_slr_scenarios.py    # Phase 2: SLR scenario table
..\.venv\Scripts\python.exe plot_elevation_map.py        # Phase 2: elevation map
```

`plot_sea_level.py` downloads the PSMSL data (if not already in `data/`),
computes a 12-month rolling average, fits a linear trend from 1897 onward,
and saves `output/sf_sea_level_trend.png`.

`plot_elevation_map.py` colors a USGS 3DEP elevation model of Linda Mar
Beach and marks how far inland NOAA's 2022 "Intermediate" scenario projects
high tide to reach by 2050 and 2100.

## Status

- **Phase 1 (done):** historical sea level trend from the SF tide gauge —
  measured at ~1.98 mm/yr, matching NOAA's published figure.
- **Phase 2 (in progress):** elevation map of Linda Mar Beach + NOAA 2022
  sea-level-rise scenarios (San Francisco, Intermediate scenario: +0.23 m
  by 2050, +0.91 m by 2100, relative to year 2000).
- **Phase 3 (planned):** interactive map/dashboard to explore scenarios.

See `CLAUDE.md` for full project details.
