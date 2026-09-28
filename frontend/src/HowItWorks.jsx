import React from 'react';

// Static, purely explanatory pipeline diagram -- no data, no props, no
// backend calls. Describes the actual existing stages already implemented
// in src/ml/ and src/data_processing/ (feature_extraction.py ->
// anomaly_detection.py's Isolation Forest -> candidate_detection.py's
// DBSCAN clustering -> mineralization_scoring.py -> candidate ranking),
// nothing new or fabricated. This component only renders text/emoji; it
// does not compute, rank, or fetch anything.
const PIPELINE_STEPS = [
  {
    icon: '🛰️',
    title: 'Sentinel-2 Satellite Data',
    description: 'Multispectral satellite imagery provides the input data.',
  },
  {
    icon: '🧪',
    title: 'Spectral Feature Extraction',
    description: 'Spectral bands and derived features are extracted for each valid pixel.',
  },
  {
    icon: '🤖',
    title: 'Isolation Forest',
    description: 'An unsupervised ML model identifies pixels with unusual spectral characteristics.',
  },
  {
    icon: '📍',
    title: 'Spectral Anomaly Detection',
    description: 'Pixels that differ significantly from the surrounding spectral patterns are marked as anomalies.',
  },
  {
    icon: '🔗',
    title: 'DBSCAN Spatial Clustering',
    description: 'Nearby anomalous pixels are grouped into spatial candidate zones.',
  },
  {
    icon: '⛏️',
    title: 'Mineralization Scoring',
    description: 'Candidate zones receive a relative mineralization score based on the extracted evidence.',
  },
  {
    icon: '🏆',
    title: 'Candidate Ranking',
    description: "Candidates are ranked using the project's scoring and percentile metrics.",
  },
  {
    icon: '🎯',
    title: 'Exploration Target',
    description: 'High-ranked candidates can be investigated as priority exploration targets.',
  },
];

export default function HowItWorks() {
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex flex-col gap-1">
        {PIPELINE_STEPS.map((step, i) => (
          <React.Fragment key={step.title}>
            <div className="rounded-lg border border-purple-500/20 bg-slate-950/40 px-2.5 py-2 flex items-start gap-2">
              <span className="text-lg leading-none shrink-0">{step.icon}</span>
              <div className="min-w-0">
                <p className="text-[11px] font-bold font-sans uppercase tracking-wide text-white">
                  {step.title}
                </p>
                <p className="text-[10px] font-sans text-slate-300 leading-snug mt-0.5">
                  {step.description}
                </p>
              </div>
            </div>
            {i < PIPELINE_STEPS.length - 1 && (
              <div className="flex justify-center text-purple-400/80 text-sm leading-none" aria-hidden="true">
                ↓
              </div>
            )}
          </React.Fragment>
        ))}
      </div>

      <p className="text-[9px] font-sans text-slate-400 italic pt-2 border-t border-purple-500/10 leading-snug">
        Screening workflow — results support exploration decisions and do not replace geological validation.
      </p>
    </div>
  );
}
