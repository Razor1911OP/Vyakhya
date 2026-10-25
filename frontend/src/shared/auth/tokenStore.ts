const KEY = 'vyakhya.access_token'

type Listener = (token: string | null) => void
const listeners = new Set<Listener>()

export const tokenStore = {
  get(): string | null {
    return sessionStorage.getItem(KEY)
  },
  set(token: string | null) {
    if (token) sessionStorage.setItem(KEY, token)
    else sessionStorage.removeItem(KEY)
    listeners.forEach((l) => l(token))
  },
  subscribe(listener: Listener) {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  },
}
