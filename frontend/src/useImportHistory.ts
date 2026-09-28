import { useEffect, useRef, useState } from 'react'
import type { ImportPage } from './bundleImports'

export function useImportHistory<T>(key: string | null, load: (before?: number) => Promise<ImportPage<T>>, identity: (item: T) => string) {
  const [page, setPage] = useState<ImportPage<T>>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const sequence = useRef(0); const locked = useRef(false)
  const pageKey = useRef(key)
  const latest = useRef({ load, identity }); latest.current = { load, identity }
  useEffect(() => {
    const seq = ++sequence.current
    if (pageKey.current !== key) { pageKey.current = key; setPage(undefined) }
    setError(null); setLoading(!!key); locked.current = !!key
    if (key) void latest.current.load().then(value => { if (sequence.current === seq) setPage(value) }).catch(reason => {
      if (sequence.current === seq) setError(reason instanceof Error ? reason.message : 'Saved history is unavailable.')
    }).finally(() => { if (sequence.current === seq) { locked.current = false; setLoading(false) } })
    return () => { sequence.current++; locked.current = false }
  }, [key, revision])
  async function older() {
    if (locked.current || !page?.next_before) return
    const seq = ++sequence.current; locked.current = true; setLoading(true); setError(null)
    try {
      const value = await latest.current.load(page.next_before)
      if (sequence.current !== seq) return
      const merged = new Map(page.items.map(item => [latest.current.identity(item), item]))
      value.items.forEach(item => merged.set(latest.current.identity(item), item))
      setPage({ ...value, items: [...merged.values()], skipped: (page.skipped ?? 0) + (value.skipped ?? 0) })
    } catch (reason) { if (sequence.current === seq) setError(reason instanceof Error ? reason.message : 'Older history is unavailable.') }
    finally { if (sequence.current === seq) { locked.current = false; setLoading(false) } }
  }
  return { page: pageKey.current === key ? page : undefined, loading, error, refresh: () => setRevision(value => value + 1), older }
}
