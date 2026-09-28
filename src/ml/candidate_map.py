"""
Geographic visualization stage for the SIH Manganese AI Project, built on
top of data/processed/candidate_sites.csv (produced by candidate_detection.py,
which this script does not modify).

Renders every candidate site from that CSV onto an interactive Leaflet map
(via folium) and saves it as a single self-contained HTML file that opens
directly in a browser -- no server, no extra services. Candidates are
colored/sized by rank_score, and the top 10 are put in their own toggleable
layer so they stand out immediately. Clicking a marker shows every field for
that candidate.

IMPORTANT — terminology: markers on this map represent "potential
mineralization / manganese exploration target" candidates ONLY. They are NOT
confirmed manganese deposits -- this project has never used any real
manganese location as ground truth. Every candidate requires independent
geological / ground-truth validation. The map is deliberately generic: it
never hardcodes Keonjhar, T45QUE, or any known deposit location -- it just
plots whatever candidate_sites.csv contains, so the exact same script runs
against any future scene (e.g. the correctly preprocessed T45QUE data).
"""

import argparse
from pathlib import Path

import folium
import pandas as pd
from branca.colormap import LinearColormap

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IN_PATH = PROJECT_ROOT / "data" / "processed" / "candidate_sites.csv"
DEFAULT_OUT_PATH = PROJECT_ROOT / "data" / "processed" / "candidate_sites_map.html"

REQUIRED_COLUMNS = [
    "candidate_id",
    "rank",
    "centroid_longitude",
    "centroid_latitude",
    "pixel_count",
    "mean_anomaly_score",
    "max_anomaly_score",
    "anomaly_percentile",
    "rank_score",
]

TOP_N_HIGHLIGHT = 10


def load_candidates(in_path: Path) -> pd.DataFrame:
    if not in_path.is_file():
        raise FileNotFoundError(f"Candidate sites file not found: {in_path}")
    df = pd.read_csv(in_path)
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Expected column(s) missing from {in_path}: {missing}")
    return df.sort_values("rank").reset_index(drop=True)


def _popup_html(row: pd.Series) -> str:
    area_line = ""
    if "area_m2" in row.index and pd.notna(row["area_m2"]):
        area_line = f"<tr><td>Spatial extent</td><td>{row['area_m2']:.1f} m&sup2;</td></tr>"
    mineralization_lines = ""
    if "mean_mineralization_score" in row.index and pd.notna(row["mean_mineralization_score"]):
        mineralization_lines = f"""
        <tr><td>Mean mineralization score</td><td>{row['mean_mineralization_score']:.2f}</td></tr>
        <tr><td>Max mineralization score</td><td>{row['max_mineralization_score']:.2f}</td></tr>
        <tr><td>Mineralization percentile</td><td>{row['mineralization_percentile']:.2f}</td></tr>"""
    return f"""
    <div style="font-family: sans-serif; font-size: 13px;">
      <b>{row['candidate_id']}</b> (rank {int(row['rank'])})<br>
      <i>Potential mineralization / manganese exploration target -- NOT a confirmed manganese deposit</i>
      <table>
        <tr><td>Longitude</td><td>{row['centroid_longitude']:.6f}</td></tr>
        <tr><td>Latitude</td><td>{row['centroid_latitude']:.6f}</td></tr>
        <tr><td>Pixel count</td><td>{int(row['pixel_count'])}</td></tr>
        <tr><td>Mean anomaly score</td><td>{row['mean_anomaly_score']:.6f}</td></tr>
        <tr><td>Max anomaly score</td><td>{row['max_anomaly_score']:.6f}</td></tr>
        <tr><td>Anomaly percentile</td><td>{row['anomaly_percentile']:.3f}</td></tr>
        {mineralization_lines}
        {area_line}
        <tr><td>Rank score</td><td>{row['rank_score']:.2f}</td></tr>
      </table>
    </div>
    """


def build_map(
    df: pd.DataFrame,
    pipeline_test: bool,
    scene_label: str,
) -> folium.Map:
    center_lat = float(df["centroid_latitude"].mean())
    center_lon = float(df["centroid_longitude"].mean())

    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=11, tiles="OpenStreetMap")

    colormap = LinearColormap(
        colors=["#2c7bb6", "#ffffbf", "#d7191c"],
        vmin=float(df["rank_score"].min()),
        vmax=float(df["rank_score"].max()),
        caption="rank_score (anomaly strength + spatial density)",
    )
    colormap.add_to(fmap)

    top_group = folium.FeatureGroup(name=f"Top {TOP_N_HIGHLIGHT} candidates", show=True)
    other_group = folium.FeatureGroup(name="Other candidates", show=True)

    for _, row in df.iterrows():
        is_top = row["rank"] <= TOP_N_HIGHLIGHT
        radius = 10 if is_top else 5
        color = colormap(row["rank_score"])
        marker = folium.CircleMarker(
            location=[row["centroid_latitude"], row["centroid_longitude"]],
            radius=radius,
            color="black" if is_top else color,
            weight=2 if is_top else 1,
            fill=True,
            fill_color=color,
            fill_opacity=0.9 if is_top else 0.6,
            popup=folium.Popup(_popup_html(row), max_width=320),
            tooltip=f"{row['candidate_id']} (rank {int(row['rank'])}, score {row['rank_score']:.1f})",
        )
        marker.add_to(top_group if is_top else other_group)

    top_group.add_to(fmap)
    other_group.add_to(fmap)
    folium.LayerControl(collapsed=False).add_to(fmap)

    banner_note = (
        f"PIPELINE TEST -- source scene: {scene_label}. Coordinates below are NOT "
        "evidence of manganese anywhere."
        if pipeline_test
        else f"Source scene: {scene_label}."
    )
    title_html = f"""
    <div style="position: fixed; top: 10px; left: 60px; z-index: 9999;
                background: white; padding: 10px 14px; border: 2px solid #444;
                border-radius: 6px; font-family: sans-serif; max-width: 480px;">
      <b>Potential Mineralization / Manganese Exploration Targets</b><br>
      <span style="font-size: 12px;">
        Potential mineralization / manganese exploration target candidates
        requiring geological / ground-truth validation.
        <b>NOT confirmed manganese deposits.</b><br>
        {banner_note}<br>
        {len(df)} candidate site(s) shown, ranked by rank_score.
      </span>
    </div>
    """
    fmap.get_root().html.add_child(folium.Element(title_html))

    return fmap


def run(
    in_path: Path = DEFAULT_IN_PATH,
    out_path: Path = DEFAULT_OUT_PATH,
    pipeline_test: bool = True,
    scene_label: str = "UNKNOWN (verify against source ml_features.csv)",
) -> Path:
    df = load_candidates(in_path)
    print(f"Loaded {len(df)} candidate site(s) from {in_path}")

    if df.empty:
        raise ValueError("No candidate sites to map.")

    fmap = build_map(df, pipeline_test=pipeline_test, scene_label=scene_label)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(out_path))
    print(f"Saved interactive map to: {out_path}")
    return out_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Render candidate_sites.csv as an interactive Leaflet map (folium). "
            "Markers are spectral anomaly candidate sites / potential mineralization "
            "targets -- NOT confirmed manganese deposits."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_IN_PATH, help="Path to candidate_sites.csv")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT_PATH, help="Path to write the map HTML")
    parser.add_argument(
        "--scene-label",
        type=str,
        default="UNKNOWN (verify against source ml_features.csv)",
        help="Human-readable label for which scene this run's data came from, e.g. 'T35XNG' or 'T45QUE'",
    )
    parser.add_argument(
        "--pipeline-test",
        dest="pipeline_test",
        action="store_true",
        default=True,
        help="Mark the map as a pipeline test run (default: on)",
    )
    parser.add_argument(
        "--no-pipeline-test",
        dest="pipeline_test",
        action="store_false",
        help="Turn off the pipeline-test banner once data is a validated production scene",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    run(
        in_path=args.input,
        out_path=args.output,
        pipeline_test=args.pipeline_test,
        scene_label=args.scene_label,
    )


if __name__ == "__main__":
    main()
