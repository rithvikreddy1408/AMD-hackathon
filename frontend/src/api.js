/**
 * Central API configuration.
 *
 * Development (vite dev server, port 5173):
 *   - VITE_API_URL is unset → falls back to http://localhost:8000
 *   - WS_BASE → ws://localhost:8000
 *
 * Production (served via Nginx on port 80):
 *   - VITE_API_URL is injected as "/api" at build time
 *   - WS_BASE is derived from the browser's own host so Nginx can proxy /ws/
 */
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

// In production, API_URL="/api" (relative), so we derive WS from window.location.
// In development, API_URL="http://localhost:8000" so we swap the scheme directly.
const WS_BASE = API_URL.startsWith('http')
  ? API_URL.replace(/^http/, 'ws')                              // dev: ws://localhost:8000
  : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}`; // prod: ws(s)://your-host

export { API_URL, WS_BASE };
