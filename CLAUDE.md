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

### Running CoastSat scripts: two hard rules

1. **Always `conda activate coastsat` first**, in a normal (non-sandboxed)
   terminal window. Don't call `envs\coastsat\python.exe` by full path
   without activating — GDAL's DLLs live in that env's `Library\bin`, and
   only proper activation reliably puts that on PATH (see GDAL gotcha
   above; this was traced back to `conda init powershell` never having
   been run — fixed once, via `condabin\conda.bat init powershell`, but
   worth restating the rule since calling the interpreter by full path is
   an easy habit to fall back into and silently breaks GDAL again).
2. **Any interactive/credential-prompting command (browser logins, OAuth,
   anything that opens a browser or waits on a local network callback)
   must be run by the user directly, in their own terminal — not through
   the assistant's own tool calls, and not proxied through `!` if it can
   be avoided either.** Root-caused during GEE setup (see below): the
   assistant's own shell tool runs in a network-sandboxed context, so a
   local OAuth callback server bound inside it (`localhost:8085`) is not
   reachable by the browser on the user's real desktop — the browser
   completes Google's consent screen fine, but the final redirect has
   nowhere real to land, and the process hangs forever waiting for a
   callback that can't arrive. Running the identical script in the user's
   own terminal works immediately, because the local server and the
   browser are then in the same real network namespace.

### Google Earth Engine authentication — how it was actually resolved

This took multiple failed attempts and is worth recording in detail so it
isn't re-debugged from scratch:

- Account: free GEE signup at https://signup.earthengine.google.com/,
  registered to Google Cloud project `linda-mar-coastsat`.
- `gcloud` CLI installed (`winget install --id Google.CloudSDK`), then
  user ran `gcloud init` themselves (needs their own login).
- **`Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
  was required** before `gcloud init` would run at all — Windows blocks
  gcloud's PowerShell wrapper scripts by default.
- **`ee.Authenticate(auth_mode='gcloud')` (and plain `ee.Authenticate()`
  with no arguments, which auto-selects `'gcloud'` mode whenever gcloud is
  installed — see `ee/oauth.py`'s `authenticate()`) both fail with "This
  app is blocked."** Root cause, confirmed by reading `ee/oauth.py`
  directly: both delegate to `gcloud auth application-default login`
  using gcloud's own shared/generic OAuth client (the same client ID
  every `gcloud auth application-default login` on every machine uses,
  `764086051850-...`), and Google has restricted that specific shared
  client from being granted the Drive scope `ee.Authenticate()` requests
  by default (the tool even prints a warning about this beforehand: "The
  following scopes will be blocked soon for the default client ID").
  This is **not** fixable via the OAuth consent screen's test-user list —
  the user doesn't own or control that client, Google does. Verified this
  wasn't a project-registration or API-enablement problem first, by
  calling the Earth Engine REST API directly with a plain `gcloud
  auth print-access-token` token and confirming it got past
  authentication into normal request handling.
- **Fix**: force `ee.Authenticate(auth_mode='localhost')` explicitly. This
  skips the gcloud-delegation branch entirely and uses Earth Engine's own
  dedicated, already Google-verified OAuth client (a distinct `CLIENT_ID`
  constant in `ee/oauth.py`, `517222506229-...`) via a short-lived local
  webserver on `localhost:8085`. This is the version now in
  `scripts/coastsat/authenticate_gee.py`.
- Combined with hard rule #2 above (must run in the user's own terminal),
  this succeeded: `Earth Engine authenticated and initialized for project:
  linda-mar-coastsat`, credentials cached at
  `~/.config/earthengine/credentials`.
- **This was one-time setup.** Now that a valid token is cached, ordinary
  future scripts should just call
  `SDS_download.authenticate_and_initialize('linda-mar-coastsat')` (which
  tries the existing token first) or plain
  `ee.Initialize(project='linda-mar-coastsat')` — no browser step, no
  terminal-vs-`!` distinction, unless the token expires or is revoked.

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
- `coastsat_data/` — downloaded satellite imagery and CoastSat's native
  `.pkl` output land here (gitignored — this is easily 100s of MB to GBs,
  and fully reproducible by re-running the download, so not committed)
- `data/coastsat_shorelines.geojson` — small, tracked in git: just the
  extracted shoreline geometries + dates (no imagery), written by
  `scripts/coastsat/extract_shorelines.py`
- `data/coastsat_reference_shoreline.npy` — reference coastline built from
  the Phase 2 DEM (see below), tracked in git (small, ~100KB)

### Region of interest and first validation batch (done)

- ROI: a tight rectangle in WGS84 lon/lat around the sandy beach and surf
  zone (`scripts/coastsat/download_imagery.py`'s `polygon`), lon -122.5205
  to -122.5025, lat 37.5785 to 37.6015 — spans the full ~2.5 km of coast
  from the beach itself up through the rockier point immediately north of
  it (turns out this ROI extends further north than just the sand beach —
  relevant below).
- First batch pulled: Sentinel-2 only, 2023-01-01 to 2025-01-01 (129
  images, ~2 years) — a deliberately small/fast validation run before
  committing to the full historical pull. All images landed in
  `coastsat_data/LINDAMAR/S2/`.
- `scripts/coastsat/extract_shorelines.py` runs CoastSat's automated
  (non-interactive) shoreline detection on downloaded imagery — reads
  `metadata` via `SDS_download.get_metadata(inputs)`, does not
  re-download anything.
  - **Gotcha**: `SDS_shoreline.py` locates its ML classifier models via
    `os.path.join(os.getcwd(), 'classification', 'models')` — i.e. it
    assumes CoastSat's own repo directory is the current working
    directory, not a path relative to the `coastsat` package. Our script
    calls `os.chdir(COASTSAT_DIR)` right after imports to handle this
    (our own file outputs all use absolute paths, so this is safe).
- 56/129 images produced a shoreline (the rest filtered by cloud
  cover/quality — normal for coastal Northern California's frequent fog).

### Reference shoreline — built from the Phase 2 DEM, not hand-digitized

CoastSat's normal way to reject spurious detections is a hand-digitized
`reference_shoreline` (an interactive click tool) that constrains
detection to a buffer (`max_dist_ref`, meters) around a known coastline.
Instead, `scripts/coastsat/build_reference_shoreline.py` derives one
programmatically from `data/linda_mar_dem.tif`: extracts the MHHW
elevation contour (same 1.798 m NAVD88 reference as all of Phase 2) with
`skimage.measure.find_contours`, and saves it as
`data/coastsat_reference_shoreline.npy` for `extract_shorelines.py` to
load into `settings['reference_shoreline']` (`max_dist_ref = 100`).

**Gotcha**: the coastline splits into multiple *disconnected* contour
pieces at this elevation (6 pieces total; the sandy beach and the rockier
point north of it are two separate pieces, not one continuous line) — an
earlier version of the script picked only the single contour with the
most points inside the ROI, which kept the rocky-point piece (2585
points, 56% in-ROI) but silently dropped the *separate* beach piece (1272
points, 97% in-ROI!) since it had fewer total points. Fixed by combining
every contour piece with meaningful ROI overlap (`>20` points or `>30%`
inside the ROI bbox), not just the single best one.

### Validating the extraction — and a second, sneakier geometry bug

First unconstrained run (no reference shoreline) produced 56 shorelines
that mostly traced the real coast well, but with obvious spurious
diagonal lines cutting straight across the ROI and messy squiggles
through the inland marsh/neighborhood — likely fog/cloud-contaminated
Sentinel-2 passes producing false whole-image splits. Plotted with
`scripts/plot_shoreline_validation.py` (runs in the project's `.venv`,
not the `coastsat` env — reads the GeoJSON with plain `json`, no
geopandas needed, just to overlay on the Phase 2 elevation basemap).

Adding the reference shoreline (`max_dist_ref=100m`) fixed most of it, but
a few diagonal spikes remained. A per-*point* distance filter
(`filter_points_near_reference`, tighter 50 m threshold, in
`extract_shorelines.py`) dropped 1279 stray points but **did not remove
the remaining diagonal spikes at all** — because both endpoints of each
spike were individually near real coastline (one end near the south beach,
one end near the north point), just not near *each other*. The actual bug:
`SDS_tools.output_to_gdf(output, 'lines')` builds one `LineString` per
date by connecting *every point in array order* with no gap check —
CoastSat's contour tracer can return several genuinely disconnected
coastline pieces for one image, concatenated into a single array, and
naively connecting them draws a spurious straight "connector" segment
between two otherwise-valid detections. Fixed with our own
`output_to_gdf_split_on_gaps()` in `extract_shorelines.py`, which splits
each date's points into separate `LineString`s (emitted as a
`MultiLineString`) wherever the gap between consecutive points exceeds
50 m — real traced contour points are normally a few meters apart at
most, so a multi-hundred-meter jump is unambiguously an artifact, not a
real traced edge.

**Net effect of both fixes**: `output/coastsat_shoreline_validation.png`
went from a mix of good coastal traces + spurious diagonal streaks +
inland marsh noise, to all 56 shorelines tracing tightly and continuously
along the real coastline with no artifacts. This 3-piece pipeline
(reference-shoreline-constrained extraction → per-point distance filter →
gap-split geometry) is now the standard path in `extract_shorelines.py`.

### Full historical pull (done)

Validated pipeline confirmed to generalize correctly beyond the Sentinel-2
validation batch, run on the complete historical record:

- `download_imagery.py` extended from the 2-year/S2-only validation batch
  to `dates = ['1984-01-01', '2026-08-13']`, `sat_list = ['L5','L7','L8',
  'L9','S2']` — same `sitename`, so `retrieve_images()` skipped the 129
  already-downloaded S2 validation images rather than re-fetching them.
- 2,736 images downloaded (637 L5, 813 L7, 449 L8, 127 L9, 710 S2 total)
  — **1.23 GB on disk**, all in gitignored `coastsat_data/`. Took roughly
  1.5–2 hours.
  - Storage estimate method (in case a similar sizing question comes up
    for a different ROI/date range): ~0.58 MB/image for Sentinel-2,
    ~0.47 MB/image for Landsat (all 4 Landsat missions treated at the same
    15 m pixel size by CoastSat, per `SDS_shoreline.py`) — measured from
    actual downloaded files, not a generic guess.
- Final `extract_shorelines.py` run (same reference-shoreline +
  point-filter + gap-split pipeline as the validation batch, no code
  changes needed) on the complete set: **1,051 clean shorelines**, 1984-05-02
  to 2026-08-03, across all 5 satellites — visually confirmed clean (no
  diagonal-spike or marsh-noise artifacts) in
  `output/coastsat_shoreline_validation.png`.
- Runtime note: extraction over the full ~2,700 images took several
  minutes with no visible per-image progress output during the "Mapping
  shorelines" step (unlike the download step, which does print a running
  %) — don't mistake this for a hang; let it run.

### Transects and the final trend (done)

- `scripts/coastsat/define_transects.py` — derives shore-normal transects
  programmatically (not CoastSat's normal interactive click-tool) from the
  same MHHW DEM contour used for the reference shoreline. Isolates the
  sandy-beach contour piece specifically (same highest-in-ROI-fraction
  selection logic as `build_reference_shoreline.py`), then places transects
  every 100 m along it, saving `data/coastsat_transects.geojson` (16
  transects) and `output/coastsat_transects_map.png` for visual QA.
  - **Gotcha, and the fix**: a per-transect local tangent (finite
    difference over a small window, even after Gaussian-smoothing the DEM
    the same way `plot_elevation_map.py` does) was too sensitive to
    meter-scale wiggle in the traced beach edge — individual transects
    ended up rotated tens of degrees apart and crossing each other instead
    of fanning out cleanly, visually obvious in the QA plot. Fixed by
    recognizing Linda Mar Beach is close to a straight line over the
    transect-placement range (confirmed via PCA: long-axis/short-axis
    ratio ~11:1) and fitting **one global shore-normal direction** for the
    whole beach, reused for every transect — only the alongshore origin
    differs per transect. This is standard practice for a fairly straight
    beach and matches how CoastSat's own examples look when a person draws
    transects by eye.
  - Seaward direction (which of the two normal directions to use) is
    picked automatically, not assumed from geometry: sample DEM elevation
    30 m to each side of the beach midpoint and take whichever side is
    lower (open coast here has no missing/NaN elevation data — the DEM's
    minimum is ~-17 m, clearly water/nearshore seafloor).
  - Each transect: origin 50 m landward of the MHHW point, extending 450 m
    seaward — generous enough to hold the full historical range of
    detected shoreline positions (including low-tide passes) without
    clipping.
- `scripts/coastsat/compute_transect_timeseries.py` — loads the raw
  CoastSat output already saved by `extract_shorelines.py`
  (`coastsat_data/LINDAMAR/LINDAMAR_output.pkl`, not re-extracted), applies
  the same cleanup already used for the shoreline geojson (duplicate/
  inaccurate-georef removal, then `filter_points_near_reference` — reused
  directly from `extract_shorelines.py`, not reimplemented), then uses
  CoastSat's `SDS_transects.compute_intersection_QC` (same QC settings as
  CoastSat's own `example.py`: `along_dist=25`, `min_points=3`,
  `max_std=15`, `max_range=30`, `min_chainage=-100`, `multiple_inter='auto'`)
  to measure cross-shore distance along each transect for every image date.
  Saves `data/coastsat_transect_timeseries.csv` (small, tracked in git).
- `scripts/plot_transect_trend.py` — runs in the project's regular `.venv`
  (like `plot_shoreline_validation.py`, needs no geopandas since it reads
  the transects geojson with plain `json`). Fits a linear trend per
  transect and one overall alongshore-mean trend, and plots both: a map of
  transects colored by trend (red=retreating, green=advancing) next to the
  alongshore-mean cross-shore-distance time series with its trend line.
  Saves `output/coastsat_transect_trend.png`.

**Result**: 15 of 16 transects show a positive (seaward/accreting) trend,
one is flat; the alongshore-mean trend is **+0.131 m/yr, p=0.001** (linear
regression, n=958 dates, 1984–2026) — Linda Mar Beach has been slightly
**advancing**, not retreating, over the full CoastSat record. Note the
scale: individual detections scatter roughly ±50 m around the mean (visible
in `coastsat_transect_trend.png`) — mostly seasonal/storm beach-width
cycling and uncorrected tidal noise (see below), dwarfing the ~0.13 m/yr
trend itself. The trend is statistically significant but the *practical*
takeaway is "no evidence of erosion," not "measurable steady accretion" —
consistent with Linda Mar being a sediment-fed pocket beach (San Pedro
Creek outlet) rather than one of the more erosion-prone open stretches of
Pacifica.

## Phase 4 — Interactive three.js site (done)

`site/` is a static, rotatable 3D model of the terrain with two time controls.
**Terrain is present-day only and never changes** — only the water level and
the shoreline positions do.

- `scripts/build_site.py` → `site/data/*` (Int16 binaries + JSON) and vendors
  three.js into `site/vendor/`. `scripts/bundle_site.py` → `dist/` single-file
  bundles. `site/index.html`, `style.css`, `app.js` are hand-authored; only
  `site/data/` and `site/vendor/` are generated, so no markup lives in Python
  strings.
- Payload: terrain 891×614 Int16 centimetres (1.09 MB, 1 cm precision, covers
  the full −17.6…276.3 m range without clamping); shorelines 296k points
  quantised to Int16 over their own bbox (1.18 MB, 5.5 cm precision).
- Headline numbers come from `summary.json`, recomputed at build time from the
  same sources as `plot_summary.py`, so the site can't drift from the phases.
  Flood areas are computed from the **full-resolution** DEM, not the decimated
  display grid.
- The shoreline year slider draws that year's raw passes plus an annual line
  rebuilt from the 16 transect medians — the same numbers behind +0.131 m/yr.
  1989/1992/1999 cover only 11–15 of 16 transects; the line skips the missing
  ones and the panel says so.

### Why three.js rather than the Plotly prototype

An earlier Plotly version (`scripts/build_interactive.py`, now deleted) hit a
wall: Plotly can't recolour a 137k-point surface per slider step, so flooding
had to be read off a translucent plane seen edge-on, and the 276 m hills forced
an ugly terrain cap. In three.js the terrain material is patched via
`onBeforeCompile` with a `uWaterLevel` uniform that tints submerged fragments,
so flood extent reads from **any** camera angle and the terrain keeps its full
height. Keeping both stacks wasn't worth it.

### Gotchas worth not re-deriving

- **`[hidden]` loses to an author `display` rule.** `.loading`/`.fatal` are
  `display:grid`, which beats the UA stylesheet's `[hidden]{display:none}`, so
  both overlays rendered on top of a perfectly working scene and it looked like
  WebGL had failed. Fixed with an explicit `[hidden]{display:none!important}`.
- **Vertical exaggeration has a narrow usable band.** 276 m over a 3.5 km scene
  is a 0.08 ratio: flat at 1×, a sheer unreadable wall past ~4×. Default is
  2.5×, with a slider so the viewer decides.
- **The single-file bundle cannot use ES modules.** Two independent reasons,
  both found the hard way: a strict CSP (the Artifact sandbox) refuses a
  `data:`-URL importmap, so the app module never executed at all; and Chrome
  blocks module loading over `file://` on CORS grounds, so double-clicking
  would have failed too. `bundle_site.py` rewrites three.js's single trailing
  `export{...}` into a `window.THREE` assignment and converts everything to
  classic strict-mode IIFEs. `site/` itself still uses normal ES modules — it
  is served over http, where they work fine.
- **Inlined data must not be fetched as `data:` URIs either.** Fetching a
  `data:` URL is governed by CSP `connect-src`, which strict hosts deny. The
  bundle instead decodes base64 in-process and hands back a synthetic
  `Response`, so the page makes zero network requests and `app.js` stays
  byte-identical between the hosted site and the bundle.
- **Diagnosing a blank artifact:** the loading overlay starts at "Starting…"
  and only says "Loading terrain…" once `app.js` runs. If it's stuck on
  "Starting…", the script never executed — a different bug from a slow fetch.
  That distinction is what isolated the importmap failure.
- Some shoreline points sit ~49 m west of the DEM's edge (open ocean), so the
  terrain sampler clamps to bounds; without it those vertices come back NaN and
  poison the buffer.

## Summary figure (all three phases)

`scripts/plot_summary.py` (project `.venv`) combines all three phases into
`output/linda_mar_summary.png`: a stat row with the three headline numbers,
then ① the Phase 1 sea level record, ② the Phase 3 shoreline position, and
③ the Phase 2 projected flood extent. All three numbers are recomputed from
the source data at render time (never hardcoded), so the figure can't drift
out of sync with the phase results.

Design decisions worth keeping (per the `dataviz` skill):

- **Panel order follows the argument, not the phase numbering.** The two
  *observed* histories stack on the left (sea level rising, beach holding)
  and the *projection* they lead to takes the tall right-hand panel — so
  reading order and narrative order match. An earlier draft had the map on
  the left as ②, which made the eye jump ②→①→③.
- **Shared visual grammar across both time-series panels**, so the reader
  learns it once: muted gray = raw noisy observations, blue (categorical
  slot 1) = the smoothed signal (12-month rolling average / annual median),
  orange (slot 2) = the fitted linear trend.
- **Flood extent is drawn as filled nested zones, not contour lines.** The
  first draft reused Phase 2's contour-lines-over-a-purple/gold-diverging-
  basemap approach, and at summary-figure size the three lines were nearly
  coincident and essentially unreadable. Flood extent is an *area*, so it
  gets area fills; the terrain underneath drops to a recessive light-gray
  ramp so the only loud thing on the map is the water. The Phase 2
  deliverable keeps its LSU purple/gold scale — there the color *is* the
  data (elevation itself), which is a different job.
- **The flood zones use a one-hue ordinal blue ramp** (darkest = already wet
  today, lightest = only under High-2100), because the thresholds are
  genuinely ordered — not three arbitrary categorical hues as in the
  Phase 2 map.
- **Palettes were validated, not eyeballed** — `scripts/validate_palette.py`
  (run it: `.\.venv\Scripts\python.exe scripts\validate_palette.py`). Node
  isn't installed on this machine, so the `dataviz` skill's
  `validate_palette.js` checks were ported to Python; the port self-tests
  against the reference values documented in the skill's own `palette.md`
  (adjacent CVD ΔE 9.1 / normal-vision 19.6 for the shipped 8-slot order)
  and aborts if it ever stops reproducing them, so a silently-drifted port
  can't quietly bless a bad palette. Results: the blue/orange series pair
  passes every categorical check (CVD ΔE 24.7, normal-vision 33.6, both
  ≥ 3:1 contrast); the blue flood ramp passes the ordinal checks (monotone
  lightness, step gaps ≥ 0.06, light end 2.06:1, hue spread 3°).
  Note the ordinal ramp must be checked with the *ordinal* checks — a
  correct one-hue ramp fails the categorical lightness-band and chroma
  gates by design, since it's built to span lightness and go pale at one end.
- **Shoreline panel y-axis is capped at ±50 m**, which excludes 5 of 958
  passes — stated on the panel itself rather than silently dropped, since
  letting those outliers set the scale flattened the signal.
- **Stat tile ③ is labeled "vs. 2000 baseline", not "above today's MHHW"** —
  the NOAA scenario values are relative to a year-2000 baseline (see Phase 2
  above), and the map legend carries the unambiguous absolute NAVD88
  elevations that rise implies.

### Not yet decided

- Whether to reuse a folium/leafmap-based interactive view (the original
  Phase 3 idea, before this session's shoreline-change scope) as a later
  way to explore the shoreline results, or keep it script/notebook-based.
- Tidal correction (`pyfes` + FES2022, still intentionally skipped — see
  above) would tighten the scatter in the time series and could sharpen
  the trend estimate, but is unlikely to reverse its sign given how
  consistent the direction is across 15/16 independent transects.
