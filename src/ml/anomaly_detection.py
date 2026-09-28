"""
First unsupervised anomaly-detection prototype for the SIH Manganese AI
Project, built on top of data/processed/ml_features.csv (produced by
feature_extraction.py, which this script does not modify).

No manganese ground-truth or labelled deposit coordinates are used
anywhere in this script — there aren't any in this project yet, and this
is deliberately an unsupervised method so none are required.

For every valid pixel, an Isolation Forest is fit on the standardized
spectral/index features (band reflectances + NDVI/NDWI/NDBI/BSI +
FE_OXIDE_ND/CLAY_MINERAL_ND/FERROUS_ND) and each pixel gets a continuous
anomaly_score: pixels whose feature combination is spectrally unusual
relative to the rest of the scene score higher.

IMPORTANT — terminology: a high anomaly_score means a pixel is a
"spectral anomaly" / "potential mineralization candidate" only. It is
NOT a confirmed manganese deposit. This model has never seen a real
manganese location and cannot distinguish manganese from any other kind
of spectral outlier (e.g. bare rock, mine tailings, roads, quarries).
Clustering these candidates into final site polygons is a later stage,
not implemented here.
"""

import argparse
import gc
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

PROJECT_ROOT = Path(__file__).resolve().parents[2]
IN_PATH = PROJECT_ROOT / "data" / "processed" / "ml_features.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "manganese_anomalies.csv"

FEATURE_COLUMNS = [
    "B02", "B03", "B04", "B08", "B11", "B12",
    "NDVI", "NDWI", "NDBI", "BSI",
    "FE_OXIDE_ND", "CLAY_MINERAL_ND", "FERROUS_ND",
]

RANDOM_STATE = 42


def parse_args() -> argparse.Namespace:
    """--input/--output let a separate AOI (e.g. Chennai) be run through this
    stage without touching the T45QUE data. Both default to the existing
    hardcoded paths, so running with no flags is unchanged. The Isolation
    Forest itself is always fit fresh on whatever --input contains (see
    module docstring); this only changes where that input/output live."""
    parser = argparse.ArgumentParser(
        description="Fit an Isolation Forest anomaly score over ml_features.csv."
    )
    parser.add_argument(
        "--input", type=Path, default=IN_PATH,
        help=f"Path to ml_features.csv (default: {IN_PATH})",
    )
    parser.add_argument(
        "--output", type=Path, default=OUT_PATH,
        help=f"Path to write manganese_anomalies.csv (default: {OUT_PATH})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    in_path = args.input
    out_path = args.output

    if not in_path.is_file():
        raise FileNotFoundError(f"Feature dataset not found: {in_path}")

    df = pd.read_csv(in_path)
    input_pixels = len(df)
    print(f"Loaded {input_pixels} pixels from {in_path}")

    missing = [c for c in FEATURE_COLUMNS + ["longitude", "latitude"] if c not in df.columns]
    if missing:
        raise ValueError(f"Expected column(s) missing from {in_path}: {missing}")

    # Safety net: feature_extraction.py already excludes invalid/NaN/inf
    # pixels, but this stage re-checks independently so a bad row can
    # never silently reach the model. Computed as a bare ndarray (not
    # stored as a separate DataFrame) so the temporary is freed as soon
    # as this line finishes, instead of lingering as a live local for
    # the rest of the run.
    finite_mask = np.isfinite(df[FEATURE_COLUMNS].to_numpy(dtype=np.float64)).all(axis=1)
    dropped = int((~finite_mask).sum())
    if dropped:
        print(f"Dropping {dropped} pixel(s) with non-finite feature values.")

    clean_df = df.loc[finite_mask].reset_index(drop=True) if dropped else df.reset_index(drop=True)
    del df
    gc.collect()

    # Pull out longitude/latitude now and drop clean_df before building X,
    # so the ~56M-row DataFrame and the feature ndarray are never both
    # resident at once (at T45QUE scale that's several GB avoided).
    lon_lat = clean_df[["longitude", "latitude"]].reset_index(drop=True)
    X = clean_df[FEATURE_COLUMNS].to_numpy(dtype=np.float64)
    del clean_df
    gc.collect()

    # Standardize: puts reflectances (~0-0.3) and normalized-difference
    # indices (-1 to 1) on comparable scales so no single feature
    # dominates the isolation splits purely due to its raw magnitude.
    X_scaled = StandardScaler().fit_transform(X)
    del X
    gc.collect()

    # n_jobs=1: with n_jobs=-1, sklearn/joblib spawns one worker process per
    # CPU core, and each worker independently allocates a full-length int64
    # bootstrap-index array sized to ALL samples (not just its share) before
    # building any trees. At T45QUE's 56.1M-pixel scale that multiplies out
    # to more memory than is available; a single process avoids the
    # multiplication. Fits the exact same model on the exact same data,
    # just serially instead of in parallel.
    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=RANDOM_STATE,
        n_jobs=1,
    )
    model.fit(X_scaled)

    # decision_function: higher = more normal, lower = more anomalous.
    # Negate so anomaly_score follows the more intuitive convention:
    # higher score = more anomalous.
    anomaly_score = -model.decision_function(X_scaled)
    del X_scaled, model
    gc.collect()

    out_df = pd.DataFrame({
        "longitude": lon_lat["longitude"],
        "latitude": lon_lat["latitude"],
        "anomaly_score": anomaly_score,
    })
    del lon_lat
    gc.collect()

    # rank 1 = most anomalous; percentile 100 = most anomalous.
    out_df["anomaly_rank"] = out_df["anomaly_score"].rank(ascending=False, method="min").astype(int)
    out_df["anomaly_percentile"] = out_df["anomaly_score"].rank(pct=True) * 100.0

    out_df = out_df.sort_values("anomaly_score", ascending=False).reset_index(drop=True)
    out_df.to_csv(out_path, index=False)

    output_pixels = len(out_df)
    print(f"Output pixels: {output_pixels}")
    print(f"Anomaly score range: [{out_df['anomaly_score'].min():.6f}, {out_df['anomaly_score'].max():.6f}]")
    print(f"Saved to: {out_path}")

    print("\nTop 10 spectral anomalies / potential mineralization candidates (NOT confirmed deposits):")
    print(out_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
