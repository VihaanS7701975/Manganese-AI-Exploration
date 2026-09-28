"""
Comprehensive Unit & Integration Test Suite for GIS & Satellite Pipeline Modules
"""

import os
import sys
from pathlib import Path
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from gis_module.sampler import (
    sample_raster_at_coordinates,
    get_available_scenes,
    find_latest_processed_geotiff
)
from gis_module.pipeline import run_pipeline
from backend.main import app


def test_geospatial_sampler():
    print("[*] Testing Geospatial Sampler...")
    scenes = get_available_scenes()
    assert len(scenes) > 0, "No available preprocessed scenes found!"
    print(f"    Found {len(scenes)} preprocessed scene(s). Latest: {scenes[0]['scene_id']}")

    # Sample inside Balaghat belt
    res = sample_raster_at_coordinates(lat=21.8129, lon=80.1849)
    assert res["is_live_satellite_sample"] is True
    assert "spectral_features" in res
    assert res["spectral_features"]["b04_red"] is not None
    assert res["spectral_features"]["b08_nir"] is not None
    assert res["spectral_features"]["ndvi"] is not None
    assert res["manganese_confidence"] > 0.0
    print(f"    [OK] In-bounds sampling verified: Confidence={res['manganese_confidence']}, Ore={res['ore_type_detected']}")

    # Sample outside active tile
    res_out = sample_raster_at_coordinates(lat=15.0, lon=75.0)
    assert res_out["is_live_satellite_sample"] is False
    print(f"    [OK] Out-of-bounds fallback verified: {res_out['message']}")


def test_fastapi_endpoints():
    print("\n[*] Testing FastAPI Backend Endpoints...")
    client = TestClient(app)

    # 1. Health check
    res = client.get("/")
    assert res.status_code == 200
    assert res.json()["status"] == "online"
    print("    [OK] GET / -> 200 OK")

    # 2. Scenes listing
    res = client.get("/api/scenes")
    assert res.status_code == 200
    assert res.json()["count"] >= 1
    print(f"    [OK] GET /api/scenes -> {res.json()['count']} scene(s)")

    # 3. Raster metadata
    res = client.get("/api/raster/metadata")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"
    print("    [OK] GET /api/raster/metadata -> 200 OK")

    # 4. Predict
    res = client.post("/api/predict", json={"lat": 21.8129, "lon": 80.1849})
    assert res.status_code == 200
    data = res.json()
    assert data["is_live_satellite_sample"] is True
    assert "shortfall_metrics" in data
    print(f"    [OK] POST /api/predict -> 200 OK (Confidence: {data['manganese_confidence']})")

    # 5. Direct sample
    res = client.post("/api/sample", json={"lat": 21.8129, "lon": 80.1849})
    assert res.status_code == 200
    assert res.json()["is_live_satellite_sample"] is True
    print("    [OK] POST /api/sample -> 200 OK")

    # 6. Candidates
    res = client.get("/api/candidates")
    assert res.status_code == 200
    candidates = res.json()
    assert len(candidates) == 8262
    assert "candidate_id" in candidates[0]
    assert "centroid_latitude" in candidates[0]
    assert "centroid_longitude" in candidates[0]
    assert "rank_score" in candidates[0]
    print(f"    [OK] GET /api/candidates -> 200 OK ({len(candidates)} candidates loaded)")


if __name__ == "__main__":
    print("========================================")
    print("Running SIH GIS & Satellite Engine Tests")
    print("========================================")
    test_geospatial_sampler()
    test_fastapi_endpoints()
    print("\n========================================")
    print("[ALL TESTS PASSED SUCCESSFULLY]")
    print("========================================")