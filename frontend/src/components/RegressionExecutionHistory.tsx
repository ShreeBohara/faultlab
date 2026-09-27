import { useEffect, useId, useRef, useState } from 'react'
import { api, type RegressionExecutionPage } from '../api'
import type { RegressionBundle, RegressionExecution } from '../generated/contracts'
import { Empty, label } from './common'

export function matchingExecution(value: RegressionExecution, bundle: RegressionBundle, expectedId?: string): RegressionExecution {
  if (expectedId && value.execution_id !== expectedId) throw new Error('The saved execution ID does not match the requested ID.')
  if (value.bundle_id !== bundle.bundle_id || value.manifest_hash !== bundle.manifest_hash) throw new Error('The saved execution does not match the selected bundle and manifest.')
  return value
}

export function RegressionExecutionHistory({ regressionId, bundle, selectedId, disabled, onOpen }: { regressionId: string; bundle: RegressionBundle; selectedId: string; disabled: boolean; onOpen: (id: string) => void }) {
  const selectorId = useId()
  const [page, setPage] = useState<RegressionExecutionPage>()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const requestSeq = useRef(0)
  const locked = useRef(false)

  useEffect(() => {
    const seq = ++requestSeq.current
    locked.current = true; setLoading(true); setError(null)
    void api.executions(regressionId).then(value => {
      value.executions.forEach(execution => matchingExecution(execution, bundle))
      if (requestSeq.current === seq) setPage(value)
    }).catch(reason => {
      if (requestSeq.current === seq) setError(reason instanceof Error ? reason.message : 'Saved executions could not be loaded.')
    }).finally(() => {
      if (requestSeq.current === seq) { locked.current = false; setLoading(false) }
    })
    return () => { requestSeq.current++; locked.current = false }
  }, [regressionId, bundle, refresh])

  async function older() {
    if (locked.current || !page?.next_before) return
    const seq = ++requestSeq.current
    locked.current = true; setLoading(true); setError(null)
    try {
      const value = await api.executions(regressionId, page.next_before)
      value.executions.forEach(execution => matchingExecution(execution, bundle))
      if (requestSeq.current !== seq) return
      const merged = new Map(page.executions.map(execution => [execution.execution_id, execution]))
      value.executions.forEach(execution => merged.set(execution.execution_id, execution))
      setPage({ ...value, executions: [...merged.values()] })
    } catch (reason) {
      if (requestSeq.current === seq) setError(reason instanceof Error ? reason.message : 'Older executions could not be loaded.')
    } finally {
      if (requestSeq.current === seq) { locked.current = false; setLoading(false) }
    }
  }

  return <section className="regression-history" aria-label="Saved regression execution history">
    <h3>Saved executions for this bundle</h3>
    <p className="muted">Selecting a saved run reads its original result. It does not start or resume execution.</p>
    <label htmlFor={selectorId}>Saved executions</label><select id={selectorId} value={page?.executions.some(execution => execution.execution_id === selectedId) ? selectedId : ''} disabled={disabled || !page?.executions.length} onChange={event => { if (event.target.value) onOpen(event.target.value) }}>
      <option value="">Select a saved execution</option>
      {page?.executions.map(execution => <option key={execution.execution_id} value={execution.execution_id}>{execution.execution_id} · {label(execution.status)} · {execution.episode_ids.length} trials</option>)}
    </select>
    <div className="controls"><button className="text-button" disabled={disabled || loading} onClick={() => setRefresh(value => value + 1)}>Refresh saved executions</button>{page?.has_more && <button className="text-button" disabled={disabled || loading} onClick={() => void older()}>Load older executions</button>}</div>
    {loading && <p className="muted" role="status">Loading saved executions…</p>}
    {error && <p className="error" role="alert">{page ? 'Previously verified execution history remains available. ' : ''}{error} Refresh saved executions to try again.</p>}
    {!loading && !error && page?.executions.length === 0 && <Empty>No saved executions for this bundle.</Empty>}
    {!!page?.executions.length && <p className="muted">{page.executions.length} saved executions loaded · newest created first. Refresh returns to the newest page; open a run again to refresh its saved status.</p>}
  </section>
}
