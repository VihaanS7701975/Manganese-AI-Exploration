# PROVENANCE — consolidated independent project

Single squashed import (Option A). Full upstream history is preserved separately in the
recovery mirror and was deliberately NOT rewritten here.

- Original collaboration repository: https://github.com/uhammad222-ctrl/Manganese_AI_Project.git (UNTOUCHED — no push, no rewrite)
- Recovery mirror (canonical history source): `C:\SIH-recovery\collab-mirror.git`
  (branches `main` @4fa1a25, `preserve-t45que-ml` @87394d7, `integrate-t45que-june25` @6b2553a; 17 commits; 54 LFS objects SHA256-verified)
- Surviving locals (UNTOUCHED): `C:\S.I.H` (content-free), `C:\t45que-integrate-wt` (= `6b2553a` bytes + materialized rasters)
- Staging area: `C:\SIH-consolidated\` (`_sources/`, `_superseded/`, `_reports/conflict-report.md` are staging-only, NOT part of this repository)

## Component sources (selected implementations)

| Component | Source branch @ commit | Notes |
|---|---|---|
| `backend/main.py` (dataset-aware API: t45que+chennai, `/api/pixel_overlay`, `/api/candidates?dataset=`, nearest-candidate predict) | preserve-t45que-ml @87394d7 | Conflict C1 winner; main's STAC routes NOT ported yet (gap C1) |
| `frontend/src/App.jsx` (1215 lines: Chennai AOI/dataset switch, score breakdown, ExplainableAI, Analytics, TopTargets, Sidebar, HowItWorks) | preserve-t45que-ml @9686913..87394d7 | Conflict C2 winner; main's 8k-node drawer paging NOT ported yet (gap C2) |
| `frontend/src/{AnalyticsDashboard,ExplainableAI,SidebarMenu,TopTargetsPanel,HowItWorks,CandidateScoreBreakdown}.jsx`, `potentialLevel.js` | preserve-t45que-ml @d986d1a/@9e99eeb/@9686913 | Preserve-only |
| `src/ml/*.py` (feature_extraction, anomaly_detection[IsolationForest], mineralization_scoring, candidate_detection[DBSCAN+ranking], candidate_map, manganese_evidence) | preserve-t45que-ml @f23b7b9..87394d7 | Preserve-only. No LOF exists upstream |
| `src/data_processing/{load_satellite_data,preprocess_satellite}.py` | preserve-t45que-ml @deafac4/@87394d7 | Deterministic SAFE selection (C6) |
| `src/data_processing/{clip_to_aoi,render_score_overlay}.py` | preserve-t45que-ml @87394d7 | Preserve-only |
| `gis_module/{pipeline,preprocessor,sampler}.py`, `scripts/acquire_sentinel.py` | main @2f164bd | STAC pipeline + raster sampling (main-only) |
| `gis_module/test_gis.py` | main @2f164bd/@8f199a7 | Conflict C5 winner |
| `requirements.txt` (full freeze; UTF-16 — normalize to UTF-8 on first env build) | main @b714a93 | Conflict C3 winner |
| `.gitignore` (+ widened SAFE un-ignore, see below) | integrate-t45que-june25 @6b2553a | Conflict C4 winner, deliberately extended |
| `.gitattributes` (LFS for SAFE `**/*.jp2`) | all branches @3459239 (identical) | Unchanged |
| All other code/config | identical across branches @3459239/@5e8fa46/@997586b | Taken once |
| `frontend/package-lock.json` | surviving worktree (untracked artifact) | Optional; keep or gitignore at maintainer discretion |
| `data/raw/...T45QUE...SAFE/` (81 files, 668,687,985 bytes) | surviving worktree bytes = mirror LFS oids (54/54 SHA256 match) | 54 JP2s LFS-backed, metadata committed directly |

## Superseded implementations (kept in staging `_superseded/`, NOT in this repo)

- `_superseded/main/`: backend.main.py, App.jsx, .gitignore (main-line variants)
- `_superseded/integrate-t45que-june25/`: backend.main.py, App.jsx, requirements.txt (minimal), test_gis.py (stub), load_satellite_data.py, preprocess_satellite.py (base versions)

## Missing generated outputs (MISSING/REGENERABLE — never committed, absent locally)

`data/processed/*`, `candidate_sites.csv` (t45que + chennai/689-row), `manganese_evidence.csv`,
`ml_features.csv`, `copernicus_search_results.json`. Regenerate by running the staged preserve-tip chain.
0-byte stubs (`backend/app.py`, `feature_generator.py`, `spectral_analysis.py`, `visualization.py`,
4 notebooks, READMEs) are upstream placeholders, kept as-is.

## Known integration gaps (not resolved in this import)

- C1: port main's `/api/sample`, `/api/scenes`, `/api/raster/metadata`, `/api/pipeline/run` into `backend/main.py`.
- C2: verify `TopTargetsPanel` scales to the ~8,262-node T45QUE candidate set or port main's drawer paging.

## Environment notes

- Provide your own `.env` (never committed): `CDSE_USERNAME` / `CDSE_PASSWORD` for live Copernicus downloads.
- No dependencies installed, no pipelines run during consolidation.
