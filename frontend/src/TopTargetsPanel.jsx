import React, { useEffect, useMemo, useState } from 'react';
import { Radio, X } from 'lucide-react';
import { levelOf, LEVEL_BADGE_CLASS, LEVEL_TEXT_CLASS } from './potentialLevel.js';

const isFiniteNum = (v) => typeof v === 'number' && Number.isFinite(v);

const TOP_DEFAULT = 10;
// C2 scale handling: the T45QUE set holds ~8,262 ranked candidates, so the
// drawer pages through the whole already-loaded `candidates` array instead
// of capping at a fixed Top 10/25 window no one can scroll past.
const PAGE_SIZE = 25;

// The single right-side ranking panel (also formerly duplicated as a
// left-menu flyout -- that duplicate has been removed; this is now the
// only ranking UI). Reads the already-loaded `candidates` array
// (candidate_sites.csv rows for whichever dataset is active, from
// /api/candidates) -- no new ranking is computed here, just a compact view
// over the existing `rank` / `rank_score` fields. Clicking a row reuses
// fetchPrediction (via onSelectCandidate), the same navigation flow every
// other candidate-selection control already uses.
//
// Positioning-agnostic by design: the root element just fills whatever box
// its parent gives it (w-72, h-full) -- App.jsx's shared right-side flex
// row (Mineral Potential Legend + this panel) owns the actual
// absolute/top/right/bottom placement, so this component doesn't fight
// with the legend over the same screen coordinates.
export default function TopTargetsPanel({ candidates, loading, error, selectedCandidateId, onSelectCandidate, onClose }) {
  const [page, setPage] = useState(0);
  const [rankJump, setRankJump] = useState('');
  const [topOnly, setTopOnly] = useState(false);

  const ranked = useMemo(() => {
    if (!Array.isArray(candidates)) return [];
    return candidates
      .filter((c) => isFiniteNum(c?.rank) && isFiniteNum(c?.rank_score))
      .slice()
      .sort((a, b) => a.rank - b.rank);
  }, [candidates]);

  // Reset paging whenever the dataset (and therefore the array) changes.
  useEffect(() => {
    setPage(0);
    setRankJump('');
    setTopOnly(false);
  }, [candidates]);

  const totalPages = Math.max(1, Math.ceil(ranked.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages - 1);
  const pageStart = safePage * PAGE_SIZE;
  const visible = topOnly
    ? ranked.slice(0, TOP_DEFAULT)
    : ranked.slice(pageStart, pageStart + PAGE_SIZE);

  const goToRank = () => {
    const n = parseInt(rankJump, 10);
    if (!Number.isFinite(n) || n < 1 || ranked.length === 0) return;
    const clamped = Math.min(n, ranked.length);
    setTopOnly(false);
    setPage(Math.floor((clamped - 1) / PAGE_SIZE));
  };

  return (
    <div className="w-72 h-full flex flex-col">
      <div className="gis-lavender-card p-2.5 flex flex-col gap-1.5 max-h-full overflow-hidden">
        <div className="flex items-center justify-between pb-1.5 border-b border-purple-500/20 shrink-0">
          <h2 className="text-[10px] font-bold font-sans uppercase tracking-wider text-white flex items-center gap-1">
            <span>🏆</span> Rank Index
          </h2>
          <div className="flex items-center gap-1 shrink-0">
            <span
              className="font-mono text-[9px] text-slate-300 shrink-0"
              title={`${ranked.length} ranked candidates loaded`}
            >
              {ranked.length.toLocaleString()} TOTAL
            </span>
            <button
              onClick={() => setTopOnly((prev) => !prev)}
              className="gis-btn-lavender-ghost px-1.5 py-0.5 text-[9px] text-white shrink-0"
              title={topOnly ? 'Show paged full ranking' : 'Show only Top 10'}
            >
              <span className="text-white font-bold">{topOnly ? 'VIEW ALL' : 'TOP 10'}</span>
            </button>
            {onClose && (
              <button
                onClick={onClose}
                className="p-0.5 rounded-full bg-slate-950/80 hover:bg-purple-500/30 text-slate-300 hover:text-white border border-purple-500/30 transition-colors duration-150 cursor-pointer"
                title="Close Rank Index"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {loading ? (
          <div className="flex flex-col items-center justify-center gap-2 py-4 animate-pulse">
            <Radio className="w-5 h-5 text-purple-400 animate-spin" />
            <p className="text-[10px] font-mono text-slate-300 uppercase tracking-wider">
              Loading candidates...
            </p>
          </div>
        ) : error || ranked.length === 0 ? (
          <p className="text-[11px] font-sans text-slate-300 text-center py-3">
            No ranked candidates available.
          </p>
        ) : (
          <div className="flex flex-col gap-1 overflow-y-auto custom-scrollbar pr-0.5 max-h-[55vh]">
            {!topOnly && totalPages > 1 && (
              <div className="flex items-center justify-between gap-1 pb-1 shrink-0">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={safePage === 0}
                  className="gis-btn-lavender-ghost px-1.5 py-0.5 text-[9px] text-white shrink-0 disabled:opacity-30"
                  title="Previous page"
                >
                  <span className="text-white font-bold">‹ PREV</span>
                </button>
                <span className="font-mono text-[9px] text-slate-300">
                  {pageStart + 1}–{Math.min(pageStart + PAGE_SIZE, ranked.length)} / {ranked.length.toLocaleString()}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={safePage >= totalPages - 1}
                  className="gis-btn-lavender-ghost px-1.5 py-0.5 text-[9px] text-white shrink-0 disabled:opacity-30"
                  title="Next page"
                >
                  <span className="text-white font-bold">NEXT ›</span>
                </button>
              </div>
            )}
            {visible.map((c) => {
              const level = levelOf(c.rank_score);
              const isSelected = selectedCandidateId != null && c.candidate_id === selectedCandidateId;
              const canNavigate = isFiniteNum(c.centroid_latitude) && isFiniteNum(c.centroid_longitude);
              return (
                <button
                  key={c.candidate_id ?? c.rank}
                  onClick={() => canNavigate && onSelectCandidate && onSelectCandidate(c)}
                  disabled={!canNavigate}
                  className={`w-full text-left rounded-lg border flex items-center gap-1.5 px-1.5 py-1 transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-40 ${
                    isSelected
                      ? 'bg-purple-500/25 border-purple-400/70 shadow-[0_0_12px_rgba(168,85,247,0.25)]'
                      : 'bg-slate-950/50 border-slate-800/90 hover:bg-purple-500/10 hover:border-purple-500/30'
                  }`}
                  title={`${c.candidate_id ?? ''} -- Rank #${c.rank}`}
                >
                  <span className="font-mono text-[9px] font-bold text-slate-400 w-5 shrink-0">
                    #{c.rank}
                  </span>
                  <span className="flex-1 min-w-0 font-mono text-[9px] font-semibold text-white truncate">
                    {c.candidate_id ?? '--'}
                  </span>
                  {level && (
                    <span className={`shrink-0 rounded font-mono font-bold border text-[7px] px-1 py-0.5 ${LEVEL_BADGE_CLASS[level]}`}>
                      {level}
                    </span>
                  )}
                  <span className={`shrink-0 font-mono font-black tabular-nums text-[11px] ${LEVEL_TEXT_CLASS[level] ?? 'text-white'}`}>
                    {c.rank_score.toFixed(1)}
                  </span>
                </button>
              );
            })}
            {!topOnly && ranked.length > PAGE_SIZE && (
              <div className="flex items-center gap-1 pt-1 shrink-0">
                <input
                  value={rankJump}
                  onChange={(e) => setRankJump(e.target.value.replace(/[^0-9]/g, ''))}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') goToRank();
                  }}
                  placeholder={`Rank 1–${ranked.length.toLocaleString()}`}
                  inputMode="numeric"
                  className="flex-1 min-w-0 bg-slate-950/60 border border-purple-500/25 rounded px-1.5 py-1 font-mono text-[9px] text-white placeholder:text-slate-500 focus:outline-none focus:border-purple-400/60"
                  title="Jump to a rank"
                />
                <button
                  onClick={goToRank}
                  className="gis-btn-lavender-ghost px-1.5 py-1 text-[9px] text-white shrink-0"
                  title="Jump to rank"
                >
                  <span className="text-white font-bold">GO</span>
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
