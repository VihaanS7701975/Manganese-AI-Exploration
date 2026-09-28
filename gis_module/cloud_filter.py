from pathlib import Path

import numpy as np
import rasterio


# ============================================================
# S.I.H - Satellite Cloud / Invalid Pixel Filter
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "test_satellite.tif"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "filtered_test.tif"


def create_test_cloud_mask(height, width):
    """
    Create a simple test mask.

    True  = valid pixel
    False = invalid/cloud pixel

    IMPORTANT:
    This is only for testing. Real Sentinel-2 processing
    will use the SCL layer instead.
    """

    mask = np.ones((height, width), dtype=bool)

    # Create a small artificial "cloud" region
    mask[20:40, 20:40] = False

    return mask


def filter_raster(input_file, output_file):
    """Remove invalid pixels from a test raster."""

    with rasterio.open(input_file) as src:

        data = src.read()

        height = src.height
        width = src.width

        # Create our temporary test mask
        valid_mask = create_test_cloud_mask(
            height,
            width
        )

        # Count valid and invalid pixels
        total_pixels = height * width
        invalid_pixels = np.count_nonzero(~valid_mask)
        valid_pixels = np.count_nonzero(valid_mask)

        # Convert mask for broadcasting across all bands
        invalid_mask = ~valid_mask

        # Set invalid pixels to zero
        data[:, invalid_mask] = 0

        # Copy original raster metadata
        profile = src.profile.copy()

        # Write filtered raster
        with rasterio.open(
            output_file,
            "w",
            **profile
        ) as dst:

            dst.write(data)

    print("===== CLOUD / INVALID PIXEL FILTER =====")
    print(f"Total pixels:   {total_pixels}")
    print(f"Valid pixels:   {valid_pixels}")
    print(f"Invalid pixels: {invalid_pixels}")
    print()
    print("SUCCESS!")
    print(f"Filtered raster saved to:")
    print(output_file)


if __name__ == "__main__":

    if not INPUT_FILE.exists():

        print("ERROR: Input raster not found.")
        print(INPUT_FILE)

    else:

        OUTPUT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        filter_raster(
            INPUT_FILE,
            OUTPUT_FILE
        )