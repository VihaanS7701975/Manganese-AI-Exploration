"""Multi-date / time-series support structures (F6) plus shared methodology
constants used by the exploration report (F12).

All functions are read-only over files already on disk and degrade to
honest empty results when processed data has not been generated yet.
Only pandas (already a backend dependency) is required.

Persistence model: a candidate in one observation is "persistent" when
another observation contains a candidate within `threshold_m` metres
(equirectangular approximation -- adequate for the <=150 m scales used
here; the DBSCAN stage itself uses exact UTM projection). Persistence
across dates is remote-sensing supporting evidence ONLY, never
geological confirmation of manganese.
"""

import math
import re
from pathlib import Path

import pandas as pd

# Mirrors src/ml/candidate_detection.py ranking weights (single reference
# copy for reporting; the detection module remains the authority).
RANK_WEIGHTS = {
    "strength": 0.35,
    "density": 0.25,
    "mineralization": 0.40,
}

# Mirrors src/ml/mineralization_scoring.py reward/penalty weights.
MINERALIZATION_WEIGHTS = {
    "reward": {"anomaly": 0.40, "alteration": 0.35, "bare_earth": 0.25},
    "penalty": {"vegetation": 0.10, "water": 0.05, "builtup": 0.05},
}

METHODOLOGY = {
    "features": "B02,B03,B04,B08,B11,B12 + NDVI/NDWI/NDBI/BSI + FE_OXIDE_ND/CLAY_MINERAL_ND/FERROUS_ND",
    "anomaly": "IsolationForest (200 trees), score = -decision_function, percentile 0-100",
    "mineralization": "0-100 reward-minus-penalty percentile blend (see MINERALIZATION_WEIGHTS)",
    "detection": "DBSCAN over UTM metres (default top 1% pixels, eps 150 m, min_samples 5)",
    "ranking": "rank_score = 0.35*strength_pct + 0.25*density_pct + 0.40*mineralization_pct",
    "sources": {
        "ranking_weights": "src/ml/candidate_detection.py",
        "mineralization_weights": "src/ml/mineralization_scoring.py",
        "anomaly_model": "src/ml/anomaly_detection.py",
    },
}

LIMITATIONS = [
    "Unsupervised screening only: no manganese ground-truth labels exist in this project.",
    "Anomaly/mineralization scores are spectral-outlier percentiles, not manganese assays.",
    "Candidate zones are exploration targets requiring geological / ground-truth validation.",
    "Yield, deficit-reduction and feasibility figures are illustrative reference scenarios, not predictions.",
    "Persistence across dates is remote-sensing supporting evidence, not geological confirmation.",
]

# e.g. S2B_MSIL2A_20260625T044659_... -> 2026-06-25
SAFE_DATE_RE = re.compile(r"S2[AB]_MSIL2A_(\d{4})(\d{2})(\d{2})T")
# Fallback-scene naming (e.g. S2C_44PMV_20260114_0_L2A -> 2026-01-14):
# any S2?_<...>_YYYYMMDD fragment.
SAFE_DATE_FALLBACK_RE = re.compile(r"S2[A-Z]_.*?(\d{4})(\d{2})(\d{2})")

CANDIDATE_COLUMNS = [
    "candidate_id", "rank", "centroid_longitude", "centroid_latitude",
    "rank_score", "mineralization_percentile", "anomaly_percentile",
    "strength_percentile", "density_percentile", "pixel_count", "area_m2",
]


def parse_safe_date(safe_name: str):
    m = SAFE_DATE_RE.search(safe_name or "")
    if not m:
        m = SAFE_DATE_FALLBACK_RE.search(safe_name or "")
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _read_candidates(path: Path) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame()
    try:
        df = pd.read_csv(path)
    except Exception:
        return pd.DataFrame()
    keep = [c for c in CANDIDATE_COLUMNS if c in df.columns]
    return df[keep] if keep else pd.DataFrame()


def list_observations(project_root: Path, datasets: dict, raw_roots: dict) -> list:
    """One record per known dataset: raw SAFE scenes found + processed
    candidate availability. Never fabricates: missing files are reported
    as missing."""
    out = []
    for key in datasets:
        cand_path = datasets[key]
        df = _read_candidates(cand_path)
        scenes = []
        raw_root = raw_roots.get(key)
        if raw_root and raw_root.is_dir():
            for safe in sorted(raw_root.glob("*.SAFE")):
                mtd = safe / "MTD_MSIL2A.xml"
                scenes.append({
                    "scene_id": safe.name,
                    "sensing_date": parse_safe_date(safe.name),
                    "metadata_present": mtd.is_file(),
                })
        obs = {
            "dataset": key,
            "candidates_available": not df.empty,
            "candidate_count": int(len(df)),
            "candidates_path": str(cand_path),
            "scenes": scenes,
        }
        dates = sorted(s for s in (x["sensing_date"] for x in scenes) if s)
        obs["observation_dates"] = dates
        obs["observation_count"] = len(dates)
        out.append(obs)
    return out


def _to_metres(df: pd.DataFrame):
    """Equirectangular lon/lat -> local metres (adequate for ~100 m matching)."""
    lat0 = math.radians(float(df["centroid_latitude"].mean()))
    kx = 111320.0 * math.cos(lat0)
    ky = 110540.0
    return (
        df["centroid_longitude"].to_numpy() * kx,
        df["centroid_latitude"].to_numpy() * ky,
    )


def compute_persistence(dfs: dict, threshold_m: float = 150.0) -> dict:
    """Cross-date persistence for candidate sets keyed by scene/dataset id.

    For every candidate in every scene, finds the nearest candidate in each
    other scene; a match within threshold_m counts that scene as supporting.
    Returns per-scene match lists + summary. Empty in/out handled honestly.
    """
    keys = [k for k, df in dfs.items() if df is not None and not df.empty]
    if len(keys) < 1:
        return {"scenes": keys, "threshold_m": threshold_m,
                "persistent": [], "summary": {"total": 0, "persistent_count": 0}}
    coords = {k: _to_metres(dfs[k]) for k in keys}
    persistent = []
    for k in keys:
        df = dfs[k]
        xs, ys = coords[k]
        others = [o for o in keys if o != k]
        for i, row in df.iterrows():
            supporting = []
            for o in others:
                ox, oy = coords[o]
                d2 = (ox - xs[i]) ** 2 + (oy - ys[i]) ** 2
                best = float(d2.min()) ** 0.5
                if best <= threshold_m:
                    supporting.append({"scene": o, "distance_m": round(best, 1)})
            persistent.append({
                "scene": k,
                "candidate_id": str(row["candidate_id"]),
                "rank": int(row["rank"]),
                "rank_score": float(row["rank_score"]),
                "centroid_longitude": float(row["centroid_longitude"]),
                "centroid_latitude": float(row["centroid_latitude"]),
                "supporting_scenes": supporting,
                "support_count": len(supporting),
                "persistent": len(supporting) > 0,
            })
    total = len(persistent)
    pcount = sum(1 for p in persistent if p["persistent"])
    return {
        "scenes": keys,
        "threshold_m": threshold_m,
        "persistent": persistent,
        "summary": {
            "total": total,
            "persistent_count": pcount,
            "single_scene_note": "Only one observation available; persistence needs 2+ dates."
            if len(keys) < 2 else None,
        },
    }
