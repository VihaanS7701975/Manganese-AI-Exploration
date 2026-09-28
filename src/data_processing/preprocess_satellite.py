"""
Preprocess a Sentinel-2 L2A SAFE product that has already been downloaded
under data/raw/satellite_images/.

For B02, B03, B04, B08 (native 10 m) and B11, B12 (native 20 m):
  - locate the correct JP2 file from IMG_DATA/R10m or IMG_DATA/R20m
  - resample the 20 m bands onto the B02 10 m reference grid
  - convert digital numbers to surface reflectance using the
    BOA_QUANTIFICATION_VALUE / BOA_ADD_OFFSET values from MTD_MSIL2A.xml
  - build a valid-data/cloud mask from the Scene Classification Layer (SCL)
  - write everything as aligned GeoTIFFs to data/processed/cleaned_images/

Does not touch QI_DATA, MSK_* files, or load_satellite_data.py, and does not
download anything.
"""

import argparse
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject


# ==========================
# CONFIG
# ==========================

PROJECT_ROOT = Path(__file__).resolve().parents[2]

RAW_ROOT = PROJECT_ROOT / "data" / "raw" / "satellite_images"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "cleaned_images"

BANDS_10M = ["B02", "B03", "B04", "B08"]
BANDS_20M = ["B11", "B12"]
ALL_BANDS = BANDS_10M + BANDS_20M
REFERENCE_BAND = "B02"

# SCL classes treated as invalid: 0 no data, 1 saturated/defective,
# 3 cloud shadows, 8/9 cloud medium/high probability, 10 thin cirrus.
INVALID_SCL_CLASSES = {0, 1, 3, 8, 9, 10}


class PreprocessingError(Exception):
    """Raised when the SAFE product is missing something or is ambiguous."""


# ==========================
# LOCATE THE SAFE PRODUCT
# ==========================

# Tile this pipeline is currently configured to process. Used only to break
# ties deterministically when more than one candidate SAFE product is present
# (see find_safe_product); it never widens which files are accepted.
TARGET_TILE = "T45QUE"


def find_safe_product(raw_root: Path) -> Path:
    """Return the single valid SAFE product root (the dir holding MTD_MSIL2A.xml).

    If more than one candidate is found, deterministically prefers the one
    whose directory name contains TARGET_TILE; if that doesn't narrow it to
    exactly one, still refuses to guess.
    """

    if not raw_root.is_dir():
        raise PreprocessingError(
            f"Raw satellite data folder not found: {raw_root}"
        )

    candidates = sorted({p.parent for p in raw_root.rglob("MTD_MSIL2A.xml")})

    if not candidates:
        raise PreprocessingError(
            f"No Sentinel-2 SAFE product found under {raw_root} "
            "(no MTD_MSIL2A.xml located)."
        )

    if len(candidates) > 1:
        tile_matches = [c for c in candidates if TARGET_TILE in c.name]
        if len(tile_matches) == 1:
            return tile_matches[0]
        listed = "\n".join(f"  - {c}" for c in candidates)
        raise PreprocessingError(
            "Multiple candidate SAFE products found, refusing to guess "
            f"which one to use:\n{listed}"
        )

    return candidates[0]


def find_granule_dir(safe_root: Path) -> Path:
    granule_root = safe_root / "GRANULE"

    if not granule_root.is_dir():
        raise PreprocessingError(f"GRANULE folder not found under {safe_root}")

    subdirs = [d for d in granule_root.iterdir() if d.is_dir()]

    if not subdirs:
        raise PreprocessingError(f"No granule folder found under {granule_root}")

    if len(subdirs) > 1:
        listed = "\n".join(f"  - {d}" for d in subdirs)
        raise PreprocessingError(
            f"Multiple granule folders found under {granule_root}, "
            f"refusing to guess which one to use:\n{listed}"
        )

    return subdirs[0]


def find_band_file(res_dir: Path, band: str, res_label: str) -> Path:
    """Find exactly one IMG_DATA jp2 file for `band` at `res_label` (e.g. '10m')."""

    if not res_dir.is_dir():
        raise PreprocessingError(f"Resolution folder not found: {res_dir}")

    matches = sorted(
        p for p in res_dir.glob(f"*_{band}_{res_label}.jp2")
        if "QI_DATA" not in p.parts and not p.name.startswith("MSK")
    )

    if not matches:
        raise PreprocessingError(
            f"Could not find band {band} ({res_label}) in {res_dir}"
        )

    if len(matches) > 1:
        listed = "\n".join(f"  - {m}" for m in matches)
        raise PreprocessingError(
            f"Multiple files matched band {band} ({res_label}) in {res_dir}, "
            f"refusing to guess which one to use:\n{listed}"
        )

    return matches[0]


def find_scl_file(img_data_dir: Path) -> Path:
    """
    Locate the Scene Classification Layer under IMG_DATA. The 20 m product
    is preferred (matches the resolution of B11/B12); the 60 m product is
    used only as a fallback if the 20 m one is missing. QI_DATA and MSK_*
    files are never considered, even if they happen to match the glob.
    """

    search_order = [
        ("R20m", "*_SCL_20m.jp2"),
        ("R60m", "*_SCL_60m.jp2"),
    ]

    for subdir_name, pattern in search_order:
        subdir = img_data_dir / subdir_name

        if not subdir.is_dir():
            continue

        matches = sorted(
            p for p in subdir.glob(pattern)
            if "QI_DATA" not in p.parts and not p.name.startswith("MSK")
        )

        if len(matches) > 1:
            listed = "\n".join(f"  - {m}" for m in matches)
            raise PreprocessingError(
                f"Multiple SCL files found in {subdir}, refusing to guess "
                f"which one to use:\n{listed}"
            )

        if len(matches) == 1:
            return matches[0]

    raise PreprocessingError(
        f"Could not find the Scene Classification Layer (SCL) under {img_data_dir} "
        "(looked for R20m/*_SCL_20m.jp2, then R60m/*_SCL_60m.jp2)."
    )


# ==========================
# METADATA: DN -> REFLECTANCE
# ==========================

def _normalize_band_code(band: str) -> str:
    """'B02' -> 'B2', 'B11' -> 'B11' (matches MTD_MSIL2A.xml physicalBand values)."""

    match = re.match(r"^B0?(\d+)$", band)

    if not match:
        raise PreprocessingError(f"Unrecognized band code: {band}")

    return f"B{int(match.group(1))}"


def parse_reflectance_metadata(safe_root: Path) -> dict:
    """
    Read MTD_MSIL2A.xml and return:
      {
        "quantification_value": float,
        "offsets": {"B2": -1000.0, ...},   # per physical band, 0.0 if absent
        "special_values": {"NODATA": 0, "SATURATED": 65535, ...},
      }

    Sentinel-2 L2A processing baseline >= 04.00 adds a BOA_ADD_OFFSET before
    scaling by BOA_QUANTIFICATION_VALUE; older baselines only scale. We check
    the actual metadata instead of assuming either convention.
    """

    mtd_path = safe_root / "MTD_MSIL2A.xml"

    if not mtd_path.is_file():
        raise PreprocessingError(f"Missing product metadata file: {mtd_path}")

    tree = ET.parse(mtd_path)
    root = tree.getroot()

    quant_elem = root.find(".//BOA_QUANTIFICATION_VALUE")

    if quant_elem is None or quant_elem.text is None:
        raise PreprocessingError(
            f"BOA_QUANTIFICATION_VALUE not found in {mtd_path}; "
            "cannot safely convert digital numbers to reflectance."
        )

    quantification_value = float(quant_elem.text)

    baseline_elem = root.find(".//PROCESSING_BASELINE")
    baseline = float(baseline_elem.text) if baseline_elem is not None and baseline_elem.text else None

    id_to_band = {
        elem.get("bandId"): elem.get("physicalBand")
        for elem in root.iter("Spectral_Information")
        if elem.get("bandId") is not None
    }

    offsets = {}
    offset_list = root.find(".//BOA_ADD_OFFSET_VALUES_LIST")

    if offset_list is not None:
        for offset_elem in offset_list.findall("BOA_ADD_OFFSET"):
            physical_band = id_to_band.get(offset_elem.get("band_id"))
            if physical_band and offset_elem.text is not None:
                offsets[physical_band] = float(offset_elem.text)

    if baseline is not None and baseline >= 4.0 and not offsets:
        raise PreprocessingError(
            f"Processing baseline {baseline:.2f} in {mtd_path} implies BOA_ADD_OFFSET "
            "values should be present, but none were found. Refusing to guess "
            "whether to apply an offset before scaling by BOA_QUANTIFICATION_VALUE."
        )

    special_values = {}
    for sv in root.iter("Special_Values"):
        text_elem = sv.find("SPECIAL_VALUE_TEXT")
        index_elem = sv.find("SPECIAL_VALUE_INDEX")
        if text_elem is not None and index_elem is not None:
            special_values[text_elem.text] = int(index_elem.text)

    return {
        "quantification_value": quantification_value,
        "offsets": offsets,
        "special_values": special_values,
    }


def band_offset(reflectance_meta: dict, band: str) -> float:
    return reflectance_meta["offsets"].get(_normalize_band_code(band), 0.0)


# ==========================
# READ + RESAMPLE
# ==========================

def read_reference_band(path: Path):
    with rasterio.open(path) as src:
        data = src.read(1)
        info = {
            "crs": src.crs,
            "transform": src.transform,
            "width": src.width,
            "height": src.height,
            "res": src.res,
            "nodata": src.nodata,
        }
    return data, info


def read_aligned(path: Path, target: dict, resampling: Resampling):
    """Read a band and, if needed, reproject/resample it onto the target grid."""

    with rasterio.open(path) as src:
        input_shape = (src.height, src.width)
        input_res = src.res
        input_crs = src.crs
        src_nodata = src.nodata

        already_aligned = (
            src.crs == target["crs"]
            and src.transform == target["transform"]
            and src.width == target["width"]
            and src.height == target["height"]
        )

        if already_aligned:
            data = src.read(1)
        else:
            data = np.zeros((target["height"], target["width"]), dtype=src.dtypes[0])
            reproject(
                source=rasterio.band(src, 1),
                destination=data,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=target["transform"],
                dst_crs=target["crs"],
                resampling=resampling,
            )

    return data, {
        "input_shape": input_shape,
        "input_res": input_res,
        "input_crs": input_crs,
        "nodata": src_nodata,
    }


# ==========================
# REFLECTANCE + MASKING
# ==========================

def dn_to_reflectance(dn: np.ndarray, invalid_mask: np.ndarray, offset: float, quant_value: float) -> np.ndarray:
    reflectance = np.full(dn.shape, np.nan, dtype=np.float32)
    valid = ~invalid_mask
    reflectance[valid] = (dn[valid].astype(np.float32) + offset) / quant_value
    return reflectance


def invalid_dn_mask(dn: np.ndarray, nodata: int, special_values: dict) -> np.ndarray:
    invalid_values = set(special_values.values())
    if nodata is not None:
        invalid_values.add(int(nodata))

    mask = np.zeros(dn.shape, dtype=bool)
    for value in invalid_values:
        mask |= (dn == value)

    return mask


# ==========================
# OUTPUT
# ==========================

def write_geotiff(path: Path, data: np.ndarray, target: dict, dtype: str, nodata):
    path.parent.mkdir(parents=True, exist_ok=True)

    profile = {
        "driver": "GTiff",
        "height": data.shape[0],
        "width": data.shape[1],
        "count": 1,
        "dtype": dtype,
        "crs": target["crs"],
        "transform": target["transform"],
        "nodata": nodata,
        "compress": "deflate",
    }

    with rasterio.open(path, "w", **profile) as dst:
        dst.write(data, 1)


def describe(label, path, input_shape, input_res, crs, output_shape, output_res, output_path):
    print(f"\n[{label}]")
    print(f"  input path       : {path}")
    print(f"  input shape      : {input_shape}")
    print(f"  input resolution : {input_res}")
    print(f"  CRS              : {crs}")
    print(f"  output shape     : {output_shape}")
    print(f"  output resolution: {output_res}")
    print(f"  output path      : {output_path}")


# ==========================
# MAIN
# ==========================

def parse_args() -> argparse.Namespace:
    """--raw-root/--out-dir let a separate AOI (e.g. Chennai, downloaded to
    its own data/raw/chennai/ tree) be preprocessed without touching the
    T45QUE data. Both default to the existing hardcoded paths, so running
    this script with no flags is byte-for-byte identical to before."""
    parser = argparse.ArgumentParser(
        description="Preprocess a Sentinel-2 L2A SAFE product into aligned GeoTIFFs."
    )
    parser.add_argument(
        "--raw-root", type=Path, default=RAW_ROOT,
        help=f"Folder to search for a SAFE product under (default: {RAW_ROOT})",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=OUT_DIR,
        help=f"Folder to write the cleaned GeoTIFFs to (default: {OUT_DIR})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    raw_root = args.raw_root
    out_dir = args.out_dir

    print(f"Searching for SAFE product under: {raw_root}")
    safe_root = find_safe_product(raw_root)
    print(f"Using SAFE product: {safe_root}")

    granule_dir = find_granule_dir(safe_root)
    img_data = granule_dir / "IMG_DATA"
    r10m_dir = img_data / "R10m"
    r20m_dir = img_data / "R20m"

    reflectance_meta = parse_reflectance_metadata(safe_root)
    quant_value = reflectance_meta["quantification_value"]
    special_values = reflectance_meta["special_values"]

    print(f"BOA_QUANTIFICATION_VALUE: {quant_value}")
    print(f"BOA_ADD_OFFSET per band : {reflectance_meta['offsets']}")
    print(f"Special DN values       : {special_values}")

    band_paths = {}
    for band in BANDS_10M:
        band_paths[band] = find_band_file(r10m_dir, band, "10m")
    for band in BANDS_20M:
        band_paths[band] = find_band_file(r20m_dir, band, "20m")

    scl_path = find_scl_file(img_data)

    # --- reference grid: B02 at 10 m ---
    ref_data, ref_info = read_reference_band(band_paths[REFERENCE_BAND])
    target = {
        "crs": ref_info["crs"],
        "transform": ref_info["transform"],
        "width": ref_info["width"],
        "height": ref_info["height"],
    }

    out_dir.mkdir(parents=True, exist_ok=True)

    combined_invalid = np.zeros((target["height"], target["width"]), dtype=bool)
    summary_rows = []

    for band in ALL_BANDS:
        # Continuous reflectance data: bilinear. The native 10 m bands are
        # already on the reference grid, so this only ever applies to B11/B12.
        resampling = Resampling.bilinear
        path = band_paths[band]

        if band == REFERENCE_BAND:
            dn = ref_data
            read_info = {
                "input_shape": (ref_info["height"], ref_info["width"]),
                "input_res": ref_info["res"],
                "input_crs": ref_info["crs"],
                "nodata": ref_info["nodata"],
            }
        else:
            dn, read_info = read_aligned(path, target, resampling)

        invalid = invalid_dn_mask(dn, read_info["nodata"], special_values)
        combined_invalid |= invalid

        offset = band_offset(reflectance_meta, band)
        reflectance = dn_to_reflectance(dn, invalid, offset, quant_value)

        out_path = out_dir / f"{band}.tif"
        write_geotiff(out_path, reflectance, target, "float32", np.nan)

        output_res = (target["transform"].a, -target["transform"].e)

        describe(
            band,
            path,
            read_info["input_shape"],
            read_info["input_res"],
            read_info["input_crs"],
            reflectance.shape,
            output_res,
            out_path,
        )

        summary_rows.append({
            "label": band,
            "input_path": path,
            "input_shape": read_info["input_shape"],
            "input_res": read_info["input_res"],
            "output_shape": reflectance.shape,
            "output_res": output_res,
            "output_path": out_path,
        })

    # --- valid-data / cloud mask from the Scene Classification Layer ---
    scl, scl_info = read_aligned(scl_path, target, Resampling.nearest)
    scl_invalid = np.isin(scl, list(INVALID_SCL_CLASSES))

    valid_mask = (~combined_invalid & ~scl_invalid).astype(np.uint8)

    total_pixels = int(valid_mask.size)
    valid_pixels = int(valid_mask.sum())
    valid_pct = 100.0 * valid_pixels / total_pixels

    mask_path = out_dir / "valid_mask.tif"
    write_geotiff(mask_path, valid_mask, target, "uint8", None)

    scl_output_res = (target["transform"].a, -target["transform"].e)

    describe(
        "valid_mask (SCL-based)",
        scl_path,
        scl_info["input_shape"],
        scl_info["input_res"],
        scl_info["input_crs"],
        valid_mask.shape,
        scl_output_res,
        mask_path,
    )
    print(f"  valid pixels     : {valid_pixels} / {total_pixels} ({valid_pct:.2f}%)")

    # --- verify all six band outputs share one identical grid, at 10 m ---
    print("\nVerifying output grid alignment...")

    band_output_paths = [out_dir / f"{band}.tif" for band in ALL_BANDS]
    reference_grid = None

    for out_path in band_output_paths:
        with rasterio.open(out_path) as ds:
            grid = (ds.width, ds.height, ds.crs, ds.transform, ds.res)

        if reference_grid is None:
            reference_grid = grid
            continue

        if grid[:4] != reference_grid[:4]:
            raise PreprocessingError(
                f"Grid mismatch: {out_path} has width/height/CRS/transform "
                f"{grid[:4]}, expected {reference_grid[:4]}"
            )

    ref_width, ref_height, ref_crs, ref_transform, ref_res = reference_grid

    if round(ref_res[0], 6) != 10.0 or round(ref_res[1], 6) != 10.0:
        raise PreprocessingError(
            f"Output resolution is {ref_res}, expected exactly 10m x 10m."
        )

    print(
        "All six output rasters share identical width, height, CRS and transform, "
        "at 10m resolution:\n"
        f"  width={ref_width} height={ref_height} crs={ref_crs}\n"
        f"  transform={ref_transform}\n  resolution={ref_res}"
    )

    # --- final summary ---
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Scene (SAFE product) : {safe_root}")
    print(f"Granule               : {granule_dir}")
    print(f"CRS                   : {ref_crs}")
    print(f"Output grid           : {ref_width} x {ref_height} @ {ref_res}")

    for row in summary_rows:
        print(f"\n  {row['label']}")
        print(f"    input path      : {row['input_path']}")
        print(f"    input shape/res : {row['input_shape']} / {row['input_res']}")
        print(f"    output shape/res: {row['output_shape']} / {row['output_res']}")
        print(f"    output path     : {row['output_path']}")

    print(f"\n  SCL (source for valid_mask)")
    print(f"    input path      : {scl_path}")
    print(f"    input shape/res : {scl_info['input_shape']} / {scl_info['input_res']}")
    print(f"    output shape/res: {valid_mask.shape} / {scl_output_res}")
    print(f"    output path     : {mask_path}")
    print(f"    valid pixels    : {valid_pixels} / {total_pixels} ({valid_pct:.2f}%)")

    print(f"\nAll outputs written to: {out_dir}")
    print("Done.")


if __name__ == "__main__":
    main()
