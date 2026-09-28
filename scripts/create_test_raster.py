from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin


# ============================================================
# S.I.H - Test Satellite Raster Generator
# ============================================================

# Find the main S.I.H project folder
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Define the raw data folder
RAW_FOLDER = PROJECT_ROOT / "data" / "raw"

# Make sure the raw folder exists
RAW_FOLDER.mkdir(parents=True, exist_ok=True)

# Output GeoTIFF file
OUTPUT_FILE = RAW_FOLDER / "test_satellite.tif"


# ============================================================
# Create test satellite data
# ============================================================

WIDTH = 100
HEIGHT = 100
BANDS = 6

print("Creating test satellite raster...")
print(f"Output location: {OUTPUT_FILE}")


# Generate random values to simulate satellite bands
data = np.random.randint(
    0,
    10000,
    size=(BANDS, HEIGHT, WIDTH),
    dtype=np.uint16
)


# ============================================================
# Geographic information
# ============================================================

# Approximate starting location
transform = from_origin(
    85.0,       # longitude
    21.0,       # latitude
    0.001,      # pixel width
    0.001       # pixel height
)


# ============================================================
# GeoTIFF configuration
# ============================================================

profile = {
    "driver": "GTiff",
    "height": HEIGHT,
    "width": WIDTH,
    "count": BANDS,
    "dtype": "uint16",
    "crs": "EPSG:4326",
    "transform": transform
}


# ============================================================
# Write the GeoTIFF
# ============================================================

with rasterio.open(
    OUTPUT_FILE,
    "w",
    **profile
) as dst:

    dst.write(data)


# ============================================================
# Finished
# ============================================================

print()
print("SUCCESS!")
print("Test satellite raster created successfully.")
print(f"Location: {OUTPUT_FILE}")
print(f"Size: {WIDTH} x {HEIGHT}")
print(f"Bands: {BANDS}")