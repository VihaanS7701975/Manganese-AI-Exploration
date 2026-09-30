// AOI helpers (F2): parse, build, and convert areas of interest into the
// existing pipeline's expected format (bbox [min_lon, min_lat, max_lon, max_lat],
// matching backend PipelineRunRequest and load_satellite_data AOI_PRESETS).
// Pure functions only -- no map, no fetch, no new scoring.

export function parseCoordinateInput(text) {
  if (!text) return null;
  let s = String(text).trim().toUpperCase().replace(/°/g, '');
  // Accept "lat, lon", "lat lon", with optional N/S/E/W suffixes.
  const m = s.match(/^([NS])?\s*(-?\d+(?:\.\d+)?)\s*[,\s]\s*([EW])?\s*(-?\d+(?:\.\d+)?)\s*([NS])?\s*([EW])?\s*$/);
  if (!m) {
    const parts = s.split(/[,\s]+/).filter(Boolean).map(Number);
    if (parts.length !== 2 || parts.some((v) => !Number.isFinite(v))) return null;
    const [lat, lon] = parts;
    return validLatLon(lat, lon) ? { lat, lon } : null;
  }
  let lat = parseFloat(m[2]);
  let lon = parseFloat(m[4]);
  const latHem = m[1] || m[5];
  const lonHem = m[3] || m[6];
  if (latHem === 'S') lat = -Math.abs(lat);
  if (latHem === 'N') lat = Math.abs(lat);
  if (lonHem === 'W') lon = -Math.abs(lon);
  if (lonHem === 'E') lon = Math.abs(lon);
  return validLatLon(lat, lon) ? { lat, lon } : null;
}

export function validLatLon(lat, lon) {
  return Number.isFinite(lat) && Number.isFinite(lon)
    && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
}

export function bboxFromRectangle(p1, p2) {
  return {
    lon_min: Math.min(p1.lon, p2.lon),
    lat_min: Math.min(p1.lat, p2.lat),
    lon_max: Math.max(p1.lon, p2.lon),
    lat_max: Math.max(p1.lat, p2.lat),
  };
}

export function bboxFromPolygon(points) {
  const lons = points.map((p) => p.lon);
  const lats = points.map((p) => p.lat);
  return {
    lon_min: Math.min(...lons),
    lat_min: Math.min(...lats),
    lon_max: Math.max(...lons),
    lat_max: Math.max(...lats),
  };
}

// Same flat array shape the backend expects: [min_lon, min_lat, max_lon, max_lat].
export function aoiToPipeline(bbox) {
  return { bbox: [bbox.lon_min, bbox.lat_min, bbox.lon_max, bbox.lat_max] };
}

export function centroidOf(points) {
  const n = points.length || 1;
  return {
    lat: points.reduce((a, p) => a + p.lat, 0) / n,
    lon: points.reduce((a, p) => a + p.lon, 0) / n,
  };
}

// Ray-cast point-in-polygon over [lat, lon] rings. Used for F14
// reference-vs-AI overlap; purely geometric, no geological meaning.
export function pointInPolygon(lat, lon, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const xi = poly[i][1]; const yi = poly[i][0];
    const xj = poly[j][1]; const yj = poly[j][0];
    if (((yi > lat) !== (yj > lat))
      && (lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi)) {
      inside = !inside;
    }
  }
  return inside;
}

export function formatBbox(b) {
  if (!b) return '—';
  return `${b.lon_min.toFixed(3)}, ${b.lat_min.toFixed(3)} → ${b.lon_max.toFixed(3)}, ${b.lat_max.toFixed(3)}`;
}

// Rough bbox area in km² (equirectangular) for display context only.
export function bboxAreaKm2(b) {
  if (!b) return null;
  const latMid = ((b.lat_min + b.lat_max) / 2) * (Math.PI / 180);
  const w = (b.lon_max - b.lon_min) * 111.32 * Math.cos(latMid);
  const h = (b.lat_max - b.lat_min) * 110.54;
  return Math.max(0, w * h);
}
