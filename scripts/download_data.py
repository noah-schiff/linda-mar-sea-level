"""Download PSMSL RLR monthly mean sea level data for a tide gauge station.

Usage:
    python scripts/download_data.py [station_id]

Defaults to station 10 (San Francisco). Saves to data/<station_id>.rlrdata.
"""

import sys
from pathlib import Path

import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def download_station(station_id: int) -> Path:
    url = f"https://psmsl.org/data/obtaining/rlr.monthly.data/{station_id}.rlrdata"
    out_path = DATA_DIR / f"{station_id}.rlrdata"

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    out_path.write_bytes(response.content)
    print(f"Saved {out_path} ({len(response.content)} bytes)")
    return out_path


if __name__ == "__main__":
    station = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    download_station(station)
