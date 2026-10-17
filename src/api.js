const LOCAL_HOSTS = ['localhost', '127.0.0.1', '[::1]']

/* The backend address. A "localhost" setting only means "this computer", so when the
   site is opened from another laptop on the same Wi-Fi (e.g. http://192.168.1.25:5173)
   the backend is on that same machine: use the page's host instead. Hosted setups
   (VITE_API_URL pointing at a real domain) are left as they are. */
function apiBase() {
  const configured = new URL(import.meta.env.VITE_API_URL || 'http://localhost:8000')
  const pageHost = window.location.hostname
  if (LOCAL_HOSTS.includes(configured.hostname) && pageHost && !LOCAL_HOSTS.includes(pageHost)) {
    configured.hostname = pageHost
  }
  return configured.toString().replace(/\/$/, '')
}

const API_BASE = apiBase()

export async function api(path, { method = 'GET', body, accessToken, userId, role } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`
  else if (userId) headers['X-User-Id'] = userId
  if (role) headers['X-Role'] = role
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || `API request failed (${response.status})`)
  return data
}

export { API_BASE }
