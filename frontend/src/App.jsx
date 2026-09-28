import React, { useState, useEffect } from 'react';
import {
  MapContainer,
  TileLayer,
  ImageOverlay,
  Marker,
  Popup,
  Polygon,
  Tooltip as LeafletTooltip,
  useMapEvents,
  useMap
} from 'react-leaflet';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip as ChartTooltip,
  ResponsiveContainer,
  CartesianGrid
} from 'recharts';
import {
  Activity,
  TrendingUp,
  Crosshair,
  Layers,
  Satellite,
  Radio,
  Compass,
  CheckCircle2,
  AlertCircle,
  Sliders,
  ShieldAlert,
  ChevronUp,
  ChevronDown,
  X,
  Layers3
} from 'lucide-react';
import 'leaflet/dist/leaflet.css';

import ExplainableAI from './ExplainableAI.jsx';
import AnalyticsDashboard from './AnalyticsDashboard.jsx';
import TopTargetsPanel from './TopTargetsPanel.jsx';
import SidebarMenu from './SidebarMenu.jsx';
import HowItWorks from './HowItWorks.jsx';
import CandidateScoreBreakdown from './CandidateScoreBreakdown.jsx';
import { LEVEL_EMOJI, LEVEL_DOT_CLASS, LEVEL_RANGE_LABEL } from './potentialLevel.js';
import { API_BASE_URL, apiUrl } from './apiConfig.js';
import L from 'leaflet';
import icon from 'leaflet/dist/images/marker-icon.png';
import iconShadow from 'leaflet/dist/images/marker-shadow.png';

const DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34]
});
L.Marker.prototype.options.icon = DefaultIcon;

// National manganese supply shortfall trends
const shortfallTrend = [
  { year: '2023', deficit: 1.8, target: 4.5 },
  { year: '2024', deficit: 2.1, target: 5.2 },
  { year: '2025', deficit: 2.6, target: 6.0 },
  { year: '2026 (Est)', deficit: 1.2, target: 6.8 },
];

// National Manganese Belts Dataset across India.
// Each entry's `dataset` is the backend candidate dataset/AOI identifier
// (see backend/main.py's DATASET_PATHS) that clicking it should query.
// All of these are pre-existing T45QUE-scoped corridors, so they're pinned
// to 't45que' explicitly -- this guarantees they keep querying the original
// dataset even if the app is currently in "chennai" mode, preserving exact
// existing T45QUE behavior regardless of what was selected before.
const MANGANESE_BELTS = [
  {
    id: 'balaghat',
    name: 'Balaghat-Chhindwara Belt (Madhya Pradesh)',
    shortName: 'Balaghat',
    state: 'Madhya Pradesh',
    center: [21.8129, 80.1849],
    dataset: 't45que',
    coords: [
      [21.65, 79.95],
      [21.95, 79.95],
      [22.05, 80.40],
      [21.60, 80.35]
    ],
    color: '#f59e0b', // Raw Gold/Amber - High Grade
    fillColor: '#f59e0b',
    ore: 'Braunite / Pyrolusite (51% Mn)',
    grade: 'Tier-1 High Potential',
    confidence: 0.90,
    description: 'Tier-1 reference corridor: Braunite / Pyrolusite-type ground historically reported above 51% Mn (reference geology, not a measured reserve here).'
  },
  {
    id: 'nagpur',
    name: 'Nagpur-Bhandara Belt (Maharashtra)',
    shortName: 'Nagpur',
    state: 'Maharashtra',
    center: [21.4000, 79.6000],
    dataset: 't45que',
    coords: [
      [21.25, 79.35],
      [21.55, 79.35],
      [21.65, 79.85],
      [21.20, 79.80]
    ],
    color: '#3b82f6', // Steel Blue
    fillColor: '#3b82f6',
    ore: 'Gondite-type Metasediments',
    grade: 'Tier-2 Active Mining',
    confidence: 0.78,
    description: 'Tier-2 Active Mining Gondite metasedimentary formation across Vidarbha belt.'
  },
  {
    id: 'keonjhar',
    name: 'Bonai-Keonjhar Belt (Odisha)',
    shortName: 'Keonjhar',
    state: 'Odisha',
    center: [21.9012, 85.3421],
    dataset: 't45que',
    coords: [
      [21.70, 85.15],
      [22.15, 85.15],
      [22.20, 85.55],
      [21.65, 85.50]
    ],
    color: '#06b6d4', // Precision Cyan
    fillColor: '#06b6d4',
    ore: 'Iron-Manganese Ore (44% Mn)',
    grade: 'Tier-1 High Potential',
    confidence: 0.86,
    description: 'Tier-1 High Potential Iron-Manganese Complex in Singhbhum-Keonjhar craton.'
  },
  {
    id: 'sundargarh',
    name: 'Sundargarh-Gangpur Belt (Odisha)',
    shortName: 'Sundargarh',
    state: 'Odisha',
    center: [22.2500, 84.1000],
    dataset: 't45que',
    coords: [
      [22.10, 83.90],
      [22.40, 83.90],
      [22.45, 84.35],
      [22.05, 84.30]
    ],
    color: '#0ea5e9', // Deep Cobalt
    fillColor: '#0ea5e9',
    ore: 'Dolomite-Associated Manganese',
    grade: 'Tier-2 Secondary Corridor',
    confidence: 0.76,
    description: 'Tier-2 Secondary Gangpur Group dolomite-associated manganese horizons.'
  },
  {
    id: 'sandur',
    name: 'Sandur-Bellary Belt (Karnataka)',
    shortName: 'Sandur',
    state: 'Karnataka',
    center: [15.0800, 76.5500],
    dataset: 't45que',
    coords: [
      [14.95, 76.40],
      [15.25, 76.40],
      [15.30, 76.75],
      [14.90, 76.70]
    ],
    color: '#eab308', // Mineral Ochre Gold
    fillColor: '#eab308',
    ore: 'Psilomelane / Pyrolusite',
    grade: 'Tier-1 Major South Corridor',
    confidence: 0.88,
    description: 'Tier-1 reference corridor within Sandur Schist Belt (Dharwar Craton).'
  },
  {
    id: 'vizianagaram',
    name: 'Vizianagaram-Garbham Belt (Andhra Pradesh)',
    shortName: 'Vizianagaram',
    state: 'Andhra Pradesh',
    center: [18.2800, 83.5000],
    dataset: 't45que',
    coords: [
      [18.15, 83.35],
      [18.45, 83.35],
      [18.50, 83.70],
      [18.10, 83.65]
    ],
    color: '#6366f1', // Indigo Metamorphic
    fillColor: '#6366f1',
    ore: 'Kodurite / Khondalite Complex',
    grade: 'Tier-2 Alteration Zone',
    confidence: 0.75,
    description: 'Tier-2 Alteration Zone Eastern Ghats mobile belt Kodurite-type manganese reference corridor.'
  },
  {
    id: 'goa',
    name: 'North Goa Belt (Goa)',
    shortName: 'North Goa',
    state: 'Goa',
    center: [15.5000, 74.1000],
    dataset: 't45que',
    coords: [
      [15.35, 74.00],
      [15.65, 74.00],
      [15.70, 74.25],
      [15.30, 74.20]
    ],
    color: '#d97706', // Lateritic Copper
    fillColor: '#d97706',
    ore: 'Ferruginous Manganese',
    grade: 'Tier-3 Detrital Pocket',
    confidence: 0.68,
    description: 'Tier-3 Detrital Pocket secondary ferruginous manganese enrichment.'
  }
];

// Regional/exploration-view zoom for the MANGANESE_BELTS corridors above.
// These entries carry no zoom of their own, so their flyTo previously fell
// through to MapViewController's `Math.max(map.getZoom(), 7)` fallback --
// that reuses whatever zoom the map is CURRENTLY at, so once the map had
// been zoomed in for any reason (e.g. Chennai's city-level zoom 11, or a
// manual scroll-zoom), Math.max locked every subsequent corridor selection
// at that same tight zoom instead of the whole exploration polygon. Each
// corridor click now passes this fixed value explicitly so it no longer
// depends on the map's prior zoom state.
const CORRIDOR_ZOOM = 9;

// The real Chennai processing/search AOI (west=79.95, south=12.85,
// east=80.45, north=13.25 -- AOI_PRESETS["chennai"] in
// src/data_processing/load_satellite_data.py). This is the actual AOI the
// 689 real candidates were generated within -- NOT a fabricated
// confidence/tier boundary like MANGANESE_BELTS' polygons, so it is kept
// separate from that array and rendered with plain, static styling.
const CHENNAI_AOI_BOUNDS = [
  [12.85, 79.95], // SW
  [12.85, 80.45], // SE
  [13.25, 80.45], // NE
  [13.25, 79.95], // NW
];


// Plain navigation targets -- deliberately NOT added to MANGANESE_BELTS.
// That array carries a fabricated confidence/ore/grade per entry used to
// render colored "mineral belt" polygons; neither Tamil Nadu nor Chennai
// has that kind of fabricated tier/confidence data, so attaching one here
// would visually imply an AI survey result that doesn't exist.
//
// Chennai now DOES have a real candidate dataset (data/processed/chennai/
// candidate_sites.csv, 689 AOI-clipped, geographically-validated
// candidates -- see backend/main.py's DATASET_PATHS['chennai']), so
// selecting it switches the active dataset to 'chennai' and re-centers on
// Chennai's real published city coordinates; the existing real prediction
// flow then returns a real nearest-candidate result from that dataset
// (or "Outside Surveyed Area" if the click falls outside the Chennai AOI,
// same honest behavior as any other location).
//
// Tamil Nadu (the whole state) has no dataset of its own -- it stays
// pinned to 't45que' and will still honestly report "Outside Surveyed
// Area", exactly as before.
const EXTRA_LOCATIONS = [
  {
    id: 'tamilnadu',
    name: 'Tamil Nadu',
    shortName: 'Tamil Nadu',
    state: 'Tamil Nadu',
    center: [11.1271, 78.6569], // real published geographic centroid of Tamil Nadu
    dataset: 't45que',
    zoom: 7,
  },
  {
    id: 'chennai',
    name: 'Chennai',
    shortName: 'Chennai',
    state: 'Tamil Nadu',
    center: [13.0827, 80.2707],
    dataset: 'chennai',
    zoom: 11, // city-level
  },
];

function LocationSelector({ onSelectLocation }) {
  useMapEvents({
    click(e) {
      onSelectLocation(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

function MapViewController({ coords }) {
  const map = useMap();
  useEffect(() => {
    if (coords && coords.lat && coords.lon) {
      // coords.zoom is an optional per-target zoom (e.g. city-level for
      // Chennai); when absent this falls back to the exact original
      // behavior every other corridor/map-click already relies on.
      const targetZoom = coords.zoom ?? Math.max(map.getZoom(), 7);
      map.flyTo([coords.lat, coords.lon], targetZoom, {
        duration: 1.2,
      });
    }
  }, [coords, map]);
  return null;
}

export default function App() {
  const [selectedCoords, setSelectedCoords] = useState({ lat: 21.8129, lon: 80.1849 });
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);
  const [basemap, setBasemap] = useState('dark');
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.70);
  const [showExportToast, setShowExportToast] = useState(false);
  // Which single left-menu section (Detection Sensitivity / Classification
  // Result / Explainable AI / Analytics) is currently open, or null if none
  // are -- replaces the old single "is the whole panel open" boolean now
  // that each feature has its own compact toggle button (SidebarMenu.jsx).
  const [activeSection, setActiveSection] = useState(null);
  // Right-side Rank Index panel (TopTargetsPanel) -- closed by default;
  // toggled by its own small floating button, independent of the left menu.
  const [rankIndexOpen, setRankIndexOpen] = useState(false);
  const [hoveredBelt, setHoveredBelt] = useState(null);
  const [legendOpen, setLegendOpen] = useState(false);
  const [headerExpanded, setHeaderExpanded] = useState(true);
  const [candidates, setCandidates] = useState([]);
  const [candidatesLoading, setCandidatesLoading] = useState(true);
  const [candidatesError, setCandidatesError] = useState(false);
  // RED/YELLOW/GREEN pixel-level exploration-potential overlay metadata
  // (image URL + its real WGS84 bounds) for whichever dataset is active.
  // Null until /api/pixel_overlay resolves or if no pre-rendered overlay
  // exists for this dataset.
  const [pixelOverlay, setPixelOverlay] = useState(null);
  // Which candidate dataset/AOI is currently active: 't45que' (original,
  // default -- preserves exact existing behavior) or 'chennai' (the
  // AOI-clipped, 689-candidate Chennai run). Passed through to the existing
  // /api/predict and /api/candidates endpoints via their new optional
  // `dataset` parameter; nothing else about those endpoints changes.
  const [selectedDataset, setSelectedDataset] = useState('t45que');

  // `dataset` is optional: omit it (e.g. a plain map click) to query
  // whichever dataset is currently active; pass it explicitly (corridor /
  // location buttons) to both switch the active dataset and query it.
  const fetchPrediction = async (lat, lon, zoom, dataset) => {
    const activeDataset = dataset ?? selectedDataset;
    setLoading(true);
    setSelectedCoords({ lat, lon, zoom });
    if (dataset && dataset !== selectedDataset) {
      setSelectedDataset(dataset);
    }
    try {
      const response = await fetch(apiUrl('/api/predict'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lat, lon, dataset: activeDataset })
      });
      const data = await response.json();
      setPrediction(data);
    } catch (err) {
      console.error('Failed to fetch inference:', err);
    } finally {
      setLoading(false);
    }
  };

  // Pre-load default belt prediction on initial render (t45que, unchanged)
  useEffect(() => {
    fetchPrediction(21.8129, 80.1849, CORRIDOR_ZOOM, 't45que');
  }, []);

  // Load the full candidate dataset for the Analytics Dashboard whenever
  // the active dataset changes. Reuses the existing /api/candidates
  // endpoint (candidate_sites.csv, unmodified) -- no new pipeline or
  // scoring is introduced here; only which dataset's file it reads.
  useEffect(() => {
    const loadCandidates = async () => {
      setCandidatesLoading(true);
      setCandidatesError(false);
      try {
        const response = await fetch(apiUrl(`/api/candidates?dataset=${selectedDataset}`));
        const data = await response.json();
        setCandidates(Array.isArray(data.candidates) ? data.candidates : []);
      } catch (err) {
        console.error('Failed to fetch candidate analytics:', err);
        setCandidatesError(true);
      } finally {
        setCandidatesLoading(false);
      }
    };
    loadCandidates();
  }, [selectedDataset]);

  // Load the pre-rendered pixel-level RED/YELLOW/GREEN score overlay
  // (src/data_processing/render_score_overlay.py output, served via
  // /api/pixel_overlay) whenever the active dataset changes, so switching
  // T45QUE <-> Chennai automatically swaps the correct raster overlay.
  useEffect(() => {
    let cancelled = false;
    const loadOverlay = async () => {
      setPixelOverlay(null);
      try {
        const response = await fetch(apiUrl(`/api/pixel_overlay?dataset=${selectedDataset}`));
        const data = await response.json();
        if (cancelled) return;
        if (response.ok && data.available) {
          setPixelOverlay(data);
        } else {
          // Was silently swallowed before -- a stale/older backend process
          // (running from before /api/pixel_overlay existed) 404s here with
          // valid JSON ({"detail":"Not Found"}), so response.json() never
          // throws and the overlay just never appeared with no console
          // signal. Surface it explicitly so this failure mode is visible.
          console.warn(
            `Pixel overlay unavailable for dataset "${selectedDataset}" (HTTP ${response.status}). ` +
            'If data/processed/overlays/*_score_overlay.png exists on disk, the backend process at ' +
            `${API_BASE_URL} is likely running an older build -- restart it.`
          );
        }
      } catch (err) {
        console.error('Failed to fetch pixel overlay:', err);
      }
    };
    loadOverlay();
    return () => {
      cancelled = true;
    };
  }, [selectedDataset]);

  // Global Keyboard shortcuts ('H' for Corridors bar, 'O' for both Corridors & Inspector)
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName) || ['INPUT', 'TEXTAREA'].includes(e.target.tagName)) return;

      if (e.key === 'h' || e.key === 'H') {
        setHeaderExpanded((prev) => !prev);
      }

      if (e.key === 'o' || e.key === 'O') {
        setHeaderExpanded((prevHeader) => {
          const nextState = !prevHeader;
          // Collapsing also closes whichever left-menu section is open;
          // expanding doesn't force one open (no single "the" section
          // exists anymore now that each feature has its own button).
          if (!nextState) setActiveSection(null);
          return nextState;
        });
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const activeBelt = MANGANESE_BELTS.find(
    b => Math.abs(selectedCoords.lat - b.center[0]) < 0.15 && Math.abs(selectedCoords.lon - b.center[1]) < 0.15
  );

  const DARK_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}';
  const DARK_ATTR = '&copy; Esri, HERE, Garmin';
  const SATELLITE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
  const SATELLITE_ATTR = '&copy; Esri, Maxar, Earthstar Geographics';
  const LABELS_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}';

  const activeBeltsCount = MANGANESE_BELTS.filter(b => b.confidence >= confidenceThreshold).length;

  // Export Geological Prospectus Dossier Download
  const handleExportProspectus = () => {
    if (!prediction) return;
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const filename = `geological_prospectus_${timestamp}.json`;

    const dossier = {
      prospectus_title: "GeoManganese Mineral Potential & Resource Dossier (Illustrative Reference Scenario)",
      program: "Smart India Hackathon (SIH26009)",
      team: "Team RIZZLERS",
      generated_at: new Date().toISOString(),
      engine: "GeoManganese AI Sentinel-2 / ASTER Multispectral Inversion Engine",
      estimate_kind: "illustrative_capacity_scenario",
      scenario_note: "Yield, deficit-reduction and feasibility figures below are static reference-scenario values for demo context. No ore-mineralogy or tonnage/yield model exists in this project; they are not ML predictions and not measured reserves.",
      target_geography: {
        latitude: selectedCoords.lat,
        longitude: selectedCoords.lon,
        coordinates_formatted: `${selectedCoords.lat.toFixed(4)}°N, ${selectedCoords.lon.toFixed(4)}°E`,
        nearest_belt: activeBelt ? activeBelt.name : 'Custom Survey Target'
      },
      inference_metrics: {
        classification: prediction.classification,
        manganese_confidence: prediction.manganese_confidence,
        confidence_percentage: `${(prediction.manganese_confidence * 100).toFixed(1)}%`,
        ore_type_detected: prediction.ore_type_detected,
        estimated_yield_tons: prediction.shortfall_metrics?.estimated_yield_tons ?? 145000,
        annual_deficit_reduction_pct: prediction.shortfall_metrics?.annual_deficit_reduction_pct ?? 14.8,
        extraction_feasibility_score: prediction.shortfall_metrics?.extraction_feasibility_score ?? 8.5
      },
      national_impact_summary: {
        national_manganese_deficit_reference_mt: 6.8,
        deficit_alleviation_contribution_illustrative: `+${prediction.shortfall_metrics?.annual_deficit_reduction_pct ?? 14.8}%`,
        recommended_exploration_action:
          prediction.manganese_confidence > 0.8
            ? "Priority Ground-Truthing & Core Drilling Advised"
            : "Secondary High-Resolution Hyperspectral Pass Recommended"
      }
    };

    const jsonStr = JSON.stringify(dossier, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);

    setShowExportToast(true);
    setTimeout(() => {
      setShowExportToast(false);
    }, 3500);
  };

  const isLegendExpanded = hoveredBelt !== null || legendOpen;

  // Left-menu sections for SidebarMenu.jsx -- each existing control's exact
  // pre-existing markup/state/callbacks, just grouped behind its own
  // compact button instead of one long always-open panel. No new
  // functionality: "Analytics" bundles the two existing chart cards
  // (National Deficit + AnalyticsDashboard) that used to sit one after
  // another in that same panel; "Dossier" is unchanged -- it was always an
  // instant export action (handleExportProspectus), not a togglable panel,
  // so it stays an action button rather than opening a section.
  const menuSections = [
    {
      key: 'detection',
      emoji: '🎯',
      label: 'Detection',
      tooltip: 'Adjust detection sensitivity',
      description: 'Adjust anomaly detection sensitivity',
      content: (
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5 text-xs font-sans font-semibold text-white">
              <Sliders className="w-3.5 h-3.5 text-purple-300" />
              <span className="text-[11px] uppercase tracking-wider font-sans font-bold text-white">DETECTION SENSITIVITY</span>
            </div>
            <span className="gis-badge-lavender font-mono text-white">
              {(confidenceThreshold * 100).toFixed(0)}%
            </span>
          </div>

          {/* Range input slider */}
          <div className="flex items-center gap-2 mt-0.5">
            <span className="text-[10px] text-slate-300 font-mono">0.50</span>
            <input
              type="range"
              min="0.50"
              max="0.95"
              step="0.05"
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
              className="w-full h-1.5 bg-slate-800/90 rounded-lg appearance-none cursor-pointer"
            />
            <span className="text-[10px] text-slate-300 font-mono">0.95</span>
          </div>

          <div className="flex items-center justify-between text-[10px] font-mono text-white pt-0.5">
            <span className="font-sans text-[10px] uppercase text-slate-300 font-medium">SWIR Ratio Cutoff</span>
            <span className="text-white font-bold font-mono">
              {activeBeltsCount}/{MANGANESE_BELTS.length} ACTIVE_ZONES
            </span>
          </div>
        </div>
      ),
    },
    {
      key: 'classification',
      emoji: '📊',
      label: 'Classification',
      tooltip: 'View target assessment',
      description: 'View selected target assessment',
      content: loading ? (
        <div className="flex flex-col items-center justify-center gap-3 animate-pulse text-center py-4">
          <Radio className="w-6 h-6 text-purple-400 animate-spin" />
          <div>
            <p className="text-xs font-bold font-mono text-white uppercase tracking-wider">
              SYNTHESIZING SPECTRAL BANDS
            </p>
            <p className="text-[10px] font-mono text-slate-300 mt-1">
              Sentinel-2 L2A SWIR/VNIR Inversion in progress...
            </p>
          </div>
        </div>
      ) : prediction ? (
        <div className="flex flex-col gap-2.5">

          {/* Header Badge */}
          <div className="flex justify-between items-center pb-2 border-b border-purple-500/20">
            <span className="text-[10px] font-sans font-bold uppercase tracking-wider text-white">
              CLASSIFICATION RESULT
            </span>
            <span className="gis-badge-lavender font-mono text-white">
              {prediction.classification}
            </span>
          </div>

          {/* Structured Telemetry Grid */}
          <div className="grid grid-cols-2 gap-2">
            {/* Mineralization Percentile Tile (formerly labeled "Confidence
                Idx" -- terminology-only fix, same underlying value:
                prediction.manganese_confidence, unchanged). */}
            <div
              className="gis-metric-tile border-purple-500/20"
              title="Relative percentile of mineralization strength within the selected exploration area. This is not a probability of manganese occurrence."
            >
              <span className="gis-spec-label text-white">MINERALIZATION PERCENTILE</span>
              <div className="mt-1">
                <p className="text-xl font-bold font-mono text-white tracking-tight">
                  {(prediction.manganese_confidence * 100).toFixed(1)}%
                </p>
                <div className="w-full bg-slate-800 h-1 rounded-full mt-1.5 overflow-hidden">
                  <div
                    className="bg-gradient-to-r from-purple-500 to-purple-300 h-full rounded-full transition-all duration-500"
                    style={{ width: `${(prediction.manganese_confidence * 100).toFixed(0)}%` }}
                  ></div>
                </div>
                <p className="text-[8px] font-sans text-slate-400 mt-1 leading-tight">
                  Relative percentile within this area — not a probability of manganese occurrence.
                </p>
              </div>
            </div>

            {/* Illustrative Yield Tile -- reference-scenario values from the
                backend (tons, not megatons); not an ML prediction or a
                measured reserve. */}
            <div className="gis-metric-tile border-purple-500/20">
              <span className="gis-spec-label text-white">EST YIELD (ILLUSTRATIVE)</span>
              <div className="mt-1">
                <p className="text-lg font-bold font-mono text-white tracking-tight">
                  {(prediction.shortfall_metrics?.estimated_yield_tons ?? 0).toLocaleString()}
                  <span className="text-[10px] text-slate-300 ml-1">tons</span>
                </p>
                <span className="text-[10px] font-mono text-white font-semibold">
                  FEASIBILITY: {prediction.shortfall_metrics?.extraction_feasibility_score ?? '8.5'}/10
                </span>
                <p className="text-[8px] font-sans text-slate-400 mt-1 leading-tight">
                  Illustrative capacity scenario — not a measured reserve or ML-predicted yield.
                </p>
              </div>
            </div>
          </div>

          {/* Threshold warning if confidence is lower than slider */}
          {prediction.manganese_confidence < confidenceThreshold && (
            <div className="px-2.5 py-1 rounded bg-amber-500/10 border border-amber-500/30 text-amber-300 text-[10px] font-mono flex items-center gap-1.5">
              <ShieldAlert className="w-3.5 h-3.5 shrink-0" />
              <span>[!] CONFIDENCE BELOW ACTIVE CUTOFF ({(confidenceThreshold * 100).toFixed(0)}%)</span>
            </div>
          )}

          {/* Assay Spec Table -- ore label and deficit figure are the
              backend's illustrative reference scenario, not assay results. */}
          <div className="rounded border border-purple-500/20 divide-y divide-purple-500/15 bg-slate-950/40">
            <div className="gis-spec-row">
              <span className="gis-spec-label text-white">ORE COMPLEX (INDICATIVE)</span>
              <span className="text-white text-right text-[11px] font-mono font-medium">{prediction.ore_type_detected}</span>
            </div>
            <div className="gis-spec-row">
              <span className="gis-spec-label text-white">DEFICIT REDUCTION (ILLUSTRATIVE)</span>
              <span className="text-white text-right font-bold font-mono">+{prediction.shortfall_metrics?.annual_deficit_reduction_pct}%</span>
            </div>
            <div className="gis-spec-row">
              <span className="gis-spec-label text-white">COORDINATES</span>
              <span className="text-white text-right text-[10px] font-mono font-medium">{selectedCoords.lat.toFixed(4)}°N, {selectedCoords.lon.toFixed(4)}°E</span>
            </div>
            <div className="gis-spec-row">
              <span className="gis-spec-label text-white">REFERENCE ZONE</span>
              <span className="text-white text-right text-[10px] font-mono font-medium">{activeBelt ? activeBelt.shortName : 'CUSTOM_SECTOR'}</span>
            </div>
          </div>

          {/* CANDIDATE SCORE BREAKDOWN -- reuses this exact same
              prediction.nearest_candidate object (no new selection state,
              no new fetch); shows at a glance why this candidate ranks the
              way it does. Placed here rather than in Explainable AI since
              that panel already covers this same data in a different
              (narrative) format -- this keeps it compact and non-duplicative. */}
          <CandidateScoreBreakdown candidate={prediction.nearest_candidate ?? null} />
        </div>
      ) : (
        <div className="flex flex-col items-center gap-2 text-center py-4">
          <Crosshair className="w-5 h-5 text-purple-400/60" />
          <p className="text-xs font-sans text-slate-300">
            Click map or select mineral corridor to trigger multispectral assay.
          </p>
        </div>
      ),
    },
    {
      key: 'explainable',
      emoji: '✨',
      label: 'Explainable AI',
      tooltip: 'Why is this location important?',
      description: 'Understand why this target was selected',
      // Same guard as before (!loading && prediction) -- ExplainableAI
      // itself already handles a null candidate with its own empty state,
      // this just mirrors the exact prior render condition.
      content: !loading && prediction ? (
        <ExplainableAI candidate={prediction.nearest_candidate ?? null} />
      ) : (
        <div className="flex flex-col items-center gap-2 text-center py-4">
          <p className="text-xs font-sans text-slate-300">
            {loading ? 'Synthesizing spectral bands...' : 'Click map or select mineral corridor to trigger multispectral assay.'}
          </p>
        </div>
      ),
    },
    {
      key: 'analytics',
      emoji: '📈',
      label: 'Analytics',
      tooltip: 'Explore candidate statistics',
      description: 'Explore candidate distribution and scores',
      // Bundles the two existing chart cards that already sat back-to-back
      // in the old single panel (National Deficit chart + AnalyticsDashboard)
      // -- same components/props/state, just grouped under one button.
      content: (
        <div className="flex flex-col gap-2.5">
          <div className="gis-lavender-card p-3 flex flex-col flex-1 min-h-[185px]">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-1.5 text-xs font-sans font-semibold text-white">
                <TrendingUp className="h-3.5 w-3.5 text-orange-400" />
                <span className="font-sans text-[11px] uppercase tracking-wider font-bold text-white">NATIONAL DEFICIT (MT, ILLUSTRATIVE)</span>
              </div>
              <span className="text-[9px] font-mono text-slate-300">2023-2026_EST</span>
            </div>

            <div className="w-full h-32">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={shortfallTrend} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                  <XAxis dataKey="year" stroke="#94a3b8" fontSize={9} tickLine={false} fontFamily="monospace" />
                  <YAxis stroke="#94a3b8" fontSize={9} tickLine={false} fontFamily="monospace" />
                  <ChartTooltip
                    cursor={{ fill: 'rgba(249, 115, 22, 0.15)' }}
                    contentStyle={{
                      backgroundColor: '#020617',
                      borderColor: '#f97316',
                      borderRadius: '0.375rem',
                      fontSize: '10px',
                      fontFamily: 'monospace',
                      color: '#ffffff'
                    }}
                  />
                  <Bar
                    dataKey="deficit"
                    fill="#f97316"
                    name="Deficit (MT)"
                    radius={[3, 3, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <p className="text-[9px] font-sans text-slate-300 text-center mt-1">
              * Illustrative reference projection for demo context — not observed production data.
            </p>
          </div>

          <AnalyticsDashboard
            candidates={candidates}
            loading={candidatesLoading}
            error={candidatesError}
            onExploreCandidate={fetchPrediction}
          />
        </div>
      ),
    },
    {
      key: 'dossier',
      emoji: '⬇️',
      label: 'Download',
      tooltip: 'Download target information',
      isAction: true,
      disabled: !prediction,
      onAction: handleExportProspectus,
    },
    {
      key: 'howitworks',
      emoji: '⚙️',
      label: 'How It Works',
      tooltip: 'See the detection pipeline',
      description: 'The actual screening pipeline behind every candidate',
      // Purely static/explanatory -- HowItWorks.jsx takes no props and
      // touches no candidate/prediction/dataset state. Same open/close
      // toggle as every other left-menu section (activeSection).
      content: <HowItWorks />,
    },
  ];

  return (
    <div className="relative w-screen h-screen overflow-hidden bg-slate-950 text-white font-sans select-none">

      {/* TOAST NOTIFICATION ON EXPORT */}
      {showExportToast && (
        <div className="absolute top-20 right-6 z-50 pointer-events-auto animate-bounce flex items-center gap-2 px-3.5 py-2 bg-slate-950/95 border border-purple-500/50 shadow-2xl rounded-lg text-white text-xs font-mono font-semibold backdrop-blur-md">
          <CheckCircle2 className="w-3.5 h-3.5 text-purple-400" />
          <span>[✓ DOSSIER_EXPORTED_SUCCESSFULLY .JSON]</span>
        </div>
      )}

      {/* SPATIAL RASTER VIEWPORT CONTAINER */}
      <div id="spatial-raster-viewport" data-engine="sentinel-spatial-runtime" className="gis-viewport-root">
        <MapContainer
          center={[21.8129, 80.1849]}
          zoom={6}
          scrollWheelZoom={true}
          zoomControl={false}
          attributionControl={false}
          className="h-full w-full"
        >
          <TileLayer
            key={basemap}
            url={basemap === 'dark' ? DARK_URL : SATELLITE_URL}
            attribution={basemap === 'dark' ? DARK_ATTR : SATELLITE_ATTR}
            maxZoom={19}
          />
          <TileLayer
            url={LABELS_URL}
            opacity={0.85}
            maxZoom={19}
            zIndex={10}
          />
          <MapViewController coords={selectedCoords} />
          <LocationSelector onSelectLocation={(lat, lon) => fetchPrediction(lat, lon)} />

          {/* PIXEL-LEVEL RED/YELLOW/GREEN EXPLORATION-POTENTIAL OVERLAY --
              pre-rendered raster PNG (src/data_processing/render_score_overlay.py)
              from the pipeline's own real per-pixel mineralization_percentile,
              clipped to this dataset's real processing/surveillance AOI and
              with SCL water pixels masked transparent. Bounds come straight
              from the PNG's own georeferencing (/api/pixel_overlay), never
              fabricated. Leaflet renders ImageOverlay in the overlayPane,
              which sits below markerPane by default, so candidate markers
              stay on top and clickable without any extra z-index handling. */}
          {pixelOverlay && (
            <ImageOverlay
              url={`${API_BASE_URL}${pixelOverlay.image_url}`}
              bounds={pixelOverlay.leaflet_bounds}
              opacity={1}
            />
          )}

          {/* REFERENCE MINERAL CORRIDOR POLYGONS (static reference geology, not survey results) */}
          {MANGANESE_BELTS.map((belt) => {
            const isPassingThreshold = belt.confidence >= confidenceThreshold;
            const isHovered = hoveredBelt && hoveredBelt.id === belt.id;
            return (
              <Polygon
                key={belt.id}
                positions={belt.coords}
                pathOptions={{
                  color: isHovered ? '#ffffff' : belt.color,
                  fillColor: belt.fillColor,
                  fillOpacity: isHovered ? 0.55 : isPassingThreshold ? (belt.confidence > 0.85 ? 0.35 : 0.28) : 0.06,
                  weight: isHovered ? 3.5 : isPassingThreshold ? 2.5 : 1,
                  opacity: isPassingThreshold ? 1.0 : 0.3,
                  dashArray: isPassingThreshold ? undefined : '6, 6'
                }}
                eventHandlers={{
                  click: () => {
                    fetchPrediction(belt.center[0], belt.center[1], CORRIDOR_ZOOM, belt.dataset);
                  },
                  mouseover: () => {
                    setHoveredBelt(belt);
                  },
                  mouseout: () => {
                    setHoveredBelt(null);
                  }
                }}
              >
                <LeafletTooltip direction="top" offset={[0, -10]} opacity={0.96} sticky>
                  <div className="text-xs font-sans text-white p-0.5">
                    <div className="font-bold font-sans flex items-center gap-1.5 text-white">
                      <span
                        className="inline-block w-2 h-2 rounded-sm"
                        style={{ backgroundColor: belt.color }}
                      />
                      {belt.name}
                    </div>
                    <div className="text-[11px] text-amber-300 mt-0.5 font-mono">{belt.ore}</div>
                    <div className="text-[11px] text-slate-200 mt-0.5 font-sans">{belt.grade}</div>
                    <div className="text-[10px] text-slate-300 mt-1 font-mono flex items-center gap-2">
                      <span className="text-amber-400 font-semibold">
                        CONF: {(belt.confidence * 100).toFixed(0)}%
                      </span>
                      <span>•</span>
                      <span className="font-sans text-white">{belt.state}</span>
                    </div>
                    {!isPassingThreshold && (
                      <div className="text-[10px] text-amber-400 font-medium mt-1 font-mono flex items-center gap-1">
                        <ShieldAlert className="w-3 h-3" /> BELOW_CUTOFF ({(confidenceThreshold * 100).toFixed(0)}%)
                      </div>
                    )}
                  </div>
                </LeafletTooltip>
              </Polygon>
            );
          })}

          {/* CHENNAI AOI POLYGON -- the real processing/search AOI (see
              CHENNAI_AOI_BOUNDS above), shown only while the Chennai dataset
              is active. Same cyan styling as the Keonjhar belt polygon
              above (color/fillColor '#06b6d4'), but static -- no
              confidence-threshold/hover logic, since there is no fabricated
              tier data for this AOI, unlike MANGANESE_BELTS entries. */}
          {selectedDataset === 'chennai' && (
            <Polygon
              positions={CHENNAI_AOI_BOUNDS}
              pathOptions={{
                color: '#06b6d4',
                fillColor: '#06b6d4',
                fillOpacity: 0.28,
                weight: 2.5,
                opacity: 1.0,
              }}
            >
              <LeafletTooltip direction="top" offset={[0, -10]} opacity={0.96} sticky>
                <div className="text-xs font-sans text-white p-0.5">
                  <div className="font-bold font-sans flex items-center gap-1.5 text-white">
                    <span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: '#06b6d4' }} />
                    Chennai Exploration AOI
                  </div>
                  <div className="text-[10px] text-slate-300 mt-1 font-mono">
                    Sentinel-2 processing/search area -- 689 candidates
                  </div>
                </div>
              </LeafletTooltip>
            </Polygon>
          )}

          {/* Note: T45QUE previously had a dashed cyan "Keonjhar AOI" polygon
              here, added solely to outline the pixel-score overlay's old
              (incorrectly small) clip box. Removed: the overlay now covers
              this dataset's real full raster extent (see
              render_score_overlay.py), and that box no longer corresponded
              to any real, independently-meaningful surveillance boundary --
              unlike CHENNAI_AOI_BOUNDS below, which is the real Chennai
              processing/search AOI clip_to_aoi.py actually clipped the
              raster to, and stays untouched. */}

          {/* CHENNAI REFERENCE MARKER -- reuses the existing react-leaflet
              Marker/Tooltip components, same as the belt tooltips above.
              Real published city coordinates; this is a plain geographic
              label (not a mineral-potential indicator itself -- it carries
              no fabricated confidence/ore/grade the way MANGANESE_BELTS
              entries do). The real Chennai candidate data it sits near is
              queried via the 'chennai' corridor button / EXTRA_LOCATIONS
              entry below (and any map click while that dataset is active),
              same as any other selectable location. */}
          <Marker position={[13.0827, 80.2707]}>
            <LeafletTooltip permanent direction="top" offset={[0, -10]} opacity={0.92}>
              <div className="text-xs font-sans font-bold text-white px-0.5">Chennai</div>
            </LeafletTooltip>
          </Marker>

          {/* SELECTED LOCATION PIN */}
          <Marker position={[selectedCoords.lat, selectedCoords.lon]}>
            <Popup className="custom-map-popup">
              <div className="p-1 text-slate-900 font-mono">
                <div className="text-xs font-bold uppercase tracking-wider text-amber-700 flex items-center gap-1">
                  <Crosshair className="w-3.5 h-3.5" /> PROBE_TARGET_COORDS
                </div>
                <div className="mt-1 text-xs font-semibold">
                  LAT: {selectedCoords.lat.toFixed(4)}°N<br />
                  LON: {selectedCoords.lon.toFixed(4)}°E
                </div>
              </div>
            </Popup>
          </Marker>
        </MapContainer>
      </div>

      {/* TOP-LEFT: DETACHED FRAMELESS BRANDING ISLAND */}
      <div className="absolute top-4 left-4 z-20 pointer-events-auto flex items-center gap-3 drop-shadow-[0_2px_8px_rgba(0,0,0,0.8)]">
        <div className="flex items-center justify-center w-8 h-8 rounded bg-amber-500/20 border border-amber-500/40 text-amber-400 font-mono font-black text-xs shadow-inner backdrop-blur-sm">
          Mn25
        </div>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-sm md:text-base font-extrabold font-sans tracking-tight text-white uppercase">
              GeoManganese AI <span className="text-amber-400 font-normal">//</span> <span className="text-white">Team RIZZLERS</span>
            </h1>
            <span className="gis-badge-slate text-[9px] hidden sm:inline-block text-white">SIH26009</span>
          </div>
          <p className="text-[11px] font-sans text-slate-300 font-medium tracking-normal hidden md:block">
            Multispectral Remote Sensing & Mineral Potential Inversion
          </p>
        </div>
      </div>

      {/* TOP-CENTER: INDEPENDENT CORRIDOR FLOATING BAR */}
      <div className="absolute top-4 left-[54%] -translate-x-1/2 z-20 pointer-events-auto">
        {headerExpanded ? (
          <div className="gis-island-charcoal px-3.5 py-1.5 flex items-center gap-2 shadow-2xl transition-all duration-300">
            <span className="text-[10px] font-sans font-bold uppercase tracking-widest text-white shrink-0 hidden lg:inline-block mr-1">
              CORRIDORS:
            </span>
            <div className="flex items-center gap-1.5 overflow-x-auto max-w-xs sm:max-w-md md:max-w-lg lg:max-w-xl custom-scrollbar py-0.5">
              {[...MANGANESE_BELTS, ...EXTRA_LOCATIONS].map((belt) => {
                const isSelected =
                  Math.abs(selectedCoords.lat - belt.center[0]) < 0.15 &&
                  Math.abs(selectedCoords.lon - belt.center[1]) < 0.15;
                return (
                  <button
                    key={belt.id}
                    onClick={() => fetchPrediction(belt.center[0], belt.center[1], belt.zoom ?? CORRIDOR_ZOOM, belt.dataset)}
                    className={`gis-btn-tactical shrink-0 text-white ${
                      isSelected ? 'gis-btn-tactical-active' : 'gis-btn-tactical-idle'
                    }`}
                    title={belt.grade ? `${belt.name} • ${belt.grade}` : belt.name}
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-sm shrink-0"
                      style={{ backgroundColor: belt.color || '#64748b' }}
                    />
                    <span className="text-white">{belt.shortName}</span>
                  </button>
                );
              })}
            </div>
            <button
              onClick={() => setHeaderExpanded(false)}
              className="p-1 rounded hover:bg-slate-800 text-slate-300 hover:text-white transition cursor-pointer border-l border-slate-700/80 pl-2 ml-0.5"
              title="Compact Corridors (Press 'H')"
            >
              <ChevronUp className="w-3.5 h-3.5" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => setHeaderExpanded(true)}
            className="gis-island-charcoal px-3 py-1.5 flex items-center gap-1.5 text-xs font-mono font-semibold text-white hover:text-amber-400 transition cursor-pointer"
            title="Expand Mineral Corridors (Press 'H')"
          >
            <Layers3 className="w-3.5 h-3.5 text-amber-400" />
            <span className="text-white">CORRIDORS [{MANGANESE_BELTS.length + EXTRA_LOCATIONS.length}]</span>
            <ChevronDown className="w-3.5 h-3.5 text-amber-400" />
          </button>
        )}
      </div>

      {/* TOP-RIGHT: DETACHED CYAN BASEMAP SWITCHER */}
      <div className="absolute top-4 right-4 z-20 pointer-events-auto flex items-center gap-2.5">
        {/* Electric Cyan Basemap Pill */}
        <div className="gis-island-cyan p-1 flex items-center gap-1">
          <button
            onClick={() => setBasemap('dark')}
            className={`px-2.5 py-1 rounded-lg text-xs font-mono font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              basemap === 'dark'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/50 shadow-sm shadow-cyan-950'
                : 'text-slate-300 hover:text-white'
            }`}
            title="Esri Dark Canvas Basemap"
          >
            <Layers className="w-3.5 h-3.5" />
            <span>DARK</span>
          </button>
          <button
            onClick={() => setBasemap('satellite')}
            className={`px-2.5 py-1 rounded-lg text-xs font-mono font-semibold flex items-center gap-1.5 transition-all cursor-pointer ${
              basemap === 'satellite'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-400/50 shadow-sm shadow-cyan-950'
                : 'text-slate-300 hover:text-white'
            }`}
            title="Esri Satellite Basemap"
          >
            <Satellite className="w-3.5 h-3.5" />
            <span>SAT</span>
          </button>
        </div>
      </div>

      {/* RIGHT-SIDE PANEL ROW -- Mineral Potential Legend (left) + Rank Index
          (right, rightmost/anchored edge) in one flex row, replacing two
          independently positioned absolute boxes that used to overlap (the
          legend was bottom-right; Rank Index spans top-20 to bottom-16 --
          both competed for the same right-4 column). Neither panel's own
          content, state, or callbacks changed -- only their shared
          positioning wrapper. flex-wrap + a max-width cap keep them from
          ever overlapping even if a viewport is too narrow to fit both on
          one line; nothing is hidden, it just reflows. */}
      <div className="absolute top-20 right-4 bottom-16 z-20 flex flex-wrap items-start justify-end gap-3 max-w-[calc(100vw-2rem)]">

        {/* MINERAL POTENTIAL LEGEND -- was bottom-right (drop-shadow'd
            standalone box); now sits immediately left of Rank Index,
            top-aligned, sized to its own natural (unstretched) content
            height via the row's default items-start. Content/state/toggle
            behavior (isLegendExpanded/setLegendOpen/hoveredBelt) unchanged. */}
        <div className="pointer-events-auto drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)]">
          {!isLegendExpanded ? (
            <button
              onClick={() => setLegendOpen(true)}
              onMouseEnter={() => setLegendOpen(true)}
              className="p-1.5 px-3 rounded-lg bg-slate-950/30 hover:bg-slate-900/60 backdrop-blur-sm border border-slate-700/40 flex items-center gap-2 text-xs text-white cursor-pointer transition-all active:scale-95 group font-mono"
              title="View Mineral Potential Legend"
            >
              <Layers className="w-3.5 h-3.5 text-amber-400 group-hover:scale-110 transition-transform" />
              <span className="font-semibold text-[10px] uppercase font-sans text-white">LEGEND</span>
            </button>
          ) : (
            <div
              onMouseLeave={() => setLegendOpen(false)}
              className="bg-slate-950/35 backdrop-blur-[3px] p-3 rounded-xl text-xs text-white w-80 flex flex-col gap-2 transition-all duration-300 border border-slate-700/30"
            >
              <div className="flex items-center justify-between border-b border-white/10 pb-1.5">
                <span className="font-bold uppercase tracking-wider text-[10px] font-sans text-white flex items-center gap-1.5">
                  <Layers className="w-3.5 h-3.5 text-amber-400" /> MINERAL POTENTIAL LEGEND
                </span>
                <button
                  onClick={() => {
                    setLegendOpen(false);
                    setHoveredBelt(null);
                  }}
                  className="p-0.5 rounded hover:bg-white/10 text-slate-300 hover:text-white transition cursor-pointer"
                  title="Minimize Legend"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>

              {/* Contextual Active Hovered Belt Banner */}
              {hoveredBelt && (
                <div className="p-2 rounded-lg bg-slate-950/50 border border-white/15 flex flex-col gap-0.5 shadow-inner">
                  <div className="flex items-center justify-between">
                    <span className="font-bold font-sans text-white text-xs flex items-center gap-1.5">
                      <span
                        className="w-2 h-2 rounded-sm"
                        style={{ backgroundColor: hoveredBelt.color }}
                      />
                      {hoveredBelt.name}
                    </span>
                    <span className="gis-badge-amber text-[10px] font-mono text-white font-bold">
                      {(hoveredBelt.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="text-[10px] text-amber-300 font-mono mt-0.5">{hoveredBelt.ore}</div>
                  <div className="text-[10px] text-white font-sans">{hoveredBelt.grade}</div>
                  <div className="text-[9px] font-mono text-slate-300 flex justify-between pt-1 border-t border-white/10 mt-0.5">
                    <span className="font-sans text-white">{hoveredBelt.state}</span>
                    <span className="text-amber-400 font-bold">CLICK_TO_ANALYZE</span>
                  </div>
                </div>
              )}

              {/* Standard Potential Badges */}
              <div className="flex flex-col gap-1.5 text-[10px] font-sans">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm bg-amber-500 shrink-0 border border-amber-400/60 shadow-sm shadow-amber-500/40"></span>
                  <span className="text-white font-medium">Tier-1 High Potential (Braunite/Pyrolusite)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm bg-cyan-500 shrink-0 border border-cyan-400/60 shadow-sm shadow-cyan-500/40"></span>
                  <span className="text-white font-medium">Tier-2 Active Mining (Fe-Mn & Gondite)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-sm bg-sky-500 shrink-0 border border-sky-400/60 shadow-sm shadow-sky-500/40"></span>
                  <span className="text-white font-medium">Tier-3 Detrital Pocket / Alteration Zone</span>
                </div>
                <div className="flex items-center gap-2 border-t border-white/10 pt-1 mt-0.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-rose-500 flex items-center justify-center shrink-0">
                    <span className="w-1 h-1 rounded-full bg-white"></span>
                  </div>
                  <span className="text-white font-mono text-[9px]">SENSOR_PROBE (ACTIVE_MARKER)</span>
                </div>
              </div>

              {/* AI CANDIDATE SCORE LEGEND -- RED/YELLOW/GREEN exploration-
                  potential colour system, driven by the same real rank_score
                  (0-100, unchanged pipeline output) used across ExplainableAI,
                  AnalyticsDashboard and the Top Exploration Targets panel. */}
              <div className="flex flex-col gap-1.5 text-[10px] font-sans border-t border-white/10 pt-1.5">
                <span className="font-bold uppercase tracking-wider text-[9px] font-mono text-slate-300">
                  AI Candidate Score
                </span>
                {Object.entries(LEVEL_DOT_CLASS).map(([level, dotClass]) => (
                  <div key={level} className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-sm shrink-0 border shadow-sm ${dotClass}`}></span>
                    <span className="text-white font-medium">
                      {LEVEL_EMOJI[level]} {level === 'HIGH' ? 'HIGH POTENTIAL' : level} — {LEVEL_RANGE_LABEL[level]}
                    </span>
                  </div>
                ))}
              </div>

              {/* PIXEL-LEVEL SCORE LEGEND -- describes the map's raster overlay
                  (render_score_overlay.py), which colours every real,
                  AOI-clipped, non-water pixel by the pipeline's own
                  mineralization_percentile using these exact same
                  RED/YELLOW/GREEN thresholds. Separate from the candidate-level
                  legend above since it labels a different (pixel, not
                  per-candidate) layer. */}
              <div className="flex flex-col gap-1.5 text-[10px] font-sans border-t border-white/10 pt-1.5">
                <span className="font-bold uppercase tracking-wider text-[9px] font-mono text-slate-300">
                  Pixel-Level AI Score
                </span>
                {Object.entries(LEVEL_DOT_CLASS).map(([level, dotClass]) => (
                  <div key={level} className="flex items-center gap-2">
                    <span className={`w-2.5 h-2.5 rounded-sm shrink-0 border shadow-sm ${dotClass}`}></span>
                    <span className="text-white font-medium">
                      {LEVEL_EMOJI[level]} {level} PIXEL POTENTIAL — {LEVEL_RANGE_LABEL[level]}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* RANK INDEX -- stays the rightmost element. self-stretch overrides
            the row's items-start default (which the legend above keeps) so
            its internal list can use the full top-20..bottom-16 height,
            same as before. Collapsible: closed by default, shows only a
            small 🏆 toggle button. Opening/closing is purely local UI state
            (rankIndexOpen) -- it never touches selectedCoords/fetchPrediction,
            so it can't navigate the map on its own. The panel itself
            (TopTargetsPanel) is unchanged -- same `candidates` array
            AnalyticsDashboard already uses, so it automatically reflects
            whichever dataset (t45que/chennai) is active, and clicking a row
            still reuses fetchPrediction, the same navigation flow every
            other candidate-selection control already uses. */}
        <div className="pointer-events-auto self-stretch flex flex-col">
          {rankIndexOpen ? (
            <TopTargetsPanel
              candidates={candidates}
              loading={candidatesLoading}
              error={candidatesError}
              selectedCandidateId={prediction?.nearest_candidate?.candidate_id ?? null}
              onSelectCandidate={(c) => fetchPrediction(c.centroid_latitude, c.centroid_longitude)}
              onClose={() => setRankIndexOpen(false)}
            />
          ) : (
            <button
              onClick={() => setRankIndexOpen(true)}
              className="gis-btn-lavender-ghost shadow-2xl px-3 py-2"
              title="Open Rank Index"
            >
              <span className="text-base leading-none">🏆</span>
            </button>
          )}
        </div>
      </div>

      {/* LEFT MENU -- compact per-feature buttons (Detection Sensitivity /
          Classification Result / Explainable AI / Analytics / Dossier)
          replacing the old single always-open panel. SidebarMenu is a
          generic presentational shell; each section's content above
          (menuSections) is the exact pre-existing markup for that feature,
          unchanged -- same state, same callbacks. */}
      <SidebarMenu
        sections={menuSections}
        activeKey={activeSection}
        onToggle={(key) => setActiveSection((prev) => (prev === key ? null : key))}
      />

      {/* FLOATING COORDINATE PILL (BOTTOM-LEFT - AMBER Mn25 SYNCHRONIZED) */}
      <div className="absolute bottom-4 left-4 z-20 pointer-events-auto">
        <div className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono rounded-lg border border-amber-500/30 bg-amber-950/20 backdrop-blur-sm shadow-[0_0_15px_rgba(245,158,11,0.1)] text-amber-400">
          <Compass className="w-3.5 h-3.5 text-amber-400 shrink-0" />
          <div className="flex items-center gap-2 font-mono">
            <span className="text-amber-500/70">LAT:</span>
            <span className="text-amber-300 font-bold">{selectedCoords.lat.toFixed(4)}°N</span>
            <span className="text-amber-700/60">|</span>
            <span className="text-amber-500/70">LON:</span>
            <span className="text-amber-300 font-bold">{selectedCoords.lon.toFixed(4)}°E</span>
          </div>
          <span className="hidden sm:inline-block text-amber-300 ml-1 border-l border-amber-500/30 pl-2 text-[10px] font-mono">
            PROBE_ACTIVE
          </span>
        </div>
      </div>

    </div>
  );
}