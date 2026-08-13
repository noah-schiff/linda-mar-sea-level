"""Plot the PSMSL RLR monthly mean sea level record for San Francisco (station 10).

Reads data/10.rlrdata (downloading it first if missing), computes a 12-month
rolling average, fits a linear trend using data from 1897 onward, and saves
the chart to output/sf_sea_level_trend.png.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from download_data import download_station

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "10.rlrdata"
OUTPUT_PATH = ROOT / "output" / "sf_sea_level_trend.png"
TREND_START_YEAR = 1897

# dataviz reference palette (references/palette.md): categorical slot 1 (blue)
# and slot 2 (orange), muted/ink tones for light-mode chrome.
COLOR_RAW = "#c3c2b7"        # muted baseline gray -- raw monthly noise
COLOR_SMOOTHED = "#2a78d6"   # series 1 blue -- 12-month rolling average
COLOR_TREND = "#eb6834"      # series 2 orange -- linear trend
COLOR_INK = "#0b0b0b"
COLOR_SECONDARY_INK = "#52514e"
COLOR_MUTED = "#898781"
COLOR_GRID = "#e1e0d9"
COLOR_SURFACE = "#fcfcfb"


def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        download_station(10)

    df = pd.read_csv(
        DATA_PATH,
        sep=";",
        header=None,
        names=["year", "height_mm", "missing_flag", "interpolated_flags"],
        skipinitialspace=True,
    )
    df["height_mm"] = df["height_mm"].where(df["height_mm"] != -99999, np.nan)
    return df


def fit_trend(df: pd.DataFrame, start_year: float) -> tuple[float, float, np.ndarray, np.ndarray]:
    """Fit a linear trend (mm per year) on data from start_year onward."""
    subset = df[(df["year"] >= start_year) & df["height_mm"].notna()]
    slope, intercept = np.polyfit(subset["year"], subset["height_mm"], 1)
    x_fit = np.array([start_year, df["year"].max()])
    y_fit = slope * x_fit + intercept
    return slope, intercept, x_fit, y_fit


def main() -> None:
    df = load_data()
    df["rolling_12mo"] = df["height_mm"].rolling(window=12, center=True, min_periods=12).mean()

    slope, intercept, trend_x, trend_y = fit_trend(df, TREND_START_YEAR)
    slope_per_century = slope * 100

    fig, ax = plt.subplots(figsize=(12, 6.5), dpi=150)
    fig.patch.set_facecolor(COLOR_SURFACE)
    ax.set_facecolor(COLOR_SURFACE)

    ax.plot(
        df["year"], df["height_mm"],
        color=COLOR_RAW, linewidth=0.8, alpha=0.8,
        label="Monthly mean", zorder=1,
    )
    ax.plot(
        df["year"], df["rolling_12mo"],
        color=COLOR_SMOOTHED, linewidth=1.8,
        label="12-month rolling average", zorder=2,
    )
    ax.plot(
        trend_x, trend_y,
        color=COLOR_TREND, linewidth=2, linestyle="--",
        label=f"Linear trend ({TREND_START_YEAR}–present): "
              f"{slope:.2f} mm/yr ({slope_per_century:.0f} mm/century)",
        zorder=3,
    )

    fig.suptitle(
        "Relative Sea Level at San Francisco, CA — PSMSL Station 10",
        fontsize=14, color=COLOR_INK, x=0.02, y=0.985, ha="left", fontweight="bold",
    )
    fig.text(
        0.02, 0.945,
        "Monthly mean sea level, RLR datum, 1854–present",
        fontsize=10, color=COLOR_SECONDARY_INK, ha="left",
    )

    ax.set_xlabel("Year", fontsize=10, color=COLOR_MUTED)
    ax.set_ylabel("Relative sea level (mm)", fontsize=10, color=COLOR_MUTED)
    ax.tick_params(colors=COLOR_MUTED, labelsize=9)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color(COLOR_MUTED)

    ax.grid(True, axis="y", color=COLOR_GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)

    legend = ax.legend(
        loc="upper left", frameon=False, fontsize=9.5, labelcolor=COLOR_SECONDARY_INK,
    )

    fig.tight_layout(rect=[0, 0, 1, 0.90])
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT_PATH, facecolor=COLOR_SURFACE)
    print(f"Saved chart to {OUTPUT_PATH}")
    print(f"Trend fit from {TREND_START_YEAR}: {slope:.3f} mm/yr "
          f"({slope_per_century:.1f} mm/century)")


if __name__ == "__main__":
    main()
