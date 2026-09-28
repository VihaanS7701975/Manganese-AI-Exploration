"""
Transparent mineralization-candidate scoring stage for the SIH Manganese AI
Project, built on top of data/processed/ml_features.csv (feature_extraction.py)
and data/processed/manganese_anomalies.csv (anomaly_detection.py). Neither
upstream script is modified.

The Isolation Forest in anomaly_detection.py gives each pixel a single
multivariate outlier score but does not explain *why* a pixel is unusual,
and its output CSV does not carry the spectral index values forward. This
stage re-joins those indices back onto the anomaly output (by exact
longitude/latitude match -- both files derive from the same pixel grid) and
combines several independent, auditable signals into one 0-100
mineralization_score per pixel:

  reward:
    anomaly_percentile        - scene-wide Isolation Forest outlier strength
    alteration_percentile     - mean of FE_OXIDE_ND / CLAY_MINERAL_ND /
                                 FERROUS_ND percentile ranks (generic
                                 iron-oxide- and clay/hydroxyl-mineral
                                 alteration indicators, NOT manganese-specific)
    bare_earth_percentile     - BSI percentile (alteration indices are only
                                 spectrally trustworthy on exposed surfaces)
  penalty:
    vegetation_penalty        - NDVI percentile (vegetation masks the substrate)
    water_penalty              - NDWI percentile (water is not an exploration target)
    builtup_penalty            - NDBI percentile (impervious/urban surfaces are not
                                 natural exploration targets)

All components are percentile ranks (0-100) computed across the whole valid
scene, so the score is scale-free and scene-relative rather than tied to
raw reflectance/index magnitudes.

IMPORTANT -- terminology: mineralization_score identifies a "potential
mineralization / manganese exploration target" candidate ONLY. No component
of this score is a proven or unique manganese detector, no manganese
ground-truth or deposit coordinates are used anywhere in this script, and a
high score is NOT a confirmed manganese deposit -- it requires independent
geological / ground-truth validation, same as the anomaly score it builds on.
"""

import argparse
import gc
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURES_PATH = PROJECT_ROOT / "data" / "processed" / "ml_features.csv"
ANOMALIES_PATH = PROJECT_ROOT / "data" / "processed" / "manganese_anomalies.csv"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "mineralization_scores.csv"

ALTERATION_COLUMNS = ["FE_OXIDE_ND", "CLAY_MINERAL_ND", "FERROUS_ND"]
REQUIRED_FEATURE_COLUMNS = ["longitude", "latitude", "BSI", "NDVI", "NDWI", "NDBI"] + ALTERATION_COLUMNS
REQUIRED_ANOMALY_COLUMNS = ["longitude", "latitude", "anomaly_score", "anomaly_percentile"]

# Reward weights sum to 1.0 (max possible reward = 100 points):
#   anomaly strength is weighted highest because the Isolation Forest is
#   already a multivariate signal fit on all 13 spectral/index features
#   jointly, so it captures unusual feature *combinations* no single ratio
#   can. Alteration is the primary domain-specific geological signal, so it
#   is weighted second, as the mean of three independent indices rather
#   than any single one (no individual ratio is treated as a manganese
#   detector). Bare-earth suitability gets the smallest reward weight: it
#   is a supporting condition (alteration indices are only meaningful on
#   exposed surfaces) rather than a mineralization signal on its own.
WEIGHT_ANOMALY = 0.40
WEIGHT_ALTERATION = 0.35
WEIGHT_BARE_EARTH = 0.25

# Penalty weights sum to 0.20 (max possible deduction = 20 points), so
# common false-positive land covers trim the score rather than dominate it
# -- a spectrally anomalous, altered, bare pixel should still score high
# even if it has some residual vegetation/moisture/impervious signal.
# Vegetation gets the largest penalty weight because it is the most common
# and most reliably measured (NDVI) source of false positives in this AOI;
# water and built-up are weighted equally and lower since valid_mask/SCL
# already removes cloud/shadow/no-data, leaving fewer of these pixels.
WEIGHT_VEGETATION_PENALTY = 0.10
WEIGHT_WATER_PENALTY = 0.05
WEIGHT_BUILTUP_PENALTY = 0.05


def _percentile(series: pd.Series) -> pd.Series:
    """Scene-wide percentile rank (0-100, ties averaged) of a column."""
    return series.rank(pct=True) * 100.0


def parse_args() -> argparse.Namespace:
    """--features/--anomalies/--output let a separate AOI (e.g. Chennai) be
    run through this stage without touching the T45QUE data. All default to
    the existing hardcoded paths, so running with no flags is unchanged."""
    parser = argparse.ArgumentParser(
        description="Combine anomaly score + alteration indices into a mineralization_score."
    )
    parser.add_argument(
        "--features", type=Path, default=FEATURES_PATH,
        help=f"Path to ml_features.csv (default: {FEATURES_PATH})",
    )
    parser.add_argument(
        "--anomalies", type=Path, default=ANOMALIES_PATH,
        help=f"Path to manganese_anomalies.csv (default: {ANOMALIES_PATH})",
    )
    parser.add_argument(
        "--output", type=Path, default=OUT_PATH,
        help=f"Path to write mineralization_scores.csv (default: {OUT_PATH})",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    features_path = args.features
    anomalies_path = args.anomalies
    out_path = args.output

    if not features_path.is_file():
        raise FileNotFoundError(f"Feature dataset not found: {features_path}")
    if not anomalies_path.is_file():
        raise FileNotFoundError(f"Anomaly output not found: {anomalies_path}")

    # usecols: at T45QUE's 56.1M-row scale, loading the raw bands
    # (B02...B12) and anomaly_rank -- neither ever referenced below -- would
    # needlessly carry several extra GB through the whole run. Reading only
    # the columns this stage actually uses changes nothing about any value
    # that IS used.
    features_df = pd.read_csv(features_path, usecols=REQUIRED_FEATURE_COLUMNS)
    anomalies_df = pd.read_csv(anomalies_path, usecols=REQUIRED_ANOMALY_COLUMNS)
    print(f"Loaded {len(features_df)} pixel(s) from {features_path}")
    print(f"Loaded {len(anomalies_df)} pixel(s) from {anomalies_path}")

    missing = [c for c in REQUIRED_FEATURE_COLUMNS if c not in features_df.columns]
    if missing:
        raise ValueError(f"Expected column(s) missing from {features_path}: {missing}")
    missing = [c for c in REQUIRED_ANOMALY_COLUMNS if c not in anomalies_df.columns]
    if missing:
        raise ValueError(f"Expected column(s) missing from {anomalies_path}: {missing}")

    # Both files derive from the same pixel grid (anomaly_detection.py copies
    # longitude/latitude straight from ml_features.csv), so an exact join on
    # coordinates re-aligns each pixel's anomaly score with its spectral
    # indices without assuming row order.
    merged = pd.merge(
        features_df,
        anomalies_df,
        on=["longitude", "latitude"],
        how="inner",
    )
    expected = min(len(features_df), len(anomalies_df))
    del features_df, anomalies_df
    gc.collect()

    if expected and len(merged) < 0.5 * expected:
        raise ValueError(
            f"Only {len(merged)}/{expected} pixels matched between {features_path.name} and "
            f"{anomalies_path.name} on (longitude, latitude); expected them to substantially "
            "share the same pixel grid. Refusing to proceed on a mostly-mismatched join."
        )
    if expected and len(merged) < 0.99 * expected:
        print(
            f"WARNING: only {len(merged)}/{expected} pixels matched between {features_path.name} "
            f"and {anomalies_path.name} on (longitude, latitude). This usually means the two "
            "files were not produced by the same feature_extraction.py / anomaly_detection.py run "
            "(e.g. ml_features.csv was regenerated afterwards). Proceeding with the pixels that do "
            "match; re-run anomaly_detection.py against the current ml_features.csv to get a full match."
        )
    print(f"Joined {len(merged)} pixel(s) on (longitude, latitude)")

    alteration_percentile = pd.concat(
        [_percentile(merged[c]) for c in ALTERATION_COLUMNS], axis=1
    ).mean(axis=1)
    bare_earth_percentile = _percentile(merged["BSI"])
    vegetation_penalty = _percentile(merged["NDVI"])
    water_penalty = _percentile(merged["NDWI"])
    builtup_penalty = _percentile(merged["NDBI"])

    reward = (
        WEIGHT_ANOMALY * merged["anomaly_percentile"]
        + WEIGHT_ALTERATION * alteration_percentile
        + WEIGHT_BARE_EARTH * bare_earth_percentile
    )
    penalty = (
        WEIGHT_VEGETATION_PENALTY * vegetation_penalty
        + WEIGHT_WATER_PENALTY * water_penalty
        + WEIGHT_BUILTUP_PENALTY * builtup_penalty
    )
    mineralization_score = (reward - penalty).clip(lower=0.0, upper=100.0)
    del reward, penalty
    gc.collect()

    out_df = pd.DataFrame({
        "longitude": merged["longitude"],
        "latitude": merged["latitude"],
        "anomaly_score": merged["anomaly_score"],
        "anomaly_percentile": merged["anomaly_percentile"],
        "alteration_percentile": alteration_percentile,
        "bare_earth_percentile": bare_earth_percentile,
        "vegetation_penalty_percentile": vegetation_penalty,
        "water_penalty_percentile": water_penalty,
        "builtup_penalty_percentile": builtup_penalty,
        "mineralization_score": mineralization_score,
    })
    del merged, alteration_percentile, bare_earth_percentile
    del vegetation_penalty, water_penalty, builtup_penalty, mineralization_score
    gc.collect()

    # rank 1 = highest score; percentile 100 = highest score. Mirrors the
    # anomaly_rank/anomaly_percentile convention from anomaly_detection.py.
    out_df["mineralization_rank"] = out_df["mineralization_score"].rank(ascending=False, method="min").astype(int)
    out_df["mineralization_percentile"] = out_df["mineralization_score"].rank(pct=True) * 100.0

    out_df = out_df.sort_values("mineralization_score", ascending=False).reset_index(drop=True)
    out_df.to_csv(out_path, index=False)

    print(f"\nWeights -- reward: anomaly={WEIGHT_ANOMALY}, alteration={WEIGHT_ALTERATION}, "
          f"bare_earth={WEIGHT_BARE_EARTH} (sum={WEIGHT_ANOMALY + WEIGHT_ALTERATION + WEIGHT_BARE_EARTH})")
    print(f"Weights -- penalty: vegetation={WEIGHT_VEGETATION_PENALTY}, water={WEIGHT_WATER_PENALTY}, "
          f"builtup={WEIGHT_BUILTUP_PENALTY} "
          f"(sum={WEIGHT_VEGETATION_PENALTY + WEIGHT_WATER_PENALTY + WEIGHT_BUILTUP_PENALTY})")
    print(f"mineralization_score range: [{out_df['mineralization_score'].min():.3f}, "
          f"{out_df['mineralization_score'].max():.3f}]")
    print(f"Saved to: {out_path}")

    print("\nTop 10 pixels by mineralization_score "
          "(potential mineralization / manganese exploration indicator ONLY -- "
          "NOT a confirmed manganese deposit):")
    print(out_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
