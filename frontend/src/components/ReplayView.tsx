import type { Campaign } from '../generated/contracts'
export function ReplayView({ campaign }: { campaign?: Campaign }) {
  return <aside className="replay-banner" role="status"><strong>Recorded playback · read only</strong><span>{campaign?.campaign_id ?? 'No campaign selected'} · {campaign?.created_at ? new Date(campaign.created_at).toLocaleString() : 'Time not recorded'}</span><p>Viewing persisted evidence. Playback makes no business, model or provider calls. Fresh execution is a separate explicit action.</p></aside>
}
