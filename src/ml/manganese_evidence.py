"""
Auxiliary, diagnostic-only "manganese evidence" layer for candidate_sites.csv
rows, built entirely from values mineralization_scoring.py already computed
(no new spectral formula, no rerun of any upstream stage).

manganese_prospectivity_score = the candidate's alteration_percentile
(nearest-pixel match to its centroid, from mineralization_scores.csv) --
the scene-wide percentile of the mean of FE_OXIDE_ND/CLAY_MINERAL_ND/
FERROUS_ND. This is the same generic iron-oxide/clay/hydroxyl alteration
signal already used inside mineralization_score, simply exposed on its own
under an honest name, because published literature (Vasilatos et al. 2023,
Bulletin of the Geological Society of Greece) found Sentinel-2's SWIR-based
alteration indices can map the broader alteration halo associated with Fe-Mn
mineralization -- NOT that they can distinguish manganese from iron within
that halo. This score is NOT manganese-specific, is NOT a new index, and
must never be treated as a manganese detector.

Writes a SEPARATE file (candidate_id, manganese_prospectivity_score,
geological_belt_context, limitation note) -- never modifies candidate_sites.csv,
mineralization_scores.csv, or any other existing pipeline output.
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

LIMITATION_NOTE = (
    "Diagnostic only. Derived from generic iron-oxide/clay/hydroxyl alteration "
    "indices (FE_OXIDE_ND, CLAY_MINERAL_ND, FERROUS_ND), NOT a manganese-specific "
    "spectral signature. Cannot distinguish manganese from other alteration "
    "sources (iron oxide, bauxite/laterite, exposed rock). No manganese "
    "ground-truth data exists in this project to validate this score. "
    "Not used in anomaly_score, mineralization_score, or rank_score."
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute an auxiliary, diagnostic-only manganese evidence layer.")
    parser.add_argument("--candidates", type=Path, required=True, help="Path to candidate_sites.csv (read-only)")
    parser.add_argument("--scores", type=Path, required=True, help="Path to mineralization_scores.csv (read-only)")
    parser.add_argument("--output", type=Path, required=True, help="Path to write the new manganese_evidence.csv")
    parser.add_argument(
        "--belt-context", type=str, required=True,
        help="Honest, factual note on whether this AOI is a documented manganese belt (from AOI_PRESETS context)",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    cand = pd.read_csv(args.candidates)
    scores = pd.read_csv(args.scores, usecols=["longitude", "latitude", "alteration_percentile"])
    print(f"Loaded {len(cand)} candidates from {args.candidates}")
    print(f"Loaded {len(scores)} scored pixels from {args.scores}")

    tree = cKDTree(scores[["longitude", "latitude"]].to_numpy())
    dist, idx = tree.query(cand[["centroid_longitude", "centroid_latitude"]].to_numpy(), k=1)
    print(f"Nearest-pixel match distance (deg): max={dist.max():.6f}, mean={dist.mean():.6f}")

    out = pd.DataFrame({
        "candidate_id": cand["candidate_id"],
        "manganese_prospectivity_score": scores["alteration_percentile"].to_numpy()[idx],
        "geological_belt_context": args.belt_context,
        "limitation": LIMITATION_NOTE,
    })

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False)
    print(f"\nSaved {len(out)} row(s) to {args.output}")
    print(f"manganese_prospectivity_score range: [{out['manganese_prospectivity_score'].min():.3f}, "
          f"{out['manganese_prospectivity_score'].max():.3f}]")
    print(out.head(5)[["candidate_id", "manganese_prospectivity_score"]].to_string(index=False))


if __name__ == "__main__":
    main()
