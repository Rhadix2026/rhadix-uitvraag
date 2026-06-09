const BASE = '/api'

let _token = null
export function setAuthToken(t) { _token = t }
export function getAuthToken()  { return _token }
export function clearAuthToken(){ _token = null }

function authHeaders(extra = {}) {
  return _token ? { Authorization: `Bearer ${_token}`, ...extra } : { ...extra }
}

export async function apiFetch(url, options = {}) {
  const { headers = {}, ...rest } = options
  const res = await fetch(url, { ...rest, headers: { ...authHeaders(), ...headers } })
  if (res.status === 401) {
    clearAuthToken()
    window.dispatchEvent(new CustomEvent('kik:unauthorized'))
  }
  return res
}

export async function getMeta() {
  const res = await apiFetch(`${BASE}/meta`)
  if (!res.ok) throw new Error(await res.text())
  return res.json()
}

export async function getHealth() {
  const res = await apiFetch(`${BASE}/health`)
  if (!res.ok) throw new Error('backend onbereikbaar')
  return res.json()
}
