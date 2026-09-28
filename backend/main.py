import json
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Manganese Reserve & Shortfall Engine")

# Allow the frontend to communicate with this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Each candidate_sites.csv is the small ranked output of
# candidate_detection.py -- safe to load once at startup. The upstream
# multi-million-row intermediates (ml_features.csv, manganese_anomalies.csv,
# mineralization_scores.csv) are never read here.
#
# "t45que" is the original/default dataset (unchanged path, unchanged
# behavior for any caller that doesn't pass a dataset). "chennai" is the
# AOI-clipped, geographically-validated Chennai run
# (data/processed/chennai/candidate_sites.csv, 689 candidates) -- NOT the
# earlier stale 3,549-candidate pre-clip result, which lived at the same
# path before being regenerated and is no longer on disk.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = "t45que"
DATASET_PATHS = {
    "t45que": PROJECT_ROOT / "data" / "processed" / "candidate_sites.csv",
    "chennai": PROJECT_ROOT / "data" / "processed" / "chennai" / "candidate_sites.csv",
}

CANDIDATES = {
    key: (pd.read_csv(path) if path.is_file() else pd.DataFrame())
    for key, path in DATASET_PATHS.items()
}

# Optional, purely additive "manganese evidence" layer (manganese_evidence.py
# output) -- diagnostic only, NOT a manganese-specific detector. Currently
# only exists for chennai; t45que has none, so its candidates keep returning
# exactly what they did before this field was introduced (manganese fields
# simply absent/null). Never modifies CANDIDATES or any existing field.
EVIDENCE_PATHS = {
    "chennai": PROJECT_ROOT / "data" / "processed" / "chennai" / "manganese_evidence.csv",
}
EVIDENCE = {
    key: (pd.read_csv(path) if path.is_file() else None)
    for key, path in EVIDENCE_PATHS.items()
}

# Pre-rendered RED/YELLOW/GREEN pixel-score overlay PNGs (see
# src/data_processing/render_score_overlay.py) -- purely a static asset
# read/served here, same pattern as CANDIDATES/EVIDENCE above. This endpoint
# does not compute, re-run, or touch any ML/ranking stage; it only reads the
# already-generated <dataset>_score_overlay.json sidecar (real bounds/pixel
# counts from that PNG's own georeferencing) and serves the PNG itself.
OVERLAYS_DIR = PROJECT_ROOT / "data" / "processed" / "overlays"
if OVERLAYS_DIR.is_dir():
    app.mount("/overlays", StaticFiles(directory=OVERLAYS_DIR), name="overlays")


def _manganese_evidence(dataset_key: str, candidate_id: str):
    """Look up the optional manganese evidence row for one candidate.
    Returns None if no evidence layer exists for this dataset (e.g. t45que)."""
    df = EVIDENCE.get(dataset_key)
    if df is None:
        return None
    match = df.loc[df["candidate_id"] == candidate_id]
    if match.empty:
        return None
    row = match.iloc[0]
    return {
        "manganese_prospectivity_score": float(row["manganese_prospectivity_score"]),
        "geological_belt_context": str(row["geological_belt_context"]),
        "limitation": str(row["limitation"]),
    }

# Bounding box each dataset's own candidates actually fall in, plus a small
# margin. The frontend's hardcoded MANGANESE_BELTS/EXTRA_LOCATIONS span
# sites hundreds of km apart across India; without this check, a click near
# e.g. Balaghat or Sandur would silently return whichever candidate happens
# to be least far away, mislabeled as if it applied there.
AOI_MARGIN_DEG = 0.1


def _aoi_bounds(df: pd.DataFrame):
    if df.empty:
        return None
    return {
        "lon_min": float(df["centroid_longitude"].min()) - AOI_MARGIN_DEG,
        "lon_max": float(df["centroid_longitude"].max()) + AOI_MARGIN_DEG,
        "lat_min": float(df["centroid_latitude"].min()) - AOI_MARGIN_DEG,
        "lat_max": float(df["centroid_latitude"].max()) + AOI_MARGIN_DEG,
    }


AOI_BOUNDS = {key: _aoi_bounds(df) for key, df in CANDIDATES.items()}


def _resolve_dataset(dataset: str) -> str:
    """Normalize and validate a dataset/scene identifier. Defaults to the
    original t45que dataset so any caller that omits it keeps the exact
    pre-existing behavior."""
    key = (dataset or DEFAULT_DATASET).strip().lower()
    if key not in DATASET_PATHS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown dataset '{dataset}'. Valid options: {sorted(DATASET_PATHS.keys())}",
        )
    return key


class CoordinateQuery(BaseModel):
    lat: float
    lon: float
    # Which candidate dataset/AOI to query against. Optional and defaults to
    # the original t45que dataset, so existing callers that don't send this
    # field get byte-identical behavior to before.
    dataset: str = DEFAULT_DATASET


@app.get("/")
def health_check():
    return {"status": "Backend running", "service": "SIH26009"}


@app.get("/api/pixel_overlay")
def pixel_overlay(dataset: str = DEFAULT_DATASET):
    """Metadata + image URL for the pre-rendered RED/YELLOW/GREEN pixel-score
    overlay (src/data_processing/render_score_overlay.py). Purely reads the
    already-generated <dataset>_score_overlay.json sidecar -- no ML/ranking
    computation happens here, same as /api/candidates reading
    candidate_sites.csv unmodified."""
    key = _resolve_dataset(dataset)
    json_path = OVERLAYS_DIR / f"{key}_score_overlay.json"
    if not json_path.is_file():
        return {"dataset": key, "available": False}
    meta = json.loads(json_path.read_text())
    meta["available"] = True
    meta["image_url"] = f"/overlays/{meta['png']}"
    return meta


@app.get("/api/candidates")
def list_candidates(dataset: str = DEFAULT_DATASET):
    """Every candidate site from the selected dataset's candidate_sites.csv,
    unmodified. `dataset` defaults to "t45que" so existing callers that
    don't pass it get exactly the original T45QUE candidates, unchanged."""
    key = _resolve_dataset(dataset)
    df = CANDIDATES[key]
    records = json.loads(df.to_json(orient="records"))
    # Additive only: attach the optional manganese evidence fields per record
    # when a layer exists for this dataset; existing fields untouched.
    for rec in records:
        evidence = _manganese_evidence(key, rec.get("candidate_id"))
        if evidence:
            rec.update(evidence)
    return {"count": len(records), "candidates": records, "dataset": key}


@app.post("/api/predict")
def predict_reserve(query: CoordinateQuery):
    # Same response shape as before (frontend contract preserved). The
    # confidence/classification/nearest_candidate fields are now grounded
    # in the nearest real candidate site from the selected dataset instead
    # of a random number; ore_type_detected and shortfall_metrics are not
    # produced by any stage of the recovered pipeline (no ore-mineralogy or
    # tonnage/yield model exists for either dataset), so they remain the
    # same static placeholder values as before.
    key = _resolve_dataset(query.dataset)
    df = CANDIDATES[key]
    aoi = AOI_BOUNDS[key]

    if df.empty:
        return {
            "location": {"lat": query.lat, "lon": query.lon},
            "manganese_confidence": 0.0,
            "classification": "No Data",
            "ore_type_detected": "Unknown",
            "shortfall_metrics": {
                "estimated_yield_tons": 0,
                "annual_deficit_reduction_pct": 0.0,
                "extraction_feasibility_score": 0.0,
            },
            "dataset": key,
        }

    in_aoi = (
        aoi["lon_min"] <= query.lon <= aoi["lon_max"] and aoi["lat_min"] <= query.lat <= aoi["lat_max"]
    )
    if not in_aoi:
        return {
            "location": {"lat": query.lat, "lon": query.lon},
            "manganese_confidence": 0.0,
            "classification": "Outside Surveyed Area",
            "ore_type_detected": f"N/A -- no {key.upper()} candidate data for this location",
            "shortfall_metrics": {
                "estimated_yield_tons": 0,
                "annual_deficit_reduction_pct": 0.0,
                "extraction_feasibility_score": 0.0,
            },
            "nearest_candidate": None,
            "dataset": key,
        }

    dist2 = (
        (df["centroid_longitude"] - query.lon) ** 2
        + (df["centroid_latitude"] - query.lat) ** 2
    )
    site = df.loc[dist2.idxmin()]

    confidence = round(float(site["mineralization_percentile"]) / 100.0, 4)

    nearest_candidate = {
        "candidate_id": str(site["candidate_id"]),
        "rank": int(site["rank"]),
        "total_candidates": int(len(df)),
        "centroid_longitude": float(site["centroid_longitude"]),
        "centroid_latitude": float(site["centroid_latitude"]),
        "rank_score": float(site["rank_score"]),
        "mineralization_percentile": float(site["mineralization_percentile"]),
        # Additional columns already present in candidate_sites.csv
        # (candidate_detection.py output), exposed as-is for the
        # Explainable AI panel -- no new computation happens here.
        "mean_anomaly_score": float(site["mean_anomaly_score"]),
        "max_anomaly_score": float(site["max_anomaly_score"]),
        "anomaly_percentile": float(site["anomaly_percentile"]),
        "mean_mineralization_score": float(site["mean_mineralization_score"]),
        "max_mineralization_score": float(site["max_mineralization_score"]),
        "strength_percentile": float(site["strength_percentile"]),
        "density_percentile": float(site["density_percentile"]),
        "pixel_count": int(site["pixel_count"]),
        "area_m2": float(site["area_m2"]),
        # manganese_prospectivity_score/geological_belt_context/limitation:
        # None unless an optional manganese_evidence.csv exists for this
        # dataset (currently chennai only) -- see _manganese_evidence().
        # Diagnostic only; NOT used in rank_score/mineralization_score above.
        "manganese_prospectivity_score": None,
        "geological_belt_context": None,
        "manganese_evidence_limitation": None,
    }
    evidence = _manganese_evidence(key, nearest_candidate["candidate_id"])
    if evidence:
        nearest_candidate["manganese_prospectivity_score"] = evidence["manganese_prospectivity_score"]
        nearest_candidate["geological_belt_context"] = evidence["geological_belt_context"]
        nearest_candidate["manganese_evidence_limitation"] = evidence["limitation"]

    return {
        "location": {"lat": query.lat, "lon": query.lon},
        "manganese_confidence": confidence,
        "classification": "High Potential Reserve" if confidence > 0.8 else "Medium Potential",
        "ore_type_detected": "Pyrolusite / Braunite Complex",
        "shortfall_metrics": {
            "estimated_yield_tons": 145000,
            "annual_deficit_reduction_pct": 14.8,
            "extraction_feasibility_score": 8.5,
        },
        "dataset": key,
        "nearest_candidate": nearest_candidate,
    }
