import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';

// Guided demo mode (F15): 8 presentation steps. Each step shows plain-language
// presenter notes for non-expert judges and fires App's per-step action
// (map moves, panels open) via onStepAction(actionKey).
// Contract with App.jsx handleDemoStep — DO NOT rename keys:
// aoi, coverage, analysis, anomaly, candidates, ranking, explain, report.
export const DEMO_STEPS = [
  {
    key: 'aoi',
    title: 'Choose your search area',
    text: 'We start with the Chennai corridor map. Everything after this — satellites, scores, targets — is calculated only inside this area. Think of it as choosing where to point the telescope.',
    look: 'Map zooms to Chennai; Area of Interest panel opens.',
    kind: 'Starting point',
  },
  {
    key: 'coverage',
    title: 'Check satellite coverage',
    text: 'Green-to-red shading shows where Sentinel-2 images were available. Blank patches mean no data, not no minerals. This tells you how much ground the satellite actually saw.',
    look: 'Satellite basemap; Workflow status panel.',
    kind: 'Reference info',
  },
  {
    key: 'analysis',
    title: 'Run the AI scan',
    text: 'The computer reads rock colours your eyes cannot see and blends them into one mineralization score (0–100). Higher means more manganese-like from space — a clue only, never proof.',
    look: 'Analytics panel with feature charts.',
    kind: 'Model output — needs ground check',
  },
  {
    key: 'anomaly',
    title: 'Spot the unusual ground',
    text: 'The anomaly score flags ground that looks odd compared to its surroundings. A 95th-percentile pixel is in the strangest 5%. Strange can mean minerals — or roads and farms.',
    look: 'Classification panel with the anomaly map.',
    kind: 'Model output — needs ground check',
  },
  {
    key: 'candidates',
    title: 'Group clues into zones',
    text: 'Lonely odd pixels are grouped into candidate zones — places worth sending a field team. Each zone is an exploration target, not a confirmed discovery of manganese.',
    look: 'Rank Index list opens over the map.',
    kind: 'Model output — needs ground check',
  },
  {
    key: 'ranking',
    title: 'Rank the best targets first',
    text: 'Zones are sorted by signal strength, size, and mineralization into one rank score. Rank 1 is the most promising place to check on foot — field testing is still required.',
    look: 'Rank Index list; look at the top row.',
    kind: 'Model output — needs ground check',
  },
  {
    key: 'explain',
    title: 'Ask why this zone matters',
    text: 'This breaks the top zone’s score into plain reasons, like which colour signals added points. Confidence percentiles show how it compares — top 10% means it beat 90% of zones.',
    look: 'Explainable AI panel for the Rank 1 zone.',
    kind: 'Model output — needs ground check',
  },
  {
    key: 'report',
    title: 'Export the field report',
    text: 'One click bundles the maps, targets, and limits into a download. Yield tons and deficit figures inside are background context only — targets need drilling before any claim.',
    look: 'Report panel; use the download button.',
    kind: 'Targets = model output · tons/figures = reference',
  },
];

const KIND_STYLES = {
  'Starting point': 'bg-sky-500/20 text-sky-200 border-sky-400/30',
  'Reference info': 'bg-sky-500/20 text-sky-200 border-sky-400/30',
  'Model output — needs ground check': 'bg-amber-500/20 text-amber-200 border-amber-400/30',
  'Targets = model output · tons/figures = reference': 'bg-amber-500/20 text-amber-200 border-amber-400/30',
};

export default function DemoMode({ onStepAction, onExit }) {
  const [idx, setIdx] = useState(0);
  const step = DEMO_STEPS[idx];
  const isLast = idx === DEMO_STEPS.length - 1;

  useEffect(() => {
    onStepAction && onStepAction(step.key);
    // Fire once per step change only.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idx]);

  return (
    <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-40 pointer-events-auto w-[min(34rem,calc(100vw-2rem))]">
      <div className="gis-lavender-card p-3 flex flex-col gap-2 shadow-2xl">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-[9px] font-mono text-purple-300 uppercase tracking-widest">
              Demo mode · step {idx + 1} of {DEMO_STEPS.length}
            </p>
            <h2 className="text-sm font-bold font-sans text-white">{step.title}</h2>
          </div>
          <button
            onClick={onExit}
            className="p-1 rounded-full bg-slate-950/80 hover:bg-purple-500/30 text-slate-300 hover:text-white border border-purple-500/30 transition-colors cursor-pointer"
            title="Exit demo mode"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
        <span
          className={`self-start text-[9px] font-sans font-semibold px-2 py-0.5 rounded-full border ${KIND_STYLES[step.kind] || 'bg-slate-700/50 text-slate-200 border-slate-600'}`}
        >
          {step.kind}
        </span>
        <p className="text-[11px] font-sans text-slate-200 leading-snug">{step.text}</p>
        <p className="text-[10px] font-sans text-purple-200/90 leading-snug">
          <span className="font-bold">What to look at: </span>
          {step.look}
        </p>
        {isLast && (
          <p className="text-[10px] font-sans text-emerald-200 leading-snug border-t border-purple-500/20 pt-2">
            <span className="font-bold">What this demo proves: </span>
            open satellite data can narrow thousands of km² to a ranked shortlist — faster, cheaper targeting, with honest limits.
          </p>
        )}
        <div className="flex items-center gap-1" role="tablist" aria-label="Demo progress">
          {DEMO_STEPS.map((s, i) => (
            <button
              key={s.key}
              onClick={() => setIdx(i)}
              title={`${i + 1}: ${s.title}`}
              aria-label={`Go to step ${i + 1}: ${s.title}`}
              className={`h-1 flex-1 rounded-full transition-colors cursor-pointer ${i <= idx ? 'bg-purple-400' : 'bg-slate-700 hover:bg-slate-600'}`}
            />
          ))}
        </div>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIdx((i) => Math.max(0, i - 1))}
              disabled={idx === 0}
              className="gis-btn-lavender-ghost px-3 py-1.5 text-[10px] text-white disabled:opacity-30"
            >
              <span className="text-white font-bold">‹ BACK</span>
            </button>
            <button
              onClick={() => setIdx(0)}
              disabled={idx === 0}
              className="gis-btn-lavender-ghost px-3 py-1.5 text-[10px] text-white disabled:opacity-30"
              title="Restart demo from step 1"
            >
              <span className="text-white font-bold">↺ RESTART</span>
            </button>
          </div>
          <div className="flex items-center gap-2">
            {!isLast && (
              <button
                onClick={() => setIdx(DEMO_STEPS.length - 1)}
                className="gis-btn-lavender-ghost px-3 py-1.5 text-[10px] text-white"
                title="Skip to last step"
              >
                <span className="text-white font-bold">SKIP »</span>
              </button>
            )}
            {!isLast ? (
              <button
                onClick={() => setIdx((i) => Math.min(DEMO_STEPS.length - 1, i + 1))}
                className="gis-btn-lavender-ghost px-3 py-1.5 text-[10px] text-white"
              >
                <span className="text-white font-bold">NEXT ›</span>
              </button>
            ) : (
              <button onClick={onExit} className="gis-btn-lavender-ghost px-3 py-1.5 text-[10px] text-white">
                <span className="text-white font-bold">✓ FINISH</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
