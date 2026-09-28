"""
Render a RED / YELLOW / GREEN pixel-level exploration-potential overlay PNG
for the map, from the pipeline's own existing per-pixel score
(mineralization_scoring.py's mineralization_percentile, 0-100 scale). This
does NOT run or modify any ML/ranking stage -- it only reads already-generated
outputs (mineralization_scores.csv, valid_mask.tif, the raw SCL band) and
reuses existing project helpers rather than re-deriving them:

  - find_safe_product / find_granule_dir / find_scl_file / read_aligned
    (preprocess_satellite.py) -- to re-derive the Scene Classification
    Layer at this raster's own grid. valid_mask.tif does NOT exclude SCL
    water (class 6 is absent from INVALID_SCL_CLASSES -- water pixels are
    only percentile-*penalized* in mineralization_scoring.py, not dropped),
    so water must be masked separately here for the overlay.

GEOMETRY: this renders the FULL extent of each dataset's own target raster
(its real width/height/transform/CRS, read directly with rasterio) rather
than clipping to a separate AOI preset box. That earlier AOI-preset clip
(AOI_PRESETS["keonjhar"] = the small original Sentinel-2 *search* bbox from
load_satellite_data.py) was wrong for T45QUE: candidate_sites.csv's own
8,262 real candidates span nearly the *entire* downloaded T45QUE tile
(lon 85.055-86.126, lat 21.606-22.604) -- proof the actual
feature_extraction.py -> anomaly_detection.py -> mineralization_scoring.py
run processed the whole tile, not that small search box. Clipping the
overlay to the search box therefore hid real, already-scored pixels
covering real candidates and made the overlay look like an undersized,
offset rectangle next to a (also-too-small) AOI polygon. Using the raster's
own full extent instead needs no new data or fabrication -- it uses exactly
the same real per-pixel mineralization_percentile values, just without an
extra artificial crop.

For Chennai this is a no-op: its target raster (cleaned_images_aoi/B02.tif)
is *already* the real clipped stack from clip_to_aoi.py, and its own real
candidates (689, lon 80.078-80.450, lat 12.852-13.218) already fall tightly
within that raster's extent, so "the raster's own full extent" is the exact
same region the old AOI-preset clip produced.

Colour rule mirrors the exact thresholds/colours already used across the
frontend (frontend/src/potentialLevel.js): RED = HIGH >= 75,
YELLOW = MODERATE 50-74.99, GREEN = LOW < 50. Same Tailwind red-500 /
yellow-500 / green-500 hex values, so the raster and the UI badges/legend
match exactly.

Output (per dataset) -> data/processed/overlays/<dataset>_score_overlay.png
(RGBA, transparent where invalid / over water / unscored) plus a
<dataset>_score_overlay.json sidecar carrying the PNG's exact WGS84 bounds,
derived directly from the raster's own georeferencing -- never fabricated.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
import rasterio.shutil as rshutil
from rasterio.enums import Resampling
from rasterio.io import MemoryFile
from rasterio.transform import rowcol
from rasterio.warp import transform as warp_transform, transform_bounds

from preprocess_satellite import (
    find_safe_product,
    find_granule_dir,
    find_scl_file,
    read_aligned,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "overlays"

# Same thresholds as frontend/src/potentialLevel.js (HIGH_CUTOFF/MODERATE_CUTOFF).
HIGH_CUTOFF = 75.0
MODERATE_CUTOFF = 50.0

# Same hex values as the frontend's Tailwind classes (bg-red-500 / bg-yellow-500
# / bg-green-500), so the raster overlay matches the UI badges/legend exactly.
COLOR_HIGH = (239, 68, 68)      # red-500
COLOR_MODERATE = (234, 179, 8)  # yellow-500
COLOR_LOW = (34, 197, 94)       # green-500
OVERLAY_ALPHA = 150             # 0-255 -- keeps the basemap/satellite visible beneath

WATER_SCL_CLASS = 6
SCORE_COLUMNS = ["longitude", "latitude", "mineralization_percentile"]

DATASETS = {
    "t45que": {
        "raw_root": PROJECT_ROOT / "data" / "raw" / "satellite_images",
        "target_raster": PROJECT_ROOT / "data" / "processed" / "cleaned_images" / "B02.tif",
        "valid_mask": PROJECT_ROOT / "data" / "processed" / "cleaned_images" / "valid_mask.tif",
        "scores_csv": PROJECT_ROOT / "data" / "processed" / "mineralization_scores.csv",
    },
    "chennai": {
        "raw_root": PROJECT_ROOT / "data" / "raw" / "chennai",
        "target_raster": PROJECT_ROOT / "data" / "processed" / "chennai" / "cleaned_images_aoi" / "B02.tif",
        "valid_mask": PROJECT_ROOT / "data" / "processed" / "chennai" / "cleaned_images_aoi" / "valid_mask.tif",
        "scores_csv": PROJECT_ROOT / "data" / "processed" / "chennai" / "mineralization_scores.csv",
    },
}


def load_scores_in_bbox(csv_path: Path, bbox: tuple, chunksize: int = 2_000_000) -> tuple[pd.DataFrame, int]:
    """Stream mineralization_scores.csv in chunks (it's multi-GB for T45QUE)
    and keep only rows whose real longitude/latitude fall inside `bbox`
    (the target raster's own real WGS84 bounds, with a small margin) --
    no new score, just a cheap geographic pre-filter of existing pixel rows
    before the exact per-pixel row/col placement below."""
    lon_min, lat_min, lon_max, lat_max = bbox
    kept = []
    total = 0
    for chunk in pd.read_csv(csv_path, usecols=SCORE_COLUMNS, chunksize=chunksize):
        total += len(chunk)
        sel = chunk[
            (chunk["longitude"] >= lon_min) & (chunk["longitude"] <= lon_max)
            & (chunk["latitude"] >= lat_min) & (chunk["latitude"] <= lat_max)
        ]
        if len(sel):
            kept.append(sel)
    df = pd.concat(kept, ignore_index=True) if kept else pd.DataFrame(columns=SCORE_COLUMNS)
    return df, total


def render_dataset(key: str, cfg: dict) -> dict:
    print(f"\n=== {key} ===")

    if not cfg["target_raster"].is_file():
        raise FileNotFoundError(f"[{key}] Missing target raster: {cfg['target_raster']}")
    if not cfg["valid_mask"].is_file():
        raise FileNotFoundError(f"[{key}] Missing valid_mask: {cfg['valid_mask']}")
    if not cfg["scores_csv"].is_file():
        raise FileNotFoundError(f"[{key}] Missing mineralization_scores.csv: {cfg['scores_csv']}")

    # The FULL extent of this dataset's own real target raster -- no AOI-box
    # clip. This *is* the real processed/surveyed region: whatever
    # valid_mask.tif marks valid within it is real Sentinel-2 data that was
    # actually scored, nothing more, nothing less.
    with rasterio.open(cfg["target_raster"]) as ref:
        crs, transform, width, height = ref.crs, ref.transform, ref.width, ref.height
        raster_bounds = ref.bounds
    print(f"Raster grid: {width}x{height} px, {crs}, bounds={tuple(raster_bounds)}")

    with rasterio.open(cfg["valid_mask"]) as vm:
        valid = vm.read(1).astype(bool)

    # Re-derive the SCL water mask at this raster's own grid. Not persisted
    # anywhere by preprocess_satellite.py (it only keeps SCL in memory to
    # build valid_mask.tif, which does not exclude water).
    safe_root = find_safe_product(cfg["raw_root"])
    granule_dir = find_granule_dir(safe_root)
    scl_path = find_scl_file(granule_dir / "IMG_DATA")
    print(f"SCL source: {scl_path}")
    target = {"crs": crs, "transform": transform, "width": width, "height": height}
    scl, _ = read_aligned(scl_path, target, Resampling.nearest)
    water = scl == WATER_SCL_CLASS
    print(f"Water pixels (SCL={WATER_SCL_CLASS}) in raster: {int(water.sum())}/{water.size}")

    # Pre-filter the (possibly multi-GB) scores CSV to this raster's own
    # real WGS84 bounds, with a small margin for reprojection rounding at
    # the edges -- a performance optimization only, never a semantic clip
    # (every row that survives still gets placed by its own exact
    # reprojected row/col below, and anything outside [0,height)x[0,width)
    # is dropped there regardless of this pre-filter).
    lon_min_b, lat_min_b, lon_max_b, lat_max_b = transform_bounds(crs, "EPSG:4326", *raster_bounds)
    margin = 0.01
    bbox = (lon_min_b - margin, lat_min_b - margin, lon_max_b + margin, lat_max_b + margin)
    df, total_scanned = load_scores_in_bbox(cfg["scores_csv"], bbox)
    print(f"Scanned {total_scanned} pixel rows in {cfg['scores_csv'].name}; {len(df)} fall inside the raster's real bounds")

    score_grid = np.full((height, width), np.nan, dtype="float32")
    if len(df):
        xs, ys = warp_transform("EPSG:4326", crs, df["longitude"].to_numpy(), df["latitude"].to_numpy())
        rows, cols = rowcol(transform, xs, ys)
        rows = np.asarray(rows)
        cols = np.asarray(cols)
        in_bounds = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)
        dropped = int((~in_bounds).sum())
        if dropped:
            print(f"  (dropping {dropped} pixel row(s) that reproject just outside the raster grid edge)")
        score_grid[rows[in_bounds], cols[in_bounds]] = df["mineralization_percentile"].to_numpy()[in_bounds]

    colorable = valid & ~water & ~np.isnan(score_grid)
    print(f"Colourable pixels (valid & non-water & scored): {int(colorable.sum())}/{colorable.size}")

    rgba = np.zeros((4, height, width), dtype="uint8")
    high = colorable & (score_grid >= HIGH_CUTOFF)
    moderate = colorable & (score_grid >= MODERATE_CUTOFF) & (score_grid < HIGH_CUTOFF)
    low = colorable & (score_grid < MODERATE_CUTOFF)
    for mask, color in ((high, COLOR_HIGH), (moderate, COLOR_MODERATE), (low, COLOR_LOW)):
        rgba[0][mask] = color[0]
        rgba[1][mask] = color[1]
        rgba[2][mask] = color[2]
        rgba[3][mask] = OVERLAY_ALPHA
    print(f"HIGH={int(high.sum())} MODERATE={int(moderate.sum())} LOW={int(low.sum())} "
          f"(transparent everywhere else, including water/invalid/unscored pixels)")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    png_path = OUT_DIR / f"{key}_score_overlay.png"
    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff", height=height, width=width, count=4, dtype="uint8",
            crs=crs, transform=transform,
        ) as mem:
            mem.write(rgba)
        with memfile.open() as mem_r:
            rshutil.copy(mem_r, str(png_path), driver="PNG")

    result = {
        "dataset": key,
        "png": png_path.name,
        "width": width,
        "height": height,
        "crs": str(crs),
        "bounds": {"lon_min": lon_min_b, "lat_min": lat_min_b, "lon_max": lon_max_b, "lat_max": lat_max_b},
        "leaflet_bounds": [[lat_min_b, lon_min_b], [lat_max_b, lon_max_b]],
        "high_cutoff": HIGH_CUTOFF,
        "moderate_cutoff": MODERATE_CUTOFF,
        "pixel_counts": {
            "high": int(high.sum()), "moderate": int(moderate.sum()), "low": int(low.sum()),
            "water_excluded": int(water.sum()), "total": int(colorable.size),
        },
    }
    json_path = OUT_DIR / f"{key}_score_overlay.json"
    json_path.write_text(json.dumps(result, indent=2))
    print(f"Wrote {png_path}")
    print(f"Wrote {json_path}")
    return result


def main():
    for key, cfg in DATASETS.items():
        render_dataset(key, cfg)


if __name__ == "__main__":
    main()
