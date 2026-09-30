import React from 'react';

// GIS evidence layers (F7). Each entry declares its real data source; layers
// without on-disk backing render disabled with the reason, never fabricated.
const LAYERS = [
  { key: 'overlay', label: 'Pixel score overlay', source: 'Pre-rendered mineralization PNG (/api/pixel_overlay)' },
  { key: 'candidates', label: 'Candidate zones', source: 'Ranked candidates (top 200 markers)' },
  { key: 'reference', label: 'Reference corridors', source: 'Built-in manganese belt index' },
  { key: 'aoi', label: 'AOI', source: 'Active AOI selection' },
  { key: 'labels', label: 'Place labels', source: 'Esri reference tiles' },
  { key: 'rgb', label: 'RGB composite', source: null, reason: 'Needs processed GeoTIFFs — run preprocessing' },
  { key: 'nir', label: 'NIR band', source: null, reason: 'Needs processed GeoTIFFs — run preprocessing' },
  { key: 'swir', label: 'SWIR bands', source: null, reason: 'Needs processed GeoTIFFs — run preprocessing' },
  { key: 'cloud', label: 'Cloud / validity mask', source: null, reason: 'Needs SCL-derived mask service — not yet exposed' },
];

export default function LayersPanel({ layers, availability, onToggle }) {
  return (
    <div className="flex flex-col gap-1.5">
      {LAYERS.map((l) => {
        const available = availability ? availability[l.key] !== false : !!l.source;
        const on = layers ? !!layers[l.key] : false;
        return (
          <button
            key={l.key}
            onClick={() => available && onToggle && onToggle(l.key)}
            disabled={!available}
            title={available ? (l.source || l.label) : (l.reason || 'Unavailable')}
            className={`w-full text-left rounded-lg border px-2 py-1.5 transition-all ${
              available ? 'cursor-pointer' : 'cursor-not-allowed opacity-40'
            } ${
              on && available
                ? 'bg-purple-500/25 border-purple-400/70'
                : 'bg-slate-950/50 border-slate-800/90 hover:bg-purple-500/10'
            }`}
          >
            <span className="text-[11px] font-sans font-semibold text-white block">
              {on && available ? '◉' : '○'} {l.label}
            </span>
            <span className="text-[9px] font-mono text-slate-400 block mt-0.5">
              {available ? l.source : l.reason}
            </span>
          </button>
        );
      })}
    </div>
  );
}
