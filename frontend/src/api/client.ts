// Thin fetch wrapper: adds the JWT, refreshes it once on 401, and turns errors into ApiError.

const ACCESS = 'slpos.access'
const REFRESH = 'slpos.refresh'

export class ApiError extends Error {
  status: number
  code?: string
  data: unknown

  constructor(status: number, data: unknown) {
    super(errorMessage(data, status))
    this.status = status
    this.data = data
    this.code = typeof data === 'object' && data && 'code' in data ? String((data as { code: unknown }).code) : undefined
  }
}

function errorMessage(data: unknown, status: number): string {
  if (!data || typeof data !== 'object') return status >= 500 ? 'Server error. Please try again.' : 'Request failed.'
  const d = data as Record<string, unknown>
  if (typeof d.detail === 'string') return d.detail
  // DRF field errors: {"field": ["msg"]} or nested lists
  const parts: string[] = []
  const walk = (value: unknown, key?: string) => {
    if (typeof value === 'string') parts.push(key && key !== 'non_field_errors' ? `${key}: ${value}` : value)
    else if (Array.isArray(value)) value.forEach((v) => walk(v, key))
    else if (value && typeof value === 'object') Object.entries(value).forEach(([k, v]) => walk(v, k))
  }
  walk(d)
  return parts.join(' ') || 'Request failed.'
}

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS)
  },
  get refresh() {
    return localStorage.getItem(REFRESH)
  },
  set(access: string, refresh?: string) {
    localStorage.setItem(ACCESS, access)
    if (refresh) localStorage.setItem(REFRESH, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS)
    localStorage.removeItem(REFRESH)
  },
}

let onUnauthorized: () => void = () => {}
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn
}

async function refreshAccess(): Promise<boolean> {
  const refresh = tokens.refresh
  if (!refresh) return false
  const res = await fetch('/api/auth/refresh/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
  if (!res.ok) return false
  const data = await res.json()
  tokens.set(data.access, data.refresh)
  return true
}

type Body = unknown

async function request<T>(method: string, url: string, body?: Body, retry = true): Promise<T> {
  const headers: Record<string, string> = {}
  const isForm = body instanceof FormData
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`
  const res = await fetch(`/api${url}`, {
    method,
    headers,
    body: body === undefined ? undefined : isForm ? body : JSON.stringify(body),
  })
  // On a sign-in, 401 means a wrong password or PIN. Sending it again would count as a second wrong try.
  const isSignIn = url === '/auth/login/' || url === '/auth/pin-login/'
  if (res.status === 401 && retry && tokens.refresh && !isSignIn) {
    if (await refreshAccess()) return request<T>(method, url, body, false)
    tokens.clear()
    onUnauthorized()
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? safeJson(text) : null
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

function safeJson(text: string) {
  try {
    return JSON.parse(text)
  } catch {
    return { detail: text.slice(0, 200) }
  }
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: Body) => request<T>('POST', url, body ?? {}),
  patch: <T>(url: string, body: Body) => request<T>('PATCH', url, body),
  put: <T>(url: string, body: Body) => request<T>('PUT', url, body),
  del: <T = void>(url: string, body?: Body) => request<T>('DELETE', url, body),
}

/** Download a CSV export (the browser saves the file). */
export async function downloadCsv(url: string, filename: string) {
  const sep = url.includes('?') ? '&' : '?'
  const res = await fetch(`/api${url}${sep}export=csv`, {
    headers: tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {},
  })
  if (!res.ok) throw new ApiError(res.status, await res.json().catch(() => null))
  const blob = await res.blob()
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}

export function qs(params: Record<string, string | number | boolean | undefined | null>) {
  const search = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '' && v !== false) search.set(k, String(v))
  })
  const s = search.toString()
  return s ? `?${s}` : ''
}
