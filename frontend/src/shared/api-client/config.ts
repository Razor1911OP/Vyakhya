const raw = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ?? ''

export const API_BASE_URL = raw.replace(/\/+$/, '')
export const API_MODE: 'mock' | 'live' = API_BASE_URL ? 'live' : 'mock'
