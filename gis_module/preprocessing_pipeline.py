from pathlib import Path
import json

import numpy as np
import pandas as pd
import rasterio

from rasterio.enums import Resampling
from rasterio.warp import reproject
from pyproj import Transformer


# ============================================================
# S.I.H - SENTINEL-2 GIS PREPROCESSING PIPELINE
# ============================================================
#
# Workflow:
#
# Copernicus search
#        ↓
# Best Sentinel-2 scene
#        ↓
# Local SAFE scene
#        ↓
# Find B02/B03/B04/B08/B11/B12/SCL
#        ↓
# Align all bands to B02
#        ↓
# Resample SCL using nearest neighbour
#        ↓
# Create valid land mask
#        ↓
# Calculate spectral features
#        ↓
# Generate latitude/longitude
#        ↓
# Sample up to 1,000,000 pixels
#        ↓
# Create ML-ready CSV
#
# ============================================================


# ============================================================
# PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SATELLITE_FOLDER = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "satellite_images"
)

PROCESSED_FOLDER = (
    PROJECT_ROOT
    / "data"
    / "processed"
)

SEARCH_RESULTS_FILE = (
    PROCESSED_FOLDER
    / "copernicus_search_results.json"
)

OUTPUT_CSV = (
    PROCESSED_FOLDER
    / "sentinel2_features.csv"
)

PROCESSING_METADATA_FILE = (
    PROCESSED_FOLDER
    / "sentinel2_processing_metadata.json"
)


# ============================================================
# ML DATASET SETTINGS
# ============================================================

# Maximum number of pixels written to the ML CSV.
#
# The original satellite imagery is NOT reduced.
# Only the derived ML table is sampled.

MAX_ML_SAMPLES = 1_000_000

# Fixed seed gives reproducible datasets.
RANDOM_SEED = 42


# ============================================================
# REQUIRED SENTINEL-2 BANDS
# ============================================================

REQUIRED_BANDS = {
    "B02": "Blue",
    "B03": "Green",
    "B04": "Red",
    "B08": "NIR",
    "B11": "SWIR1",
    "B12": "SWIR2",
    "SCL": "Scene Classification",
}


# ============================================================
# SCL CLASSES USED FOR LAND ANALYSIS
# ============================================================
#
# Sentinel-2 SCL:
#
# 0  = No data
# 1  = Saturated / defective
# 2  = Dark area / shadows
# 3  = Cloud shadow
# 4  = Vegetation
# 5  = Not vegetated
# 6  = Water
# 7  = Unclassified
# 8  = Cloud medium probability
# 9  = Cloud high probability
# 10 = Thin cirrus
# 11 = Snow / ice
#
# For the current mineral exploration preprocessing:
#
# VALID:
#   4 = vegetation
#   5 = not vegetated / bare land
#   7 = unclassified
#
# INVALID:
#   no data
#   saturated pixels
#   shadows
#   water
#   clouds
#   cirrus
#   snow/ice
#
# ============================================================

VALID_SCL_CLASSES = {
    4,
    5,
    7,
}


# ============================================================
# PRINT SECTION
# ============================================================

def print_section(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print()


# ============================================================
# SCENE SELECTION
# ============================================================

def select_scene_folder():

    print_section("SELECTING SENTINEL-2 SCENE")

    if not SATELLITE_FOLDER.exists():

        raise FileNotFoundError(
            "\nSatellite image directory does not exist:\n"
            f"{SATELLITE_FOLDER}"
        )

    # --------------------------------------------------------
    # Preferred source:
    # Copernicus search results
    # --------------------------------------------------------

    if SEARCH_RESULTS_FILE.exists():

        print("Checking Copernicus search results...")

        try:

            with open(
                SEARCH_RESULTS_FILE,
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            results = data.get("results", [])

            if results:

                scene_id = results[0].get("scene_id")

                if scene_id:

                    candidate = (
                        SATELLITE_FOLDER
                        / scene_id
                    )

                    print(
                        f"Best scene from Copernicus:\n"
                        f"{scene_id}"
                    )

                    print()

                    if candidate.exists():

                        print(
                            "✓ Selected Copernicus scene "
                            "is available locally."
                        )

                        print()
                        print("Scene:")
                        print(candidate)
                        print()

                        return candidate

                    print(
                        "WARNING:"
                    )

                    print(
                        "The best Copernicus scene is "
                        "not available locally."
                    )

                    print(
                        f"Expected:\n{candidate}"
                    )

                    print()

        except json.JSONDecodeError as error:

            print(
                "WARNING: Copernicus search result "
                "JSON is invalid."
            )

            print(f"Reason: {error}")
            print()

        except OSError as error:

            print(
                "WARNING: Could not read "
                "Copernicus search results."
            )

            print(f"Reason: {error}")
            print()

    # --------------------------------------------------------
    # Fallback:
    # Find local SAFE scenes.
    # --------------------------------------------------------

    print(
        "Searching locally available "
        "Sentinel-2 scenes..."
    )

    scenes = sorted(
        [
            folder
            for folder in SATELLITE_FOLDER.iterdir()
            if folder.is_dir()
            and folder.name.upper().endswith(".SAFE")
        ],
        key=lambda folder: folder.stat().st_mtime,
        reverse=True,
    )

    if not scenes:

        raise FileNotFoundError(
            "\nNo Sentinel-2 .SAFE scenes found.\n\n"
            f"Location:\n{SATELLITE_FOLDER}"
        )

    print(
        f"Found {len(scenes)} local scene(s)."
    )

    print()

    for index, scene in enumerate(
        scenes,
        start=1
    ):

        print(
            f"{index}. {scene.name}"
        )

    print()

    selected = scenes[0]

    print(
        "✓ Using newest local scene:"
    )

    print(selected)
    print()

    return selected


# ============================================================
# FIND REQUIRED BANDS
# ============================================================

def find_band_files(scene_folder):

    print_section(
        "SEARCHING SELECTED SENTINEL-2 SCENE"
    )

    scene_folder = Path(scene_folder)

    if not scene_folder.exists():

        raise FileNotFoundError(
            "\nSelected Sentinel-2 scene does not exist:\n"
            f"{scene_folder}"
        )

    if not scene_folder.is_dir():

        raise NotADirectoryError(
            f"\nExpected directory:\n{scene_folder}"
        )

    print("Scene:")
    print(scene_folder)
    print()

    # --------------------------------------------------------
    # Recursive search supports:
    #
    # 1. Normal SAFE structure
    #
    # SAFE/
    #   GRANULE/
    #     .../
    #       IMG_DATA/
    #
    # 2. Current downloaded structure
    #
    # SAFE/
    #   B02.jp2
    #   B03.jp2
    #   ...
    #
    # --------------------------------------------------------

    raster_files = [
        file
        for file in scene_folder.rglob("*")
        if file.is_file()
        and file.suffix.lower() in {
            ".jp2",
            ".tif",
            ".tiff",
        }
    ]

    if not raster_files:

        raise FileNotFoundError(
            "\nNo raster files found inside:\n"
            f"{scene_folder}"
        )

    band_files = {}

    # --------------------------------------------------------
    # Find each required band.
    # --------------------------------------------------------

    for band in REQUIRED_BANDS:

        matches = [
            file
            for file in raster_files
            if band in file.name.upper()
        ]

        # More precise matching.
        exact_matches = [
            file
            for file in matches
            if (
                f"_{band}_" in file.name.upper()
                or f"_{band}." in file.name.upper()
            )
        ]

        if exact_matches:

            band_files[band] = exact_matches[0]

        elif matches:

            band_files[band] = matches[0]

    # --------------------------------------------------------
    # Display.
    # --------------------------------------------------------

    print("===== REQUIRED BANDS =====")

    for band, description in REQUIRED_BANDS.items():

        if band in band_files:

            print(
                f"{band:4} | "
                f"{description:22} | "
                f"{band_files[band].name}"
            )

        else:

            print(
                f"{band:4} | "
                f"{description:22} | "
                "NOT FOUND"
            )

    print()

    # --------------------------------------------------------
    # Missing check.
    # --------------------------------------------------------

    missing = [
        band
        for band in REQUIRED_BANDS
        if band not in band_files
    ]

    if missing:

        raise FileNotFoundError(
            "\nMissing required Sentinel-2 files:\n"
            + ", ".join(missing)
            + "\n\n"
            "All required bands must come "
            "from the SAME scene."
        )

    print(
        "✓ All required bands found "
        "in the SAME scene."
    )

    print()

    return band_files


# ============================================================
# NORMALIZED DIFFERENCE
# ============================================================

def normalized_difference(
    band_a,
    band_b
):

    denominator = (
        band_a + band_b
    )

    result = np.zeros_like(
        band_a,
        dtype=np.float32
    )

    np.divide(
        band_a - band_b,
        denominator,
        out=result,
        where=denominator != 0,
    )

    return result


# ============================================================
# CLEAN ARRAY
# ============================================================

def clean_array(array):

    array = np.asarray(
        array,
        dtype=np.float32
    )

    array[~np.isfinite(array)] = 0.0

    return array


# ============================================================
# RESAMPLE SPECTRAL BAND
# ============================================================

def resample_to_reference(
    source_path,
    reference_crs,
    reference_transform,
    reference_width,
    reference_height,
):

    with rasterio.open(
        source_path
    ) as source:

        destination = np.zeros(
            (
                reference_height,
                reference_width,
            ),
            dtype=np.float32,
        )

        reproject(
            source=rasterio.band(
                source,
                1,
            ),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            dst_transform=reference_transform,
            dst_crs=reference_crs,
            src_nodata=source.nodata,
            dst_nodata=0,
            resampling=Resampling.bilinear,
        )

    return clean_array(
        destination
    )


# ============================================================
# RESAMPLE SCL
# ============================================================

def resample_scl_to_reference(
    scl_path,
    reference_crs,
    reference_transform,
    reference_width,
    reference_height,
):

    print(
        "Resampling SCL to B02 reference grid..."
    )

    # --------------------------------------------------------
    # SCL is categorical data.
    #
    # NEVER use bilinear interpolation for SCL.
    # --------------------------------------------------------

    with rasterio.open(
        scl_path
    ) as source:

        destination = np.zeros(
            (
                reference_height,
                reference_width,
            ),
            dtype=np.uint8,
        )

        reproject(
            source=rasterio.band(
                source,
                1,
            ),
            destination=destination,
            src_transform=source.transform,
            src_crs=source.crs,
            dst_transform=reference_transform,
            dst_crs=reference_crs,
            src_nodata=0,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )

    return destination


# ============================================================
# LOAD AND ALIGN BANDS
# ============================================================

def load_and_align_bands(
    band_files
):

    print_section(
        "OPENING B02 AS REFERENCE GRID"
    )

    # --------------------------------------------------------
    # B02 is the 10 m reference grid.
    # --------------------------------------------------------

    with rasterio.open(
        band_files["B02"]
    ) as reference:

        reference_crs = reference.crs
        reference_transform = reference.transform
        reference_width = reference.width
        reference_height = reference.height

        print(
            f"Width:  {reference_width:,}"
        )

        print(
            f"Height: {reference_height:,}"
        )

        print(
            f"CRS:    {reference_crs}"
        )

    print()

    # --------------------------------------------------------
    # B02
    # --------------------------------------------------------

    with rasterio.open(
        band_files["B02"]
    ) as source:

        b02 = clean_array(
            source.read(1)
        )

    bands = {
        "B02": b02
    }

    # --------------------------------------------------------
    # Align remaining spectral bands.
    # --------------------------------------------------------

    print(
        "Aligning Sentinel-2 bands..."
    )

    print()

    for band in [
        "B03",
        "B04",
        "B08",
        "B11",
        "B12",
    ]:

        print(
            f"Processing {band}..."
        )

        bands[band] = (
            resample_to_reference(
                source_path=band_files[band],
                reference_crs=reference_crs,
                reference_transform=reference_transform,
                reference_width=reference_width,
                reference_height=reference_height,
            )
        )

    print()

    print(
        "✓ All spectral bands aligned "
        "to B02 grid."
    )

    print()

    # --------------------------------------------------------
    # SCL.
    # --------------------------------------------------------

    scl = resample_scl_to_reference(
        scl_path=band_files["SCL"],
        reference_crs=reference_crs,
        reference_transform=reference_transform,
        reference_width=reference_width,
        reference_height=reference_height,
    )

    return (
        bands,
        scl,
        reference_crs,
        reference_transform,
        reference_width,
        reference_height,
    )


# ============================================================
# CREATE SCL MASK
# ============================================================

def create_scl_mask(
    scl
):

    print_section(
        "CREATING SCL LAND / VALID-PIXEL MASK"
    )

    mask = np.isin(
        scl,
        list(VALID_SCL_CLASSES)
    )

    total_pixels = mask.size

    valid_pixels = int(
        np.count_nonzero(mask)
    )

    invalid_pixels = (
        total_pixels
        - valid_pixels
    )

    valid_percentage = (
        valid_pixels
        / total_pixels
        * 100.0
    )

    print(
        "Valid SCL classes:"
    )

    print(
        "  4 = Vegetation"
    )

    print(
        "  5 = Not vegetated / bare land"
    )

    print(
        "  7 = Unclassified"
    )

    print()

    print(
        "===== SCL MASK STATISTICS ====="
    )

    print(
        f"Total pixels:     {total_pixels:,}"
    )

    print(
        f"Valid pixels:     {valid_pixels:,}"
    )

    print(
        f"Invalid pixels:   {invalid_pixels:,}"
    )

    print(
        f"Valid percentage: {valid_percentage:.2f}%"
    )

    print()

    if valid_percentage < 1.0:

        print(
            "WARNING:"
        )

        print(
            "Less than 1% of pixels are valid."
        )

        print(
            "Investigate scene quality."
        )

    elif valid_percentage < 10.0:

        print(
            "WARNING:"
        )

        print(
            "Less than 10% of pixels are valid."
        )

    else:

        print(
            "✓ Reasonable amount of "
            "land pixels available."
        )

    print()

    return mask


# ============================================================
# CALCULATE FEATURES
# ============================================================

def calculate_features(
    bands
):

    print_section(
        "CALCULATING SPECTRAL FEATURES"
    )

    b04 = bands["B04"]
    b08 = bands["B08"]
    b11 = bands["B11"]
    b12 = bands["B12"]

    # --------------------------------------------------------
    # NDVI
    # --------------------------------------------------------

    ndvi = normalized_difference(
        b08,
        b04
    )

    # --------------------------------------------------------
    # NBR
    # --------------------------------------------------------

    nbr = normalized_difference(
        b08,
        b12
    )

    # --------------------------------------------------------
    # SWIR1 / SWIR2
    # --------------------------------------------------------

    swir_ratio = np.divide(
        b11,
        b12,
        out=np.zeros_like(
            b11,
            dtype=np.float32,
        ),
        where=b12 != 0,
    )

    # --------------------------------------------------------
    # RED / SWIR1
    # --------------------------------------------------------

    red_swir_ratio = np.divide(
        b04,
        b11,
        out=np.zeros_like(
            b04,
            dtype=np.float32,
        ),
        where=b11 != 0,
    )

    features = {
        "ndvi": clean_array(ndvi),
        "nbr": clean_array(nbr),
        "swir_ratio": clean_array(swir_ratio),
        "red_swir_ratio": clean_array(red_swir_ratio),
    }

    print(
        "===== FEATURES CREATED ====="
    )

    for name, feature in features.items():

        finite_values = feature[
            np.isfinite(feature)
        ]

        if finite_values.size == 0:

            print(
                f"  {name:18} "
                "NO VALID VALUES"
            )

        else:

            print(
                f"  ✓ {name:18} "
                f"min={finite_values.min():.4f} "
                f"max={finite_values.max():.4f} "
                f"mean={finite_values.mean():.4f}"
            )

    print()

    return features


# ============================================================
# CREATE COORDINATES
# ============================================================

def create_coordinates(
    transform,
    crs,
    width,
    height,
    mask,
):

    print_section(
        "CREATING LATITUDE / LONGITUDE COORDINATES"
    )

    rows, cols = np.where(
        mask
    )

    if len(rows) == 0:

        raise RuntimeError(
            "No valid pixels are available "
            "for coordinate generation."
        )

    print(
        f"Generating coordinates for "
        f"{len(rows):,} valid pixels..."
    )

    # --------------------------------------------------------
    # Correct use of rasterio transform.
    #
    # This avoids:
    #
    # TypeError: 'Affine' object is not callable
    # --------------------------------------------------------

    xs, ys = rasterio.transform.xy(
        transform,
        rows,
        cols,
        offset="center",
    )

    xs = np.asarray(
        xs,
        dtype=np.float64,
    )

    ys = np.asarray(
        ys,
        dtype=np.float64,
    )

    # --------------------------------------------------------
    # Projected CRS -> WGS84.
    # --------------------------------------------------------

    transformer = Transformer.from_crs(
        crs,
        "EPSG:4326",
        always_xy=True,
    )

    longitude, latitude = (
        transformer.transform(
            xs,
            ys,
        )
    )

    longitude = np.asarray(
        longitude,
        dtype=np.float64,
    )

    latitude = np.asarray(
        latitude,
        dtype=np.float64,
    )

    print(
        "✓ Coordinates converted to WGS84."
    )

    print()

    return (
        latitude,
        longitude,
        rows,
        cols,
    )


# ============================================================
# SAMPLE VALID PIXELS
# ============================================================

def sample_pixels(
    rows,
    cols,
    latitude,
    longitude,
):

    total_pixels = len(rows)

    print(
        "===== ML PIXEL SAMPLING ====="
    )

    print(
        f"Available valid pixels: "
        f"{total_pixels:,}"
    )

    if total_pixels <= MAX_ML_SAMPLES:

        print(
            "✓ Total is within the ML sample limit."
        )

        print(
            f"Using all {total_pixels:,} pixels."
        )

        print()

        return (
            rows,
            cols,
            latitude,
            longitude,
        )

    # --------------------------------------------------------
    # Random sampling.
    # --------------------------------------------------------

    print(
        f"Sampling {MAX_ML_SAMPLES:,} "
        "representative pixels..."
    )

    rng = np.random.default_rng(
        RANDOM_SEED
    )

    selected_indices = (
        rng.choice(
            total_pixels,
            size=MAX_ML_SAMPLES,
            replace=False,
        )
    )

    rows = rows[
        selected_indices
    ]

    cols = cols[
        selected_indices
    ]

    latitude = latitude[
        selected_indices
    ]

    longitude = longitude[
        selected_indices
    ]

    print(
        "✓ Sampling completed."
    )

    print(
        f"Selected pixels: "
        f"{len(rows):,}"
    )

    print()

    return (
        rows,
        cols,
        latitude,
        longitude,
    )


# ============================================================
# CREATE ML DATASET
# ============================================================

def create_ml_dataset(
    bands,
    features,
    latitude,
    longitude,
    rows,
    cols,
):

    print_section(
        "CREATING ML-READY DATASET"
    )

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Sampling already happened before this function.
    #
    # Therefore we never create a 120-million-row DataFrame.
    # --------------------------------------------------------

    print(
        "Extracting sampled pixel values..."
    )

    def extract(array):

        return np.asarray(
            array[
                rows,
                cols
            ],
            dtype=np.float32,
        )

    # --------------------------------------------------------
    # Create DataFrame.
    # --------------------------------------------------------

    data = {
        "latitude": np.asarray(
            latitude,
            dtype=np.float64,
        ),

        "longitude": np.asarray(
            longitude,
            dtype=np.float64,
        ),

        "B02": extract(
            bands["B02"]
        ),

        "B03": extract(
            bands["B03"]
        ),

        "B04": extract(
            bands["B04"]
        ),

        "B08": extract(
            bands["B08"]
        ),

        "B11": extract(
            bands["B11"]
        ),

        "B12": extract(
            bands["B12"]
        ),

        "ndvi": extract(
            features["ndvi"]
        ),

        "nbr": extract(
            features["nbr"]
        ),

        "swir_ratio": extract(
            features["swir_ratio"]
        ),

        "red_swir_ratio": extract(
            features["red_swir_ratio"]
        ),
    }

    dataframe = pd.DataFrame(
        data
    )

    # --------------------------------------------------------
    # Remove NaN / infinity.
    # --------------------------------------------------------

    dataframe.replace(
        [
            np.inf,
            -np.inf,
        ],
        np.nan,
        inplace=True,
    )

    before = len(
        dataframe
    )

    dataframe.dropna(
        inplace=True
    )

    after = len(
        dataframe
    )

    removed = (
        before - after
    )

    if removed > 0:

        print(
            f"Removed {removed:,} "
            "invalid rows."
        )

        print()

    dataframe.reset_index(
        drop=True,
        inplace=True,
    )

    # --------------------------------------------------------
    # Summary.
    # --------------------------------------------------------

    print(
        "===== ML DATASET ====="
    )

    print(
        f"Rows:    {len(dataframe):,}"
    )

    print(
        f"Columns: {len(dataframe.columns)}"
    )

    print()

    print(
        "Columns:"
    )

    for column in dataframe.columns:

        print(
            f"  ✓ {column}"
        )

    print()

    return dataframe


# ============================================================
# SAVE DATASET
# ============================================================

def save_dataset(
    dataframe
):

    PROCESSED_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Remove an old output before writing the new one.
    # --------------------------------------------------------

    if OUTPUT_CSV.exists():

        try:

            OUTPUT_CSV.unlink()

            print(
                "Removed previous "
                "sentinel2_features.csv."
            )

            print()

        except OSError as error:

            raise RuntimeError(
                "\nCould not remove the old "
                "sentinel2_features.csv.\n\n"
                "Make sure it is not open in Excel "
                "or another program.\n\n"
                f"Reason: {error}"
            )

    print(
        "Saving ML dataset..."
    )

    dataframe.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    print()

    print(
        "✓ Dataset saved:"
    )

    print(
        OUTPUT_CSV
    )

    print()

    return OUTPUT_CSV


# ============================================================
# SAVE PROCESSING METADATA
# ============================================================

def save_processing_metadata(
    scene_folder,
    band_files,
    reference_crs,
    width,
    height,
    total_valid_pixels,
    sampled_pixels,
    output_csv,
):

    metadata = {
        "scene": scene_folder.name,

        "scene_path": str(
            scene_folder
        ),

        "crs": str(
            reference_crs
        ),

        "reference_width": int(
            width
        ),

        "reference_height": int(
            height
        ),

        "total_valid_pixels": int(
            total_valid_pixels
        ),

        "sampled_ml_pixels": int(
            sampled_pixels
        ),

        "max_ml_samples": int(
            MAX_ML_SAMPLES
        ),

        "random_seed": int(
            RANDOM_SEED
        ),

        "valid_scl_classes": sorted(
            VALID_SCL_CLASSES
        ),

        "output_csv": str(
            output_csv
        ),

        "bands": {
            band: str(path)
            for band, path
            in band_files.items()
        },
    }

    PROCESSED_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        PROCESSING_METADATA_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            metadata,
            file,
            indent=2,
        )

    print(
        "✓ Processing metadata saved:"
    )

    print(
        PROCESSING_METADATA_FILE
    )

    print()


# ============================================================
# MAIN
# ============================================================

def main():

    print()

    print(
        "=" * 70
    )

    print(
        "S.I.H - REAL SENTINEL-2 GIS PREPROCESSING"
    )

    print(
        "=" * 70
    )

    print()

    # ========================================================
    # STEP 1
    # ========================================================

    scene_folder = (
        select_scene_folder()
    )

    # ========================================================
    # STEP 2
    # ========================================================

    band_files = (
        find_band_files(
            scene_folder
        )
    )

    # ========================================================
    # STEP 3
    # ========================================================

    (
        bands,
        scl,
        reference_crs,
        reference_transform,
        reference_width,
        reference_height,
    ) = load_and_align_bands(
        band_files
    )

    # ========================================================
    # STEP 4
    # ========================================================

    mask = create_scl_mask(
        scl
    )

    # ========================================================
    # STEP 5
    # ========================================================

    features = calculate_features(
        bands
    )

    # ========================================================
    # STEP 6
    # ========================================================

    (
        latitude,
        longitude,
        rows,
        cols,
    ) = create_coordinates(
        transform=reference_transform,
        crs=reference_crs,
        width=reference_width,
        height=reference_height,
        mask=mask,
    )

    total_valid_pixels = len(
        rows
    )

    # ========================================================
    # STEP 7
    # Sample BEFORE creating DataFrame.
    # ========================================================

    (
        rows,
        cols,
        latitude,
        longitude,
    ) = sample_pixels(
        rows=rows,
        cols=cols,
        latitude=latitude,
        longitude=longitude,
    )

    sampled_pixels = len(
        rows
    )

    # ========================================================
    # STEP 8
    # ========================================================

    dataframe = create_ml_dataset(
        bands=bands,
        features=features,
        latitude=latitude,
        longitude=longitude,
        rows=rows,
        cols=cols,
    )

    # ========================================================
    # STEP 9
    # ========================================================

    output_csv = save_dataset(
        dataframe
    )

    # ========================================================
    # STEP 10
    # ========================================================

    save_processing_metadata(
        scene_folder=scene_folder,
        band_files=band_files,
        reference_crs=reference_crs,
        width=reference_width,
        height=reference_height,
        total_valid_pixels=total_valid_pixels,
        sampled_pixels=sampled_pixels,
        output_csv=output_csv,
    )

    # ========================================================
    # FINAL REPORT
    # ========================================================

    print_section(
        "PIPELINE COMPLETE"
    )

    print(
        "Selected scene:"
    )

    print(
        scene_folder
    )

    print()

    print(
        "CRS:"
    )

    print(
        reference_crs
    )

    print()

    print(
        "Reference grid:"
    )

    print(
        f"{reference_width:,} × "
        f"{reference_height:,}"
    )

    print()

    print(
        "Total valid pixels:"
    )

    print(
        f"{total_valid_pixels:,}"
    )

    print()

    print(
        "ML pixels sampled:"
    )

    print(
        f"{sampled_pixels:,}"
    )

    print()

    print(
        "Final dataset rows:"
    )

    print(
        f"{len(dataframe):,}"
    )

    print()

    print(
        "Final dataset columns:"
    )

    print(
        f"{len(dataframe.columns)}"
    )

    print()

    print(
        "Output:"
    )

    print(
        output_csv
    )

    print()

    print(
        "✓ Sentinel-2 preprocessing completed."
    )

    print(
        "✓ ML dataset created successfully."
    )

    print(
        "✓ Dataset is ready for Person 1."
    )

    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "PROCESS INTERRUPTED BY USER."
        )
        print()

        raise SystemExit(1)

    except Exception as error:

        print()
        print(
            "=" * 70
        )

        print(
            "PIPELINE ERROR"
        )

        print(
            "=" * 70
        )

        print()

        print(
            f"{type(error).__name__}: {error}"
        )

        print()

        raise