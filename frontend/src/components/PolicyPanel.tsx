import { useState } from 'react'
import type { PolicyVersion } from '../generated/contracts'
import type { Resource } from '../useResource'
import { object, request } from '../api'
import { Badge, Empty, EpisodeLinks, Field, Hash, Json, Panel, ResourceNote } from './common'

function OriginalProposal({ policy }: { policy: PolicyVersion }) {
  const [raw, setRaw] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  async function load() {
    setLoading(true); setError('')
    try {
      const value = await request(`/policies/${encodeURIComponent(policy.version)}/proposal`, value => {
        if (!object(value) || value.policy_version !== policy.version || value.proposal_ref !== policy.raw_proposal_ref || typeof value.raw !== 'string' || value.raw.length > 100000) throw new Error('The original proposal record could not be validated.')
        return value.raw
      })
      setRaw(value)
    } catch (e) { setError(e instanceof Error ? e.message : 'Proposal unavailable.') }
    finally { setLoading(false) }
  }
  return <div><button className="text-button" disabled={loading} onClick={() => void load()}>{loading ? 'Loading original proposal…' : 'Read original model proposal'}</button>{error && <p role="alert" className="error">{error}</p>}{raw !== null && <details className="json" open><summary>Original proposal · recorded text</summary><pre>{raw}</pre></details>}</div>
}

export function policyDiff(current: PolicyVersion, parent?: PolicyVersion) {
  const before = parent?.content?.rules ?? []
  const after = current.content?.rules ?? []
  return { removed: before.filter(a => !after.some(b => JSON.stringify(a) === JSON.stringify(b))), added: after.filter(a => !before.some(b => JSON.stringify(a) === JSON.stringify(b))) }
}
export function PolicyPanel({ policies, active, onEpisode }: { policies: Resource<PolicyVersion[]>; active?: string; onEpisode: (id: string) => void }) {
  const [selected, setSelected] = useState('')
  const policy = policies.data?.find(p => p.version === (selected || active)) ?? policies.data?.at(-1)
  const parent = policies.data?.find(p => p.version === policy?.parent_version)
  const diff = policy && policyDiff(policy, parent)
  return <Panel title="Recovery policy" number="03" className="policy-panel"><ResourceNote resource={policies} />
    <p className="muted">Only a persisted accepted decision changes the active policy.</p>
    {policies.data?.length ? <label>Immutable version<select value={policy?.version ?? ''} onChange={e => setSelected(e.target.value)}>{policies.data.map(p => <option key={p.version} value={p.version}>{p.version} · {p.decision}{p.version === active ? ' · active' : ''}</option>)}</select></label> : <Empty>No policy versions recorded.</Empty>}
    {policy && <><div className="policy-title"><h3>{policy.version}</h3><Badge value={policy.decision} /></div><dl className="facts"><Field name="Author">{policy.author === 'manual' ? 'Handwritten reference / operator' : policy.author}</Field><Field name="Active version">{active ?? 'Not recorded'}</Field><Field name="Parent">{policy.parent_version ?? 'None — baseline'}</Field><Field name="Exact content hash"><Hash value={policy.policy_hash} /></Field><Field name="Decision reference"><code>{policy.decision_ref ?? 'No decision record'}</code></Field><Field name="Proposal reference"><code>{policy.raw_proposal_ref ?? 'No model proposal'}</code></Field></dl>
      <h3>Structural diff {parent ? `from ${parent.version}` : ''}</h3>{diff && (!diff.added.length && !diff.removed.length) ? <p className="empty">No rule changes. {policy.decision === 'BASELINE' && 'Empty overlay is the baseline.'}</p> : <div className="policy-diff">{diff?.removed.map((r, i) => <pre className="removed" key={`r${i}`}>− {JSON.stringify(r, null, 2)}</pre>)}{diff?.added.map((r, i) => <pre className="added" key={`a${i}`}>+ {JSON.stringify(r, null, 2)}</pre>)}</div>}
      {policy.raw_proposal_ref && <OriginalProposal key={policy.version} policy={policy} />}
      <h3>Development sources</h3><EpisodeLinks ids={policy.development_episode_ids} onSelect={onEpisode} /><Json value={policy} title="Policy content and complete provenance" /></>}
  </Panel>
}
