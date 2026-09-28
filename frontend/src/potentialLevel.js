// Shared RED / YELLOW / GREEN exploration-potential colour system.
//
// Single source of truth for classifying the existing real rank_score /
// percentile fields (0-100, from candidate_detection.py -- unchanged) into
// HIGH / MODERATE / LOW, and for the colours used to render that
// classification everywhere it appears (ExplainableAI, AnalyticsDashboard,
// TopTargetsPanel, App's legend). No new score is computed here -- this
// only maps the pipeline's existing score to a colour.
export const HIGH_CUTOFF = 75;
export const MODERATE_CUTOFF = 50;

export function levelOf(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  if (value >= HIGH_CUTOFF) return 'HIGH';
  if (value >= MODERATE_CUTOFF) return 'MODERATE';
  return 'LOW';
}

// RED = HIGH (>=75), YELLOW = MODERATE (50-74.99), GREEN = LOW (<50).
export const LEVEL_EMOJI = {
  HIGH: '🔴',
  MODERATE: '🟡',
  LOW: '🟢',
};

export const LEVEL_TEXT_CLASS = {
  HIGH: 'text-red-400',
  MODERATE: 'text-yellow-400',
  LOW: 'text-green-400',
};

export const LEVEL_BAR_CLASS = {
  HIGH: 'bg-gradient-to-r from-red-500 to-red-300',
  MODERATE: 'bg-gradient-to-r from-yellow-500 to-yellow-300',
  LOW: 'bg-gradient-to-r from-green-500 to-green-300',
};

export const LEVEL_BADGE_CLASS = {
  HIGH: 'bg-red-500/15 border-red-500/40 text-red-300',
  MODERATE: 'bg-yellow-500/15 border-yellow-500/40 text-yellow-300',
  LOW: 'bg-green-500/15 border-green-500/40 text-green-300',
};

export const LEVEL_DOT_CLASS = {
  HIGH: 'bg-red-500 border-red-400/60 shadow-red-500/40',
  MODERATE: 'bg-yellow-500 border-yellow-400/60 shadow-yellow-500/40',
  LOW: 'bg-green-500 border-green-400/60 shadow-green-500/40',
};

export const LEVEL_RANGE_LABEL = {
  HIGH: '75–100',
  MODERATE: '50–74.99',
  LOW: '0–49.99',
};
