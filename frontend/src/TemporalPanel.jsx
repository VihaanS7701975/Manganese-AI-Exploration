import React from 'react';
import { Clock } from 'lucide-react';

// Multi-date / time-series panel (F6): observation dates, persistence
// summary, and per-candidate cross-date support from /api/temporal/*.
// A persisting signal is supporting remote-sensing evidence ONLY.
export default function TemporalPanel({ scenes, temporal, loading, dataset }) {
  const summary = temporal?.summary;
  const rows = (temporal?.persistent || [])
    .filter((p) => p.persistent)
    .sort((a, b) => a.rank - b.rank)
    .slice(0, 15);

  return (
    <div className="flex flex-col gap-2.5">
      <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2">
        <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white flex items-center gap-1.5 mb-1.5">
          <Clock className="w-3 h-3 text-purple-300" /> Observations ({dataset})
        </span>
        {!scenes || scenes.length === 0 ? (
          <p className="text-[10px] font-sans text-slate-400 italic">No dated observations registered yet.</p>
        ) : (
          <div className="flex flex-col gap-1">
            {scenes.map((o) => (
              <div key={o.dataset} className="text-[10px] font-mono">
                <span className="text-white font-bold">{o.dataset}</span>
                <span className="text-slate-300"> — {(o.observation_dates || []).join(', ') || 'date n/a'}</span>
                <span className="text-slate-400"> · {o.candidate_count.toLocaleString()} candidates{o.candidates_available ? '' : ' (pending)'}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <p className="text-[10px] font-mono text-slate-300 text-center py-2 animate-pulse">Computing persistence…</p>
      ) : !summary ? (
        <p className="text-[10px] font-sans text-slate-400 italic text-center">Persistence not computed for this dataset yet.</p>
      ) : (
        <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2">
          <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
            Persistence (≤ {temporal.threshold_m} m match)
          </span>
          <p className="text-[11px] font-mono text-white mb-1.5">
            {summary.persistent_count.toLocaleString()} / {summary.total.toLocaleString()} persist
          </p>
          {summary.single_scene_note && (
            <p className="text-[10px] font-sans text-amber-300 mb-1.5">{summary.single_scene_note}</p>
          )}
          {rows.length > 0 && (
            <div className="flex flex-col gap-1 max-h-48 overflow-y-auto custom-scrollbar">
              {rows.map((p) => (
                <div key={`${p.scene}-${p.candidate_id}`} className="flex items-center justify-between text-[10px] font-mono border border-slate-800/80 rounded px-1.5 py-1">
                  <span className="text-white font-semibold">{p.candidate_id} <span className="text-slate-400">#{p.rank}</span></span>
                  <span className="text-green-400 font-bold">+{p.support_count} scene{p.support_count === 1 ? '' : 's'}</span>
                </div>
              ))}
            </div>
          )}
          <p className="text-[9px] font-sans text-slate-400 italic mt-1.5">
            Persisting signals support follow-up; they do not confirm manganese.
          </p>
        </div>
      )}
    </div>
  );
}
