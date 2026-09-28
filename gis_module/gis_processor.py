from pathlib import Path

import numpy as np
import rasterio


# ============================================================
# S.I.H - GIS Spectral Feature Processor
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RASTER_FILE = PROJECT_ROOT / "data" / "raw" / "test_satellite.tif"


def calculate_normalized_difference(band_a, band_b):
    """
    Calculate a normalized difference between two bands.

    Formula:
        (Band A - Band B) / (Band A + Band B)

    A small value is added to the denominator to avoid
    division by zero.
    """

    denominator = band_a + band_b

    return np.divide(
        band_a - band_b,
        denominator,
        out=np.zeros_like(band_a, dtype=np.float32),
        where=denominator != 0
    )


def process_raster(file_path):
    """Read the raster and calculate spectral features."""

    print("Opening satellite raster...")
    print()

    with rasterio.open(file_path) as src:

        print("===== RASTER INFORMATION =====")
        print(f"Width: {src.width}")
        print(f"Height: {src.height}")
        print(f"Bands: {src.count}")
        print(f"Coordinate system: {src.crs}")

        # ----------------------------------------------------
        # Read six bands
        # ----------------------------------------------------

        band1 = src.read(1).astype(np.float32)
        band2 = src.read(2).astype(np.float32)
        band3 = src.read(3).astype(np.float32)
        band4 = src.read(4).astype(np.float32)
        band5 = src.read(5).astype(np.float32)
        band6 = src.read(6).astype(np.float32)

        print()
        print("===== SPECTRAL FEATURES =====")

        # ----------------------------------------------------
        # Calculate normalized differences
        # ----------------------------------------------------

        feature_1 = calculate_normalized_difference(
            band4,
            band3
        )

        feature_2 = calculate_normalized_difference(
            band5,
            band4
        )

        feature_3 = calculate_normalized_difference(
            band6,
            band5
        )

        # ----------------------------------------------------
        # Display statistics
        # ----------------------------------------------------

        features = {
            "Feature 1 (Band4-Band3)": feature_1,
            "Feature 2 (Band5-Band4)": feature_2,
            "Feature 3 (Band6-Band5)": feature_3
        }

        for name, feature in features.items():

            print()
            print(name)
            print(f"  Minimum: {feature.min():.4f}")
            print(f"  Maximum: {feature.max():.4f}")
            print(f"  Mean: {feature.mean():.4f}")


if __name__ == "__main__":

    if not RASTER_FILE.exists():

        print("ERROR: Satellite raster was not found.")
        print(f"Expected location: {RASTER_FILE}")

    else:

        process_raster(RASTER_FILE)