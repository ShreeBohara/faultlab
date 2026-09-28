import { useEffect, useRef, useState } from 'react'
import { api, type CampaignPage } from '../api'
import type { Campaign } from '../generated/contracts'
import { Badge, Empty, Field, Panel, label } from './common'

export function CampaignHistory({ selectedId, currentCampaign, refreshKey, onOpen }: { selectedId: string; currentCampaign?: Campaign; refreshKey: number; onOpen: (id: string) => void }) {
  const [page, setPage] = useState<CampaignPage>()
  const [choice, setChoice] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  const requestSeq = useRef(0)
  const locked = useRef(false)

  useEffect(() => {
    const seq = ++requestSeq.current
    locked.current = true; setLoading(true); setError(null)
    void api.campaigns().then(value => {
      if (requestSeq.current === seq) setPage(value)
    }).catch(reason => {
      if (requestSeq.current === seq) setError(reason instanceof Error ? reason.message : 'Campaign history could not be loaded.')
    }).finally(() => {
      if (requestSeq.current === seq) { locked.current = false; setLoading(false) }
    })
    return () => { requestSeq.current++; locked.current = false }
  }, [refresh, refreshKey])

  async function older() {
    if (locked.current || !page?.next_before) return
    const seq = ++requestSeq.current
    locked.current = true; setLoading(true); setError(null)
    try {
      const value = await api.campaigns(page.next_before)
      if (requestSeq.current !== seq) return
      const merged = new Map<string, Campaign>(page.campaigns.map(campaign => [campaign.campaign_id, campaign]))
      value.campaigns.forEach(campaign => merged.set(campaign.campaign_id, campaign))
      setPage({ ...value, campaigns: [...merged.values()] })
    } catch (reason) {
      if (requestSeq.current === seq) setError(reason instanceof Error ? reason.message : 'Older campaigns could not be loaded.')
    } finally {
      if (requestSeq.current === seq) { locked.current = false; setLoading(false) }
    }
  }

  // History is a bounded snapshot. The selected campaign's live record already
  // follows execution, so use it for the matching row without reloading history.
  const campaigns = page?.campaigns.map(campaign => currentCampaign?.campaign_id === selectedId && campaign.campaign_id === selectedId ? currentCampaign : campaign)
  const selected = campaigns?.find(campaign => campaign.campaign_id === (choice || selectedId))
  return <Panel title="Campaign history" className="history-panel" aside={<span className="small-label">Read saved evidence</span>}>
    <p className="muted">Open a saved campaign without starting or resuming it. New execution is a separate action in the Run desk.</p>
    <div className="history-controls">
      <div className="history-picker"><label htmlFor="saved-campaign-history">Saved campaigns</label><select id="saved-campaign-history" value={selected?.campaign_id ?? ''} disabled={!page?.campaigns.length} onChange={event => setChoice(event.target.value)}>
        <option value="">Select a saved campaign</option>
        {campaigns?.map(campaign => <option key={campaign.campaign_id} value={campaign.campaign_id}>{campaign.created_at ? new Date(campaign.created_at).toLocaleString() : 'Time not recorded'} · {campaign.mode} · {label(campaign.state ?? 'IDLE')} · {campaign.order_id} · {campaign.campaign_id}</option>)}
      </select></div>
      <button disabled={!selected} onClick={() => { if (selected) onOpen(selected.campaign_id) }}>Open selected campaign</button>
      <button className="text-button" disabled={loading} onClick={() => setRefresh(value => value + 1)}>Refresh history</button>
      {page?.has_more && <button className="text-button" disabled={loading} onClick={() => void older()}>Load older campaigns</button>}
    </div>
    {loading && <p className="muted" role="status">Loading saved campaigns…</p>}
    {error && <p className="error" role="alert">{page ? 'Previously loaded history remains available. ' : ''}{error} Use Refresh history to try again.</p>}
    {!loading && !error && page?.campaigns.length === 0 && <Empty>No saved campaigns yet. Create a new campaign in the Run desk.</Empty>}
    {!!page?.campaigns.length && <p className="muted">{page.campaigns.length} saved campaigns loaded · newest created first{page.has_more ? ' · older campaigns available' : ''}. Refresh returns to the newest page.</p>}
    {selected && <div className="history-selection"><Badge value={selected.state ?? 'IDLE'} /><dl className="facts compact"><Field name="Saved task">{selected.task_text}</Field><Field name="Saved campaign"><code>{selected.campaign_id}</code></Field></dl></div>}
  </Panel>
}
