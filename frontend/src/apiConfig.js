// Single source of truth for the backend API base URL.
//
// Override with VITE_API_BASE_URL in frontend/.env for non-local backends:
//   VITE_API_BASE_URL=https://your-backend-host:8000
//
// Default preserves the existing local-development behavior
// (http://localhost:8000). All API calls and served-asset URLs in App.jsx
// must go through API_BASE_URL / apiUrl() instead of hard-coded hosts.
const raw = import.meta.env?.VITE_API_BASE_URL || 'http://localhost:8000';

export const API_BASE_URL = String(raw).replace(/\/$/, '');

export function apiUrl(path) {
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${p}`;
}
