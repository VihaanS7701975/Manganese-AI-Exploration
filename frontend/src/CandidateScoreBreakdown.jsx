import React from 'react';
import { levelOf, LEVEL_BAR_CLASS, LEVEL_TEXT_CLASS, LEVEL_BADGE_CLASS } from './potentialLevel.js';

const isFiniteNum = (v) => typeof v === 'number' && Number.isFinite(v);

// Each row's exact source field on the real `nearest_candidate` object
// returned by POST /api/predict (backend/main.py, itself a pass-through of
// candidate_detection.py's candidate_sites.csv row -- see the "Additional
// columns already present..." comment there). No renaming, no derived or
// estimated values: mineralization_percentile/anomaly_percentile/
// density_percentile/strength_percentile are the exact same 0-100
// percentile fields ExplainableAI.jsx already reads from this object.
const METRIC_ROWS = [
  { field: 'mineralization_percentile', icon: '⛏️', label: 'Mineralization', clause: 'strong mineralization', solo: 'its strong mineralization score' },
  { field: 'anomaly_percentile', icon: '📍', label: 'Anomaly', clause: 'anomalous spectral characteristics', solo: 'its anomalous spectral signature' },
  { field: 'density_percentile', icon: '📊', label: 'Density', clause: 'a dense, spatially coherent cluster', solo: 'its dense, spatially coherent cluster' },
  { field: 'strength_percentile', icon: '💪', label: 'Strength', clause: 'a strong relative anomaly signal', solo: 'its strong relative anomaly signal' },
];

function joinWithAnd(parts) {
  if (parts.length === 0) return '';
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`;
  return `${parts.slice(0, -1).join(', ')}, and ${parts[parts.length - 1]}`;
}

// Builds a short, honest sentence from whichever metrics are actually
// present -- never claims a factor is "strong" unless its own real value
// crosses the same HIGH cutoff used everywhere else (potentialLevel.js),
// and never mentions a metric that isn't available on this candidate.
function buildExplanation(candidate, level, available) {
  if (!level || available.length === 0) return null;
  const priorityWord = level === 'HIGH' ? 'High' : level === 'MODERATE' ? 'Moderate' : 'Low';

  if (level === 'HIGH') {
    const strong = available.filter((m) => candidate[m.field] >= 75);
    if (strong.length >= 2) {
      return `${priorityWord} priority due to ${joinWithAnd(strong.map((m) => m.clause))}.`;
    }
    if (strong.length === 1) {
      return `${priorityWord} priority based on ${strong[0].solo}.`;
    }
  }

  const names = available.map((m) => m.label.toLowerCase());
  const plural = names.length > 1 ? 'scores' : 'score';
  return `${priorityWord} priority based on its current ${joinWithAnd(names)} ${plural}.`;
}

// Compact "why is this candidate ranked the way it is" card for whichever
// candidate is currently selected -- reuses the exact same `nearest_candidate`
// object already flowing through App.jsx's `prediction` state (from
// fetchPrediction/POST /api/predict), the same object ExplainableAI.jsx and
// the Classification Result card already consume. No new selection state,
// no new fetch, no new scoring: purely a compact read of existing fields.
export default function CandidateScoreBreakdown({ candidate }) {
  if (!candidate) {
    return (
      <p className="text-[10px] font-sans text-slate-400 text-center py-2 italic">
        Select a candidate to inspect its score.
      </p>
    );
  }

  const available = METRIC_ROWS.filter((m) => isFiniteNum(candidate[m.field]));
  const level = levelOf(candidate.rank_score);
  const explanation = buildExplanation(candidate, level, available);

  return (
    <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2 flex flex-col gap-2">
      <div className="flex items-center justify-between pb-1.5 border-b border-purple-500/15">
        <span className="text-[10px] font-mono font-bold text-white truncate">
          {candidate.candidate_id ?? 'CANDIDATE'}
        </span>
        {isFiniteNum(candidate.rank) && (
          <span className="text-[10px] font-mono text-slate-300 shrink-0">
            🏆 #{candidate.rank}
            {isFiniteNum(candidate.total_candidates) && (
              <span className="text-slate-500"> / {candidate.total_candidates}</span>
            )}
          </span>
        )}
      </div>

      {available.length === 0 ? (
        <p className="text-[10px] font-sans text-slate-400 italic">
          No score breakdown metrics available for this candidate.
        </p>
      ) : (
        <div className="flex flex-col gap-1.5">
          {available.map((m) => {
            const value = candidate[m.field];
            const rowLevel = levelOf(value);
            return (
              <div key={m.field}>
                <div className="flex items-center justify-between text-[10px] font-mono mb-0.5">
                  <span className="text-white font-semibold flex items-center gap-1">
                    <span>{m.icon}</span> {m.label}
                  </span>
                  <span className={`font-bold ${LEVEL_TEXT_CLASS[rowLevel] ?? 'text-white'}`}>
                    {value.toFixed(1)}%ile
                  </span>
                </div>
                <div className="w-full bg-slate-800 h-1 rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${LEVEL_BAR_CLASS[rowLevel] ?? 'bg-slate-600'}`}
                    style={{ width: `${Math.min(100, Math.max(2, value))}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {level && (
        <div className="flex items-center justify-between pt-1 border-t border-purple-500/15">
          <span className="text-[10px] font-sans font-semibold uppercase tracking-wide text-slate-300">Potential</span>
          <span className={`px-1.5 py-0.5 rounded text-[9px] font-mono font-bold border ${LEVEL_BADGE_CLASS[level]}`}>
            {level}
          </span>
        </div>
      )}

      {explanation && (
        <p className="text-[10px] font-sans text-slate-200 leading-snug bg-slate-950/50 border border-purple-500/10 rounded p-1.5">
          {explanation}
        </p>
      )}
    </div>
  );
}
