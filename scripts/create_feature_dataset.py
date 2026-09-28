from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import xy


# ============================================================
# S.I.H - GIS Feature Dataset Generator
# ============================================================

# Find the S.I.H project folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Input satellite raster
RASTER_FILE = PROJECT_ROOT / "data" / "raw" / "test_satellite.tif"

# Output folder
PROCESSED_FOLDER = PROJECT_ROOT / "data" / "processed"

# Output CSV
OUTPUT_FILE = PROCESSED_FOLDER / "satellite_features.csv"


def normalized_difference(band_a, band_b):
    """
    Calculate a normalized difference between two bands.

    Formula:
        (A - B) / (A + B)

    A small protection against division by zero is included.
    """

    denominator = band_a + band_b

    return np.divide(
        band_a - band_b,
        denominator,
        out=np.zeros_like(band_a, dtype=np.float32),
        where=denominator != 0
    )


def create_feature_dataset():
    """Convert raster pixels into an ML-ready CSV dataset."""

    print("Opening satellite raster...")
    print(f"Input: {RASTER_FILE}")
    print()

    with rasterio.open(RASTER_FILE) as src:

        # ----------------------------------------------------
        # Read all six bands
        # ----------------------------------------------------

        band1 = src.read(1).astype(np.float32)
        band2 = src.read(2).astype(np.float32)
        band3 = src.read(3).astype(np.float32)
        band4 = src.read(4).astype(np.float32)
        band5 = src.read(5).astype(np.float32)
        band6 = src.read(6).astype(np.float32)

        height = src.height
        width = src.width

        print(f"Image size: {width} x {height}")
        print(f"Total pixels: {width * height}")
        print()

        # ----------------------------------------------------
        # Calculate spectral features
        # ----------------------------------------------------

        feature1 = normalized_difference(band4, band3)
        feature2 = normalized_difference(band5, band4)
        feature3 = normalized_difference(band6, band5)

        # ----------------------------------------------------
        # Create pixel coordinate grid
        # ----------------------------------------------------

        rows, cols = np.indices((height, width))

        # Convert pixel positions into geographic coordinates
        xs, ys = rasterio.transform.xy(
            src.transform,
            rows,
            cols
        )

        longitude = np.array(xs)
        latitude = np.array(ys)

        # ----------------------------------------------------
        # Flatten everything
        # ----------------------------------------------------

        data = {
            "latitude": latitude.flatten(),
            "longitude": longitude.flatten(),

            "band_1": band1.flatten(),
            "band_2": band2.flatten(),
            "band_3": band3.flatten(),
            "band_4": band4.flatten(),
            "band_5": band5.flatten(),
            "band_6": band6.flatten(),

            "feature_1": feature1.flatten(),
            "feature_2": feature2.flatten(),
            "feature_3": feature3.flatten()
        }

        # ----------------------------------------------------
        # Create Pandas DataFrame
        # ----------------------------------------------------

        df = pd.DataFrame(data)

        # ----------------------------------------------------
        # Create output folder if necessary
        # ----------------------------------------------------

        PROCESSED_FOLDER.mkdir(
            parents=True,
            exist_ok=True
        )

        # ----------------------------------------------------
        # Save CSV
        # ----------------------------------------------------

        df.to_csv(
            OUTPUT_FILE,
            index=False
        )

        print("===== DATASET CREATED =====")
        print(f"Rows: {len(df)}")
        print(f"Columns: {len(df.columns)}")
        print()
        print("Columns:")
        
        for column in df.columns:
            print(f"  - {column}")

        print()
        print(f"Saved to:")
        print(OUTPUT_FILE)


# ============================================================
# Program entry point
# ============================================================

if __name__ == "__main__":

    if not RASTER_FILE.exists():

        print("ERROR: Satellite raster was not found.")
        print(f"Expected: {RASTER_FILE}")

    else:

        create_feature_dataset()