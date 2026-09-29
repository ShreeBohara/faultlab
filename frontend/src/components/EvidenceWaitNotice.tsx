import { useRef, useState } from 'react'
import type { Campaign } from '../generated/contracts'
import { api } from '../api'
import { evidenceWaitApi, type AutomaticEvidenceRetry } from '../evidenceWait'
import { useResource } from '../useResource'
import { Badge, Field, ResourceNote } from './common'

const clock = (iso: string) => new Date(iso).toLocaleTimeString()
/** What an attempt achieved, not only that its telemetry job finished: a finished job can leave evidence unverified. */
const result = (item: AutomaticEvidenceRetry) => item.status === 'COMPLETED' || item.status === 'PENDING'
  ? (item.verified && !item.still_pending ? 'EVIDENCE_VERIFIED' : item.still_pending === 0 && item.verified === 0 ? item.status : 'STILL_UNVERIFIED')
  : item.status

/** Shown while a campaign waits for verified Weave evidence. Read once per campaign state change (never on a timer). */
export function EvidenceWaitNotice({ campaign, readOnly, replay }: { campaign: Campaign; readOnly: boolean; replay: boolean }) {
  const waiting = campaign.state === 'WAITING_EVIDENCE'
  const wait = useResource(waiting ? `evidence-wait:${campaign.campaign_id}:${campaign.state_seq ?? 0}` : null, () => evidenceWaitApi.get(campaign.campaign_id), null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const lock = useRef(false)
  if (!waiting) return null
  const data = wait.data
  const current = data?.current ?? null
  const declared = data?.declared ?? null
  return <section className={`evidence-wait${data?.needs_operator ? ' needs-operator' : ''}`} aria-label="Evidence wait">
    <div className="split-heading"><h3>{data?.needs_operator ? 'Needs operator: evidence still unverified' : 'Waiting for Weave evidence'}</h3>{data && <Badge value={data.status} />}</div>
    <ResourceNote resource={wait} />
    <p>{data?.message ?? campaign.terminal_reason ?? 'Waiting for verified Weave evidence.'}</p>
    {data && !current && campaign.terminal_reason && campaign.terminal_reason !== data.message && <p>Saved campaign reason: {campaign.terminal_reason}</p>}
    {current && <dl className="facts compact">
      <Field name="Blocked episode"><code>{current.episode_id}</code></Field>
      <Field name="Episodes this wait needs">{current.pending_episode_ids.length}</Field>
      <Field name="Automatic retries">{declared ? `${current.automatic_attempts.length} of ${declared.automatic_retries_per_wait} made` : 'Not declared for this campaign'}</Field>
      <Field name="Next automatic retry">{current.next_automatic_retry_at ? clock(current.next_automatic_retry_at) : 'None scheduled'}</Field>
    </dl>}
    {data && declared && <dl className="facts compact">
      <Field name="Automatic retries this campaign">{declared.automatic_retries_per_campaign === undefined ? `${data.automatic_retries_total} (this earlier rule has no campaign limit)` : `${data.automatic_retries_total} of ${declared.automatic_retries_per_campaign}`}</Field>
    </dl>}
    {!!current?.automatic_attempts.length && <ol className="retry-attempts" aria-label="Automatic retry attempts">{current.automatic_attempts.map(item => <li key={item.attempt}>
      Retry {item.attempt} · <Badge value={result(item)} />{item.verified !== null && ` · ${item.verified} verified, ${item.still_pending ?? 0} still pending`}
    </li>)}</ol>}
    {data && <p className="muted">{declared
      ? 'Automatic retries are telemetry only: they re-send saved trace records and read them back. No episode, business action or model request is repeated, and nothing is charged.'
      : data.declared_note}</p>}
    <div className="controls"><button disabled={readOnly || replay || busy} onClick={async () => {
      if (readOnly || replay || lock.current) return
      lock.current = true; setBusy(true); setMessage(null)
      // Only the episodes this wait needs, blocked episode first; with no wait record, every campaign episode.
      const episodes = (current?.pending_episode_ids ?? []).slice(0, 200)
      try {
        await api.retry(campaign.campaign_id, episodes)
        setMessage(`Retry accepted for ${episodes.length ? `the ${episodes.length === 1 ? 'episode' : `${episodes.length} episodes`} this wait needs` : 'every episode of this campaign'} (saved evidence only). The campaign reads the evidence again when it finishes.`)
      }
      catch (error) { setMessage(error instanceof Error ? error.message : 'Retry failed.') }
      finally { lock.current = false; setBusy(false) }
    }}>{busy ? 'Requesting retry…' : 'Retry evidence sync now'}</button></div>
    {message && <p className="muted">{message}</p>}
  </section>
}
