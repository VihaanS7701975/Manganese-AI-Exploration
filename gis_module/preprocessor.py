"""
Phase 2: Satellite Preprocessing Engine
Resamples 20m SWIR bands to 10m VNIR, applies SCL cloud masking,
and calculates diagnostic mineral spectral indices.
"""

import os
import glob
import numpy as np
import rasterio
from rasterio.enums import Resampling
from typing import Dict, Tuple

# Cloud classes in Sentinel-2 SCL band to mask out
# 0: NO_DATA, 1: SATURATED_OR_DEFECTIVE, 3: CLOUD_SHADOW, 8: CLOUD_MEDIUM_PROB, 9: CLOUD_HIGH_PROB, 10: THIN_CIRRUS
SCL_CLOUD_CLASSES = [0, 1, 3, 8, 9, 10]


def resample_band_to_reference(
    src_path: str,
    ref_profile: dict,
    resampling: Resampling = Resampling.bilinear
) -> np.ndarray:
    """
    Resamples a raster (e.g. 20m SWIR or SCL mask) to match the dimensions, CRS,
    and transform of the reference 10m VNIR band.
    """
    with rasterio.open(src_path) as src:
        data = src.read(
            1,
            out_shape=(ref_profile["height"], ref_profile["width"]),
            resampling=resampling,
        )
        return data.astype(np.float32)


def preprocess_scene(scene_dir: str, output_dir: str = "data/processed") -> Tuple[str, str]:
    """
    Processes all downloaded bands in a scene directory:
    - Aligns resolutions to 10m
    - Masks clouds using SCL
    - Computes NDVI, SWIR ratio (B12/B11), and Ferrous Index (B11/B8)
    - Exports a stacked .npy array and GeoTIFF for Person 2's ML pipeline
    """
    print(f"\n[*] Starting Preprocessing on Scene: {os.path.basename(scene_dir)}")
    os.makedirs(output_dir, exist_ok=True)
    scene_id = os.path.basename(scene_dir.rstrip("/\\"))

    # Reference 10m band (B04 - Red)
    ref_band_path = os.path.join(scene_dir, "B04.tif")
    if not os.path.exists(ref_band_path):
        raise FileNotFoundError(f"Reference band B04 not found in {scene_dir}")

    with rasterio.open(ref_band_path) as ref:
        ref_profile = ref.profile.copy()
        ref_crs = ref.crs
        ref_transform = ref.transform
        b4 = ref.read(1).astype(np.float32)

    print(f"[+] Spatial Reference Grid: {ref_profile['width']}x{ref_profile['height']} at 10m resolution (CRS: {ref_crs})")

    # Read 10m VNIR bands
    with rasterio.open(os.path.join(scene_dir, "B02.tif")) as src:
        b2 = src.read(1).astype(np.float32)
    with rasterio.open(os.path.join(scene_dir, "B03.tif")) as src:
        b3 = src.read(1).astype(np.float32)
    with rasterio.open(os.path.join(scene_dir, "B08.tif")) as src:
        b8 = src.read(1).astype(np.float32)

    # Resample 20m SWIR bands to 10m (bilinear)
    print("[+] Resampling B11 (SWIR-1) and B12 (SWIR-2) from 20m to 10m...")
    b11 = resample_band_to_reference(os.path.join(scene_dir, "B11.tif"), ref_profile, Resampling.bilinear)
    b12 = resample_band_to_reference(os.path.join(scene_dir, "B12.tif"), ref_profile, Resampling.bilinear)

    # Cloud Masking via SCL (nearest neighbor for categorical classes)
    scl_path = os.path.join(scene_dir, "SCL.tif")
    if os.path.exists(scl_path):
        print("[+] Resampling SCL mask and filtering cloud/shadow pixels...")
        scl = resample_band_to_reference(scl_path, ref_profile, Resampling.nearest)
        cloud_mask = np.isin(scl.astype(int), SCL_CLOUD_CLASSES)
    else:
        print("[!] SCL band not present; using threshold-based fallback masking.")
        cloud_mask = (b2 > 3000) & (b4 > 2500)

    # Calculate Mineral Spectral Indices (avoid zero-division)
    print("[+] Computing Diagnostic Manganese Indices (NDVI, SWIR Ratio, Ferrous)...")
    np.seterr(divide="ignore", invalid="ignore")
    
    ndvi = (b8 - b4) / (b8 + b4 + 1e-6)
    swir_ratio = b12 / (b11 + 1e-6)
    ferrous_index = b11 / (b8 + 1e-6)

    # Apply Cloud Mask: Set masked pixels to NaN
    for band_arr in [b2, b3, b4, b8, b11, b12, ndvi, swir_ratio, ferrous_index]:
        band_arr[cloud_mask] = np.nan

    # Stack into a 9-channel feature matrix:
    # [B02, B03, B04, B08, B11, B12, NDVI, SWIR_RATIO, FERROUS_INDEX]
    feature_stack = np.stack(
        [b2, b3, b4, b8, b11, b12, ndvi, swir_ratio, ferrous_index],
        axis=0
    )

    # 1. Save as NumPy array for Person 2's ML Model
    npy_path = os.path.join(output_dir, f"{scene_id}_features.npy")
    np.save(npy_path, feature_stack)
    print(f"[+] Feature matrix saved for Person 2 ML: {npy_path} (Shape: {feature_stack.shape})")

    # 2. Save as Multi-Band GeoTIFF for GIS / Person 1
    geotiff_path = os.path.join(output_dir, f"{scene_id}_preprocessed.tif")
    ref_profile.update(
        count=feature_stack.shape[0],
        dtype="float32",
        nodata=-9999.0
    )
    
    band_names = ["B02", "B03", "B04", "B08", "B11", "B12", "NDVI", "SWIR_RATIO", "FERROUS_INDEX"]
    # Replace NaN with -9999.0 for GeoTIFF nodata representation
    geotiff_data = np.nan_to_num(feature_stack, nan=-9999.0).astype(np.float32)

    with rasterio.open(geotiff_path, "w", **ref_profile) as dst:
        for idx in range(feature_stack.shape[0]):
            dst.write(geotiff_data[idx], idx + 1)
            dst.set_band_description(idx + 1, band_names[idx])
            
    print(f"[+] Aligned GeoTIFF exported: {geotiff_path}")

    return npy_path, geotiff_path


if __name__ == "__main__":
    # Automatically locate the most recently downloaded scene in data/raw
    raw_scenes = glob.glob("data/raw/*")
    if not raw_scenes:
        print("[!] No scenes found in data/raw. Run acquire_sentinel.py first.")
    else:
        latest_scene = max(raw_scenes, key=os.path.getctime)
        preprocess_scene(latest_scene)