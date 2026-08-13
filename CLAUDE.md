# Linda Mar Sea Level Project

Mapping sea level change and its impact on Linda Mar Beach, Pacifica, CA.

The nearest long-running tide gauge to Linda Mar Beach is the San Francisco
station (PSMSL station 10 / NOAA station 9414290), which has one of the
longest continuous sea level records in North America. This project uses that
record as the basis for historical trends, then projects those trends onto
the local terrain at Linda Mar Beach to visualize future inundation risk.

## Environment

- Python virtual environment: `.venv` (created with `py -m venv .venv`)
- Activate on Windows: `.\.venv\Scripts\Activate.ps1`, or call
  `.\.venv\Scripts\python.exe` directly without activating
- Installed packages: `requests`, `pandas`, `numpy`, `matplotlib` (Phase 1);
  `pyproj`, `tifffile`, `netCDF4`, `cftime` (Phase 2, for DEM reprojection/
  reading and reading the SLR scenario NetCDF). All pinned in
  `requirements.txt`. Note: this project uses Python 3.14 (very new as of
  2026) — `rasterio`/GDAL-based packages may lack prebuilt Windows wheels for
  it; `tifffile` was used instead to sidestep that, and it has been
  sufficient so far since we always know our own raster's georeferencing
  (we set it when requesting the DEM) rather than needing to parse it back
  out of GeoTIFF tags.

## Project structure

- `data/` — downloaded/raw data files (not manually edited)
- `scripts/` — Python scripts, one purpose per file
- `output/` — generated charts, maps, and other deliverables

## Phase 1 — Historical sea level trend (done)

Download and plot the long-term mean sea level record for the San Francisco
tide gauge.

- Data source: PSMSL RLR (Revised Local Reference) monthly mean sea level,
  station 10 — `https://psmsl.org/data/obtaining/rlr.monthly.data/10.rlrdata`.
  RLR means all years are on one consistent vertical datum, so the record is
  comparable across equipment/reference changes over the station's history.
- File format: semicolon-separated, no header —
  `decimal_year; height_mm; missing_flag; interpolated_flags`. Missing months
  are coded as `-99999` and must be treated as NaN.
- `scripts/download_data.py` — downloads a station's `.rlrdata` file into
  `data/`. Takes an optional PSMSL station ID argument (defaults to 10).
- `scripts/plot_sea_level.py` — loads the data, computes a 12-month centered
  rolling average, fits a linear trend on data from **1897 onward** (the
  standard start year NOAA uses for this station, since earlier 1850s–1890s
  data is noisier/less complete), and saves the chart to
  `output/sf_sea_level_trend.png`.
- Result: trend of **~1.98 mm/yr (~198 mm/century)**, consistent with NOAA's
  published San Francisco trend (~1.97 mm/yr) — a good sanity check that the
  fit is correct.

## Phase 2 — Elevation map + future sea-level-rise scenarios (in progress)

Get a digital elevation model (DEM) covering Linda Mar Beach / Pacifica and
overlay projected sea-level-rise scenarios to show where future inundation
would occur.

Area of interest: bounding box lon -122.520 to -122.492, lat 37.578 to
37.610 (WGS84) — covers Linda Mar Beach, the San Pedro Creek floodplain
behind it, and enough surrounding Pacifica terrain for context.

### Elevation data

- `scripts/download_dem.py` — downloads a 2 m/pixel bare-earth DEM for the
  area of interest from the USGS 3DEP seamless mosaic (served by
  `elevation.nationalmap.gov`'s `exportImage` ArcGIS ImageServer endpoint;
  along this coast the mosaic resolves to 1 m lidar, contributed in part
  via NOAA Digital Coast). Requests the output already reprojected to UTM
  zone 10N (EPSG:32610) so pixels are true square meters. Saves
  `data/linda_mar_dem.tif` (float32 GeoTIFF, elevation in **meters, NAVD88**
  vertical datum) plus a `data/linda_mar_dem.meta.json` sidecar recording
  the exact bbox/resolution we requested (used instead of re-parsing
  GeoTIFF georeferencing tags — see `tifffile` note above).
- Read with `tifffile.imread()`; combine with the `.meta.json` for extent.

### Sea level rise scenarios

- NOAA released updated regional/local sea-level-rise scenarios in Feb 2022
  via the interagency report "Global and Regional Sea Level Rise Scenarios
  for the United States" (NOAA-NOS-TR01). The report's own supplementary
  dataset (not easily scraped from NOAA's JS-based viewer tools) is
  archived at Zenodo record 5951626 (`TR_local_projections.nc`, station-level
  projections keyed by PSMSL ID).
- `scripts/extract_slr_scenarios.py` — downloads/reads that NetCDF (already
  fetched into `data/slr_scenarios/Results/TR_local_projections.nc`),
  extracts all 5 scenarios × 3 percentiles (17th/50th/83rd) × report years
  for San Francisco (PSMSL 10), and saves `data/sf_slr_scenarios.csv`.
- **Values are relative sea level rise in meters, relative to a year-2000
  baseline** — not an absolute elevation. To compare against the DEM
  (NAVD88), add the local MHHW-NAVD88 offset (see below).
- Median (50th percentile) projections for San Francisco:

  | Scenario | 2050 | 2100 |
  |---|---|---|
  | Low | 0.15 m | 0.28 m |
  | Intermediate-Low | 0.19 m | 0.46 m |
  | **Intermediate** | **0.23 m** | **0.91 m** |
  | Intermediate-High | 0.31 m | 1.41 m |
  | High | 0.37 m | 1.96 m |

  The full table (all scenarios/years/percentiles) is in
  `data/sf_slr_scenarios.csv`.

### Tying scenarios to elevation (tidal datum)

- MHHW (Mean Higher High Water — the elevation today's high tide reaches)
  relative to NAVD88 at the SF gauge (NOAA station 9414290), from the NOAA
  CO-OPS datums API
  (`api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/9414290/datums.json`):
  MHHW = 3.602 m and NAVD88 = 1.804 m, both relative to station datum →
  **MHHW = 1.798 m above NAVD88**.
- "Projected high tide elevation" for a given year/scenario = MHHW_NAVD88 +
  SLR scenario value for that year. This is a simple/standard screening
  approach (used e.g. by NOAA's own Sea Level Rise Viewer): land at or
  below that elevation is land the tide would regularly reach by that year,
  ignoring storm surge, wave run-up, and drainage/hydrological connectivity
  ("bathtub model" — a reasonable first pass, not a substitute for a real
  hydrodynamic flood study).
- Threshold elevations (median/50th-percentile scenario values), in meters
  and feet NAVD88:

  | Scenario | 2050 | 2100 |
  |---|---|---|
  | Low | 1.94 m / 6.4 ft | 2.08 m / 6.8 ft |
  | Intermediate | 2.03 m / 6.7 ft | 2.71 m / 8.9 ft |
  | High | 2.17 m / 7.1 ft | 3.76 m / 12.3 ft |

  (Today's MHHW for reference: 1.798 m / 5.90 ft NAVD88.)

### Map

- `scripts/plot_elevation_map.py` — loads the DEM, colors it with a
  diverging purple→cream→gold scale (LSU brand colors, per user request)
  centered on *today's* MHHW so the coloring itself is meaningful (purple =
  land already reached by today's high tide, gold = dry), then overlays
  contour lines for the 2050 and 2100 threshold under all three of Low,
  Intermediate, and High scenarios (color = scenario, line style = year;
  Low is drawn last/on top since it sits closest to Intermediate and would
  otherwise get covered where they nearly coincide). Saves
  `output/linda_mar_elevation_map.png`.
- Design notes:
  - A direct two-color purple-to-gold blend produced a muddy brown
    transition band (linear RGB interpolation between near-complementary
    hues) — fixed by inserting a neutral cream midpoint, per the dataviz
    skill's rule that diverging scales need a neutral zero, not a third hue.
  - The raw 2 m DEM resolves individual curbs/driveways/yard grading in the
    developed West Linda Mar neighborhood, which made the High-2100 contour
    (3.76 m — close to that neighborhood's typical pad elevation) zigzag
    illegibly across small bumps. Fixed by Gaussian-smoothing the DEM
    (`scipy.ndimage.gaussian_filter`, sigma=6 px ≈ 12 m) before both display
    and contouring — appropriate for a screening-level map, not for anything
    needing survey precision.

### Comparison against USGS CoSMoS / Our Coast Our Future

Checked our simple bathtub thresholds against USGS's CoSMoS model
(what powers ourcoastourfuture.org) for a sanity check. They are **not
directly numerically comparable**, and CoSMoS should be read as the more
realistic/higher estimate:

- CoSMoS is a dynamic hydrodynamic + wave model (Delft3D/XBeach), not a
  static elevation threshold. Even its mildest "background/average
  conditions" scenario includes spring tide *and* wave setup/runup — so it
  will generally show water reaching further inland than our MHHW+SLR
  bathtub does, for the same SLR amount.
- CoSMoS models SLR increments of 0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5,
  3.0, and 5.0 m, each crossed with storm return periods (background,
  1-yr, 20-yr, 100-yr) — Pacifica/Linda Mar is specifically flagged by USGS
  as one of the most exposed open-coast cities in California to this
  modeling, because Linda Mar Beach itself provides little wave protection.
- Cross-checks that DO line up: Pacifica's own 2018 city Sea Level Rise
  Vulnerability Assessment used a worst-case 5.7 ft by 2100, and California's
  2024 OPC state guidance gives a 3–6.6 ft by 2100 range — our Intermediate
  (+2.99 ft above today's tide) to High (+6.42 ft) span brackets that range
  reasonably well.
- We attempted to pull actual CoSMoS flood-hazard rasters for San Mateo
  County from USGS ScienceBase (they exist, at the same SLR-increment
  granularity, and would allow a real pixel-for-pixel overlay) but
  ScienceBase's API was unresponsive/timing out from this environment.
  Revisit if a rigorous quantitative comparison is wanted — either retry
  the ScienceBase download (search "CoSMoS v3.1 flood hazard average
  conditions San Mateo County"), or use `claude-in-chrome` to read specific
  scenario extents directly off the interactive map at ourcoastourfuture.org.

### Still open in Phase 2

- Bathtub model doesn't account for hydrological connectivity (e.g. water
  reaching contiguous low areas only) — could refine with a flood-fill
  from the ocean/creek rather than a flat elevation threshold.
- A rigorous quantitative comparison against CoSMoS/OCOF flood extents is
  still open (see above).

## Phase 3 — Shoreline change at Linda Mar (in progress)

Goal: find out whether Linda Mar Beach itself has been advancing or
retreating over the past few decades, using **CoastSat**
(https://github.com/kvos/CoastSat, Vos et al. 2019), an open-source tool
that extracts shoreline position from 40+ years of public Landsat/Sentinel-2
satellite imagery via Google Earth Engine (GEE), then measures cross-shore
distance along user-defined transects over time — the same kind of
trend-over-time analysis as Phase 1, but for beach width instead of sea
level.

### Environment (separate from the project's `.venv`)

CoastSat needs GDAL, which is unreliable to install via plain `pip` on
Windows (the same issue we avoided in Phase 2 by using `tifffile` instead
of `rasterio`). Its own instructions use conda/mamba instead, pinned to
**Python 3.11** — a different toolchain from this project's `.venv`
(Python 3.14), so it lives in its own conda environment rather than being
merged in.

- Installed **Miniforge** (conda/mamba) via `winget install --id
  CondaForge.Miniforge3`. Installed to `C:\Users\schif\Miniforge3`; **not**
  added to system PATH by the installer, and a fresh PowerShell process
  doesn't inherit PATH changes made by an earlier one anyway — so every
  command needs either the full path to the executable, or to prepend PATH
  manually first:
  ```powershell
  $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')
  ```
- Created a `coastsat` conda environment (Python 3.11):
  ```
  C:\Users\schif\Miniforge3\condabin\mamba.bat create -n coastsat python=3.11 geopandas gdal -y
  C:\Users\schif\Miniforge3\condabin\mamba.bat install -n coastsat earthengine-api scikit-image matplotlib astropy notebook pyyaml -y
  C:\Users\schif\Miniforge3\envs\coastsat\python.exe -m pip install pyqt5 imageio-ffmpeg
  ```
- **Gotcha**: importing `osgeo.gdal` fails with `DLL load failed... The
  specified procedure could not be found` unless the environment's
  `Library\bin` folder is on PATH (this is what `conda activate` normally
  does, but calling `envs\coastsat\python.exe` directly by full path
  bypasses that). Fix — prepend before running anything that touches GDAL:
  ```powershell
  $env:Path = "C:\Users\schif\Miniforge3\envs\coastsat\Library\bin;C:\Users\schif\Miniforge3\envs\coastsat;C:\Users\schif\Miniforge3\envs\coastsat\Scripts;" + $env:Path
  ```
- **Deliberately skipped**: `pyfes`, CoastSat's tidal-correction package.
  See "Tidal correction" below — this is a real limitation of the first
  pass, not an oversight.
- Cloned the actual toolkit (not on PyPI/conda — used by cloning the repo
  and importing its `coastsat` package directly) into `external/CoastSat/`:
  ```
  git clone https://github.com/kvos/CoastSat.git external/CoastSat
  ```
  `external/` is gitignored — treated as a vendored dependency, not project
  code, and it's multi-hundred-MB with its own git history, both bad fits
  for our repo. Re-clone any time; nothing local is customized in it.

### Still needed before it runs (blocked on the user)

CoastSat authenticates to Google Earth Engine as the user, not as this
session, so these steps need to be done by the user directly, the same
pattern as the earlier `gh auth login` step:

1. Free GEE account at https://signup.earthengine.google.com/
2. Install Google Cloud CLI, then `gcloud init` and `gcloud auth
   application-default login` to link a (free, non-commercial-tier) Google
   Cloud project.
3. Note the project ID (`gcloud config get-value project`) — passed into
   CoastSat's `SDS_download.authenticate_and_initialize(project_name)`.

### Tidal correction: intentionally skipped for the first pass

Where the shoreline appears to be on a given day is affected by the tide
level at the moment the satellite passed over, independent of any real
erosion/accretion — a satellite pass at high tide reads as a more landward
shoreline than one at low tide, purely from the tide. CoastSat can correct
for this using a global tide model (`pyfes`), but that package needs a
~10GB-RAM FES2022 tidal-constituents file we chose not to pull in for a
first pass.

**Practical effect**: the raw (uncorrected) shoreline time series will have
extra scatter from the tidal cycle layered on top of the real long-term
trend. With enough satellite passes spread across different tide states
over years, that noise should mostly average out of a *multi-year trend*
direction — but any single date-to-date comparison, or a short time window,
is not reliable evidence of erosion/accretion on its own. Add tidal
correction (`pyfes` + FES2022 data) before trusting short-term or
small-magnitude results.

### Data locations

- `external/CoastSat/` — the toolkit itself (gitignored, vendored)
- `coastsat_data/` — downloaded satellite imagery and extracted-shoreline
  outputs land here (gitignored — this is easily 100s of MB to GBs, and
  fully reproducible by re-running the download, so not committed)

### Not yet decided

- Exact region-of-interest polygon and transects for Linda Mar Beach.
- Whether to reuse a folium/leafmap-based interactive view (the original
  Phase 3 idea, before this session's shoreline-change scope) as a later
  way to explore the shoreline results, or keep it script/notebook-based.
