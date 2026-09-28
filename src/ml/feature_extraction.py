"""
Build an ML-ready feature table from the processed Sentinel-2 GeoTIFFs in
data/processed/cleaned_images/.

For every pixel where valid_mask.tif == 1, computes:
  B02, B03, B04, B08, B11, B12 (reflectance)
  NDVI, NDWI, NDBI, BSI
  FE_OXIDE_ND, CLAY_MINERAL_ND, FERROUS_ND (see below)
  VIS_BRIGHTNESS (see below -- experimental, auxiliary only)
  longitude, latitude (EPSG:4326, from the pixel's UTM center)

FE_OXIDE_ND, CLAY_MINERAL_ND and FERROUS_ND are generic bare-surface /
iron-and-hydroxyl-mineral indicators adapted from published band-ratio
indices (Segal 1982; Abrams et al. 1983; Kaufmann 1988), expressed as
normalized differences for the same [-1, 1] scale and divide-by-zero
behaviour as NDVI/NDWI/NDBI/BSI. They characterize iron-oxide- and
clay-bearing exposed surfaces in general and are NOT a manganese-specific
signature or detector on their own — manganese identification requires
further (unsupervised) analysis on top of this feature table.

VIS_BRIGHTNESS = mean(B02, B03, B04) is an EXPERIMENTAL auxiliary feature,
added for offline analysis only. Low reflectance/brightness can be
associated with Fe-Mn mineralized surfaces, but this feature is NOT
manganese-specific and is affected by vegetation, water, shadows, dark
soil, illumination and other surface conditions. It is deliberately NOT
consumed by anomaly_detection.py (whose FEATURE_COLUMNS list is a fixed,
explicit enumeration that does not include it) or by mineralization_scoring.py
(which loads ml_features.csv via a fixed `usecols` list that does not
include it either) -- adding this column here does not change either
stage's behavior or output.

Reads in row chunks and appends only valid rows to the CSV, so the full
10980x10980 grid (only ~0.76% valid) is never materialized as one DataFrame.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.warp import transform as warp_transform
from rasterio.windows import Window

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_DIR = PROJECT_ROOT / "data" / "processed" / "cleaned_images"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "ml_features.csv"

BANDS = ["B02", "B03", "B04", "B08", "B11", "B12"]
CHUNK_ROWS = 512


def parse_args() -> argparse.Namespace:
    """--input-dir/--output let a separate AOI (e.g. Chennai) be run through
    this stage without touching the T45QUE data. Both default to the
    existing hardcoded paths, so running with no flags is unchanged."""
    parser = argparse.ArgumentParser(
        description="Build an ML-ready feature table from cleaned Sentinel-2 GeoTIFFs."
    )
    parser.add_argument(
        "--input-dir", type=Path, default=IN_DIR,
        help=f"Folder with the cleaned band GeoTIFFs + valid_mask.tif (default: {IN_DIR})",
    )
    parser.add_argument(
        "--output", type=Path, default=OUT_PATH,
        help=f"Path to write ml_features.csv (default: {OUT_PATH})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    in_dir = args.input_dir
    out_path = args.output

    band_paths = {b: in_dir / f"{b}.tif" for b in BANDS}
    mask_path = in_dir / "valid_mask.tif"

    for p in list(band_paths.values()) + [mask_path]:
        if not p.is_file():
            raise FileNotFoundError(f"Required input file not found: {p}")

    srcs = {b: rasterio.open(p) for b, p in band_paths.items()}
    mask_src = rasterio.open(mask_path)

    ref = srcs["B02"]
    height, width, transform, crs = ref.height, ref.width, ref.transform, ref.crs

    for name, src in {**srcs, "valid_mask": mask_src}.items():
        if (src.height, src.width) != (height, width) or src.transform != transform or src.crs != crs:
            raise ValueError(f"{name} grid does not match the B02 reference grid")

    a, b_, c, d, e, f = transform.a, transform.b, transform.c, transform.d, transform.e, transform.f

    columns = ["longitude", "latitude"] + BANDS + [
        "NDVI", "NDWI", "NDBI", "BSI",
        "FE_OXIDE_ND", "CLAY_MINERAL_ND", "FERROUS_ND",
        "VIS_BRIGHTNESS",
    ]
    total_valid = 0
    wrote_header = False

    for row0 in range(0, height, CHUNK_ROWS):
        rows = min(CHUNK_ROWS, height - row0)
        window = Window(0, row0, width, rows)

        mask = mask_src.read(1, window=window).astype(bool)
        if not mask.any():
            continue

        b02 = srcs["B02"].read(1, window=window)
        b03 = srcs["B03"].read(1, window=window)
        b04 = srcs["B04"].read(1, window=window)
        b08 = srcs["B08"].read(1, window=window)
        b11 = srcs["B11"].read(1, window=window)
        b12 = srcs["B12"].read(1, window=window)

        with np.errstate(divide="ignore", invalid="ignore"):
            ndvi = (b08 - b04) / (b08 + b04)
            ndwi = (b03 - b08) / (b03 + b08)
            ndbi = (b11 - b08) / (b11 + b08)
            bsi = ((b11 + b04) - (b08 + b02)) / ((b11 + b04) + (b08 + b02))

            # Generic iron-/hydroxyl-mineral indicators for bare surfaces
            # (not manganese-specific — see module docstring).
            fe_oxide_nd = (b04 - b02) / (b04 + b02)
            clay_mineral_nd = (b11 - b12) / (b11 + b12)
            ferrous_nd = (b12 - b08) / (b12 + b08)

            # VIS_BRIGHTNESS -- experimental auxiliary feature (mean visible
            # reflectance, B02/B03/B04). Low reflectance/brightness can be
            # associated with Fe-Mn mineralized surfaces, but this feature is
            # NOT manganese-specific and is affected by vegetation, water,
            # shadows, dark soil, illumination and other surface conditions.
            # Not part of anomaly_detection.py's or mineralization_scoring.py's
            # feature sets (both select columns by an explicit fixed list, so
            # adding this column here does not change either stage's output).
            vis_brightness = (b02 + b03 + b04) / 3.0

        valid = mask
        for arr in (
            b02, b03, b04, b08, b11, b12,
            ndvi, ndwi, ndbi, bsi,
            fe_oxide_nd, clay_mineral_nd, ferrous_nd,
            vis_brightness,
        ):
            valid &= np.isfinite(arr)

        if not valid.any():
            continue

        rr, cc = np.nonzero(valid)
        col_centers = cc + 0.5
        row_centers = rr + row0 + 0.5
        xs = a * col_centers + b_ * row_centers + c
        ys = d * col_centers + e * row_centers + f
        lon, lat = warp_transform(crs, "EPSG:4326", xs, ys)

        chunk_df = pd.DataFrame({
            "longitude": lon,
            "latitude": lat,
            "B02": b02[valid],
            "B03": b03[valid],
            "B04": b04[valid],
            "B08": b08[valid],
            "B11": b11[valid],
            "B12": b12[valid],
            "NDVI": ndvi[valid],
            "NDWI": ndwi[valid],
            "NDBI": ndbi[valid],
            "BSI": bsi[valid],
            "FE_OXIDE_ND": fe_oxide_nd[valid],
            "CLAY_MINERAL_ND": clay_mineral_nd[valid],
            "FERROUS_ND": ferrous_nd[valid],
            "VIS_BRIGHTNESS": vis_brightness[valid],
        })

        chunk_df.to_csv(out_path, mode="w" if not wrote_header else "a", header=not wrote_header, index=False)
        wrote_header = True
        total_valid += len(chunk_df)

    for src in srcs.values():
        src.close()
    mask_src.close()

    if not wrote_header:
        pd.DataFrame(columns=columns).to_csv(out_path, index=False)

    print(f"Valid pixels: {total_valid}")
    print(f"CSV path: {out_path}")
    print(f"CSV columns: {columns}")
    print(f"Rows: {total_valid}")


if __name__ == "__main__":
    main()
