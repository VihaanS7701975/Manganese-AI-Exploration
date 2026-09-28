"""
Phase 3: Automated Satellite Acquisition & Preprocessing Pipeline
Chains Planetary Computer STAC search, multi-spectral band downloading,
cloud masking, resolution alignment, and diagnostic mineral feature extraction.
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

# Ensure project root is in sys.path for cross-module imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from scripts.acquire_sentinel import search_sentinel_scene, download_bands_for_scene
    from gis_module.preprocessor import preprocess_scene
except ImportError:
    # Support direct relative path execution
    sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))
    sys.path.append(os.path.dirname(__file__))
    from acquire_sentinel import search_sentinel_scene, download_bands_for_scene
    from preprocessor import preprocess_scene


def run_pipeline(
    bbox: List[float],
    date_range: str = "2024-01-01/2024-05-30",
    max_cloud: int = 15,
    raw_dir: str = "data/raw",
    processed_dir: str = "data/processed"
) -> Dict[str, Any]:
    """
    Automated end-to-end satellite data pipeline:
    1. Queries Planetary Computer STAC API to find the optimal Sentinel-2 Level-2A scene.
    2. Downloads required VNIR, SWIR, and SCL cloud mask bands.
    3. Aligns resolutions to 10m, masks cloud/shadows, and generates mineral spectral indices.
    4. Exports .npy feature matrix and 9-band GeoTIFF.
    5. Returns processed artifact paths and complete scene metadata.

    Args:
        bbox: Geographic bounding box [min_lon, min_lat, max_lon, max_lat]
        date_range: Datetime range ISO string (e.g. '2024-01-01/2024-05-30')
        max_cloud: Maximum cloud cover percentage (default: 15)
        raw_dir: Directory to save downloaded raw bands
        processed_dir: Directory to save preprocessed matrices & GeoTIFFs

    Returns:
        Dictionary containing scene metadata, band filepaths, and processed artifact paths.
    """
    print(f"============================================================")
    print(f"[*] Starting Automated Satellite Pipeline")
    print(f"    AOI Bounding Box : {bbox}")
    print(f"    Date Range       : {date_range}")
    print(f"    Max Cloud Cover  : {max_cloud}%")
    print(f"============================================================")

    # 1. Search STAC Catalog for optimal scene
    scene_item = search_sentinel_scene(
        bbox=bbox,
        date_range=date_range,
        max_cloud_cover=max_cloud
    )

    if not scene_item:
        raise RuntimeError(f"No Sentinel-2 scene could be retrieved for bbox: {bbox}")

    scene_id = scene_item.id
    acq_date = scene_item.datetime.strftime("%Y-%m-%d") if hasattr(scene_item, "datetime") else "unknown"
    cloud_cover = scene_item.properties.get("eo:cloud_cover", 0.0)

    # 2. Download VNIR/SWIR bands + SCL mask
    print(f"\n[*] Downloading bands for scene {scene_id}...")
    downloaded_paths = download_bands_for_scene(scene_item, output_dir=raw_dir)

    scene_dir = os.path.join(raw_dir, scene_id)
    if not os.path.exists(scene_dir):
        # Fallback to directory of downloaded files
        scene_dir = os.path.dirname(list(downloaded_paths.values())[0])

    # 3. Preprocess Scene & Generate Alteration Features
    print(f"\n[*] Preprocessing scene bands & extracting spectral indices...")
    npy_path, geotiff_path = preprocess_scene(scene_dir=scene_dir, output_dir=processed_dir)

    # 4. Compile Pipeline Metadata Response
    result = {
        "status": "success",
        "scene_id": scene_id,
        "acquisition_date": acq_date,
        "cloud_cover": round(float(cloud_cover), 2),
        "bbox": bbox,
        "spatial_resolution_m": 10,
        "bands_count": 9,
        "band_names": [
            "B02", "B03", "B04", "B08", "B11", "B12",
            "NDVI", "SWIR_RATIO", "FERROUS_INDEX"
        ],
        "downloaded_bands": downloaded_paths,
        "features_npy_path": os.path.abspath(npy_path),
        "preprocessed_geotiff_path": os.path.abspath(geotiff_path)
    }

    print(f"\n[+] Automated Pipeline Complete!")
    print(f"    GeoTIFF Artifact : {result['preprocessed_geotiff_path']}")
    print(f"    NumPy Matrix     : {result['features_npy_path']}")
    print(f"============================================================\n")

    return result


if __name__ == "__main__":
    # Test Run: Balaghat Mineral Corridor [min_lon, min_lat, max_lon, max_lat]
    BALAGHAT_BBOX = [80.10, 21.75, 80.25, 21.90]
    
    pipeline_result = run_pipeline(
        bbox=BALAGHAT_BBOX,
        date_range="2024-01-01/2024-05-30",
        max_cloud=15
    )

    print("Pipeline Output Summary:")
    for k, v in pipeline_result.items():
        if k != "downloaded_bands":
            print(f"  {k}: {v}")
