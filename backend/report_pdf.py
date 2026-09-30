"""Server-side PDF exploration report renderer (Task: full PDF report).

Uses only matplotlib (already a project dependency) + stdlib: no new
packages. Every value rendered comes from the caller-supplied payload,
which main.py assembles from the real on-disk pipeline outputs
(/api/report, /api/aoi/search, /api/temporal/*, overlay PNG). Nothing is
synthesized here: unavailable sections are labelled "Not available"
instead of fabricated.

Layout: A4 portrait pages with a header band, footer with page number +
generation timestamp, and one section per page (tables/charts flow onto
extra pages when long).
"""

import io
from datetime import datetime, timezone

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# Professional geological-report palette (muted, print-friendly).
INK = "#1a2332"
MUTED = "#5b6472"
ACCENT = "#8a6d1b"  # dark gold
RULE = "#c9c2ae"
HEADER_BG = "#1a2332"
HEADER_FG = "#f5f1e6"
HIGH = "#c0392b"
MODERATE = "#b7950b"
LOW = "#1e8449"

TITLE = "GeoManganese AI — Mineral Exploration Report"
ORG = "Team RIZZLERS · Smart India Hackathon SIH26009"


def _level(score):
    if score is None:
        return "n/a"
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MODERATE"
    return "LOW"


def _fmt(v, digits=1, suffix=""):
    if v is None:
        return "n/a"
    try:
        return f"{float(v):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return "n/a"


class _Doc:
    """Page helper: header/footer, section titles, wrapped text, tables."""

    def __init__(self, generated_at: str):
        self.generated_at = generated_at
        self.page_no = 0

    def new_page(self):
        fig = plt.figure(figsize=(8.27, 11.69))  # A4 portrait (inches)
        fig.patch.set_facecolor("white")
        self.page_no += 1
        # Header band.
        fig.patches.extend([
            plt.Rectangle((0, 0.94), 1, 0.06, facecolor=HEADER_BG,
                          transform=fig.transFigure, figure=fig,
                          linewidth=0),
        ])
        fig.text(0.05, 0.968, TITLE, color=HEADER_FG, fontsize=11,
                 weight="bold", va="center", ha="left")
        fig.text(0.95, 0.968, ORG, color=HEADER_FG, fontsize=6.5,
                 va="center", ha="right")
        # Footer: page number + generation timestamp.
        fig.text(0.05, 0.03, f"Generated {self.generated_at} (UTC)",
                 color=MUTED, fontsize=6.5, va="center", ha="left")
        fig.text(0.95, 0.03, f"Page {self.page_no}", color=MUTED,
                 fontsize=6.5, va="center", ha="right")
        self.y = 0.89
        return fig

    def section(self, fig, title, subtitle=None):
        fig.text(0.05, self.y, title, color=INK, fontsize=13,
                 weight="bold", va="top", ha="left")
        self.y -= 0.035
        if subtitle:
            fig.text(0.05, self.y, subtitle, color=MUTED, fontsize=8,
                     va="top", ha="left", style="italic")
            self.y -= 0.025
        # Rule.
        ax = fig.add_axes([0.05, self.y - 0.008, 0.9, 0.008])
        ax.axis("off")
        ax.axhline(0.5, color=RULE, linewidth=1)
        self.y -= 0.02

    def para(self, fig, text, size=8.5, gap=0.0, bold=False, color=INK):
        fig.text(0.05, self.y, text, color=color, fontsize=size,
                 va="top", ha="left", weight="bold" if bold else "normal",
                 wrap=True,
                 bbox=dict(boxstyle="square,pad=0", facecolor="white",
                           edgecolor="white"))
        # Rough line-count advance (wraps at ~105 chars at 8.5pt).
        lines = max(1, sum(len(ln) // 105 + 1 for ln in text.split("\n")))
        self.y -= lines * (0.016 if size <= 8.5 else 0.019) + 0.008 + gap

    def note(self, fig, text):
        fig.text(0.05, self.y, text, color=MUTED, fontsize=7.5,
                 va="top", ha="left", style="italic", wrap=True)
        lines = max(1, len(text) // 110 + 1)
        self.y -= lines * 0.015 + 0.012

    def table(self, fig, headers, rows, col_widths=None, fontsize=7):
        """Simple text table; caller must ensure it fits (split rows first)."""
        n = len(headers)
        if col_widths is None:
            col_widths = [0.9 / n] * n
        x = 0.05
        # Header row.
        for h, w in zip(headers, col_widths):
            fig.text(x, self.y, str(h), color="white", fontsize=fontsize,
                     weight="bold", va="top", ha="left",
                     bbox=dict(boxstyle="square,pad=0.35", facecolor=INK,
                               edgecolor=INK))
            x += w
        self.y -= 0.024
        for i, row in enumerate(rows):
            x = 0.05
            bg = "#f4f1e8" if i % 2 == 0 else "white"
            for cell, w in zip(row, col_widths):
                fig.text(x, self.y, str(cell), color=INK, fontsize=fontsize,
                         va="top", ha="left",
                         bbox=dict(boxstyle="square,pad=0.3", facecolor=bg,
                                   edgecolor=bg))
                x += w
            self.y -= 0.020


def _cover(doc, pdf, p):
    fig = doc.new_page()
    fig.text(0.5, 0.78, "GeoManganese AI", color=INK, fontsize=30,
             weight="bold", va="center", ha="center")
    fig.text(0.5, 0.73, "Satellite-based manganese exploration targeting",
             color=MUTED, fontsize=11, va="center", ha="center")
    fig.text(0.5, 0.70, ORG, color=MUTED, fontsize=9, va="center",
             ha="center")
    ax = fig.add_axes([0.2, 0.62, 0.6, 0.005])
    ax.axis("off")
    ax.axhline(0.5, color=ACCENT, linewidth=2)
    info = [
        f"Dataset: {p['dataset']}",
        f"Candidates in dataset: {p['candidate_count']:,}",
        f"Satellite scenes on disk: {p['scene_summary']}",
        f"Generated (UTC): {p['generated_at']}",
    ]
    y = 0.56
    for line in info:
        fig.text(0.5, y, line, color=INK, fontsize=10, va="center",
                 ha="center")
        y -= 0.04
    fig.text(0.08, 0.22,
             "Problem statement: India imports the bulk of its manganese "
             "ore. This report documents a fully unsupervised multispectral "
             "screening pipeline (Sentinel-2 → spectral features → Isolation "
             "Forest anomaly scoring → mineralization blend → DBSCAN "
             "clustering → transparent ranking) that narrows thousands of "
             "square kilometres to a ranked shortlist of exploration "
             "targets. Every candidate is an exploration target requiring "
             "independent geological and ground-truth validation — never a "
             "confirmed deposit.",
             color=INK, fontsize=9, va="top", ha="left", wrap=True)
    fig.text(0.08, 0.10,
             "Illustrative reference-scenario figures (yield tons, deficit "
             "reduction, feasibility) appear for demo context only and are "
             "not ML predictions or measured reserves.",
             color=MUTED, fontsize=8, va="top", ha="left", style="italic",
             wrap=True)
    pdf.savefig(fig)
    plt.close(fig)


def _aoi_imagery(doc, pdf, p):
    fig = doc.new_page()
    doc.section(fig, "1 · Area of interest & satellite source",
                "Real bounds and scenes from files on disk.")
    aoi = p.get("aoi")
    if aoi:
        doc.para(fig,
                 f"Dataset AOI (bounds of the dataset's own candidates plus "
                 f"margin): lon {aoi['lon_min']:.3f}–{aoi['lon_max']:.3f}, "
                 f"lat {aoi['lat_min']:.3f}–{aoi['lat_max']:.3f}.")
    else:
        doc.para(fig, "AOI: not available (no candidate data for this dataset).")
    scenes = (p.get("imagery") or {}).get("scenes") or []
    if scenes:
        doc.table(fig, ["Scene (SAFE)", "Sensing date"],
                  [[s.get("scene_id", "n/a"), s.get("sensing_date") or "n/a"]
                   for s in scenes],
                  col_widths=[0.65, 0.25])
    else:
        doc.para(fig, "Satellite scenes: none found on disk for this dataset.")
    doc.note(fig, "Source: real Sentinel-2 Level-2A products "
             "(Copernicus / AWS Earth Search); bands B02, B03, B04, B08 "
             "(10 m) + B11, B12, SCL (20 m, resampled to the 10 m grid).")
    pdf.savefig(fig)
    plt.close(fig)


def _methodology(doc, pdf, p):
    fig = doc.new_page()
    doc.section(fig, "2 · Methodology (AI/ML screening chain)",
                "Each stage reads the previous stage's files; no black boxes.")
    m = p.get("methodology") or {}
    for key in ("features", "anomaly", "mineralization", "detection",
                "ranking"):
        if m.get(key):
            doc.para(fig, f"{key.capitalize()}: {m[key]}", gap=0.004)
    rw = p.get("rank_weights") or {}
    if rw:
        doc.para(fig, "Ranking weights: " + ", ".join(
            f"{k} = {v}" for k, v in rw.items()), gap=0.004)
    mw = p.get("mineralization_weights")
    if mw:
        doc.para(fig, "Mineralization blend: reward "
                 + ", ".join(f"{k} {v}" for k, v in mw.get("reward", {}).items())
                 + "; penalty "
                 + ", ".join(f"{k} {v}" for k, v in mw.get("penalty", {}).items())
                 + ".", gap=0.004)
    doc.para(fig, "Spectral features / bands: B02, B03, B04, B08, B11, B12 "
             "plus indices NDVI, NDWI, NDBI, BSI and alteration proxies "
             "FE_OXIDE_ND, CLAY_MINERAL_ND, FERROUS_ND with scene brightness "
             "and geographic coordinates.", gap=0.004)
    if p.get("sample_note"):
        doc.note(fig, "Sampling note: " + p["sample_note"])
    pdf.savefig(fig)
    plt.close(fig)


def _charts(doc, pdf, p):
    cands = p.get("candidates") or []
    if not cands:
        return
    import numpy as np
    scores = np.array([c.get("rank_score") for c in cands
                       if c.get("rank_score") is not None], dtype=float)
    fig = doc.new_page()
    doc.section(fig, "3 · Candidate analytics",
                "Distribution of the ranked shortlist (real pipeline output).")
    # Histogram of rank scores.
    ax = fig.add_axes([0.08, 0.52, 0.84, 0.26])
    ax.hist(scores, bins=20, color="#8a6d1b", edgecolor="white")
    ax.set_title("Rank-score distribution (all listed candidates)",
                 fontsize=9, color=INK)
    ax.set_xlabel("rank_score (0–100)", fontsize=8)
    ax.set_ylabel("candidates", fontsize=8)
    ax.tick_params(labelsize=7)
    # Top-10 bar chart.
    top = sorted(cands, key=lambda c: c.get("rank_score") or 0,
                 reverse=True)[:10]
    ax2 = fig.add_axes([0.08, 0.10, 0.84, 0.30])
    labels = [c.get("candidate_id", "?") for c in top]
    vals = [c.get("rank_score") or 0 for c in top]
    colors = [HIGH if v >= 75 else MODERATE if v >= 50 else LOW
              for v in vals]
    ax2.barh(labels[::-1], vals[::-1], color=colors[::-1])
    ax2.set_title("Top-10 candidates by rank_score", fontsize=9, color=INK)
    ax2.set_xlabel("rank_score (0–100)", fontsize=8)
    ax2.tick_params(labelsize=7)
    pdf.savefig(fig)
    plt.close(fig)


def _candidate_table(doc, pdf, p):
    cands = p.get("candidates") or []
    headers = ["ID", "Rank", "Lat, Lon", "Score", "Min%", "Anom%", "Px"]
    widths = [0.16, 0.08, 0.28, 0.10, 0.10, 0.10, 0.08]
    per_page = 30
    for i in range(0, max(len(cands), 1), per_page):
        fig = doc.new_page()
        doc.section(fig, "4 · Ranked candidate table",
                    f"Candidates {i + 1}–{min(i + per_page, len(cands))} "
                    f"of {p['candidate_count']:,} in dataset "
                    f"(showing {len(cands)}).")
        rows = [[
            c.get("candidate_id", "?"),
            c.get("rank", "?"),
            f"{_fmt(c.get('centroid_latitude'), 4)}, "
            f"{_fmt(c.get('centroid_longitude'), 4)}",
            _fmt(c.get("rank_score")),
            _fmt(c.get("mineralization_percentile")),
            _fmt(c.get("anomaly_percentile")),
            c.get("pixel_count", "?"),
        ] for c in cands[i:i + per_page]]
        if rows:
            doc.table(fig, headers, rows, col_widths=widths)
        else:
            doc.para(fig, "No candidates to list (empty dataset).")
        pdf.savefig(fig)
        plt.close(fig)


def _explain(doc, pdf, p):
    sel = p.get("selected_candidate")
    cands = p.get("candidates") or []
    cand = sel or (sorted(cands, key=lambda c: c.get("rank") or 0)[0]
                   if cands else None)
    fig = doc.new_page()
    doc.section(fig, "5 · Explainable AI — score breakdown",
                "Why this target ranks where it does (transparent weights).")
    if not cand:
        doc.para(fig, "No candidate available to explain.")
        pdf.savefig(fig)
        plt.close(fig)
        return
    s = cand.get("strength_percentile") or 0
    d = cand.get("density_percentile") or 0
    m = cand.get("mineralization_percentile") or 0
    doc.para(fig,
             f"Candidate {cand.get('candidate_id')} (rank "
             f"{cand.get('rank')} of {p['candidate_count']:,}) at "
             f"{_fmt(cand.get('centroid_latitude'), 4)}°N, "
             f"{_fmt(cand.get('centroid_longitude'), 4)}°E — overall level "
             f"{_level(cand.get('rank_score'))}.", gap=0.006)
    ax = fig.add_axes([0.08, 0.50, 0.84, 0.22])
    labels = ["Anomaly strength × 0.35", "Spatial density × 0.25",
              "Mineralization × 0.40"]
    vals = [0.35 * s, 0.25 * d, 0.40 * m]
    ax.barh(labels, vals, color=["#5b2d8e", "#1f6f8b", "#8a6d1b"])
    ax.set_title("Contribution to rank_score (score points)",
                 fontsize=9, color=INK)
    ax.set_xlabel("points", fontsize=8)
    ax.tick_params(labelsize=7)
    for lab, v in zip(labels, vals):
        doc.para(fig, f"{lab}: {_fmt(v)} pts", size=8, gap=0.0)
    doc.para(fig,
             f"Anomaly score mean/max: {_fmt(cand.get('mean_anomaly_score'), 3)}"
             f" / {_fmt(cand.get('max_anomaly_score'), 3)}; mineralization "
             f"mean/max: {_fmt(cand.get('mean_mineralization_score'))} / "
             f"{_fmt(cand.get('max_mineralization_score'))}; footprint "
             f"{_fmt(cand.get('area_m2'), 0)} m² over "
             f"{cand.get('pixel_count', '?')} pixels.", gap=0.004)
    if cand.get("geological_belt_context"):
        doc.note(fig, "Geological context (diagnostic only): "
                 + str(cand["geological_belt_context"]))
    if cand.get("manganese_evidence_limitation"):
        doc.note(fig, "Evidence limitation: "
                 + str(cand["manganese_evidence_limitation"]))
    doc.note(fig, "Interpretation: spectral-outlier percentiles relative to "
             "this surveyed scene — not a probability of manganese and not "
             "an assay. Requires ground validation.")
    pdf.savefig(fig)
    plt.close(fig)


def _aoi_temporal(doc, pdf, p):
    fig = doc.new_page()
    doc.section(fig, "6 · AOI search & temporal persistence",
                "User-drawn area results and multi-date supporting evidence.")
    aoi = p.get("aoi_result")
    if aoi is None:
        doc.para(fig, "AOI search: no user AOI was supplied with this "
                 "report — run /api/aoi/search (or Analyze AOI in the app) "
                 "to scope candidates to a drawn area.")
    elif aoi.get("count", 0) == 0:
        doc.para(fig, "AOI search: 0 candidates fall inside the supplied "
                 "area (explicit empty result — nothing fabricated).")
    else:
        doc.para(fig, f"AOI search: {aoi['count']} candidate(s) inside the "
                 f"supplied area; best is {aoi['top_id']} (rank "
                 f"{aoi['top_rank']}, score "
                 f"{_fmt(aoi.get('top_score'))}).")
    t = p.get("temporal") or {}
    scenes = t.get("scenes") or []
    summ = t.get("summary") or {}
    doc.para(fig, f"Observations available: "
             f"{', '.join(scenes) if scenes else 'single observation'}. "
             f"Persistent candidates (within threshold): "
             f"{summ.get('persistent_count', 'n/a')} of "
             f"{summ.get('total', 'n/a')}.", gap=0.004)
    if summ.get("single_scene_note"):
        doc.note(fig, summ["single_scene_note"])
    doc.note(fig, "Persistence across dates is remote-sensing supporting "
             "evidence only, never geological confirmation of manganese.")
    pdf.savefig(fig)
    plt.close(fig)


def _overlay_page(doc, pdf, p):
    fig = doc.new_page()
    doc.section(fig, "7 · Candidate / score-overlay visualization",
                "Pre-rendered pixel-level exploration-potential overlay.")
    img_path = p.get("overlay_path")
    if img_path:
        try:
            from PIL import Image
            im = Image.open(img_path)
            im.thumbnail((1600, 1600))
            ax = fig.add_axes([0.05, 0.12, 0.9, 0.68])
            ax.imshow(im)
            ax.axis("off")
            ax.set_title("RED (≥75) / YELLOW (50–75) / GREEN (<50) "
                         "mineralization-percentile pixels; transparent = "
                         "water / invalid / unscored", fontsize=8, color=INK)
            doc.note(fig, "Overlay source: " + str(img_path) +
                     " — rendered from the pipeline's own per-pixel "
                     "mineralization_percentile, never fabricated.")
        except Exception as exc:
            doc.para(fig, "Overlay image could not be embedded "
                     f"({exc}) — labelled unavailable, not replaced.")
    else:
        doc.para(fig, "Score-overlay image: not available for this dataset "
                 "(no pre-rendered overlay on disk). Candidate coordinates "
                 "in Section 4 remain the authoritative spatial reference.")
    pdf.savefig(fig)
    plt.close(fig)


def _limits(doc, pdf, p):
    fig = doc.new_page()
    doc.section(fig, "8 · Provenance, limitations & disclaimer",
                "What this report is — and is not.")
    doc.para(fig, "Provenance: " + (p.get("generated_note") or "n/a"),
             gap=0.004)
    for lim in p.get("limitations") or []:
        doc.para(fig, "•  " + lim, gap=0.002)
    doc.note(fig, (p.get("shortfall_note") or "") +
             " Yield/deficit/feasibility figures are static "
             "reference-scenario values for demo context.")
    doc.para(fig, "Report generated read-only from pipeline outputs on "
             "disk; regenerate after re-running the chain. "
             f"Timestamp (UTC): {p['generated_at']}.",
             color=MUTED, size=8)
    pdf.savefig(fig)
    plt.close(fig)


def render_exploration_pdf(payload: dict) -> bytes:
    """Render the full multi-page report. All values come from `payload`."""
    buf = io.BytesIO()
    doc = _Doc(payload["generated_at"])
    with PdfPages(buf) as pdf:
        try:
            pdf.infodict()["Title"] = TITLE
            pdf.infodict()["Author"] = ORG
        except Exception:
            pass
        _cover(doc, pdf, payload)
        _aoi_imagery(doc, pdf, payload)
        _methodology(doc, pdf, payload)
        _charts(doc, pdf, payload)
        _candidate_table(doc, pdf, payload)
        _explain(doc, pdf, payload)
        _aoi_temporal(doc, pdf, payload)
        _overlay_page(doc, pdf, payload)
        _limits(doc, pdf, payload)
    return buf.getvalue()
