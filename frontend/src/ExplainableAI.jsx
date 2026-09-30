import React from 'react';
import { Sparkles } from 'lucide-react';
import { levelOf, LEVEL_BAR_CLASS, LEVEL_TEXT_CLASS } from './potentialLevel.js';

function joinWithAnd(parts) {
  if (parts.length === 0) return '';
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`;
  return `${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]}`;
}

function buildExplanation(candidate, factorLevels) {
  const clauses = [];

  if (factorLevels.anomaly === 'HIGH') clauses.push('a strong spectral anomaly signature');
  else if (factorLevels.anomaly === 'MODERATE') clauses.push('a moderate spectral anomaly signature');
  else if (factorLevels.anomaly === 'LOW') clauses.push('a comparatively weak spectral anomaly signature');

  if (factorLevels.mineralization === 'HIGH') clauses.push('high predicted mineralization potential');
  else if (factorLevels.mineralization === 'MODERATE') clauses.push('moderate predicted mineralization potential');
  else if (factorLevels.mineralization === 'LOW') clauses.push('lower predicted mineralization potential');

  if (factorLevels.density === 'HIGH') clauses.push('a dense, spatially coherent anomaly cluster');
  else if (factorLevels.density === 'MODERATE') clauses.push('a moderately coherent anomaly cluster');
  else if (factorLevels.density === 'LOW') clauses.push('a sparse, loosely-packed anomaly footprint');

  const overall = factorLevels.overall;
  const overallWord =
    overall === 'HIGH' ? 'ranked highly among all detected candidates'
    : overall === 'MODERATE' ? 'ranked moderately among all detected candidates'
    : overall === 'LOW' ? 'ranked relatively low among all detected candidates'
    : 'ranked among the detected candidates';

  let sentence = `This location is ${overallWord} (#${candidate.rank} of ${candidate.total_candidates})`;
  sentence += clauses.length ? ` because it shows ${joinWithAnd(clauses)}.` : '.';
  return sentence;
}

const RANK_W = { strength: 0.35, density: 0.25, mineralization: 0.40 };
const num = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);

// F5 ranking-contribution breakdown: rank_score is a weighted mean of three
// 0-100 components (src/ml/candidate_detection.py). Contributions are shown
// in score points so judges see exactly what each factor added.
function contributions(candidate) {
  const s = num(candidate?.strength_percentile);
  const d = num(candidate?.density_percentile);
  const m = num(candidate?.mineralization_percentile);
  const rows = [];
  if (s != null) rows.push({ label: 'Anomaly strength × 0.35', points: RANK_W.strength * s });
  if (d != null) rows.push({ label: 'Spatial density × 0.25', points: RANK_W.density * d });
  if (m != null) rows.push({ label: 'Mineralization × 0.40', points: RANK_W.mineralization * m });
  return rows;
}

export default function ExplainableAI({ candidate, persistence }) {
  const factors = candidate
    ? [
        { key: 'anomaly', label: 'Spectral Anomaly Strength', value: candidate.strength_percentile },
        { key: 'mineralization', label: 'Mineralization Potential', value: candidate.mineralization_percentile },
        { key: 'density', label: 'Target Footprint Density', value: candidate.density_percentile },
        { key: 'overall', label: 'Overall AI Rank Score', value: candidate.rank_score },
      ].filter((f) => f.value !== null && f.value !== undefined && !Number.isNaN(f.value))
    : [];

  const factorLevels = {};
  factors.forEach((f) => {
    factorLevels[f.key] = levelOf(f.value);
  });

  const explanation = candidate ? buildExplanation(candidate, factorLevels) : null;

  const topPct = candidate ? ((candidate.rank / candidate.total_candidates) * 100).toFixed(2) : null;

  const bullets = candidate
    ? [
        `Ranked #${candidate.rank} of ${candidate.total_candidates} candidate sites detected in the surveyed scene (top ${topPct}%).`,
        factorLevels.anomaly &&
          `Spectral anomaly strength is ${factorLevels.anomaly} (${candidate.strength_percentile.toFixed(1)} percentile among candidates; mean anomaly score ${candidate.mean_anomaly_score.toFixed(3)}).`,
        factorLevels.mineralization &&
          `Mineralization potential is ${factorLevels.mineralization} at the ${candidate.mineralization_percentile.toFixed(1)} percentile scene-wide (mean score ${candidate.mean_mineralization_score.toFixed(1)}/100).`,
        factorLevels.density &&
          `Cluster spans ${candidate.pixel_count} pixel(s) (~${Math.round(candidate.area_m2).toLocaleString()} m²) with ${factorLevels.density} spatial density (${candidate.density_percentile.toFixed(1)} percentile).`,
      ].filter(Boolean)
    : [];

  return (
    <div className="gis-lavender-card p-3 flex flex-col gap-2.5">
      <div className="flex items-center gap-2 pb-2 border-b border-purple-500/20">
        <Sparkles className="w-3.5 h-3.5 text-purple-300 shrink-0" />
        <h2 className="text-xs font-bold font-sans uppercase tracking-wider text-white">
          🤖 Explainable AI — Why This Location?
        </h2>
      </div>

      {!candidate ? (
        <p className="text-[11px] font-sans text-slate-300 text-center py-3">
          No AI candidate data available for this location (outside the surveyed exploration area).
        </p>
      ) : (
        <>
          {/* Contributing factors */}
          <div className="flex flex-col gap-2">
            {factors.map((f) => (
              <div key={f.key}>
                <div className="flex justify-between items-center text-[10px] font-mono mb-1">
                  <span className="uppercase tracking-wide text-white font-sans font-semibold">{f.label}</span>
                  <span className={`font-bold ${LEVEL_TEXT_CLASS[factorLevels[f.key]]}`}>
                    {factorLevels[f.key]} · {f.value.toFixed(0)}
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${LEVEL_BAR_CLASS[factorLevels[f.key]]}`}
                    style={{ width: `${Math.min(100, Math.max(2, f.value))}%` }}
                  />
                </div>
              </div>
            ))}
          </div>

          {/* Human-readable explanation */}
          <p className="text-[11px] font-sans text-slate-200 leading-relaxed bg-slate-950/40 border border-purple-500/15 rounded-lg p-2">
            {explanation}
          </p>

          {/* F5: ranking contribution in score points (methodology-transparent) */}
          {(() => {
            const rows = contributions(candidate);
            if (!rows.length) return null;
            const sum = rows.reduce((a, r) => a + r.points, 0);
            return (
              <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2">
                <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
                  Ranking contribution (points of {num(candidate.rank_score) != null ? candidate.rank_score.toFixed(1) : '—'})
                </span>
                {rows.map((r) => (
                  <div key={r.label} className="flex justify-between items-center text-[10px] font-mono mb-0.5">
                    <span className="text-slate-300">{r.label}</span>
                    <span className="text-white font-bold">+{r.points.toFixed(1)}</span>
                  </div>
                ))}
                <div className="flex justify-between items-center text-[10px] font-mono pt-1 mt-1 border-t border-purple-500/15">
                  <span className="text-slate-400">SUM ≈ RANK SCORE</span>
                  <span className="text-white font-bold">{sum.toFixed(1)}</span>
                </div>
              </div>
            );
          })()}

          {/* F5: spectral signals + spatial coherence from real candidate fields */}
          <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2">
            <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
              Spectral signals & spatial coherence
            </span>
            <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
              {[
                ['MEAN ANOMALY', num(candidate.mean_anomaly_score)?.toFixed(3)],
                ['MAX ANOMALY', num(candidate.max_anomaly_score)?.toFixed(3)],
                ['MEAN MINERAL.', num(candidate.mean_mineralization_score)?.toFixed(1)],
                ['MAX MINERAL.', num(candidate.max_mineralization_score)?.toFixed(1)],
                ['ANOMALY %ILE', num(candidate.anomaly_percentile)?.toFixed(1)],
                ['FOOTPRINT', num(candidate.pixel_count) != null ? `${candidate.pixel_count} px` : null],
                ['AREA', num(candidate.area_m2) != null ? `~${Math.round(candidate.area_m2).toLocaleString()} m²` : null],
                ['DENSITY %ILE', num(candidate.density_percentile)?.toFixed(1)],
              ].filter(([, v]) => v != null).map(([k, v]) => (
                <div key={k}><span className="text-slate-400">{k} </span><span className="text-white font-bold">{v}</span></div>
              ))}
            </div>
            {/* F5/F6: temporal persistence when a summary is loaded */}
            <p className="text-[10px] font-sans text-slate-300 mt-1.5 pt-1.5 border-t border-purple-500/15">
              {persistence
                ? `Persistence: signal matched in ${persistence.support_count} other observation(s) — supporting remote-sensing evidence, not confirmation.`
                : 'Persistence: single observation — cross-date support unknown.'}
            </p>
          </div>

          {/* Why This Rank? */}
          <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2">
            <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
              Why This Rank?
            </span>
            <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono mb-2">
              <div><span className="text-slate-400">RANK </span><span className="text-white font-bold">#{candidate.rank} / {candidate.total_candidates}</span></div>
              <div><span className="text-slate-400">AI SCORE </span><span className="text-white font-bold">{candidate.rank_score.toFixed(1)}/100</span></div>
              <div><span className="text-slate-400">MINERALIZATION </span><span className="text-white font-bold">{candidate.mineralization_percentile.toFixed(1)}%ile</span></div>
              <div><span className="text-slate-400">ANOMALY </span><span className="text-white font-bold">{candidate.anomaly_percentile.toFixed(1)}%ile</span></div>
              <div className="col-span-2"><span className="text-slate-400">COORDS </span><span className="text-white font-bold">{candidate.centroid_latitude.toFixed(4)}°N, {candidate.centroid_longitude.toFixed(4)}°E</span></div>
            </div>
            <ul className="text-[10px] font-sans text-slate-200 list-disc list-inside space-y-1">
              {bullets.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          </div>

          {/* MANGANESE EVIDENCE (DIAGNOSTIC ONLY) -- optional, additive field
              from candidate.manganese_prospectivity_score (backend's
              manganese_evidence.csv layer, present for Chennai only so far).
              Deliberately kept separate from "Why This Rank?" above: this
              score does NOT feed rank_score/mineralization_score/anomaly_score. */}
          {typeof candidate.manganese_prospectivity_score === 'number' && !Number.isNaN(candidate.manganese_prospectivity_score) && (
            <div className="rounded border border-amber-500/25 bg-slate-950/40 p-2">
              <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-amber-300 block mb-1.5">
                Manganese Evidence (Diagnostic Only)
              </span>
              <div className="flex justify-between items-center text-[10px] font-mono mb-1.5">
                <span className="uppercase tracking-wide text-white font-sans font-semibold">Prospectivity Score</span>
                <span className="font-bold text-amber-300">{candidate.manganese_prospectivity_score.toFixed(1)} / 100</span>
              </div>
              {candidate.geological_belt_context && (
                <p className="text-[10px] font-sans text-slate-300 mb-1.5">{candidate.geological_belt_context}</p>
              )}
              {candidate.manganese_evidence_limitation && (
                <p className="text-[9px] font-sans text-slate-400 italic">{candidate.manganese_evidence_limitation}</p>
              )}
            </div>
          )}
        </>
      )}

      <p className="text-[9px] font-sans text-slate-400 italic pt-1.5 border-t border-purple-500/10">
        Explanation is based on the available model inputs and derived indicators; it supports exploration decisions and does not replace geological validation.
      </p>
    </div>
  );
}
