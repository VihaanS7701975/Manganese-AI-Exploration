# PyInstaller build for the Manganese AI FastAPI backend (Task: desktop app).
#
# NOT executed during development (rasterio/GDAL native packaging is slow
# and environment-sensitive). Build on the demo machine with the validated
# Python 3.13 environment:
#
#   C:\...\Python313\python.exe -m pip install pyinstaller
#   C:\...\Python313\python.exe -m PyInstaller electron/backend-pyinstaller.spec
#
# Output: dist/manganese-backend/manganese-backend.exe -- place it at
# <electron-resources>/backend/manganese-backend.exe so electron/main.js
# picks it up (resolution step 1). No secrets are bundled: the exe reads
# the local .env at runtime if present, same as `uvicorn backend.main:app`.
#
# Data bundled: ONLY the demo-required runtime files (candidate tables,
# score overlays, sample provenance -- mirrors electron/builder.json).
# data/raw (multi-GB Sentinel-2 SAFE products) and full-scene ML
# intermediates (ml_features.csv etc.) are deliberately EXCLUDED:
# workflow/temporal panels degrade to their honest "no scenes" states
# without them; copy a SAFE next to the exe to re-enable.
#
# Entry: backend/main.py's `if __name__ == "__main__"` block serves the
# API itself (`manganese-backend.exe --port 8000`), so no separate
# launcher script is needed. pathex keeps `backend.*` imports working.

import os
from PyInstaller.building.build_main import Analysis, EXE, COLLECT
from PyInstaller.utils.hooks import collect_all

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

PROCESSED = os.path.join(PROJECT_ROOT, 'data', 'processed')
datas = [
    (os.path.join(PROCESSED, 'candidate_sites.csv'), 'data/processed'),
    (os.path.join(PROCESSED, 'candidate_sites_report.txt'), 'data/processed'),
    (os.path.join(PROCESSED, 'overlays'), 'data/processed/overlays'),
    (os.path.join(PROCESSED, 'chennai', 'candidate_sites_sample.csv'), 'data/processed/chennai'),
    (os.path.join(PROCESSED, 'chennai', 'candidate_sites_sample_report.txt'), 'data/processed/chennai'),
    (os.path.join(PROCESSED, 'chennai', 'manganese_evidence_sample.csv'), 'data/processed/chennai'),
    (os.path.join(PROCESSED, 'chennai', 'SAMPLE_NOTE.json'), 'data/processed/chennai'),
    (os.path.join(PROJECT_ROOT, 'frontend', 'dist'), 'frontend/dist'),
]
binaries = []
hiddenimports = ['uvicorn', 'fastapi', 'backend.main', 'backend.temporal', 'backend.report_pdf']

# Native-heavy deps: bundle code + binaries + data (GDAL/PROJ tables, MPL data).
for pkg in ('rasterio', 'sklearn', 'scipy', 'matplotlib', 'pandas', 'PIL'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [os.path.join(PROJECT_ROOT, 'backend', 'main.py')],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    noarchive=False,
)
exe = EXE(
    a.scripts,
    [],
    exclude_binaries=True,
    name='manganese-backend',
    console=False,  # no visible terminal for the backend
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='manganese-backend',
)
