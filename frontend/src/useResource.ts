import { useEffect, useRef, useState } from 'react'
import type { Event } from './generated/contracts'
import { api, validateEvents } from './api'
export type Resource<T> = { data?: T; error: string | null; loading: boolean; updatedAt?: number }
export const pollDelay = (failures: number) => failures ? Math.min(6000, 750 * 2 ** failures) : 750
export function useResource<T>(key: string | null, fetcher: () => Promise<T>, interval = 750): Resource<T> {
  const latest = useRef(fetcher); latest.current = fetcher
  const [state, setState] = useState<Resource<T> & { key: string | null }>({ key, error: null, loading: !!key })
  useEffect(() => {
    let cancelled = false; let timer: number; let failures = 0
    setState({ key, error: null, loading: !!key })
    if (!key) return
    async function poll() {
      try {
        const data = await latest.current()
        if (cancelled) return
        failures = 0; setState({ key, data, error: null, loading: false, updatedAt: Date.now() })
      } catch (error) {
        if (cancelled) return
        failures++; setState(old => ({ ...old, error: error instanceof Error ? error.message : 'Local backend unavailable.', loading: false }))
      }
      if (!cancelled) timer = window.setTimeout(poll, failures ? pollDelay(failures) : interval)
    }
    void poll()
    return () => { cancelled = true; window.clearTimeout(timer) }
  }, [key, interval])
  return state.key === key ? state : { error: null, loading: !!key }
}
export function useEvents(episodeId: string | null): Resource<Event[]> {
  const cache = useRef<{ id: string | null; events: Event[]; after: number }>({ id: null, events: [], after: 0 })
  return useResource(episodeId ? `events:${episodeId}` : null, async () => {
    if (cache.current.id !== episodeId) {
      cache.current = { id: episodeId, events: [], after: 0 }
      try {
        const saved = sessionStorage.getItem(`faultlab:events:${episodeId}`)
        if (saved) { const page = validateEvents(JSON.parse(saved), episodeId!, 0); cache.current = { id: episodeId, events: page.events, after: page.next_after } }
      } catch { /* Discard invalid cache and load server truth from zero. */ }
    }
    const captured = cache.current
    const page = await api.events(episodeId!, captured.after)
    if (cache.current !== captured) return captured.events
    captured.events = [...new Map([...captured.events, ...page.events].map(event => [event.seq, event])).values()].sort((a, b) => a.seq - b.seq); captured.after = Math.max(captured.after, page.next_after)
    try { sessionStorage.setItem(`faultlab:events:${episodeId}`, JSON.stringify({ events: captured.events, next_after: captured.after, has_more: false })) } catch { /* Privacy mode does not prevent playback. */ }
    return captured.events
  })
}
