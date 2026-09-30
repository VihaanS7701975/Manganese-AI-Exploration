import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

app = FastAPI(title="Manganese Prospectivity Engine")

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
# sample-derived Chennai run (data/processed/chennai/candidate_sites_sample.csv,
# 53 candidates from a deterministic 1-in-55 systematic spatial sample of the
# real 16.5M-row Chennai feature table -- see
# data/processed/chennai/SAMPLE_NOTE.json). Sample files keep *_sample.csv
# names and never overwrite canonical full-scene filenames.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = "t45que"
DATASET_PATHS = {
    "t45que": PROJECT_ROOT / "data" / "processed" / "candidate_sites.csv",
    "chennai": PROJECT_ROOT / "data" / "processed" / "chennai" / "candidate_sites_sample.csv",
}

CANDIDATES = {
    key: (pd.read_csv(path) if path.is_file() else pd.DataFrame())
    for key, path in DATASET_PATHS.items()
}

# Optional, purely additive "manganese evidence" layer (manganese_evidence.py
# output) -- diagnostic only, NOT a manganese-specific detector. Currently
# only exists for chennai (sample-derived, matching the sample candidate set);
# t45que has none, so its candidates keep returning
# exactly what they did before this field was introduced (manganese fields
# simply absent/null). Never modifies CANDIDATES or any existing field.
EVIDENCE_PATHS = {
    "chennai": PROJECT_ROOT / "data" / "processed" / "chennai" / "manganese_evidence_sample.csv",
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
def list_candidates(
    dataset: str = DEFAULT_DATASET, limit: int = 0, offset: int = 0
):
    """Every candidate site from the selected dataset's candidate_sites.csv,
    unmodified. `dataset` defaults to "t45que" so existing callers that
    don't pass it get exactly the original T45QUE candidates, unchanged.
    Optional `limit`/`offset` paginate the ranked rows (C2 scale handling);
    `limit` <= 0 returns all rows, preserving the exact previous default.
    `total` always reports the full dataset size regardless of paging."""
    key = _resolve_dataset(dataset)
    df = CANDIDATES[key]
    total = len(df)
    if limit > 0:
        df = df.iloc[max(offset, 0): max(offset, 0) + limit]
    records = json.loads(df.to_json(orient="records"))
    # Additive only: attach the optional manganese evidence fields per record
    # when a layer exists for this dataset; existing fields untouched.
    for rec in records:
        evidence = _manganese_evidence(key, rec.get("candidate_id"))
        if evidence:
            rec.update(evidence)
    return {
        "count": len(records),
        "total": total,
        "offset": max(offset, 0),
        "limit": limit,
        "candidates": records,
        "dataset": key,
    }


class AoiSearchQuery(BaseModel):
    # Which candidate dataset to search. Defaults to the active-dataset
    # convention used elsewhere in this module.
    dataset: str = DEFAULT_DATASET
    # Axis-aligned search box in WGS84 degrees (from a rectangle draw,
    # a place search, or a polygon's own bounds).
    bbox: Optional[dict] = None  # {lon_min, lat_min, lon_max, lat_max}
    # Polygon ring as [[lat, lon], ...] (from a polygon draw). When
    # present with >= 3 vertices, candidates are additionally tested
    # against the ring (ray-cast); the bbox is still applied first.
    polygon: Optional[list] = None
    # Cap on returned rows (rank order); total/count always reflect the
    # full in-AOI match regardless of this cap.
    limit: int = 50


def _point_in_ring(lat: float, lon: float, ring) -> bool:
    inside = False
    n = len(ring)
    for i in range(n):
        yi, xi = ring[i][0], ring[i][1]
        yj, xj = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if ((yi > lat) != (yj > lat)) and (
            lon < ((xj - xi) * (lat - yi) / (yj - yi) + xi)
        ):
            inside = not inside
    return inside


@app.get("/api/report.pdf")
def exploration_report_pdf(
    dataset: str = DEFAULT_DATASET,
    limit: int = 25,
    candidate_id: Optional[str] = None,
    bbox: Optional[str] = None,
):
    """Professional multi-page PDF exploration report (Task: full PDF).

    Assembled read-only from the same real payloads as /api/report,
    /api/temporal/persistence and /api/aoi/search, rendered server-side
    with matplotlib only (no new dependencies). Optional `candidate_id`
    features one candidate's ExplainableAI breakdown; optional `bbox`
    ("lon_min,lat_min,lon_max,lat_max") scopes the AOI-results section
    via the real aoi_search path. Unavailable images/sections are
    labelled, never fabricated."""
    try:
        from backend.report_pdf import render_exploration_pdf
    except ImportError:
        try:
            from report_pdf import render_exploration_pdf
        except ImportError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"PDF renderer unavailable: {exc}",
            )
    key = _resolve_dataset(dataset)
    rep = exploration_report(dataset=key, limit=limit)
    persist = temporal_persistence(dataset=key)

    selected = None
    if candidate_id:
        df = CANDIDATES[key]
        match = df.loc[df["candidate_id"] == candidate_id]
        if not match.empty:
            rec = json.loads(match.iloc[[0]].to_json(orient="records"))[0]
            evidence = _manganese_evidence(key, rec.get("candidate_id"))
            if evidence:
                rec.update(evidence)
            selected = rec

    aoi_result = None
    if bbox:
        try:
            parts = [float(x) for x in bbox.split(",")]
            if len(parts) != 4:
                raise ValueError
            lon_min, lat_min, lon_max, lat_max = parts
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="bbox must be lon_min,lat_min,lon_max,lat_max with numeric values.",
            )
        search = aoi_search(AoiSearchQuery(
            dataset=key,
            bbox={"lon_min": lon_min, "lat_min": lat_min,
                  "lon_max": lon_max, "lat_max": lat_max},
            limit=10,
        ))
        top = search.get("top") or {}
        aoi_result = {
            "count": search.get("count", 0),
            "top_id": top.get("candidate_id"),
            "top_rank": top.get("rank"),
            "top_score": top.get("rank_score"),
        }

    overlay_png = OVERLAYS_DIR / f"{key}_score_overlay.png"
    scenes = ((rep.get("imagery") or {}).get("scenes")) or []
    payload = {
        "dataset": key,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "candidate_count": rep.get("candidate_count", 0),
        "scene_summary": ("; ".join(
            f"{s.get('scene_id')} ({s.get('sensing_date') or 'date n/a'})"
            for s in scenes) or "none on disk"),
        "aoi": rep.get("aoi"),
        "imagery": rep.get("imagery"),
        "methodology": rep.get("methodology"),
        "rank_weights": rep.get("rank_weights"),
        "mineralization_weights": None,
        "sample_note": None,
        "candidates": rep.get("candidates") or [],
        "selected_candidate": selected,
        "aoi_result": aoi_result,
        "temporal": {
            "scenes": persist.get("scenes") or [],
            "summary": persist.get("summary") or {},
        },
        "overlay_path": str(overlay_png) if overlay_png.is_file() else None,
        "generated_note": rep.get("generated_note"),
        "limitations": rep.get("limitations"),
        "shortfall_note": rep.get("shortfall_note"),
    }
    try:
        from backend.temporal import MINERALIZATION_WEIGHTS
    except ImportError:
        try:
            from temporal import MINERALIZATION_WEIGHTS
        except ImportError:
            MINERALIZATION_WEIGHTS = None
    payload["mineralization_weights"] = MINERALIZATION_WEIGHTS
    if key == "chennai":
        payload["sample_note"] = (
            "Chennai candidates are derived from a deterministic 1-in-55 "
            "systematic spatial sample of the real scene feature table "
            "(see data/processed/chennai/SAMPLE_NOTE.json) — sample "
            "results, not a full-scene run.")
    try:
        pdf_bytes = render_exploration_pdf(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"PDF rendering failed: {exc}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition":
                 f"attachment; filename=exploration_report_{key}.pdf"},
    )


@app.post("/api/aoi/search")
def aoi_search(query: AoiSearchQuery):
    """Candidates of one dataset filtered to a user-drawn AOI.

    Read-only over the already-loaded candidate table: bbox pre-filter,
    then optional polygon ring test. Returns matches in rank order with
    an explicit empty state (count 0) when nothing falls inside --
    never a fabricated result."""
    key = _resolve_dataset(query.dataset)
    df = CANDIDATES[key]
    if df.empty:
        return {
            "dataset": key, "count": 0, "total": 0,
            "candidates": [], "top": None,
            "note": "No candidate data for this dataset yet.",
        }
    if not query.bbox and not query.polygon:
        raise HTTPException(
            status_code=400,
            detail="Provide 'bbox' ({lon_min, lat_min, lon_max, lat_max}) and/or 'polygon' ([[lat, lon], ...]).",
        )
    work = df
    if query.bbox:
        try:
            b = {k: float(query.bbox[k]) for k in ("lon_min", "lat_min", "lon_max", "lat_max")}
        except (KeyError, TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="bbox must be {lon_min, lat_min, lon_max, lat_max} with numeric values.",
            )
        if b["lon_min"] >= b["lon_max"] or b["lat_min"] >= b["lat_max"]:
            raise HTTPException(
                status_code=400,
                detail="bbox must satisfy lon_min < lon_max and lat_min < lat_max.",
            )
        work = work[
            (work["centroid_longitude"] >= b["lon_min"])
            & (work["centroid_longitude"] <= b["lon_max"])
            & (work["centroid_latitude"] >= b["lat_min"])
            & (work["centroid_latitude"] <= b["lat_max"])
        ]
    ring = None
    if query.polygon:
        if len(query.polygon) < 3:
            raise HTTPException(
                status_code=400,
                detail="polygon needs at least 3 vertices.",
            )
        ring = query.polygon
        mask = [
            _point_in_ring(float(la), float(lo), ring)
            for lo, la in zip(work["centroid_longitude"], work["centroid_latitude"])
        ]
        work = work[pd.Series(mask, index=work.index)]
    total = len(work)
    ranked = work.sort_values("rank").head(max(query.limit, 0)) if query.limit > 0 else work.sort_values("rank")
    records = json.loads(ranked.to_json(orient="records"))
    for rec in records:
        evidence = _manganese_evidence(key, rec.get("candidate_id"))
        if evidence:
            rec.update(evidence)
    top = records[0] if records else None
    return {
        "dataset": key,
        "count": total,
        "total": total,
        "limit": query.limit,
        "candidates": records,
        "top": top,
        "bbox": query.bbox,
        "polygon_vertices": len(ring) if ring else 0,
    }


@app.post("/api/predict")
def predict_reserve(query: CoordinateQuery):
    # Same response shape as before (frontend contract preserved). The
    # confidence/classification/nearest_candidate fields are now grounded
    # in the nearest real candidate site from the selected dataset instead
    # of a random number; ore_type_detected and shortfall_metrics are not
    # produced by any stage of the recovered pipeline (no ore-mineralogy or
    # tonnage/yield model exists for either dataset), so they remain static
    # illustrative reference-scenario values. They are explicitly labelled
    # as such in the response (estimate_kind/note) and must never be read
    # as ML predictions or measured reserves.
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
        "classification": "High Potential Target" if confidence > 0.8 else "Medium Potential",
        "ore_type_detected": "Pyrolusite / Braunite Complex (indicative reference label, not an assay result)",
        "shortfall_metrics": {
            "estimate_kind": "illustrative_capacity_scenario",
            "estimated_yield_tons": 145000,
            "annual_deficit_reduction_pct": 14.8,
            "extraction_feasibility_score": 8.5,
            "note": "Static reference-scenario values (tons) for demo context; not an ML prediction or measured reserve.",
        },
        "dataset": key,
        "nearest_candidate": nearest_candidate,
        "estimate_kind": "illustrative_capacity_scenario",
        "scenario_note": (
            "Reference-scenario values for demo context only: no ore-mineralogy "
            "or tonnage/yield model exists in this project, so these numbers are "
            "not ML predictions and not measured reserves."
        ),
    }


# ---------------------------------------------------------------------------
# C1 -- STAC / raster-sampling integration (previously missing).
# Thin wrappers over the existing gis_module code; no new acquisition logic.
# Imports are lazy so this module still loads in minimal environments where
# rasterio / pystac / planetary-computer are not installed -- in that case
# the routes report "unavailable" instead of failing at startup.
# ---------------------------------------------------------------------------

class SampleQuery(BaseModel):
    lat: float
    lon: float
    raster_path: Optional[str] = None


class PipelineRunRequest(BaseModel):
    # Geographic bounding box [min_lon, min_lat, max_lon, max_lat].
    bbox: list[float]
    date_range: str = "2024-01-01/2024-05-30"
    max_cloud: int = 15


@app.get("/api/scenes")
def list_scenes():
    """Preprocessed satellite scenes visible to gis_module/sampler.py.

    Read-only: lists metadata for every *_preprocessed.tif under
    data/processed/. Empty until the preprocessing pipeline has been run."""
    try:
        from gis_module.sampler import get_available_scenes
    except ImportError:
        return {"count": 0, "scenes": [], "status": "sampler_unavailable"}
    scenes = get_available_scenes()
    return {
        "count": len(scenes),
        "scenes": scenes,
        "status": "ready" if scenes else "no_preprocessed_scenes",
    }


@app.get("/api/raster/metadata")
def raster_metadata():
    """Metadata of the latest preprocessed raster scene, if any.

    Read-only: reports the newest *_preprocessed.tif. No scene is present
    until the preprocessing pipeline has been run."""
    try:
        from gis_module.sampler import get_available_scenes
    except ImportError:
        return {"status": "sampler_unavailable", "scene": None}
    scenes = get_available_scenes()
    if not scenes:
        return {"status": "no_preprocessed_scenes", "scene": None}
    return {"status": "ready", "scene": scenes[0], "count": len(scenes)}


@app.post("/api/sample")
def sample_raster(query: SampleQuery):
    """Sample the preprocessed raster at one coordinate.

    Read-only against local GeoTIFFs via
    gis_module/sampler.sample_raster_at_coordinates -- performs no download
    and runs no ML; outside the active scene it returns the sampler's own
    regional-estimate fallback."""
    try:
        from gis_module.sampler import sample_raster_at_coordinates
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="Raster sampler unavailable: gis_module dependencies are not installed.",
        )
    return sample_raster_at_coordinates(
        lat=query.lat, lon=query.lon, raster_path=query.raster_path
    )


@app.post("/api/pipeline/run")
def pipeline_run(req: PipelineRunRequest):
    """Run the existing STAC acquisition + preprocessing pipeline.

    Validates the request, then delegates to
    gis_module/pipeline.run_pipeline (Planetary Computer STAC search,
    band download, resampling, cloud masking, index extraction). This is
    network- and compute-heavy by nature: it downloads real satellite data
    and must only be invoked deliberately, never as part of validation."""
    if len(req.bbox) != 4:
        raise HTTPException(
            status_code=400,
            detail="bbox must be [min_lon, min_lat, max_lon, max_lat].",
        )
    try:
        from gis_module.pipeline import run_pipeline
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="STAC pipeline unavailable: gis_module dependencies are not installed.",
        )
    try:
        return run_pipeline(
            bbox=list(req.bbox),
            date_range=req.date_range,
            max_cloud=req.max_cloud,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


# ---------------------------------------------------------------------------
# F1/F6/F12 -- workflow status, multi-date observations, exploration report.
# Read-only assembly over files on disk; honest empty states when the
# processing chain has not been run. No downloads, no ML execution.
# ---------------------------------------------------------------------------

try:
    from backend.temporal import (
        LIMITATIONS,
        METHODOLOGY,
        RANK_WEIGHTS,
        compute_persistence,
        list_observations,
        parse_safe_date,
    )
except ImportError:  # backend run as top-level script directory
    from temporal import (
        LIMITATIONS,
        METHODOLOGY,
        RANK_WEIGHTS,
        compute_persistence,
        list_observations,
        parse_safe_date,
    )

# Raw download roots per dataset (mirrors load_satellite_data --out-root
# convention) and per-dataset processed stage files (mirrors
# preprocess_satellite OUT_DIR, render_score_overlay DATASETS).
RAW_ROOTS = {
    "t45que": PROJECT_ROOT / "data" / "raw" / "satellite_images",
    "chennai": PROJECT_ROOT / "data" / "raw" / "chennai",
}
PROCESSED_ROOTS = {
    "t45que": PROJECT_ROOT / "data" / "processed",
    "chennai": PROJECT_ROOT / "data" / "processed" / "chennai",
}
def _stage_paths(key: str):
    proot = PROCESSED_ROOTS[key]
    if key == "t45que":
        overlay = PROJECT_ROOT / "data" / "processed" / "overlays" / "t45que_score_overlay.png"
        anomalies = proot / "manganese_anomalies.csv"
        mineralization = proot / "mineralization_scores.csv"
    else:
        # Chennai: full-scene ml_features.csv exists (16.5M rows); the
        # downstream anomaly/mineralization stages were run on a documented
        # 1-in-55 systematic sample only (see SAMPLE_NOTE.json), so the
        # sample filenames are the honest availability signal here.
        overlay = PROJECT_ROOT / "data" / "processed" / "overlays" / "chennai_score_overlay.png"
        anomalies = proot / "manganese_anomalies_sample.csv"
        mineralization = proot / "mineralization_scores_sample.csv"
    return {
        "imagery_downloaded": None,
        "preprocessed": proot / "cleaned_images" / "B02.tif",
        "preprocessed_aoi": proot / "cleaned_images_aoi" / "B02.tif",
        "features": proot / "ml_features.csv",
        "anomalies": anomalies,
        "mineralization": mineralization,
        "candidates": DATASET_PATHS[key],
        "overlay": overlay,
    }


@app.get("/api/workflow/status")
def workflow_status(dataset: str = DEFAULT_DATASET):
    """Per-stage availability for the one-click exploration workflow (F1).

    Reports which pipeline stages have outputs on disk for the dataset so
    the UI can show real progress and honest next steps. Pure existence
    checks -- no computation, no downloads."""
    key = _resolve_dataset(dataset)
    raw_root = RAW_ROOTS[key]
    safes = sorted(p.name for p in raw_root.glob("*.SAFE")) if raw_root.is_dir() else []
    stages = {"imagery_downloaded": len(safes) > 0}
    paths = _stage_paths(key)
    for name, path in paths.items():
        if name == "imagery_downloaded":
            continue
        stages[name] = bool(path and path.is_file())
    return {
        "dataset": key,
        "stages": stages,
        "scenes": [
            {"scene_id": s, "sensing_date": parse_safe_date(s)} for s in safes
        ],
        "candidate_count": int(len(CANDIDATES[key])),
        "ready_for_demo": stages["candidates"],
    }


@app.get("/api/temporal/scenes")
def temporal_scenes():
    """Multi-date observation registry (F6): raw scenes + processed
    candidate availability per dataset. Missing files reported as missing."""
    return {
        "observations": list_observations(PROJECT_ROOT, DATASET_PATHS, RAW_ROOTS),
        "note": "Persistence across dates is remote-sensing supporting evidence, "
        "not geological confirmation of manganese.",
    }


@app.get("/api/temporal/persistence")
def temporal_persistence(dataset: str = DEFAULT_DATASET, threshold_m: float = 150.0):
    """Cross-observation persistence for one dataset's candidates (F6).

    Matches each candidate of the requested dataset against every other
    loaded dataset/observation within threshold_m metres. Supporting
    scenes are remote-sensing evidence ONLY, never geological
    confirmation. Honestly reports single-observation state when no other
    observation overlaps."""
    key = _resolve_dataset(dataset)
    df = CANDIDATES[key]
    if df.empty:
        return {
            "dataset": key,
            "threshold_m": threshold_m,
            "scenes": [],
            "persistent": [],
            "summary": {"total": 0, "persistent_count": 0,
                        "note": "No processed candidates for this dataset yet."},
        }
    # All non-empty datasets act as observations (t45que, chennai, ...).
    # compute_persistence matches across keys; we then scope the per-row
    # list to the requested dataset while keeping cross-scene support.
    dfs = {k: v for k, v in CANDIDATES.items() if v is not None and not v.empty}
    result = compute_persistence(dfs, threshold_m=threshold_m)
    scoped = [p for p in result.get("persistent", []) if p.get("scene") == key]
    pcount = sum(1 for p in scoped if p.get("persistent"))
    summary = {
        "total": len(scoped),
        "persistent_count": pcount,
    }
    if len(result.get("scenes", [])) < 2:
        summary["single_scene_note"] = (
            "Only one observation available; persistence needs 2+ dates "
            "over the same ground."
        )
    elif pcount == 0:
        summary["note"] = (
            "No cross-observation matches within threshold; observations "
            "cover different ground and/or different dates."
        )
    result["persistent"] = scoped
    result["summary"] = summary
    result["dataset"] = key
    return result


@app.get("/api/report")
def exploration_report(dataset: str = DEFAULT_DATASET, limit: int = 25):
    """Automatic exploration report payload (F12): AOI, imagery, dates,
    methodology, ranked candidates, evidence, limitations. All values come
    from files on disk or static methodology notes; illustrative figures
    stay labelled as such."""
    key = _resolve_dataset(dataset)
    df = CANDIDATES[key]
    aoi = AOI_BOUNDS[key]
    obs = list_observations(PROJECT_ROOT, {key: DATASET_PATHS[key]}, RAW_ROOTS)
    top = df.sort_values("rank_score", ascending=False).head(max(limit, 0)) \
        if not df.empty and "rank_score" in df.columns else df.head(0)
    cand_rows = json.loads(top.to_json(orient="records"))
    for rec in cand_rows:
        evidence = _manganese_evidence(key, rec.get("candidate_id"))
        if evidence:
            rec.update(evidence)
    return {
        "dataset": key,
        "generated_note": "Assembled read-only from pipeline outputs on disk; "
        "regenerate after re-running the chain.",
        "aoi": aoi,
        "aoi_note": "Bounds of this dataset's own candidates plus margin; "
        "not a mineral-prospectivity boundary." if aoi else None,
        "imagery": obs[0] if obs else None,
        "methodology": METHODOLOGY,
        "rank_weights": RANK_WEIGHTS,
        "candidate_count": int(len(df)),
        "candidates": cand_rows,
        "shortfall_basis": "illustrative_capacity_scenario",
        "shortfall_note": "Yield/deficit/feasibility figures are static "
        "reference-scenario values for demo context, not ML predictions.",
        "limitations": LIMITATIONS,
    }


# ---------------------------------------------------------------------------
# Desktop-packaging entrypoint (Electron/PyInstaller glue only -- no
# scientific logic). Lets the packaged backend serve itself
# (`manganese-backend.exe --port 8000`) instead of requiring
# `python -m uvicorn backend.main:app`. `import backend.main` behavior is
# unchanged.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    import uvicorn

    _parser = argparse.ArgumentParser(description="Serve the Manganese AI API.")
    _parser.add_argument("--host", default="127.0.0.1")
    _parser.add_argument("--port", type=int, default=8000)
    _args = _parser.parse_args()
    uvicorn.run(app, host=_args.host, port=_args.port, log_level="warning")
