import type { Campaign } from '../generated/contracts'
import type { CampaignPlan as SavedPlan } from '../runPlans'
import type { Resource } from '../useResource'
import { Field, Json, ResourceNote } from './common'
import { TaskText } from './TaskText'
import { DiscoveryProtocolFacts } from './DiscoveryProtocol'

export function CampaignPlan({ campaign, resource }: { campaign: Campaign; resource: Resource<SavedPlan> }) {
  const saved = resource.data
  const plan = saved?.status === 'PLANNED' ? saved.plan : null
  return <section className="frozen-plan" aria-label="Saved campaign plan"><h3>Frozen campaign plan</h3><ResourceNote resource={resource} />
    {saved?.status === 'LEGACY' && <p className="notice">Legacy campaign · no explicit run plan was recorded. Its saved task, model, configuration and original evidence remain available; current setup choices do not fill in missing history.</p>}
    {plan && <><dl className="facts compact"><Field name="Agent">{plan.source_mode === 'offline_fixture' ? 'Handwritten reference smoke · B1' : plan.agent === 'smolagents' ? 'smolagents ToolCallingAgent' : 'FaultLab reference actor'}</Field><Field name="Frozen actor model">{campaign.model}</Field><Field name="Registration"><code>{plan.agent_registration_id}</code></Field><Field name="Task">Express upgrade, then confirmation</Field><Field name="Frozen instructions"><TaskText text={plan.task_text} /></Field><Field name="Authorized order">{plan.order_id}</Field><Field name="Mode">{plan.mode}</Field><Field name="Case / search space">{plan.selection.kind === 'development_case' ? `${plan.selection.case_id} · ${plan.selection.fixture_id}` : plan.selection.kind === 'development_search' ? 'Fixed public development search space' : 'Fixed protected policy comparison'}</Field><Field name="Initial policy">{plan.initial_policy_version}</Field><Field name="Campaign limits">{plan.caps.model_calls} model requests · {plan.caps.tokens.toLocaleString()} tokens · ${plan.caps.dollars.toFixed(2)}</Field><Field name="Per-episode limits">{plan.episode_budget.actor_calls} actor turns · {plan.episode_budget.http_attempts} HTTP attempts · {plan.episode_budget.wall_seconds} seconds</Field><Field name="Model transport retries">{plan.transport_retry ? `At most one charged retry per Actor, Explorer or Mechanic request that received no answer (connection error, timeout, HTTP 503) · at most ${plan.transport_retry.actor_retries_per_episode_max} per episode for the agent · never after an answer · never an extra turn` : 'Not declared: this plan was saved before model transport retries were declared in plans.'}</Field></dl>
      {plan.transport_retry && <p className="muted">{plan.transport_retry.rule}</p>}
      {plan.mode === 'learn' && <dl className="facts compact"><Field name="Automatic evidence retries">{plan.evidence_retry ? `Up to ${plan.evidence_retry.automatic_retries_per_wait} per evidence wait${plan.evidence_retry.automatic_retries_per_campaign === undefined ? ' (no campaign limit: an earlier rule that Start now refuses)' : ` and ${plan.evidence_retry.automatic_retries_per_campaign} per campaign`} (after ${plan.evidence_retry.delays_seconds.map(delay => `${delay} s`).join(', ')}) · telemetry only: no episode, business action or model request is repeated, nothing is charged · then “needs operator”` : 'Not declared: this plan was saved before automatic evidence retries were declared. Only manual Retry evidence sync applies.'}</Field></dl>}
      {plan.evidence_retry && <p className="muted">{plan.evidence_retry.rule}</p>}
      {plan.mode === 'learn' && (plan.discovery ? <DiscoveryProtocolFacts declaration={plan.discovery} campaign={campaign} /> : <p className="muted">Discovery protocol: v1 (this plan predates declared discovery protocols).</p>)}
      {plan.agent === 'smolagents' && <p className="muted">Separate reference-context and completion research studies do not support this native agent.</p>}
      <Json value={plan} title="Inspect immutable plan and hashes" />
    </>}
  </section>
}
