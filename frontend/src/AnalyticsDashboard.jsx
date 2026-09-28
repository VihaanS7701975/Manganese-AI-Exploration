import React, { useMemo } from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as ChartTooltip,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts';
import { BarChart3, Trophy, Radio } from 'lucide-react';
import { HIGH_CUTOFF, MODERATE_CUTOFF, LEVEL_BAR_CLASS, LEVEL_TEXT_CLASS } from './potentialLevel.js';

const isFiniteNum = (v) => typeof v === 'number' && Number.isFinite(v);

const mean = (arr) => (arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : null);

// Fixed 0-100 range in 10-wide buckets -- rank_score's confirmed scale, so
// bins stay meaningful and comparable across any candidate subset.
const HISTOGRAM_BIN_WIDTH = 10;

function buildHistogram(scores) {
  const bins = Array.from({ length: 10 }, (_, i) => ({
    bin: `${i * HISTOGRAM_BIN_WIDTH}-${i * HISTOGRAM_BIN_WIDTH + HISTOGRAM_BIN_WIDTH}`,
    count: 0,
  }));
  scores.forEach((s) => {
    const idx = Math.min(9, Math.max(0, Math.floor(s / HISTOGRAM_BIN_WIDTH)));
    bins[idx].count += 1;
  });
  return bins;
}

export default function AnalyticsDashboard({ candidates, loading, error, onExploreCandidate }) {
  const stats = useMemo(() => {
    if (!Array.isArray(candidates) || candidates.length === 0) return null;

    const scores = candidates.map((c) => c?.rank_score).filter(isFiniteNum);
    const anomalyPercentiles = candidates.map((c) => c?.anomaly_percentile).filter(isFiniteNum);
    const mineralPercentiles = candidates.map((c) => c?.mineralization_percentile).filter(isFiniteNum);

    if (scores.length === 0) return null;

    const totalCandidates = candidates.length;
    const highPotentialCount = scores.filter((s) => s >= HIGH_CUTOFF).length;
    const highestScore = Math.max(...scores);
    const averageScore = mean(scores);

    const highCount = scores.filter((s) => s >= HIGH_CUTOFF).length;
    const moderateCount = scores.filter((s) => s >= MODERATE_CUTOFF && s < HIGH_CUTOFF).length;
    const lowCount = scores.filter((s) => s < MODERATE_CUTOFF).length;

    const histogram = buildHistogram(scores);

    const anomalyStats = anomalyPercentiles.length
      ? {
          highest: Math.max(...anomalyPercentiles),
          average: mean(anomalyPercentiles),
          highCount: anomalyPercentiles.filter((v) => v >= HIGH_CUTOFF).length,
        }
      : null;

    const mineralStats = mineralPercentiles.length
      ? {
          highest: Math.max(...mineralPercentiles),
          average: mean(mineralPercentiles),
          highCount: mineralPercentiles.filter((v) => v >= HIGH_CUTOFF).length,
        }
      : null;

    const bestTarget = candidates.reduce((best, c) => {
      if (!isFiniteNum(c?.rank_score)) return best;
      if (!best || c.rank_score > best.rank_score) return c;
      return best;
    }, null);

    return {
      totalCandidates,
      highPotentialCount,
      highestScore,
      averageScore,
      distribution: {
        high: { count: highCount, pct: (highCount / scores.length) * 100 },
        moderate: { count: moderateCount, pct: (moderateCount / scores.length) * 100 },
        low: { count: lowCount, pct: (lowCount / scores.length) * 100 },
        total: scores.length,
      },
      histogram,
      anomalyStats,
      mineralStats,
      bestTarget,
    };
  }, [candidates]);

  return (
    <div className="gis-lavender-card p-3 flex flex-col gap-2.5">
      <div className="flex items-center gap-2 pb-2 border-b border-purple-500/20">
        <BarChart3 className="w-3.5 h-3.5 text-purple-300 shrink-0" />
        <h2 className="text-xs font-bold font-sans uppercase tracking-wider text-white">
          📊 Exploration Analytics
        </h2>
      </div>

      {loading ? (
        <div className="flex flex-col items-center justify-center gap-2 py-4 animate-pulse">
          <Radio className="w-5 h-5 text-purple-400 animate-spin" />
          <p className="text-[10px] font-mono text-slate-300 uppercase tracking-wider">
            Aggregating candidate dataset...
          </p>
        </div>
      ) : error || !stats ? (
        <p className="text-[11px] font-sans text-slate-300 text-center py-3">
          No analytics data available.
        </p>
      ) : (
        <>
          {/* KPI CARDS */}
          <div className="grid grid-cols-2 gap-2">
            <div className="gis-metric-tile border-purple-500/20">
              <span className="gis-spec-label text-white">TOTAL CANDIDATES</span>
              <p className="text-lg font-bold font-mono text-white tracking-tight mt-1">
                {stats.totalCandidates.toLocaleString()}
              </p>
            </div>
            <div className="gis-metric-tile border-purple-500/20">
              <span className="gis-spec-label text-white">HIGH-POTENTIAL</span>
              <p className="text-lg font-bold font-mono text-emerald-400 tracking-tight mt-1">
                {stats.highPotentialCount.toLocaleString()}
              </p>
            </div>
            <div className="gis-metric-tile border-purple-500/20">
              <span className="gis-spec-label text-white">HIGHEST AI SCORE</span>
              <p className="text-lg font-bold font-mono text-white tracking-tight mt-1">
                {stats.highestScore.toFixed(1)}
              </p>
            </div>
            <div className="gis-metric-tile border-purple-500/20">
              <span className="gis-spec-label text-white">AVG AI SCORE</span>
              <p className="text-lg font-bold font-mono text-white tracking-tight mt-1">
                {stats.averageScore.toFixed(1)}
              </p>
            </div>
          </div>

          {/* POTENTIAL DISTRIBUTION */}
          <div>
            <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
              Potential Distribution
            </span>
            <div className="flex flex-col gap-1.5">
              {[
                { key: 'high', label: 'HIGH', d: stats.distribution.high },
                { key: 'moderate', label: 'MODERATE', d: stats.distribution.moderate },
                { key: 'low', label: 'LOW', d: stats.distribution.low },
              ].map(({ key, label, d }) => (
                <div key={key}>
                  <div className="flex justify-between items-center text-[10px] font-mono mb-0.5">
                    <span className={`font-bold ${LEVEL_TEXT_CLASS[label]}`}>{label}</span>
                    <span className="text-white">
                      {d.count.toLocaleString()} <span className="text-slate-400">({d.pct.toFixed(1)}%)</span>
                    </span>
                  </div>
                  <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${LEVEL_BAR_CLASS[label]}`}
                      style={{ width: `${Math.max(0, Math.min(100, d.pct))}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* SCORE DISTRIBUTION HISTOGRAM */}
          <div>
            <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1">
              AI Score Distribution
            </span>
            <div className="w-full h-24">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={stats.histogram} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="bin" stroke="#94a3b8" fontSize={8} tickLine={false} fontFamily="monospace" interval={1} />
                  <YAxis stroke="#94a3b8" fontSize={8} tickLine={false} allowDecimals={false} />
                  <ChartTooltip
                    cursor={{ fill: 'rgba(168, 85, 247, 0.15)' }}
                    contentStyle={{
                      backgroundColor: '#020617',
                      borderColor: '#a855f7',
                      borderRadius: '0.375rem',
                      fontSize: '10px',
                      fontFamily: 'monospace',
                      color: '#ffffff',
                    }}
                  />
                  <Bar dataKey="count" fill="#a855f7" name="Candidates" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* ANOMALY ANALYTICS */}
          {stats.anomalyStats && (
            <div className="rounded border border-purple-500/20 divide-y divide-purple-500/15 bg-slate-950/40">
              <div className="gis-spec-row !border-b-0 !py-1 !px-2">
                <span className="gis-spec-label text-white">ANOMALY ANALYTICS</span>
                <span className="text-[9px] font-mono text-slate-400">anomaly_percentile</span>
              </div>
              <div className="gis-spec-row">
                <span className="gis-spec-label text-white">HIGHEST</span>
                <span className="gis-spec-value">{stats.anomalyStats.highest.toFixed(1)}%ile</span>
              </div>
              <div className="gis-spec-row">
                <span className="gis-spec-label text-white">AVERAGE</span>
                <span className="gis-spec-value">{stats.anomalyStats.average.toFixed(1)}%ile</span>
              </div>
              <div className="gis-spec-row">
                <span className="gis-spec-label text-white">HIGH-ANOMALY TARGETS</span>
                <span className="gis-spec-value">{stats.anomalyStats.highCount.toLocaleString()}</span>
              </div>
            </div>
          )}

          {/* MINERALIZATION ANALYTICS */}
          {stats.mineralStats && (
            <div className="rounded border border-purple-500/20 divide-y divide-purple-500/15 bg-slate-950/40">
              <div className="gis-spec-row !border-b-0 !py-1 !px-2">
                <span className="gis-spec-label text-white">MINERALIZATION ANALYTICS</span>
                <span className="text-[9px] font-mono text-slate-400">mineralization_percentile</span>
              </div>
              <div className="gis-spec-row">
                <span className="gis-spec-label text-white">HIGHEST</span>
                <span className="gis-spec-value">{stats.mineralStats.highest.toFixed(1)}%ile</span>
              </div>
              <div className="gis-spec-row">
                <span className="gis-spec-label text-white">AVERAGE</span>
                <span className="gis-spec-value">{stats.mineralStats.average.toFixed(1)}%ile</span>
              </div>
              <div className="gis-spec-row">
                <span className="gis-spec-label text-white">HIGH-MINERALIZATION TARGETS</span>
                <span className="gis-spec-value">{stats.mineralStats.highCount.toLocaleString()}</span>
              </div>
            </div>
          )}

          {/* BEST TARGET */}
          {stats.bestTarget && (
            <div className="rounded border border-amber-500/30 bg-slate-950/40 p-2">
              <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white flex items-center gap-1.5 mb-1.5">
                <Trophy className="w-3 h-3 text-amber-400" /> Best Target
              </span>
              <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
                {stats.bestTarget.rank !== undefined && (
                  <div><span className="text-slate-400">RANK </span><span className="text-white font-bold">#{stats.bestTarget.rank}</span></div>
                )}
                <div><span className="text-slate-400">AI SCORE </span><span className="text-white font-bold">{stats.bestTarget.rank_score.toFixed(1)}/100</span></div>
                {isFiniteNum(stats.bestTarget.mineralization_percentile) && (
                  <div><span className="text-slate-400">MINERALIZATION </span><span className="text-white font-bold">{stats.bestTarget.mineralization_percentile.toFixed(1)}%ile</span></div>
                )}
                {isFiniteNum(stats.bestTarget.anomaly_percentile) && (
                  <div><span className="text-slate-400">ANOMALY </span><span className="text-white font-bold">{stats.bestTarget.anomaly_percentile.toFixed(1)}%ile</span></div>
                )}
                {isFiniteNum(stats.bestTarget.centroid_latitude) && isFiniteNum(stats.bestTarget.centroid_longitude) && (
                  <div className="col-span-2">
                    <span className="text-slate-400">COORDS </span>
                    <span className="text-white font-bold">
                      {stats.bestTarget.centroid_latitude.toFixed(4)}°N, {stats.bestTarget.centroid_longitude.toFixed(4)}°E
                    </span>
                  </div>
                )}
              </div>

              {/* Reuses the app's existing candidate-selection/map-focus
                  callback (fetchPrediction in App.jsx) -- same function the
                  map click handler and belt buttons already call. No new
                  selection system, no ranking duplicated here. */}
              {onExploreCandidate && isFiniteNum(stats.bestTarget.centroid_latitude) && isFiniteNum(stats.bestTarget.centroid_longitude) && (
                <button
                  onClick={() => onExploreCandidate(stats.bestTarget.centroid_latitude, stats.bestTarget.centroid_longitude)}
                  className="gis-btn-lavender-ghost w-full justify-center mt-2 text-white"
                  title={`Focus the map on ${stats.bestTarget.candidate_id ?? 'the top-ranked candidate'}`}
                >
                  <span className="text-white font-bold">🎯 Explore Best Target</span>
                </button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
