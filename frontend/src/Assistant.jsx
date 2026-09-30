import React, { useState } from 'react';
import { Bot, Send } from 'lucide-react';

// AI Exploration Assistant (F4): rule-based answers over the actually loaded
// exploration state. Never invents values -- every number comes from the
// candidates array, the current prediction, or the temporal summary; gaps
// are stated explicitly. Labels: [Calculated] pipeline outputs,
// [Reference] static context, [Descriptive] interpretation.
const METHODOLOGY_TEXT =
  'Unsupervised chain: Sentinel-2 features → Isolation Forest anomaly percentiles → '
  + 'mineralization blend → DBSCAN spatial clusters → rank_score = 0.35·strength + 0.25·density + 0.40·mineralization. '
  + 'No ground-truth labels; candidates are exploration targets, not confirmed deposits.';

function findCandidate(candidates, token) {
  if (!Array.isArray(candidates)) return null;
  const t = String(token).toUpperCase().replace(/\s+/g, '');
  let m = t.match(/CAND_?(\d{1,4})/) || t.match(/^(\d{1,4})$/);
  if (!m) return null;
  const n = parseInt(m[1], 10);
  return candidates.find((c) => c?.rank === n)
    || candidates.find((c) => String(c?.candidate_id).toUpperCase() === `CAND_${String(n).padStart(4, '0')}`);
}

function topList(candidates, n = 3) {
  return candidates
    .filter((c) => Number.isFinite(c?.rank_score))
    .slice()
    .sort((a, b) => a.rank - b.rank)
    .slice(0, n);
}

export function answerQuestion(rawQ, ctx) {
  const q = String(rawQ || '').toLowerCase().trim();
  const { candidates = [], prediction = null, aoi = null, temporal = null, dataset = 't45que' } = ctx || {};
  if (!q) return 'Ask about the loaded results — e.g. "How many candidate zones?", "Show the strongest zones", "Explain candidate 3".';

  const hasData = candidates.length > 0;
  // Chennai candidates are a documented sample-derived subset (see
  // data/processed/chennai/SAMPLE_NOTE.json) -- label them as such so the
  // count is never mistaken for a full-scene run.
  const sampleTag = dataset === 'chennai' ? ' (sample-derived subset)' : '';
  const countLine = hasData
    ? `[Calculated] ${candidates.length.toLocaleString()} candidate zones in dataset "${dataset}"${sampleTag}.`
    : `[Calculated] No candidates loaded for dataset "${dataset}" yet (run the analysis chain).`;

  if (/(how many|count|number of|detected)/.test(q)) {
    let extra = '';
    if (hasData) {
      const hi = candidates.filter((c) => c?.rank_score >= 75).length;
      extra = ` [Calculated] ${hi.toLocaleString()} score HIGH (≥75).`;
    }
    return `${countLine}${extra}`;
  }

  if (/(strongest|top|best|highest)/.test(q)) {
    if (!hasData) return `${countLine} Load results first, then I can list the strongest zones.`;
    const tops = topList(candidates, 3).map(
      (c) => `#${c.rank} ${c.candidate_id} — score ${Number(c.rank_score).toFixed(1)} at ${Number(c.centroid_latitude).toFixed(4)}, ${Number(c.centroid_longitude).toFixed(4)}`
    );
    return `[Calculated] Strongest zones in "${dataset}":\n${tops.join('\n')}`;
  }

  const candRef = q.match(/(candidate|cand)[\s_#]*(\d{1,4})/) || q.match(/\b(\d{1,4})\b.*(explain|detail|about)/);
  if (/(explain|detail|describe|about|info)/.test(q) || candRef) {
    // candRef[0] is the full match ("candidate 1", "1 explain", ...);
    // findCandidate needs the bare number, which lives in group 2 for the
    // "candidate N" pattern and group 1 for the "N ... explain" pattern.
    let tok;
    if (candRef) {
      tok = /^(candidate|cand)/.test(candRef[0]) ? candRef[2] : candRef[1];
    } else {
      tok = q.match(/\d{1,4}/)?.[0];
    }
    const c = tok ? findCandidate(candidates, tok) : (prediction?.nearest_candidate ?? null);
    if (!c) return 'No matching candidate in the loaded set. Try "explain candidate 1" after loading results.';
    const id = c.candidate_id ?? `#${c.rank}`;
    return `[Calculated] ${id}: rank #${c.rank} of ${c.total_candidates ?? candidates.length}, `
      + `score ${Number(c.rank_score).toFixed(1)} (mineralization ${Number(c.mineralization_percentile).toFixed(1)}%ile, `
      + `anomaly strength ${Number(c.strength_percentile).toFixed(1)}%ile, density ${Number(c.density_percentile).toFixed(1)}%ile), `
      + `footprint ${c.pixel_count} px (~${Math.round(Number(c.area_m2)).toLocaleString()} m²) at `
      + `${Number(c.centroid_latitude).toFixed(4)}, ${Number(c.centroid_longitude).toFixed(4)}. `
      + `[Descriptive] Higher rank means a stronger combined spectral + spatial signal — still an exploration target, not a confirmed deposit.`;
  }

  if (/(persist|temporal|multi-?date|across dates|time)/.test(q)) {
    const s = temporal?.summary;
    if (!s) return '[Reference] No temporal summary loaded. Persistence needs 2+ dated observations over the same ground; currently each dataset has a single observation.';
    return `[Calculated] ${s.persistent_count} of ${s.total} candidates persist across observations (threshold ${temporal.threshold_m} m).`
      + (s.single_scene_note ? ` [Reference] ${s.single_scene_note}` : '');
  }

  if (/(yield|production|tonnage|shortfall|deficit|capacity)/.test(q)) {
    const sm = prediction?.shortfall_metrics;
    const vals = sm ? ` Reference scenario on screen: ${Number(sm.estimated_yield_tons).toLocaleString()} tons, +${sm.annual_deficit_reduction_pct}% deficit, feasibility ${sm.extraction_feasibility_score}/10.` : '';
    return `[Reference] Yield/deficit figures are an illustrative capacity scenario for demo context — not ML predictions or measured reserves.${vals}`;
  }

  if (/(where|location|coordinates|coords)/.test(q)) {
    if (!prediction) return 'Click the map or pick a corridor first, then ask where the assessed target is.';
    const nc = prediction.nearest_candidate;
    return `[Calculated] Probe at ${prediction.location.lat.toFixed(4)}, ${prediction.location.lon.toFixed(4)} → `
      + (nc ? `nearest candidate ${nc.candidate_id} (rank #${nc.rank}) at ${nc.centroid_latitude.toFixed(4)}, ${nc.centroid_longitude.toFixed(4)}.` : 'outside the surveyed area — no candidate applies.');
  }

  if (/(how|method|model|isolation|dbscan|weight|score|rank|work)/.test(q)) {
    return `[Reference] ${METHODOLOGY_TEXT}`;
  }

  if (aoi && /(aoi|area|bbox|selected)/.test(q)) {
    return `[Calculated] Active AOI: ${aoi.label} (${aoi.kind}), center ${aoi.center.lat.toFixed(4)}, ${aoi.center.lon.toFixed(4)}.`;
  }

  return 'I can answer from loaded results: counts, strongest zones ("show top 3"), single candidates ("explain candidate 5"), persistence, methodology, yield-scenario basis, and locations. Values I quote are [Calculated] from data or [Reference] context — I do not estimate reserves.';
}

const SUGGESTIONS = ['How many candidate zones?', 'Show the strongest zones', 'Explain candidate 1', 'How does the ranking work?', 'Are yield figures predictions?'];

export default function Assistant({ getContext }) {
  const [messages, setMessages] = useState([
    { role: 'assistant', text: 'Exploration assistant ready. I answer only from the loaded candidates, prediction, and temporal state.' },
  ]);
  const [input, setInput] = useState('');

  const send = (text) => {
    const q = (text ?? input).trim();
    if (!q) return;
    const a = answerQuestion(q, getContext ? getContext() : {});
    setMessages((m) => [...m, { role: 'user', text: q }, { role: 'assistant', text: a }]);
    setInput('');
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1.5 max-h-[40vh] overflow-y-auto custom-scrollbar">
        {messages.map((m, i) => (
          <div
            key={i}
            className={`rounded-lg border px-2 py-1.5 text-[11px] font-sans leading-snug whitespace-pre-line ${
              m.role === 'user'
                ? 'bg-purple-500/15 border-purple-500/30 text-white self-end max-w-[95%]'
                : 'bg-slate-950/50 border-slate-800/90 text-slate-200'
            }`}
          >
            {m.role === 'assistant' && <Bot className="w-3 h-3 inline mr-1 text-purple-300" />}
            {m.text}
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => send(s)}
            className="rounded-full border border-purple-500/25 bg-slate-950/50 px-2 py-0.5 text-[9px] font-sans text-slate-300 hover:text-white hover:border-purple-400/50 transition-colors cursor-pointer"
          >
            {s}
          </button>
        ))}
      </div>
      <div className="flex items-center gap-1">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') send(); }}
          placeholder="Ask about the loaded results…"
          className="flex-1 min-w-0 bg-slate-950/60 border border-purple-500/25 rounded px-2 py-1.5 font-sans text-[11px] text-white placeholder:text-slate-500 focus:outline-none focus:border-purple-400/60"
        />
        <button onClick={() => send()} className="gis-btn-lavender-ghost px-2 py-1.5 text-white" title="Send">
          <Send className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
