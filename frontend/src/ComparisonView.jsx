import React, { useMemo } from 'react';
import { pointInPolygon } from './aoi.js';

// Before/after comparison (F14): reference corridors (built-in belt index)
// vs AI candidate zones (loaded candidates). Overlap is purely geometric
// (candidate centroid inside corridor polygon). Corridor hits do NOT validate
// candidates and AI-only zones are NOT confirmed reserves -- both directions
// are stated in the panel.
export default function ComparisonView({ candidates, belts, onLocate }) {
  const stats = useMemo(() => {
    const list = Array.isArray(candidates) ? candidates : [];
    const refBelts = (belts || []).filter((b) => Array.isArray(b.coords) && b.coords.length >= 3);
    const insideAny = new Set();
    const perBelt = refBelts.map((b) => {
      const inside = list.filter(
        (c) => Number.isFinite(c?.centroid_latitude) && Number.isFinite(c?.centroid_longitude)
          && pointInPolygon(c.centroid_latitude, c.centroid_longitude, b.coords)
      );
      inside.forEach((c) => insideAny.add(c.candidate_id ?? c.rank));
      const best = inside.slice().sort((x, y) => x.rank - y.rank)[0];
      return { belt: b, count: inside.length, best };
    });
    return { total: list.length, perBelt, aiOnly: list.length - insideAny.size };
  }, [candidates, belts]);

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2">
        <div className="gis-metric-tile border-purple-500/20">
          <span className="gis-spec-label text-white">AI CANDIDATES</span>
          <p className="text-lg font-bold font-mono text-white mt-1">{stats.total.toLocaleString()}</p>
        </div>
        <div className="gis-metric-tile border-purple-500/20">
          <span className="gis-spec-label text-white">OUTSIDE CORRIDORS</span>
          <p className="text-lg font-bold font-mono text-white mt-1">{stats.aiOnly.toLocaleString()}</p>
        </div>
      </div>
      <div className="flex flex-col gap-1 max-h-[45vh] overflow-y-auto custom-scrollbar">
        {stats.perBelt.map(({ belt, count, best }) => (
          <button
            key={belt.id}
            onClick={() => onLocate && onLocate(belt.center[0], belt.center[1], undefined, belt.dataset)}
            className="w-full text-left rounded-lg border bg-slate-950/50 border-slate-800/90 hover:bg-purple-500/10 hover:border-purple-500/30 px-2 py-1.5 transition-all cursor-pointer"
            title={`Fly to ${belt.name}`}
          >
            <span className="text-[11px] font-sans font-semibold text-white block">{belt.shortName || belt.name}</span>
            <span className="text-[10px] font-mono text-slate-300">
              {belt.fixedCount != null
                ? `${belt.fixedCount.toLocaleString()} AI zone${belt.fixedCount === 1 ? '' : 's'} in ${belt.dataset} dataset`
                : `${count.toLocaleString()} AI zone${count === 1 ? '' : 's'} inside`}
              {belt.fixedCount == null && (belt.emptyNote
                ? ` · ${belt.emptyNote}`
                : best ? ` · best #${best.rank} (${Number(best.rank_score).toFixed(1)})` : ' · none')}
            </span>
          </button>
        ))}
      </div>
      <p className="text-[9px] font-sans text-slate-400 italic">
        Reference corridors are prior geographic context; overlap counts spatial coincidence only — neither side confirms manganese.
      </p>
    </div>
  );
}
