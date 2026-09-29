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
    {plan && <><dl className="facts compact"><Field name="Agent">{plan.source_mode === 'offline_fixture' ? 'Handwritten reference smoke · B1' : plan.agent === 'smolagents' ? 'smolagents ToolCallingAgent' : 'FaultLab reference actor'}</Field><Field name="Frozen actor model">{campaign.model}</Field><Field name="Registration"><code>{plan.agent_registration_id}</code></Field><Field name="Task">Express upgrade, then confirmation</Field><Field name="Frozen instructions"><TaskText text={plan.task_text} /></Field><Field name="Authorized order">{plan.order_id}</Field><Field name="Mode">{plan.mode}</Field><Field name="Case / search space">{plan.selection.kind === 'development_case' ? `${plan.selection.case_id} · ${plan.selection.fixture_id}` : plan.selection.kind === 'development_search' ? 'Fixed public development search space' : 'Fixed protected policy comparison'}</Field><Field name="Initial policy">{plan.initial_policy_version}</Field><Field name="Campaign limits">{plan.caps.model_calls} model requests · {plan.caps.tokens.toLocaleString()} tokens · ${plan.caps.dollars.toFixed(2)}</Field><Field name="Per-episode limits">{plan.episode_budget.actor_calls} actor turns · {plan.episode_budget.http_attempts} HTTP attempts · {plan.episode_budget.wall_seconds} seconds</Field></dl>
      {plan.mode === 'learn' && (plan.discovery ? <DiscoveryProtocolFacts declaration={plan.discovery} /> : <p className="muted">Discovery protocol: v1 (this plan predates declared discovery protocols).</p>)}
      {plan.agent === 'smolagents' && <p className="muted">Separate reference-context and completion research studies do not support this native agent.</p>}
      <Json value={plan} title="Inspect immutable plan and hashes" />
    </>}
  </section>
}
