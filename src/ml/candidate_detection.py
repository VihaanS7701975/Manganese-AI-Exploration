"""
Spatial clustering stage for the SIH Manganese AI Project, built on top of
data/processed/mineralization_scores.csv (produced by
mineralization_scoring.py, which this script does not modify). That file
carries forward every pixel from manganese_anomalies.csv (anomaly_score,
anomaly_percentile) plus the transparent per-pixel mineralization_score.

The anomaly detector scores every pixel independently and has no notion of
geography. That leaves thousands of individually "anomalous" pixels, many
of which are isolated single-pixel spikes (sensor noise, mixed pixels, a
single stray rock) rather than anything geologically meaningful. This
stage:

  1. selects the top X% most anomalous pixels (X configurable, by
     anomaly_percentile -- spatial candidate *selection* is intentionally
     kept independent of mineralization_score so the two stages stay
     separately auditable), then
  2. clusters the ones that are near each other in real-world space
     (DBSCAN over metres, not raw degrees) into a much smaller number of
     candidate sites, then
  3. aggregates each site's mineralization_score (mean/max/scene percentile)
     alongside its anomaly score, then
  4. scores and ranks those sites transparently.

IMPORTANT — terminology: every output row here is a "potential
mineralization / manganese exploration target" candidate. It is NOT a
confirmed manganese deposit. Nothing in this project has ever seen a real
manganese location. These candidates require independent geological /
ground-truth validation before they mean anything.

IMPORTANT — data caveat: the current data/processed/mineralization_scores.csv
was generated from the T45QUE (Keonjhar) Sentinel-2 scene. The resulting
coordinates are unconfirmed spectral-anomaly candidates only -- NOT
evidence of manganese anywhere and should not be treated as such.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from rasterio.crs import CRS
from rasterio.warp import transform
from scipy.spatial import ConvexHull, cKDTree
from sklearn.cluster import DBSCAN

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN_PATH = PROJECT_ROOT / "data" / "processed" / "mineralization_scores.csv"
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "processed" / "candidate_sites.csv"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "processed" / "candidate_sites_report.txt"

REQUIRED_COLUMNS = ["longitude", "latitude", "anomaly_score", "anomaly_percentile", "mineralization_score", "mineralization_percentile"]

# Ranking weights: mineralization_percentile already synthesizes anomaly
# strength + alteration indicators + bare-earth/vegetation/water/built-up
# adjustments (see mineralization_scoring.py), so it gets the largest share.
# Raw anomaly strength is kept as its own term because it rewards ANY
# spectral outlier (not just ones consistent with alteration indices), which
# is still a useful independent signal. Spatial density (pixels packed into
# a small area rather than scattered thinly) is a purely geometric
# coherence signal, kept smallest since it says nothing about spectral
# content. All three weights are simple percentile ranks (0-100), so the
# final score is a transparent weighted average of three easy-to-explain
# 0-100 numbers, summing to 1.0.
STRENGTH_WEIGHT = 0.35
DENSITY_WEIGHT = 0.25
MINERALIZATION_WEIGHT = 0.40


def load_anomalies(in_path: Path) -> pd.DataFrame:
    if not in_path.is_file():
        raise FileNotFoundError(f"Mineralization score output not found: {in_path}")
    df = pd.read_csv(in_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Expected column(s) missing from {in_path}: {missing}")
    return df


def select_high_anomaly_pixels(df: pd.DataFrame, top_percentile: float) -> pd.DataFrame:
    """Select pixels in the top `top_percentile` percent by anomaly score.

    e.g. top_percentile=1.0 keeps pixels with anomaly_percentile >= 99.0
    (the top 1%). top_percentile=0.1 keeps the top 0.1%, etc.
    """
    if not 0 < top_percentile <= 100:
        raise ValueError("top_percentile must be in (0, 100]")
    cutoff = 100.0 - top_percentile
    selected = df.loc[df["anomaly_percentile"] >= cutoff].reset_index(drop=True)
    return selected


def _utm_epsg_for(lon: float, lat: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


def project_to_metric(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, int]:
    """Project longitude/latitude (EPSG:4326) to a local UTM zone in metres.

    Longitude/latitude degrees are not equal-sized on the ground (a degree
    of longitude shrinks toward the poles), so raw degrees cannot be fed
    into a Euclidean-distance clustering algorithm. The UTM zone is chosen
    automatically from the data's own centroid, so this works for any
    scene without hardcoding a region.
    """
    lon0 = float(df["longitude"].mean())
    lat0 = float(df["latitude"].mean())
    epsg = _utm_epsg_for(lon0, lat0)
    xs, ys = transform(
        CRS.from_epsg(4326),
        CRS.from_epsg(epsg),
        df["longitude"].to_numpy(),
        df["latitude"].to_numpy(),
    )
    return np.asarray(xs), np.asarray(ys), epsg


def estimate_pixel_spacing_m(x_m: np.ndarray, y_m: np.ndarray, sample_size: int = 5000) -> float:
    """Estimate the native pixel spacing (metres) from nearest-neighbour
    distances, so cluster-area fallbacks don't hardcode a sensor resolution.
    """
    n = len(x_m)
    if n < 2:
        return 10.0  # degenerate fallback, essentially unused for n<2
    if n > sample_size:
        rng = np.random.default_rng(42)
        idx = rng.choice(n, size=sample_size, replace=False)
    else:
        idx = np.arange(n)
    pts = np.column_stack([x_m[idx], y_m[idx]])
    tree = cKDTree(np.column_stack([x_m, y_m]))
    dists, _ = tree.query(pts, k=2)  # k=1 is the point itself (dist 0)
    nn_dist = dists[:, 1]
    nn_dist = nn_dist[nn_dist > 0]
    if len(nn_dist) == 0:
        return 10.0
    return float(np.median(nn_dist))


def cluster_pixels(x_m: np.ndarray, y_m: np.ndarray, eps_m: float, min_samples: int) -> np.ndarray:
    """DBSCAN over projected metric coordinates. -1 = noise (not part of
    any spatially concentrated cluster) and is excluded from candidate
    sites downstream.
    """
    coords = np.column_stack([x_m, y_m])
    labels = DBSCAN(eps=eps_m, min_samples=min_samples, metric="euclidean").fit_predict(coords)
    return labels


def _cluster_area_m2(x: np.ndarray, y: np.ndarray, pixel_area_m2: float) -> float:
    """Approximate spatial extent of a cluster as its convex-hull area.
    Falls back to a pixel-count-based footprint when the hull is degenerate
    (collinear points, or fewer than 3 points).
    """
    fallback = max(len(x), 1) * pixel_area_m2
    if len(x) < 3:
        return fallback
    try:
        hull = ConvexHull(np.column_stack([x, y]))
        area = float(hull.volume)  # 2D ConvexHull.volume is the polygon area
        return max(area, fallback)
    except Exception:
        return fallback


def build_candidate_sites(
    selected: pd.DataFrame, labels: np.ndarray, x_m: np.ndarray, y_m: np.ndarray, pixel_area_m2: float
) -> pd.DataFrame:
    """Aggregate clustered pixels into one row per candidate site."""
    work = selected.copy()
    work["_cluster"] = labels
    work["_x_m"] = x_m
    work["_y_m"] = y_m

    clustered = work.loc[work["_cluster"] != -1]
    n_noise = int((work["_cluster"] == -1).sum())

    rows = []
    for cluster_id, group in clustered.groupby("_cluster"):
        area_m2 = _cluster_area_m2(group["_x_m"].to_numpy(), group["_y_m"].to_numpy(), pixel_area_m2)
        pixel_count = len(group)
        rows.append(
            {
                "pixel_count": pixel_count,
                "centroid_longitude": float(group["longitude"].mean()),
                "centroid_latitude": float(group["latitude"].mean()),
                "max_anomaly_score": float(group["anomaly_score"].max()),
                "mean_anomaly_score": float(group["anomaly_score"].mean()),
                "anomaly_percentile": float(group["anomaly_percentile"].max()),
                "max_mineralization_score": float(group["mineralization_score"].max()),
                "mean_mineralization_score": float(group["mineralization_score"].mean()),
                "mineralization_percentile": float(group["mineralization_percentile"].max()),
                "area_m2": area_m2,
                "density_pixels_per_m2": pixel_count / area_m2,
            }
        )

    sites = pd.DataFrame(rows)
    return sites, n_noise


def rank_candidates(sites: pd.DataFrame) -> pd.DataFrame:
    """Transparent ranking: a weighted average of three 0-100 percentile /
    percentile-like components — mean anomaly strength (among candidates),
    spatial density (pixels packed per unit area, among candidates), and
    mineralization_percentile (each site's peak mineralization_score
    expressed as a percentile of ALL scene pixels, from
    mineralization_scoring.py). All components and the weights are plain
    columns in the output, so the ranking is fully auditable.
    """
    if sites.empty:
        sites["strength_percentile"] = []
        sites["density_percentile"] = []
        sites["rank_score"] = []
        sites["candidate_id"] = []
        sites["rank"] = []
        return sites

    sites = sites.copy()
    sites["strength_percentile"] = sites["mean_anomaly_score"].rank(pct=True) * 100.0
    sites["density_percentile"] = sites["density_pixels_per_m2"].rank(pct=True) * 100.0
    sites["rank_score"] = (
        STRENGTH_WEIGHT * sites["strength_percentile"]
        + DENSITY_WEIGHT * sites["density_percentile"]
        + MINERALIZATION_WEIGHT * sites["mineralization_percentile"]
    )
    sites = sites.sort_values("rank_score", ascending=False).reset_index(drop=True)
    sites.insert(0, "candidate_id", [f"CAND_{i+1:04d}" for i in range(len(sites))])
    sites.insert(1, "rank", range(1, len(sites) + 1))
    return sites


def _provenance_banner(in_path: Path) -> str:
    return f"""
================================================================================
DATA PROVENANCE NOTICE
This run's input ({in_path}) carries forward the anomaly/mineralization
scores of its own source scene (see the filename and its run's own
provenance). The candidate sites below are NOT evidence of manganese
anywhere. They are "potential mineralization / manganese exploration
target" candidates produced by an unsupervised model that has never seen
a real manganese location, and every site requires independent
geological / ground-truth validation before it means anything.
================================================================================
"""


def write_report(
    report_path: Path,
    in_path: Path,
    input_pixels: int,
    selected_pixels: int,
    top_percentile: float,
    eps_m: float,
    min_samples: int,
    pixel_spacing_m: float,
    n_noise: int,
    sites: pd.DataFrame,
) -> str:
    lines = [_provenance_banner(in_path)]
    lines.append("Potential Mineralization / Manganese Exploration Target Report")
    lines.append("(potential mineralization / manganese exploration target candidates only -- NOT confirmed manganese deposits)")
    lines.append("")
    lines.append(f"Input pixels (all anomaly scores):        {input_pixels}")
    lines.append(f"Selection threshold:                       top {top_percentile}% (by anomaly_percentile)")
    lines.append(f"Anomalous pixels selected:                 {selected_pixels}")
    lines.append(f"Estimated native pixel spacing:             {pixel_spacing_m:.2f} m")
    lines.append(f"DBSCAN eps:                                 {eps_m} m")
    lines.append(f"DBSCAN min_samples:                         {min_samples}")
    lines.append(f"Pixels excluded as spatial noise (label -1): {n_noise}")
    lines.append(f"Candidate clusters produced:                {len(sites)}")
    lines.append("")

    if sites.empty:
        lines.append("No candidate clusters were produced with the current settings.")
        lines.append("Try a larger --top-percentile, larger --eps, or smaller --min-samples.")
    else:
        sizes = sites["pixel_count"]
        lines.append(
            f"Cluster size (pixel_count): min={sizes.min()}, median={sizes.median():.1f}, "
            f"max={sizes.max()}, mean={sizes.mean():.1f}"
        )
        lines.append(
            f"Anomaly score across candidate pixels: max={sites['max_anomaly_score'].max():.6f}, "
            f"min of per-cluster means={sites['mean_anomaly_score'].min():.6f}"
        )
        lines.append(
            f"Mineralization score across candidate sites: max={sites['max_mineralization_score'].max():.2f}, "
            f"min of per-cluster means={sites['mean_mineralization_score'].min():.2f}"
        )
        lines.append("")
        lines.append(
            "Top 10 candidate sites (ranked by rank_score = "
            f"{STRENGTH_WEIGHT}*strength_percentile + {DENSITY_WEIGHT}*density_percentile + "
            f"{MINERALIZATION_WEIGHT}*mineralization_percentile):"
        )
        top10 = sites.head(10)[
            [
                "candidate_id",
                "rank",
                "pixel_count",
                "centroid_longitude",
                "centroid_latitude",
                "max_anomaly_score",
                "mean_anomaly_score",
                "mean_mineralization_score",
                "max_mineralization_score",
                "mineralization_percentile",
                "rank_score",
            ]
        ]
        lines.append(top10.to_string(index=False))

    lines.append("")
    lines.append(_provenance_banner(in_path))
    text = "\n".join(lines)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")
    return text


def run(
    in_path: Path = DEFAULT_IN_PATH,
    out_path: Path = DEFAULT_OUT_PATH,
    report_path: Path = DEFAULT_REPORT_PATH,
    top_percentile: float = 1.0,
    eps_m: float = 150.0,
    min_samples: int = 5,
) -> pd.DataFrame:
    df = load_anomalies(in_path)
    input_pixels = len(df)
    print(f"Loaded {input_pixels} scored pixels from {in_path}")

    selected = select_high_anomaly_pixels(df, top_percentile)
    print(f"Selected {len(selected)} pixel(s) in the top {top_percentile}% by anomaly score")

    if selected.empty:
        raise ValueError("No pixels selected at this percentile threshold; nothing to cluster.")

    x_m, y_m, epsg = project_to_metric(selected)
    print(f"Projected coordinates to EPSG:{epsg} for metric clustering")

    pixel_spacing_m = estimate_pixel_spacing_m(x_m, y_m)
    pixel_area_m2 = pixel_spacing_m ** 2

    labels = cluster_pixels(x_m, y_m, eps_m=eps_m, min_samples=min_samples)
    n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
    print(f"DBSCAN produced {n_clusters} spatial cluster(s) (eps={eps_m}m, min_samples={min_samples})")

    sites, n_noise = build_candidate_sites(selected, labels, x_m, y_m, pixel_area_m2)
    sites = rank_candidates(sites)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    sites.to_csv(out_path, index=False)
    print(f"Saved {len(sites)} candidate site(s) to {out_path}")

    report_text = write_report(
        report_path,
        in_path,
        input_pixels=input_pixels,
        selected_pixels=len(selected),
        top_percentile=top_percentile,
        eps_m=eps_m,
        min_samples=min_samples,
        pixel_spacing_m=pixel_spacing_m,
        n_noise=n_noise,
        sites=sites,
    )
    print(report_text)
    print(f"Report saved to: {report_path}")

    return sites


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Cluster high-anomaly pixels from mineralization_scoring.py output into "
            "potential mineralization / manganese exploration target candidates. NOT a "
            "manganese detector -- output requires geological/ground-truth validation."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_IN_PATH, help="Path to mineralization_scores.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT_PATH, help="Path to write candidate_sites.csv")
    parser.add_argument(
        "--report", type=Path, default=DEFAULT_REPORT_PATH, help="Path to write the summary report (text)"
    )
    parser.add_argument(
        "--top-percentile",
        type=float,
        default=1.0,
        help="Keep the top N percent most anomalous pixels, e.g. 1.0, 0.5, or 0.1 (default: 1.0)",
    )
    parser.add_argument(
        "--eps",
        type=float,
        default=150.0,
        help="DBSCAN neighborhood radius in metres (default: 150.0)",
    )
    parser.add_argument(
        "--min-samples",
        type=int,
        default=5,
        help="DBSCAN minimum pixels to form a cluster (default: 5)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    run(
        in_path=args.input,
        out_path=args.output,
        report_path=args.report,
        top_percentile=args.top_percentile,
        eps_m=args.eps,
        min_samples=args.min_samples,
    )


if __name__ == "__main__":
    main()
