const API_URL_STORAGE = "docflow_api_url";
const API_KEY_STORAGE = "docflow_api_key";

function resolveApiBase() {
  const stored = localStorage.getItem(API_URL_STORAGE);
  if (stored) return stored.replace(/\/$/, "");
  const params = new URLSearchParams(window.location.search);
  const override = params.get("api");
  if (override) return override.replace(/\/$/, "");
  const { protocol, hostname, port } = window.location;
  if (port === "5500") return `${protocol}//${hostname}:8000`;
  if (port === "8000") return `${protocol}//${hostname}:8000`;
  return "http://127.0.0.1:8000";
}

let API_BASE = resolveApiBase();

function setApiBase(url) {
  API_BASE = (url || resolveApiBase()).replace(/\/$/, "");
  localStorage.setItem(API_URL_STORAGE, API_BASE);
}

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || "";
}

function apiHeaders(extra = {}) {
  const headers = { ...extra };
  const key = getApiKey();
  if (key) headers["X-API-Key"] = key;
  return headers;
}

async function apiFetch(path, options = {}) {
  const headers = apiHeaders(options.headers || {});
  return fetch(`${API_BASE}${path}`, { ...options, headers });
}
