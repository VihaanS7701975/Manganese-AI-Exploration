from pathlib import Path


# ============================================================
# S.I.H - Sentinel-2 Satellite Processor
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DATA_FOLDER = PROJECT_ROOT / "data" / "raw"


# Sentinel-2 bands useful for our processing pipeline
SENTINEL_BANDS = {
    "B02": "Blue",
    "B03": "Green",
    "B04": "Red",
    "B05": "Red Edge 1",
    "B06": "Red Edge 2",
    "B07": "Red Edge 3",
    "B08": "NIR",
    "B8A": "Narrow NIR",
    "B11": "SWIR 1",
    "B12": "SWIR 2",
}


def show_sentinel2_bands():
    """Display the Sentinel-2 bands required by our pipeline."""

    print("===== SENTINEL-2 BAND CONFIGURATION =====")
    print()

    for band_code, band_name in SENTINEL_BANDS.items():
        print(f"{band_code}  →  {band_name}")

    print()
    print(f"Total bands configured: {len(SENTINEL_BANDS)}")


if __name__ == "__main__":
    show_sentinel2_bands()