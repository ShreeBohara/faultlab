import os, sys
sys.path.insert(0, os.getcwd())
from app.agents.transport_retry import declaration, RULE, blind_retry_allowed, retry_payload, complete_with_one_retry, charge_ledger_retry
from app.contracts.models import content_hash
import inspect, hashlib
src = lambda f: hashlib.sha256(inspect.getsource(f).encode()).hexdigest()[:16]
print('v1 declaration(8) hash', content_hash(declaration(8)), '| RULE', content_hash(RULE)[:16],
      '| src blind_retry_allowed', src(blind_retry_allowed), 'retry_payload', src(retry_payload),
      'complete_with_one_retry', src(complete_with_one_retry), 'charge_ledger_retry', src(charge_ledger_retry))
