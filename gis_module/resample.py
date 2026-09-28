from pathlib import Path

import rasterio
from rasterio.enums import Resampling


# ============================================================
# S.I.H - Raster Resampling Module
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

INPUT_FILE = PROJECT_ROOT / "data" / "raw" / "test_satellite.tif"
OUTPUT_FILE = PROJECT_ROOT / "data" / "processed" / "resampled_test.tif"


def resample_raster(input_file, output_file, scale_factor=2):
    """
    Resample a raster to a different resolution.

    scale_factor = 2 means:
    100 x 100 → 200 x 200 pixels
    """

    with rasterio.open(input_file) as src:

        new_width = src.width * scale_factor
        new_height = src.height * scale_factor

        new_transform = src.transform * src.transform.scale(
            src.width / new_width,
            src.height / new_height
        )

        profile = src.profile.copy()

        profile.update({
            "width": new_width,
            "height": new_height,
            "transform": new_transform
        })

        with rasterio.open(output_file, "w", **profile) as dst:

            for band in range(1, src.count + 1):

                data = src.read(
                    band,
                    out_shape=(new_height, new_width),
                    resampling=Resampling.bilinear
                )

                dst.write(data, band)


if __name__ == "__main__":

    if not INPUT_FILE.exists():

        print("ERROR: Input raster not found.")
        print(INPUT_FILE)

    else:

        OUTPUT_FILE.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        print("Resampling satellite raster...")

        resample_raster(
            INPUT_FILE,
            OUTPUT_FILE
        )

        print()
        print("SUCCESS!")
        print(f"Input:  {INPUT_FILE}")
        print(f"Output: {OUTPUT_FILE}")