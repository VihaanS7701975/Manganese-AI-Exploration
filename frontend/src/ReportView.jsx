import React, { useState } from 'react';
import { FileText } from 'lucide-react';
import { apiUrl } from './apiConfig.js';

// Automatic exploration report (F12). Renders the real /api/report payload
// (AOI, imagery, dates, methodology, ranked candidates, limitations) and
// exports it as JSON or printable HTML. Nothing is synthesized: missing
// sections render as "not available".
function download(filename, text, type) {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function reportHtml(r) {
  const rows = (r.candidates || []).map((c) => (
    `<tr><td>${c.candidate_id}</td><td>${c.rank}</td><td>${Number(c.rank_score).toFixed(1)}</td>`
    + `<td>${Number(c.centroid_latitude).toFixed(4)}, ${Number(c.centroid_longitude).toFixed(4)}</td>`
    + `<td>${c.pixel_count}</td></tr>`
  )).join('');
  const esc = (s) => String(s ?? '—');
  return `<!doctype html><html><head><meta charset="utf-8"><title>Exploration report — ${esc(r.dataset)}</title>`
    + `<style>body{font-family:sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem}table{border-collapse:collapse;width:100%}td,th{border:1px solid #999;padding:4px 8px;font-size:12px}.note{background:#f5f5f5;padding:8px;border-left:3px solid #888}</style></head><body>`
    + `<h1>Exploration report — dataset ${esc(r.dataset)} (illustrative reference scenario)</h1>`
    + `<p class="note">${esc(r.generated_note)}</p>`
    + `<h2>AOI</h2><p>${r.aoi ? `lon ${r.aoi.lon_min.toFixed(3)}–${r.aoi.lon_max.toFixed(3)}, lat ${r.aoi.lat_min.toFixed(3)}–${r.aoi.lat_max.toFixed(3)}` : 'Not available (no candidates).'} ${esc(r.aoi_note)}</p>`
    + `<h2>Imagery</h2><p>${(r.imagery?.scenes || []).map((s) => `${s.scene_id} (${s.sensing_date ?? 'date n/a'})`).join('; ') || 'No scenes on disk.'}</p>`
    + `<h2>Methodology</h2><ul>${Object.entries(r.methodology || {}).filter(([k]) => k !== 'sources').map(([k, v]) => `<li><b>${k}</b>: ${v}</li>`).join('')}</ul>`
    + `<h2>Candidates (${r.candidate_count})</h2><table><tr><th>ID</th><th>Rank</th><th>Score</th><th>Centroid</th><th>Pixels</th></tr>${rows}</table>`
    + `<h2>Limitations</h2><ul>${(r.limitations || []).map((l) => `<li>${l}</li>`).join('')}</ul>`
    + `<p class="note">${esc(r.shortfall_note)}</p></body></html>`;
}

export default function ReportView({ report, loading, dataset, onLoad, selectedCandidateId, aoi }) {
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState(null);

  const downloadPdf = async () => {
    if (!report || pdfLoading) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      const params = new URLSearchParams({ dataset: report.dataset, limit: '25' });
      if (selectedCandidateId) params.set('candidate_id', selectedCandidateId);
      if (aoi?.bbox) {
        const b = aoi.bbox;
        params.set('bbox', `${b.lon_min},${b.lat_min},${b.lon_max},${b.lat_max}`);
      }
      const response = await fetch(apiUrl(`/api/report.pdf?${params.toString()}`));
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `exploration_report_${report.dataset}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (err) {
      setPdfError(err?.message || 'PDF download failed');
    } finally {
      setPdfLoading(false);
    }
  };
  return (
    <div className="flex flex-col gap-2.5">
      <button
        onClick={onLoad}
        className="gis-btn-lavender-ghost w-full justify-center text-white"
        title="Assemble the report from pipeline outputs on disk"
      >
        <span className="text-white font-bold text-[10px]">📄 {report ? 'RELOAD REPORT' : 'GENERATE REPORT'}{dataset ? ` (${dataset})` : ''}</span>
      </button>

      {loading ? (
        <p className="text-[10px] font-mono text-slate-300 text-center py-2 animate-pulse">Assembling report…</p>
      ) : !report ? (
        <p className="text-[10px] font-sans text-slate-400 italic text-center">No report loaded yet.</p>
      ) : (
        <>
          <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2 flex flex-col gap-1 text-[10px] font-sans text-slate-200">
            <span className="font-bold text-white flex items-center gap-1.5"><FileText className="w-3 h-3 text-purple-300" /> dataset {report.dataset} — {report.candidate_count.toLocaleString()} candidates</span>
            <span><b className="text-white">AOI:</b> {report.aoi ? `lon ${report.aoi.lon_min.toFixed(3)}–${report.aoi.lon_max.toFixed(3)}, lat ${report.aoi.lat_min.toFixed(3)}–${report.aoi.lat_max.toFixed(3)}` : 'n/a'}</span>
            <span><b className="text-white">Imagery:</b> {(report.imagery?.scenes || []).map((s) => s.scene_id.slice(0, 24) + '…').join('; ') || 'none on disk'}</span>
            <span><b className="text-white">Method:</b> {report.methodology?.ranking}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              onClick={() => download(`exploration_report_${report.dataset}.json`, JSON.stringify(report, null, 2), 'application/json')}
              className="gis-btn-lavender-ghost flex-1 justify-center text-white"
            >
              <span className="text-white font-bold text-[10px]">⬇ JSON</span>
            </button>
            <button
              onClick={() => download(`exploration_report_${report.dataset}.html`, reportHtml(report), 'text/html')}
              className="gis-btn-lavender-ghost flex-1 justify-center text-white"
            >
              <span className="text-white font-bold text-[10px]">⬇ HTML</span>
            </button>
            <button
              onClick={downloadPdf}
              disabled={pdfLoading}
              className="gis-btn-lavender-ghost flex-1 justify-center text-white disabled:opacity-40"
              title="Download professional multi-page PDF report (cover, methodology, candidates, ExplainableAI, overlay, limitations)"
            >
              <span className="text-white font-bold text-[10px]">{pdfLoading ? '◌ PDF…' : '⬇ PDF'}</span>
            </button>
          </div>
          {pdfError && (
            <p className="text-[10px] font-mono text-red-300">PDF failed: {pdfError}</p>
          )}
          <div className="rounded border border-purple-500/20 bg-slate-950/40 p-2">
            <span className="text-[10px] font-bold font-sans uppercase tracking-wider text-white block mb-1">Limitations</span>
            <ul className="text-[10px] font-sans text-slate-300 list-disc list-inside space-y-0.5">
              {(report.limitations || []).map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
