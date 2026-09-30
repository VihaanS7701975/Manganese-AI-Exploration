import React, { useState } from 'react';
import { Radio } from 'lucide-react';
import { formatBbox } from './aoi.js';

// One-click exploration workflow (F1): AOI -> find imagery -> preprocess ->
// analyze -> candidates -> rank & display. Every step reflects the real
// /api/workflow/status payload; nothing is simulated. Acquisition (network
// download) sits behind an explicit confirmation checkbox and is never
// triggered implicitly.
const STEPS = [
  { key: 'aoi', label: 'Select AOI', hint: 'Use the AOI panel (search, coordinates, draw).', judge: 'Search area' },
  { key: 'imagery', label: 'Find imagery', hint: 'Scenes present under data/raw for the dataset.', judge: 'Draw AOI' },
  { key: 'preprocess', label: 'Preprocess', hint: 'Aligned GeoTIFF stack (cleaned_images).', judge: 'Analyze' },
  { key: 'analyze', label: 'Analyze', hint: 'Features + anomaly + mineralization outputs.', judge: 'Explore targets' },
  { key: 'candidates', label: 'Candidates', hint: 'Ranked candidate_sites.csv available.', judge: 'Explain result' },
  { key: 'display', label: 'Rank & display', hint: 'Load results onto map + Rank Index.', judge: 'Report' },
];

function stepState(step, aoi, wf) {
  if (step === 'aoi') return aoi ? 'done' : 'pending';
  if (!wf) return 'unknown';
  const s = wf.stages || {};
  if (step === 'imagery') return s.imagery_downloaded ? 'done' : 'pending';
  if (step === 'preprocess') return (s.preprocessed || s.preprocessed_aoi) ? 'done' : 'pending';
  if (step === 'analyze') return (s.features && s.anomalies && s.mineralization) ? 'done' : 'pending';
  if (step === 'candidates') return s.candidates ? 'done' : 'pending';
  if (step === 'display') return wf.ready_for_demo ? 'done' : 'pending';
  return 'unknown';
}

const DOT = { done: 'bg-green-500', pending: 'bg-amber-500', unknown: 'bg-slate-600' };

export default function WorkflowPanel({
  aoi, dataset, workflow, workflowLoading, onCheckStatus, onShowResults, onAcquire,
}) {
  const [confirmAcquire, setConfirmAcquire] = useState(false);
  const [acquiring, setAcquiring] = useState(false);
  const [acquireMsg, setAcquireMsg] = useState(null);

  const startAcquire = async () => {
    if (!aoi?.bbox || !onAcquire || !confirmAcquire) return;
    setAcquiring(true);
    setAcquireMsg(null);
    try {
      const msg = await onAcquire(aoi.bbox);
      setAcquireMsg(msg || 'Acquisition request submitted.');
    } catch (e) {
      setAcquireMsg(`Acquisition failed: ${e?.message || e}`);
    } finally {
      setAcquiring(false);
    }
  };

  return (
    <div className="flex flex-col gap-2.5">
      <button
        onClick={onCheckStatus}
        className="gis-btn-lavender-ghost w-full justify-center text-white"
        title="Query real pipeline-stage availability from the backend"
      >
        <span className="text-white font-bold text-[10px]">↻ CHECK PIPELINE STATUS{workflow?.dataset ? ` (${workflow.dataset})` : ''}</span>
      </button>

      {workflowLoading ? (
        <div className="flex items-center justify-center gap-2 py-3 animate-pulse">
          <Radio className="w-4 h-4 text-purple-400 animate-spin" />
          <p className="text-[10px] font-mono text-slate-300 uppercase">Checking stages…</p>
        </div>
      ) : (
        <div className="flex flex-col gap-1">
          {STEPS.map((st, i) => {
            const state = stepState(st.key, aoi, workflow);
            return (
              <React.Fragment key={st.key}>
                <div className="rounded-lg border border-purple-500/20 bg-slate-950/40 px-2.5 py-2 flex items-start gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${DOT[state]}`} />
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-bold font-sans uppercase tracking-wide text-white">
                      {i + 1}. {st.label}
                      {st.judge && <span className="text-purple-300 font-mono font-normal normal-case"> · {st.judge}</span>}
                    </p>
                    <p className="text-[10px] font-sans text-slate-300 leading-snug">{st.hint}</p>
                    {st.key === 'aoi' && aoi && (
                      <p className="text-[9px] font-mono text-purple-300 mt-0.5">{aoi.label}</p>
                    )}
                    {st.key === 'imagery' && workflow && (
                      <p className="text-[9px] font-mono text-slate-400 mt-0.5">
                        {(workflow.scenes || []).length
                          ? workflow.scenes.map((s) => `${s.scene_id.slice(0, 28)}… (${s.sensing_date ?? 'date n/a'})`).join(' · ')
                          : 'No scenes on disk for this dataset.'}
                      </p>
                    )}
                    {st.key === 'candidates' && workflow && (
                      <p className="text-[9px] font-mono text-slate-400 mt-0.5">
                        {workflow.candidate_count ? `${workflow.candidate_count.toLocaleString()} candidates` : 'None yet — run the analysis chain.'}
                      </p>
                    )}
                  </div>
                </div>
                {i < STEPS.length - 1 && (
                  <div className="flex justify-center text-purple-400/80 text-sm leading-none" aria-hidden="true">↓</div>
                )}
              </React.Fragment>
            );
          })}
        </div>
      )}

      {workflow?.ready_for_demo && (
        <button
          onClick={onShowResults}
          className="gis-btn-lavender-ghost w-full justify-center text-white"
          title="Focus map on results and open the Rank Index"
        >
          <span className="text-white font-bold text-[10px]">🎯 SHOW RESULTS ON MAP</span>
        </button>
      )}

      {/* Explicit, confirmed acquisition only */}
      <div className="rounded border border-amber-500/25 bg-slate-950/40 p-2">
        <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-amber-300 block mb-1.5">
          Acquire new imagery (optional)
        </span>
        {!aoi?.bbox ? (
          <p className="text-[10px] font-sans text-slate-400 italic">Draw a rectangle/polygon AOI first — acquisition needs a bounding box.</p>
        ) : (
          <>
            <p className="text-[10px] font-mono text-slate-300 mb-1.5">BBOX {formatBbox(aoi.bbox)}</p>
            <label className="flex items-start gap-1.5 text-[10px] font-sans text-slate-200 mb-1.5 cursor-pointer">
              <input
                type="checkbox"
                checked={confirmAcquire}
                onChange={(e) => setConfirmAcquire(e.target.checked)}
                className="mt-0.5"
              />
              <span>I understand this downloads real satellite data (network + time) via /api/pipeline/run.</span>
            </label>
            <button
              onClick={startAcquire}
              disabled={!confirmAcquire || acquiring}
              className="gis-btn-lavender-ghost w-full justify-center text-white disabled:opacity-30"
            >
              <span className="text-white font-bold text-[10px]">{acquiring ? 'ACQUIRING…' : '⬇ ACQUIRE IMAGERY'}</span>
            </button>
            {acquireMsg && <p className="text-[10px] font-mono text-slate-300 mt-1.5">{acquireMsg}</p>}
          </>
        )}
      </div>
    </div>
  );
}
