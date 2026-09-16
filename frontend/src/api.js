// A deployed static site reads bondbook-config.js at runtime. The fallback
// keeps the Render API connected even if that file is cached temporarily.
const runtimeApiUrl = typeof window !== 'undefined' ? window.BONDBOOK_API_URL : ''
const API_BASE = (runtimeApiUrl || import.meta.env.VITE_API_URL || 'https://bondbook-api.onrender.com').replace(/\/+$/, '')

export function getToken() { return localStorage.getItem('bondbook_token') }
export function setToken(token) { token ? localStorage.setItem('bondbook_token', token) : localStorage.removeItem('bondbook_token') }

export async function api(path, options = {}) {
  const headers = { ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (response.status === 204) return null
  let data
  try { data = await response.json() } catch { data = null }
  if (!response.ok) {
    const error = new Error(data?.detail || 'Something went wrong. Please try again.')
    error.status = response.status
    throw error
  }
  return data
}

export async function secureBlob(path) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API_BASE}${path}`, { headers })
  if (!response.ok) throw new Error('This media file is no longer available.')
  return response.blob()
}
