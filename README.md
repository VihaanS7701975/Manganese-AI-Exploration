# GeoManganese AI — Team RIZZLERS (SIH26009)

**Using AI/ML and Space Technology to Identify Manganese Reserves and Overcome Production Shortfalls.**

An offline-first mineral-prospectivity screening prototype: Sentinel-2 satellite imagery →
spectral features → unsupervised anomaly detection → DBSCAN candidate zones → explainable
ranked targets on an interactive GIS map, with a dataset-aware assistant and one-click
exploration reports (JSON / HTML / PDF), packaged as a desktop app.

> **Honesty note (please read):** this repository ships **real implemented pipeline code**
> with **small committed demo/sample datasets**. Sample-derived outputs are labelled as
> such in the app, API and reports. They are spectral-anomaly *exploration targets* —
> **not** confirmed manganese deposits and **not** full-scene survey results.

---

## 1. Problem overview

India faces manganese production shortfalls against growing steel and battery demand.
Conventional ground surveys are slow and expensive. Open Sentinel-2 multispectral imagery
covers the whole country every few days — the opportunity is to screen large areas from
orbit first, then send geologists only to the most promising zones.

## 2. Solution overview

GeoManganese AI ingests Sentinel-2 L2A scenes, computes spectral alteration indices
(iron-oxide, clay/hydroxyl, ferrous, bare-earth vs vegetation/water/built-up), scores
every pixel with an IsolationForest anomaly model blended into a mineralization score,
clusters the top-percentile pixels with DBSCAN into ranked candidate zones, and serves
them through a FastAPI backend to a React + Leaflet GIS frontend (map, analytics,
Explainable AI, AOI search, assistant, reports) wrapped in an Electron desktop shell.

## 3. Key features

- 🛰️ Sentinel-2 SAFE ingestion + deterministic preprocessing (`src/data_processing/`)
- 🧠 IsolationForest anomaly detection + reward/penalty mineralization scoring (`src/ml/`)
- 📍 DBSCAN candidate-zone detection, ranking and evidence layers (`src/ml/`)
- 🗺️ Interactive GIS map: layers, pixel-score overlay, AOI draw/search, time panel
- 🔍 Explainable AI per-candidate score breakdown + analytics dashboard
- 💬 Dataset-aware assistant (calculated summaries + reference notes, labelled as such)
- 📄 One-click exploration report: JSON / HTML / multi-page PDF (`backend/report_pdf.py`)
- 🖥️ Electron desktop app: double-click → backend auto-starts → production UI, no terminal
- 🔄 STAC acquisition + raster sampling + workflow/temporal endpoints (`gis_module/`)

## 4. Architecture

```
Sentinel-2 SAFE (Copernicus, manual/STAC download)
        │  src/data_processing/ (load, preprocess, clip_to_aoi, render_score_overlay)
        ▼
Spectral features (B02–B12 + NDVI/NDWI/NDBI/BSI + FE_OXIDE/CLAY/FERROUS_ND)
        │  src/ml/feature_extraction.py
        ▼
IsolationForest anomaly (200 trees) + mineralization blend ──► DBSCAN candidates + rank
        │  backend/main.py (FastAPI, dataset-aware: ?dataset=t45que|chennai)
        ▼
React + Leaflet frontend (frontend/src) ◄── Electron shell (electron/main.js)
```

## 5. Satellite / GIS pipeline

- Supported input: Sentinel-2 L2A `.SAFE` products (10 m B02/B03/B04/B08; 20 m B11/B12/SCL).
- `src/data_processing/load_satellite_data.py` deterministically selects the scene;
  `preprocess_satellite.py` stacks/resamples indices; `clip_to_aoi.py` clips to an AOI;
  `render_score_overlay.py` pre-renders the RED/YELLOW/GREEN score overlay PNG + JSON sidecar.
- `gis_module/` adds live Copernicus STAC search/download (needs `.env` credentials),
  preprocessing, cloud filtering, resampling and point sampling — thinly wrapped by
  `/api/scenes`, `/api/raster/metadata`, `/api/sample`, `/api/pipeline/run`.

## 6. ML / anomaly detection

`src/ml/anomaly_detection.py` — IsolationForest (200 trees);
score = −decision_function, reported as 0–100 percentiles.
`src/ml/mineralization_scoring.py` — 0–100 reward-minus-penalty blend:
rewards anomaly 0.40 / alteration 0.35 / bare-earth 0.25; penalties vegetation 0.10 /
water 0.05 / built-up 0.05. **Unsupervised screening only — no manganese ground-truth
labels exist in this project.**

## 7. Candidate generation

`src/ml/candidate_detection.py` — DBSCAN over UTM metres (default: top 1% pixels,
eps 150 m, min_samples 5). `rank_score = 0.35·strength_pct + 0.25·density_pct +
0.40·mineralization_pct`. Output: small ranked `candidate_sites.csv` (the only file
the backend loads — multi-million-row intermediates are never served).

## 8. Explainable AI

Every candidate exposes its full score anatomy (anomaly / mineralization / strength /
density percentiles, pixel count, area, rank_score) via `/api/candidates` and
`/api/predict → nearest_candidate`, rendered in `ExplainableAI.jsx` and the candidate
score-breakdown panel. The optional `manganese_evidence` layer (Chennai sample only) is
**diagnostic only** — generic alteration indices, explicitly *not* a manganese-specific
detector and *not* used in any score.

## 9. Assistant

`Assistant.jsx` answers from the live dataset context (loaded candidates, prediction,
AOI result, temporal summary). Factual lines are prefixed `[Calculated]`; methodology
and limitation lines `[Reference]`. Chennai answers carry a `(sample-derived subset)` tag.

## 10. Report generation

`GET /api/report?dataset=&limit=` assembles AOI, imagery scenes, methodology, ranked
candidates, limitations and shortfall notes read-only from files on disk.
`GET /api/report.pdf` renders the same payload server-side with matplotlib only —
cover, methodology, candidate tables/charts, selected-candidate Explainable AI, overlay
image, provenance/limitations page. Missing sections are labelled, never fabricated.
Frontend `ReportView.jsx` offers JSON / HTML / PDF download, optionally scoped to a
selected candidate and drawn AOI bbox.

## 10. AOI / GIS interaction

Rectangle/polygon AOI drawing, India-wide manganese-belt location shortcuts
(`MANGANESE_BELTS` in `App.jsx`, each bound to its backend dataset id), layer toggles,
pixel-score overlay draped at its real WGS84 bounds, and `POST /api/aoi/search`
(bbox pre-filter + ray-cast polygon test, rank-ordered, honest empty state).
Clicking the map calls `POST /api/predict` against the active dataset; clicks outside
the surveyed bounds return `Outside Surveyed Area` instead of a fabricated match.

## 11. Desktop application

`electron/main.js`: finds a backend (bundled `manganese-backend.exe` via
`electron/backend-pyinstaller.spec`, else the first Python with the backend stack),
spawns it hidden on `127.0.0.1:8000`, polls `/` up to 90 s, then loads the production
`frontend/dist` build. Backend is killed on quit. Build with:

```powershell
cd frontend; npm install; npm run build
cd ..\electron; npm install; npm run dist   # or `npm run package` for unpacked dir
```

## 12. Current datasets ✅ REAL code / ⚠️ SAMPLE data

| Dataset key | Scene | Candidates (committed) | Status |
|---|---|---|---|
| `t45que` (default) | Sentinel-2 tile T45QUE, 2026-06-25 (tracked `.SAFE` metadata; rasters via Git-LFS) | 8,262 (`data/processed/candidate_sites.csv`) | Real pipeline output, full-scene run |
| `chennai` | Sentinel-2 tile 44PMV / Chennai AOI, 2026-01-14 | 53 (`data/processed/chennai/candidate_sites_sample.csv`) | ⚠️ **Sample-derived**: deterministic 1-in-55 systematic spatial sample of the real 16.5M-row feature table — see `data/processed/chennai/SAMPLE_NOTE.json`. Chennai is not a documented manganese belt. |

Only these small files are committed; multi-GB intermediates (`ml_features*.csv`,
`manganese_anomalies*.csv`, `mineralization_scores*.csv`, `*.tif`) are git-ignored and
regenerated locally (see `.gitignore` "Public demo data" section).

## 13. Demo limitations

- Unsupervised screening only; scores are spectral-outlier percentiles, **not assays**.
- Chennai = sample subset (see above); **not** full-scene results.
- `manganese_prospectivity_score` = generic alteration diagnostic, not manganese proof.
- Yield / deficit-reduction / feasibility figures are **static illustrative reference
  scenarios** (`estimate_kind: illustrative_capacity_scenario`), not ML predictions.
- Cross-date persistence is remote-sensing support only, not geological confirmation.
- Ground-truth validation by geologists is required before any real-world claim.

## 14. Installation

Prerequisites: Python 3.11+ with the backend stack, Node.js 18+.

```powershell
# Backend env (use the Python that has the stack; demo machine: $env:MANGANESE_PYTHON)
C:\...\python.exe -m pip install -r requirements.txt
# Frontend
cd frontend; npm install
```

Copy `.env.example` → `.env` **only** if you need live Copernicus downloads
(`CDSE_USERNAME` / `CDSE_PASSWORD`). The demo works without it.

## 15. Running the backend

```powershell
C:\...\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Smoke test: `GET /`, `/api/candidates?dataset=chennai`, `/api/candidates?dataset=t45que`,
`/api/report?dataset=chennai`, `/api/report.pdf?dataset=chennai`, `POST /api/predict`,
`POST /api/aoi/search`. Do **not** run the 16.5M-row full-scene pipeline for validation —
use the committed sample data.

## 16. Running the frontend

```powershell
cd frontend
npm run dev      # dev server (uses VITE_API_BASE_URL or defaults to localhost:8000)
npm run build    # production build (required before packaging the desktop app)
npm run preview  # serve the production build locally
```

## 17. Running the desktop application

See section 11. The Electron shell needs `frontend/dist` built first; it reuses the
existing local Python backend (set `MANGANESE_PYTHON` via `setx` on the demo machine)
or a PyInstaller bundle from `electron/backend-pyinstaller.spec`.

```powershell
cd frontend; npm install; npm run build
cd ..\electron; npm install; npm run dist
```

## 18. Project structure

```
backend/        FastAPI app (main.py), PDF renderer (report_pdf.py), temporal/methodology (temporal.py)
frontend/src/   React app: App.jsx, Landing.jsx, apiConfig.js, AOI/assistant/report/compare/workflow panels
electron/       Desktop shell (main.js, builder.json, backend-pyinstaller.spec)
src/ml/         feature_extraction, anomaly_detection, mineralization_scoring,
                candidate_detection, candidate_map, manganese_evidence
src/data_processing/  SAFE loading, preprocessing, AOI clip, score-overlay render
gis_module/     STAC search/download, preprocessing, sampler (+ tests)
scripts/        acquire_sentinel, create_feature_dataset, create_test_raster (dev scaffolding)
notebooks/      01–04 exploration/model walkthroughs (placeholders)
data/           raw SAFE scenes + processed outputs (only minimal demo files committed)
```

## 19. Team

**Team RIZZLERS — Smart India Hackathon, Problem Statement SIH26009.**
Desktop app title: "GeoManganese AI — Team RIZZLERS (SIH26009)".

## 20. Future work (NOT yet implemented)

- Ground-truth-labelled supervised models and field validation workflow
- Manganese-specific spectral library / assay-calibrated detector
- Multi-scene mosaics, change detection over 2+ co-registered dates
- Tonnage/yield estimation model (current figures are placeholders by design)
- Cloud deployment of the API + hosted demo
