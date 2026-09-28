"""
Clip an already-preprocessed, aligned raster stack (the output of
preprocess_satellite.py: B02...B12 + valid_mask.tif, all on one common
10 m grid) down to a requested AOI bounding box.

Generic by design: works on any AOI_PRESETS entry (imported from
load_satellite_data.py, the single source of truth for those boxes -- not
redefined here) or a custom --bbox, and clips every *.tif found in
--input-dir, whatever that set happens to be. No band list, resolution, or
AOI is hardcoded, so this same script clips T45QUE, Chennai, or any future
AOI without modification.

The AOI is given in WGS84 lon/lat (matching AOI_PRESETS / --bbox elsewhere
in this project) and is reprojected into the raster's own CRS with
rasterio.warp.transform_bounds before any pixel window is computed --
rasterio.windows.from_bounds does the geo-to-pixel math using the raster's
transform, so no manual lon/lat -> row/col conversion happens here.

Does not touch data/raw/ (the downloaded SAFE product) or the unclipped
preprocessed rasters in --input-dir -- it only reads them and writes new
files under --output-dir.
"""

import argparse
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds, transform as window_transform

from load_satellite_data import AOI_PRESETS, resolve_aoi

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ClipError(Exception):
    """Raised when the input stack can't be safely clipped."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Clip an aligned GeoTIFF stack (preprocess_satellite.py output) to "
            "an AOI bounding box, reprojecting the AOI into the raster's own CRS."
        )
    )
    parser.add_argument(
        "--input-dir", type=Path, required=True,
        help="Folder of aligned GeoTIFFs to clip (e.g. data/processed/chennai/cleaned_images)",
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Folder to write the clipped GeoTIFFs to (must differ from --input-dir)",
    )
    parser.add_argument(
        "--aoi", choices=AOI_PRESETS.keys(),
        help="Named AOI preset from load_satellite_data.AOI_PRESETS (alternative to --bbox).",
    )
    parser.add_argument(
        "--bbox",
        help="Custom AOI as lon_min,lat_min,lon_max,lat_max in WGS84 degrees (alternative to --aoi).",
    )
    return parser.parse_args()


def load_reference_grid(tif_paths: list[Path]) -> tuple:
    """Open the first raster as the reference grid and confirm every other
    raster in the stack shares the same CRS/transform/width/height. Refuses
    to clip a stack that isn't already aligned -- clipping a mismatched grid
    with one shared window would silently misregister some of the outputs."""

    with rasterio.open(tif_paths[0]) as ref:
        crs, transform, width, height = ref.crs, ref.transform, ref.width, ref.height

    for p in tif_paths[1:]:
        with rasterio.open(p) as ds:
            if (ds.crs, ds.transform, ds.width, ds.height) != (crs, transform, width, height):
                raise ClipError(
                    f"{p} does not share the reference grid (from {tif_paths[0]}); "
                    "refusing to clip a misaligned stack with one shared window."
                )

    return crs, transform, width, height


def compute_clip_window(bbox: tuple, crs, transform, width: int, height: int) -> Window:
    """Reproject the WGS84 AOI bbox into the raster CRS, then let rasterio
    compute the pixel window from that -- never a manual lon/lat -> pixel
    conversion. Rounded outward (floor offsets, ceil lengths) so the clip
    fully covers the requested AOI, then intersected with the raster's own
    extent in case the AOI reaches beyond what this tile actually covers."""

    lon_min, lat_min, lon_max, lat_max = bbox
    left, bottom, right, top = transform_bounds("EPSG:4326", crs, lon_min, lat_min, lon_max, lat_max)

    raw_window = from_bounds(left, bottom, right, top, transform=transform)
    raw_window = raw_window.round_lengths().round_offsets()
    window = raw_window.intersection(Window(0, 0, width, height))

    if window.width <= 0 or window.height <= 0:
        raise ClipError(
            f"Requested AOI {bbox} does not overlap this raster stack's extent at all."
        )

    # Which edges the raster-extent intersection actually cut back, as opposed
    # to sub-pixel outward rounding + WGS84<->projected-CRS reprojection
    # non-linearity (from transform_bounds) -- so the report can tell a real
    # "AOI reaches past this tile's coverage" clamp apart from an expected,
    # small (sub-pixel to low-hundreds-of-metres) geometric rounding delta.
    clamped_edges = {
        "west": raw_window.col_off < window.col_off,
        "north": raw_window.row_off < window.row_off,
        "east": (raw_window.col_off + raw_window.width) > (window.col_off + window.width),
        "south": (raw_window.row_off + raw_window.height) > (window.row_off + window.height),
    }

    return window, clamped_edges


def clip_stack(tif_paths: list[Path], window: Window, transform, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_transform = window_transform(window, transform)
    out_paths = []

    for p in tif_paths:
        with rasterio.open(p) as src:
            data = src.read(1, window=window)
            profile = src.profile.copy()
            profile.update(
                height=data.shape[0],
                width=data.shape[1],
                transform=out_transform,
            )
            out_path = output_dir / p.name
            with rasterio.open(out_path, "w", **profile) as dst:
                dst.write(data, 1)

        print(f"  {p.name}: {src.height}x{src.width} -> {data.shape[0]}x{data.shape[1]} -> {out_path}")
        out_paths.append(out_path)

    return out_paths


def validate_clipped_stack(out_paths: list[Path], bbox: tuple, clamped_edges: dict) -> None:
    """Re-open every clipped output and confirm they all still share one
    identical grid, then report that grid's CRS/bounds/resolution and how
    it compares to the requested AOI."""

    grids = {}
    for p in out_paths:
        with rasterio.open(p) as ds:
            grids[p.name] = (ds.crs, ds.transform, ds.width, ds.height, ds.res, ds.bounds, ds.nodata)

    reference_name, reference = next(iter(grids.items()))
    ref_crs, ref_transform, ref_w, ref_h, ref_res, ref_bounds, _ = reference
    mismatched = [
        name for name, g in grids.items()
        if (g[0], g[1], g[2], g[3]) != (ref_crs, ref_transform, ref_w, ref_h)
    ]

    print("\n=== Clip validation ===")
    print(f"CRS               : {ref_crs}")
    print(f"Width x Height    : {ref_w} x {ref_h}")
    print(f"Resolution        : {ref_res}")
    print(f"Bounds (native)   : {ref_bounds}")

    wgs84_bounds = transform_bounds(ref_crs, "EPSG:4326", *ref_bounds)
    print(f"Bounds (EPSG:4326): west={wgs84_bounds[0]:.6f}, south={wgs84_bounds[1]:.6f}, "
          f"east={wgs84_bounds[2]:.6f}, north={wgs84_bounds[3]:.6f}")

    lon_min, lat_min, lon_max, lat_max = bbox
    print(f"Requested AOI     : west={lon_min}, south={lat_min}, east={lon_max}, north={lat_max}")

    for label, requested, actual in [
        ("west", lon_min, wgs84_bounds[0]), ("south", lat_min, wgs84_bounds[1]),
        ("east", lon_max, wgs84_bounds[2]), ("north", lat_max, wgs84_bounds[3]),
    ]:
        delta = actual - requested
        if clamped_edges.get(label):
            status = "CLAMPED (AOI extends beyond this raster's own coverage)"
        elif abs(delta) < 5e-4:
            status = "matches (sub-pixel rounding)"
        else:
            status = "close (outward pixel-grid rounding + WGS84<->projected-CRS reprojection, expected)"
        print(f"  {label:5s}: requested={requested:.6f}  actual={actual:.6f}  delta={delta:+.6f}  {status}")

    if mismatched:
        raise ClipError(
            f"Clipped outputs do not share one identical grid: {mismatched} differ from {reference_name}"
        )
    print(f"\nAll {len(out_paths)} clipped raster(s) share one identical grid (CRS/transform/width/height).")


def main():
    args = parse_args()

    if args.input_dir.resolve() == args.output_dir.resolve():
        raise ClipError("--output-dir must differ from --input-dir (the unclipped stack is left untouched).")

    tif_paths = sorted(args.input_dir.glob("*.tif"))
    if not tif_paths:
        raise ClipError(f"No .tif files found in {args.input_dir}")

    bbox = resolve_aoi(args)
    print(f"AOI bbox (WGS84 lon_min,lat_min,lon_max,lat_max): {bbox}")
    print(f"Input rasters ({len(tif_paths)}): {[p.name for p in tif_paths]}")

    crs, transform, width, height = load_reference_grid(tif_paths)
    print(f"\nReference input grid: CRS={crs}, {width}x{height}, transform={transform}")

    window, clamped_edges = compute_clip_window(bbox, crs, transform, width, height)
    print(f"Clip window (pixels): {window}")
    if any(clamped_edges.values()):
        print(f"NOTE: requested AOI extends beyond this raster's own coverage on: "
              f"{[e for e, v in clamped_edges.items() if v]} -- clipped to what the raster actually has.")

    print(f"\nClipping {len(tif_paths)} raster(s) to {args.output_dir} ...")
    out_paths = clip_stack(tif_paths, window, transform, args.output_dir)

    validate_clipped_stack(out_paths, bbox, clamped_edges)


if __name__ == "__main__":
    main()
