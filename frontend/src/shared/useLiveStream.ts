import { useEffect, useRef, useState } from 'react'
import { API_BASE_URL, API_MODE } from './api-client/config'
import { fromApiEvent, type ApiEvent } from './api-client/live-adapter'
import { getMockBackend } from './api-client/mock/server'
import { tokenStore } from './auth/tokenStore'

export type StreamStatus = 'connecting' | 'open' | 'reconnecting' | 'closed'
export type StreamTransport = 'sse' | 'websocket' | 'mock'

interface Options {
  /** Path of the SSE endpoint. The WebSocket fallback uses `${path}/ws`. */
  path?: string
  enabled?: boolean
}

/**
 * Subscribes to the live event feed. Uses Server-Sent Events, and falls back to a
 * WebSocket if SSE cannot connect. The token is passed as a query parameter because
 * EventSource cannot set headers.
 */
export function useLiveStream<T>(onMessage: (data: T) => void, { path = '/stream', enabled = true }: Options = {}) {
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const [transport, setTransport] = useState<StreamTransport>(API_MODE === 'mock' ? 'mock' : 'sse')
  const handler = useRef(onMessage)

  useEffect(() => {
    handler.current = onMessage
  }, [onMessage])

  useEffect(() => {
    if (!enabled) {
      setStatus('closed')
      return
    }

    if (API_MODE === 'mock') {
      setStatus('open')
      const unsubscribe = getMockBackend().subscribe((e) => handler.current(e as T))
      return () => {
        unsubscribe()
        setStatus('closed')
      }
    }

    let disposed = false
    let source: EventSource | null = null
    let socket: WebSocket | null = null
    let retry: ReturnType<typeof setTimeout> | null = null
    let attempts = 0
    const token = encodeURIComponent(tokenStore.get() ?? '')
    const deliver = (raw: string) => {
      try {
        // The Node API streams its own event shape; map it to ScoredEvent like GET /events does.
        handler.current(fromApiEvent(JSON.parse(raw) as ApiEvent) as T)
      } catch {
        // ignore malformed frames (e.g. keep-alive comments)
      }
    }

    const openWebSocket = () => {
      if (disposed) return
      setTransport('websocket')
      const wsBase = API_BASE_URL.replace(/^http/, 'ws')
      socket = new WebSocket(`${wsBase}${path}/ws?access_token=${token}`)
      socket.onopen = () => {
        attempts = 0
        setStatus('open')
      }
      socket.onmessage = (e) => deliver(String(e.data))
      socket.onclose = () => {
        if (disposed) return
        setStatus('reconnecting')
        attempts += 1
        retry = setTimeout(openWebSocket, Math.min(15_000, 1000 * 2 ** attempts))
      }
    }

    const openSse = () => {
      let opened = false
      setTransport('sse')
      source = new EventSource(`${API_BASE_URL}${path}?access_token=${token}`)
      source.onopen = () => {
        opened = true
        setStatus('open')
      }
      source.onmessage = (e) => deliver(e.data)
      source.onerror = () => {
        if (disposed) return
        if (!opened) {
          source?.close()
          openWebSocket()
        } else {
          setStatus('reconnecting')
        }
      }
    }

    openSse()
    return () => {
      disposed = true
      source?.close()
      socket?.close()
      if (retry) clearTimeout(retry)
      setStatus('closed')
    }
  }, [enabled, path])

  return { status, transport }
}
