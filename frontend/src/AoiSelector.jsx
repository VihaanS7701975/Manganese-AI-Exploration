import React, { useMemo, useState } from 'react';
import { MapPin } from 'lucide-react';
import { parseCoordinateInput, bboxFromRectangle, bboxFromPolygon, centroidOf, formatBbox, bboxAreaKm2 } from './aoi.js';

// AOI selection (F2): place search over the app's existing location index,
// coordinate input, rectangle (2 map clicks) and polygon (N clicks) drawing.
// Produces an AOI object {kind,label,center,bbox,polygon,dataset}; drawing
// itself is owned by App's map click handler via drawMode/drawnPoints props.
export default function AoiSelector({
  places, aoi, onChange, onLocate,
  drawMode, onDrawModeChange, drawnPoints, onClearDraw,
  aoiResult, aoiLoading, aoiError, onAnalyzeAoi, onExploreCandidate,
}) {
  const [query, setQuery] = useState('');
  const [coordText, setCoordText] = useState('');

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q || !Array.isArray(places)) return [];
    return places
      .filter((p) => [p.name, p.shortName, p.state].filter(Boolean).join(' ').toLowerCase().includes(q))
      .slice(0, 8);
  }, [query, places]);

  const useCoordinates = () => {
    const pt = parseCoordinateInput(coordText);
    if (!pt) return;
    onChange({
      kind: 'coordinates', label: `${pt.lat.toFixed(4)}°N, ${pt.lon.toFixed(4)}°E`,
      center: pt, bbox: null, polygon: null, dataset: aoi?.dataset ?? null,
    });
    onLocate && onLocate(pt.lat, pt.lon);
  };

  const finishDraw = () => {
    if (drawMode === 'rectangle' && drawnPoints.length >= 2) {
      const bbox = bboxFromRectangle(drawnPoints[0], drawnPoints[1]);
      const center = { lat: (bbox.lat_min + bbox.lat_max) / 2, lon: (bbox.lon_min + bbox.lon_max) / 2 };
      onChange({ kind: 'rectangle', label: `Rectangle ${formatBbox(bbox)}`, center, bbox, polygon: null, dataset: null });
    } else if (drawMode === 'polygon' && drawnPoints.length >= 3) {
      const bbox = bboxFromPolygon(drawnPoints);
      const center = centroidOf(drawnPoints);
      onChange({
        kind: 'polygon', label: `Polygon (${drawnPoints.length} vertices)`,
        center, bbox, polygon: drawnPoints.map((p) => [p.lat, p.lon]), dataset: null,
      });
    }
    onDrawModeChange && onDrawModeChange(null);
  };

  const area = aoi?.bbox ? bboxAreaKm2(aoi.bbox) : null;

  return (
    <div className="flex flex-col gap-2.5">
      {/* Place / corridor search */}
      <div>
        <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
          Search places & corridors
        </span>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. Chennai, Balaghat, Keonjhar…"
          className="w-full bg-slate-950/60 border border-purple-500/25 rounded px-2 py-1.5 font-sans text-[11px] text-white placeholder:text-slate-500 focus:outline-none focus:border-purple-400/60"
        />
        {matches.length > 0 && (
          <div className="flex flex-col gap-1 mt-1.5 max-h-44 overflow-y-auto custom-scrollbar">
            {matches.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  onChange({
                    kind: 'place', label: p.name, center: { lat: p.center[0], lon: p.center[1] },
                    bbox: null, polygon: null, dataset: p.dataset ?? null, placeId: p.id,
                  });
                  onLocate && onLocate(p.center[0], p.center[1], p.zoom ?? 9, p.dataset);
                  setQuery('');
                }}
                className="w-full text-left rounded-lg border bg-slate-950/50 border-slate-800/90 hover:bg-purple-500/10 hover:border-purple-500/30 px-2 py-1.5 transition-all cursor-pointer"
              >
                <span className="text-[11px] font-sans font-semibold text-white block">{p.name}</span>
                <span className="text-[9px] font-mono text-slate-400">{p.state ?? ''}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Coordinate input */}
      <div>
        <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
          Coordinates
        </span>
        <div className="flex items-center gap-1">
          <input
            value={coordText}
            onChange={(e) => setCoordText(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') useCoordinates(); }}
            placeholder="13.0827, 80.2707"
            className="flex-1 min-w-0 bg-slate-950/60 border border-purple-500/25 rounded px-2 py-1.5 font-mono text-[11px] text-white placeholder:text-slate-500 focus:outline-none focus:border-purple-400/60"
          />
          <button
            onClick={useCoordinates}
            className="gis-btn-lavender-ghost px-2 py-1.5 text-[10px] text-white shrink-0"
            title="Go to coordinates"
          >
            <span className="text-white font-bold">GO</span>
          </button>
        </div>
      </div>

      {/* Draw tools */}
      <div>
        <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1.5">
          Draw on map
        </span>
        <div className="flex items-center gap-1.5">
          {['rectangle', 'polygon'].map((mode) => (
            <button
              key={mode}
              onClick={() => {
                onClearDraw && onClearDraw();
                onDrawModeChange && onDrawModeChange(drawMode === mode ? null : mode);
              }}
              className={`flex-1 rounded-lg border px-2 py-1.5 text-[10px] font-semibold transition-all cursor-pointer ${
                drawMode === mode
                  ? 'bg-purple-500/25 border-purple-400/70 text-white'
                  : 'bg-slate-950/50 border-slate-800/90 text-slate-200 hover:bg-purple-500/10'
              }`}
              title={mode === 'rectangle' ? 'Click two map corners' : 'Click vertices, then Finish'}
            >
              {mode === 'rectangle' ? '▭ Rectangle' : '⬠ Polygon'}
            </button>
          ))}
        </div>
        {drawMode && (
          <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2 mt-1.5 flex flex-col gap-1.5">
            <p className="text-[10px] font-sans text-slate-200">
              {drawMode === 'rectangle'
                ? `Click two map corners (${drawnPoints.length}/2 placed).`
                : `Click polygon vertices (${drawnPoints.length} placed, min 3).`}
            </p>
            <div className="flex items-center gap-1.5">
              <button
                onClick={finishDraw}
                disabled={(drawMode === 'rectangle' && drawnPoints.length < 2) || (drawMode === 'polygon' && drawnPoints.length < 3)}
                className="gis-btn-lavender-ghost flex-1 justify-center text-[10px] text-white disabled:opacity-30"
              >
                <span className="text-white font-bold">✓ Finish AOI</span>
              </button>
              <button
                onClick={() => { onClearDraw && onClearDraw(); onDrawModeChange && onDrawModeChange(null); }}
                className="gis-btn-lavender-ghost px-2 py-1 text-[10px] text-white"
              >
                <span className="text-white font-bold">✕</span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Current AOI summary */}
      <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2">
        <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white flex items-center gap-1.5 mb-1">
          <MapPin className="w-3 h-3 text-purple-300" /> Active AOI
        </span>
        {!aoi ? (
          <p className="text-[10px] font-sans text-slate-400 italic">No AOI selected yet.</p>
        ) : (
          <div className="text-[10px] font-mono text-slate-200 flex flex-col gap-0.5">
            <span className="text-white font-semibold font-sans text-[11px]">AOI SELECTED: {aoi.label}</span>
            <span className="text-slate-400">TYPE <span className="text-white">{aoi.kind}</span></span>
            <span className="text-slate-400">CENTER <span className="text-white">{aoi.center.lat.toFixed(4)}, {aoi.center.lon.toFixed(4)}</span></span>
            {aoi.bbox && <span className="text-slate-400">BBOX <span className="text-white">{formatBbox(aoi.bbox)}</span></span>}
            {area != null && <span className="text-slate-400">AREA <span className="text-white">≈ {area.toLocaleString(undefined, { maximumFractionDigits: 0 })} km²</span></span>}
            {aoi.dataset && <span className="text-slate-400">DATASET <span className="text-white">{aoi.dataset}</span></span>}
          </div>
        )}
      </div>

      {/* ANALYZE AOI — server-side search of the active dataset's
          candidates within this AOI (POST /api/aoi/search). */}
      <div>
        <button
          onClick={() => onAnalyzeAoi && onAnalyzeAoi()}
          disabled={(!aoi?.bbox && !aoi?.polygon) || aoiLoading}
          className="gis-btn-lavender-ghost w-full justify-center text-[10px] text-white disabled:opacity-30"
          title={aoi?.bbox || aoi?.polygon ? 'Search loaded candidates inside this AOI' : 'Select or draw an AOI first'}
        >
          <span className="text-white font-bold">{aoiLoading ? '◌ SEARCHING…' : '◉ ANALYZE AOI'}</span>
        </button>
        {aoiError && (
          <p className="text-[10px] font-mono text-red-300 mt-1.5">AOI search failed: {aoiError}</p>
        )}
        {!aoiLoading && !aoiError && aoiResult && (
          <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2 mt-1.5 flex flex-col gap-1">
            <span className="text-[10px] font-mono text-slate-300">
              {aoiResult.count} candidate{aoiResult.count === 1 ? '' : 's'} in AOI
            </span>
            {aoiResult.count === 0 ? (
              <p className="text-[10px] font-sans text-slate-400 italic">No model candidates found in this AOI.</p>
            ) : aoiResult.top ? (
              <button
                onClick={() => {
                  const t = aoiResult.top;
                  if (Number.isFinite(t?.centroid_latitude) && Number.isFinite(t?.centroid_longitude)) {
                    onExploreCandidate && onExploreCandidate(t.centroid_latitude, t.centroid_longitude);
                  }
                }}
                className="w-full text-left rounded-lg border bg-slate-950/50 border-slate-800/90 hover:bg-purple-500/10 hover:border-purple-500/30 px-2 py-1.5 transition-all cursor-pointer"
                title="Load explanation for this candidate"
              >
                <span className="text-[11px] font-mono font-semibold text-white block">
                  {aoiResult.top.candidate_id ?? 'candidate'} · #{aoiResult.top.rank} · score {Number(aoiResult.top.rank_score).toFixed(1)}
                </span>
                <span className="text-[9px] font-mono text-slate-400">
                  {Number(aoiResult.top.centroid_latitude).toFixed(4)}, {Number(aoiResult.top.centroid_longitude).toFixed(4)} — click to explain
                </span>
              </button>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}
