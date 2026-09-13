"""Admission always precedes effects; unknown usage never refunds reservations."""
from __future__ import annotations
from dataclasses import dataclass
from functools import wraps
import time
from app.contracts.models import CampaignBudget, EpisodeBudget, Usage, canonical_json

class BudgetExhausted(RuntimeError):
    pass

class StopRequested(RuntimeError):
    pass

PROTECTED = {'final_audit':384,'portability':288,'selection_comparison':392}
CANDIDATE_CALLS = 538  # 528 actor + proposal + eight selections + one format repair

def protected_reservations(caps):
    tokens_per_call=caps.input_tokens_per_call+caps.output_tokens_per_call
    return {name:{'calls':calls,'tokens':calls*tokens_per_call} for name,calls in PROTECTED.items()}

@dataclass
class Reservation:
    name: str
    calls: int
    tokens: int

def synchronized(method):
    @wraps(method)
    def wrapped(self,*args,**kwargs):
        with self.store.lock: return method(self,*args,**kwargs)
    return wrapped

class CampaignLedger:
    def __init__(self, store, campaign_id, caps=None, *, dollar_bound=None):
        self.store,self.campaign_id = store,campaign_id
        saved = store.get_record('budgets',campaign_id)
        campaign = store.get_record('campaigns',campaign_id)
        frozen_caps = saved.get('caps') if saved else None
        if frozen_caps is None and campaign: frozen_caps=campaign.get('caps')
        stored_caps=CampaignBudget.model_validate_json(canonical_json(frozen_caps)) if frozen_caps else None
        if caps is not None and stored_caps is not None and caps!=stored_caps:
            raise BudgetExhausted('Frozen campaign budget changed')
        self.caps = caps or stored_caps or CampaignBudget()
        self.dollar_bound=saved.get('dollar_bound') if saved else dollar_bound
        if saved and dollar_bound is not None and self.dollar_bound!=dollar_bound: raise BudgetExhausted('Frozen price bound changed')
        self.used_calls = saved['used_calls'] if saved else 0
        self.used_tokens = saved['used_tokens'] if saved else 0
        self.used_cost = saved['used_cost'] if saved else None
        self.measured_input=saved.get('measured_input_tokens',0) if saved else 0
        self.measured_output=saved.get('measured_output_tokens',0) if saved else 0
        self.usage_known=saved.get('usage_metadata_known',True) if saved else True
        self.unknown_cost_calls=saved.get('unknown_cost_calls',0) if saved else 0
        self.unknown_token_calls=saved.get('unknown_token_calls',0) if saved else 0
        self.reservations = saved['reservations'] if saved else protected_reservations(self.caps)
        self.stopped = False
        self._save()

    def _save(self):
        self.usage_known=self.unknown_token_calls==0
        self.store.put_record('budgets',self.campaign_id,{'caps':self.caps.model_dump(mode='json'),'used_calls':self.used_calls,'used_tokens':self.used_tokens,'used_cost':self.used_cost,'reservations':self.reservations,'dollar_bound':self.dollar_bound,'charged_dollar_upper_bound':self.used_calls*self.dollar_bound if self.dollar_bound is not None else None,'charged_token_upper_bound':self.used_tokens,'actual_cost_dollars':self.used_cost if self.unknown_cost_calls==0 else None,'unknown_cost_calls':self.unknown_cost_calls,'unknown_token_calls':self.unknown_token_calls,'usage_metadata_known':self.usage_known,'measured_input_tokens':self.measured_input,'measured_output_tokens':self.measured_output})

    @property
    def reserved_calls(self):
        return sum(r['calls'] for r in self.reservations.values())

    @property
    def tokens_per_call(self):
        return self.caps.input_tokens_per_call+self.caps.output_tokens_per_call

    @property
    def reserved_tokens(self):
        return sum(r['tokens'] for r in self.reservations.values())

    @synchronized
    def reserve(self, name, calls, tokens=None):
        if self.stopped: raise StopRequested()
        tokens = calls*self.tokens_per_call if tokens is None else tokens
        if name in self.reservations: raise BudgetExhausted('Batch already reserved')
        if self.dollar_bound is not None and (self.used_calls+self.reserved_calls+calls)*self.dollar_bound>self.caps.dollars: raise BudgetExhausted('Complete batch exceeds frozen dollar reservation')
        if self.used_calls+self.reserved_calls+calls > self.caps.model_calls or self.used_tokens+self.reserved_tokens+tokens > self.caps.tokens:
            raise BudgetExhausted('Complete batch cannot fit protected reserves')
        self.reservations[name]={'calls':calls,'tokens':tokens}
        self._save()
        return name

    @synchronized
    def release(self, name):
        self.reservations.pop(name,None)
        self._save()

    @synchronized
    def consume_call(self, *, reservation=None):
        if self.stopped: raise StopRequested()
        protected_calls=self.reserved_calls
        protected_tokens=self.reserved_tokens
        if reservation:
            r=self.reservations.get(reservation)
            if not r or r['calls']<1 or r['tokens']<self.tokens_per_call: raise BudgetExhausted('Batch reservation exhausted')
            protected_calls-=1; protected_tokens-=self.tokens_per_call
        if self.dollar_bound is not None and (self.used_calls+1+protected_calls)*self.dollar_bound>self.caps.dollars: raise BudgetExhausted('Model call exceeds protected dollar cap')
        if self.used_calls+1+protected_calls>self.caps.model_calls or self.used_tokens+self.tokens_per_call+protected_tokens>self.caps.tokens:
            raise BudgetExhausted('Model budget exhausted')
        if self.used_cost is not None and self.used_cost>=self.caps.dollars: raise BudgetExhausted('Dollar cap exhausted')
        if reservation:
            self.reservations[reservation]['calls']-=1
            self.reservations[reservation]['tokens']-=self.tokens_per_call
        self.used_calls+=1; self.used_tokens+=self.tokens_per_call; self.unknown_cost_calls+=1; self.unknown_token_calls+=1
        self._save()

    @synchronized
    def reconcile(self, generation):
        # Reserve worst-case tokens permanently; actual usage is separately measured.
        self.measured_input+=generation.input_tokens or 0
        self.measured_output+=generation.output_tokens or 0
        if generation.input_tokens is None or generation.output_tokens is None: self.usage_known=False
        else: self.unknown_token_calls=max(0,self.unknown_token_calls-1)
        if generation.cost_usd is not None:
            self.used_cost=(self.used_cost or 0)+generation.cost_usd
            self.unknown_cost_calls=max(0,self.unknown_cost_calls-1)
        self._save()


class EpisodeMeter:
    def __init__(self, caps=None, *, campaign=None, reservation=None, clock=time.monotonic, stop=None):
        self.caps=caps or EpisodeBudget(); self.usage=Usage()
        self.campaign,self.reservation=campaign,reservation
        self.clock=clock; self.started=clock(); self.stop=stop or (lambda:False)
        self.business_closed=False

    def check(self):
        if self.stop(): raise StopRequested('External stop requested')
        elapsed=self.clock()-self.started
        self.usage.wall_seconds=elapsed
        if elapsed>=self.caps.wall_seconds: raise BudgetExhausted('Episode deadline exhausted')

    def take(self, field, amount=1):
        self.check()
        if amount<0: raise ValueError('Negative debit')
        if getattr(self.usage,field)+amount>getattr(self.caps,field): raise BudgetExhausted(f'{field} exhausted')
        setattr(self.usage,field,getattr(self.usage,field)+amount)

    def http_attempt(self):
        self.check()
        if self.business_closed: raise BudgetExhausted('Business calls closed')
        if self.usage.http_attempts>=self.caps.http_attempts or self.usage.ticks>=self.caps.ticks: raise BudgetExhausted('HTTP/tick budget exhausted')
        self.usage.http_attempts+=1; self.usage.ticks+=1

    def wait(self,ticks):
        self.check()
        if self.business_closed: raise BudgetExhausted('Business calls closed')
        if not 1<=ticks<=4: raise ValueError('wait_ticks must be 1..4')
        if self.usage.wait_cycles>=self.caps.wait_cycles or self.usage.ticks+ticks>self.caps.ticks: raise BudgetExhausted('Wait/tick budget exhausted')
        self.usage.wait_cycles+=1; self.usage.ticks+=ticks

    def model_call(self):
        self.check()
        if self.usage.actor_calls>=self.caps.actor_calls: raise BudgetExhausted('Actor budget exhausted')
        if self.campaign: self.campaign.consume_call(reservation=self.reservation)
        self.usage.actor_calls+=1; self.usage.model_calls+=1
        # Actual token counts are populated only when returned by the provider.

    @property
    def final_turn(self):
        return self.usage.actor_calls>=self.caps.actor_calls-1 or self.business_closed
