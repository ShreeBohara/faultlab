import type { DiscoveryDeclaration } from '../runPlans'
import { Field } from './common'

export const discoveryName = (declaration: DiscoveryDeclaration) =>
  declaration.protocol === 'faultlab-discovery/v2-reachability' ? 'v2 · reachability pre-check' : 'v1 · every valid new pick runs'

/**
 * Explorer transport retries are declared separately: a retry re-sends a request that got no answer; it is not a new request.
 * The declared number covers discovery-phase Explorer requests only (review finding, September 29).
 */
export const explorerRetries = (declaration: DiscoveryDeclaration) =>
  typeof declaration.explorer_transport_retries_max === 'number'
    ? `at most ${declaration.explorer_transport_retries_max} charged Explorer transport retries during discovery (one per request with no answer)`
    : 'no Explorer transport retry declared'

/** Retries after discovery have no separate declared count; they are bounded per request and by the campaign limits. */
export const LATER_PHASE_RETRIES = 'The retry bound above covers discovery only. In later phases, every Explorer request (challenge selections, selection comparison) and every Mechanic request can also get one charged retry when no answer arrives; those retries have no separate count and are bounded by one retry per request and by the campaign limits.'

export const discoveryBudget = (declaration: DiscoveryDeclaration) =>
  `${declaration.slots} slots · at most ${declaration.explorer_requests_max} Explorer requests · ${explorerRetries(declaration)} · at most ${declaration.actor_episodes_max} Actor episodes · ${declaration.replans_per_slot ? 'one re-plan per refused slot' : 'no re-plans'}`

/** The declared discovery protocol and selection budget, in plain words. */
export function DiscoveryProtocolFacts({ declaration }: { declaration: DiscoveryDeclaration }) {
  const caller = declaration.pre_check?.caller_model
  return <div className="discovery-protocol">
    <dl className="facts compact">
      <Field name="Discovery protocol">{discoveryName(declaration)}</Field>
      <Field name="Selection budget">{discoveryBudget(declaration)}</Field>
      <Field name="Schedule identity">{declaration.schedule_identity.endsWith('v2-order-aware') ? 'Order-aware: order counts only for overlapping same-kind faults on one tool' : 'Sorted primitives (seed and order ignored)'}</Field>
    </dl>
    <p className="muted">{declaration.dispatch_rule}</p>
    {typeof declaration.explorer_transport_retries_max === 'number' && <p className="muted">{LATER_PHASE_RETRIES}</p>}
    {caller && <details><summary>Pre-check caller model · this agent's limits and typical path</summary><ul className="muted">{caller.facts.map(fact => <li key={fact}>{fact}</li>)}</ul><p className="muted">Caller model <code>{caller.caller_id}</code> describes {caller.validated_against}. The pre-check changes only which picks run; it never changes what the Actor sees or how a trial is scored.</p></details>}
  </div>
}
