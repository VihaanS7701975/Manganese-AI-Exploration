"""
Phase 1: Sentinel-2 Data Acquisition Engine
Queries Planetary Computer STAC API and downloads VNIR + SWIR bands + SCL cloud mask.
"""

import os
import requests
from pystac_client import Client
import planetary_computer as pc
from typing import Dict, List, Optional

# The 6 primary spectral bands required for manganese alteration mapping + SCL mask
REQUIRED_BANDS = ["B02", "B03", "B04", "B08", "B11", "B12", "SCL"]

def search_sentinel_scene(
    bbox: List[float],
    date_range: str = "2024-01-01/2024-05-30",
    max_cloud_cover: int = 15
) -> Optional[dict]:
    """
    Search STAC API for the cleanest Sentinel-2 Level-2A scene covering the bbox.
    bbox format: [min_lon, min_lat, max_lon, max_lat]
    """
    print(f"[*] Querying Planetary Computer STAC for AOI: {bbox}, Range: {date_range}...")
    
    catalog = Client.open("https://planetarycomputer.microsoft.com/api/stac/v1")
    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=bbox,
        datetime=date_range,
        query={"eo:cloud_cover": {"lt": max_cloud_cover}},
        sortby=[{"field": "properties.eo:cloud_cover", "direction": "asc"}]
    )

    items = list(search.items())
    if not items:
        print(f"[!] No scenes found with cloud cover < {max_cloud_cover}%. Relaxing constraint...")
        search = catalog.search(
            collections=["sentinel-2-l2a"],
            bbox=bbox,
            datetime=date_range,
            sortby=[{"field": "properties.eo:cloud_cover", "direction": "asc"}]
        )
        items = list(search.items())
        if not items:
            raise RuntimeError("No satellite scenes found for the given coordinates and dates.")

    best_item = items[0]
    print(f"[+] Selected Scene ID: {best_item.id}")
    print(f"[+] Acquisition Date: {best_item.datetime.strftime('%Y-%m-%d')}")
    print(f"[+] Cloud Cover: {best_item.properties.get('eo:cloud_cover', 0):.2f}%")
    return best_item


def download_bands_for_scene(item, output_dir: str = "data/raw") -> Dict[str, str]:
    """
    Downloads required VNIR/SWIR bands and SCL mask from the signed STAC item.
    """
    os.makedirs(output_dir, exist_ok=True)
    scene_dir = os.path.join(output_dir, item.id)
    os.makedirs(scene_dir, exist_ok=True)

    signed_item = pc.sign(item)
    downloaded_paths = {}

    for band in REQUIRED_BANDS:
        if band.lower() in signed_item.assets:
            asset_key = band.lower()
        elif band in signed_item.assets:
            asset_key = band
        else:
            print(f"[!] Warning: Band {band} not available in assets.")
            continue

        asset_url = signed_item.assets[asset_key].href
        dest_file = os.path.join(scene_dir, f"{band}.tif")
        downloaded_paths[band] = dest_file

        if os.path.exists(dest_file):
            print(f"    [~] {band} already cached at: {dest_file}")
            continue

        print(f"    [>] Downloading {band}...")
        resp = requests.get(asset_url, stream=True)
        resp.raise_for_status()
        with open(dest_file, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192 * 16):
                f.write(chunk)
        print(f"    [+] Saved {band} -> {dest_file}")

    return downloaded_paths


if __name__ == "__main__":
    # Test Run: Balaghat Mineral Corridor [min_lon, min_lat, max_lon, max_lat]
    BALAGHAT_BBOX = [80.10, 21.75, 80.25, 21.90]
    
    selected_scene = search_sentinel_scene(bbox=BALAGHAT_BBOX)
    downloaded_files = download_bands_for_scene(selected_scene)
    print("\n[SUCCESS] Phase 1 Complete. Downloaded assets:")
    for b, p in downloaded_files.items():
        print(f"  - {b}: {p}")