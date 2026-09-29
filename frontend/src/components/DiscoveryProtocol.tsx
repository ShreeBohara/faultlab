import type { DiscoveryDeclaration } from '../runPlans'
import { Field } from './common'

export const discoveryName = (declaration: DiscoveryDeclaration) =>
  declaration.protocol === 'faultlab-discovery/v2-reachability' ? 'v2 · reachability pre-check' : 'v1 · every valid new pick runs'

export const discoveryBudget = (declaration: DiscoveryDeclaration) =>
  `${declaration.slots} slots · at most ${declaration.explorer_requests_max} Explorer requests · at most ${declaration.actor_episodes_max} Actor episodes · ${declaration.replans_per_slot ? 'one re-plan per refused slot' : 'no re-plans'}`

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
    {caller && <details><summary>Pre-check caller model · this agent's limits and typical path</summary><ul className="muted">{caller.facts.map(fact => <li key={fact}>{fact}</li>)}</ul><p className="muted">Caller model <code>{caller.caller_id}</code> describes {caller.validated_against}. The pre-check changes only which picks run; it never changes what the Actor sees or how a trial is scored.</p></details>}
  </div>
}
