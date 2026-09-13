"""Offline input admission for the selected gpt-oss tokenizer.

Ranks are vendored with a verified digest. This module never downloads encodings.
Other model families use an explicit conservative byte ceiling until their own
reviewed tokenizer is registered; model switches require a configuration freeze.
"""
import base64
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from .models import canonical_json

RANKS_HASH='446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'
PATTERN='|'.join([
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r'\p{N}{1,3}',r' ?[^\s\p{L}\p{N}]+[\r\n/]*',r'\s*[\r\n]+',r'\s+(?!\S)',r'\s+',
])


@lru_cache(maxsize=1)
def encoding():
    import tiktoken
    path=Path(__file__).resolve().parents[3]/'contracts/tokenizer/o200k_base.tiktoken'
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=RANKS_HASH:raise ValueError('Reviewed tokenizer data failed integrity check')
    ranks={base64.b64decode(token):int(rank) for token,rank in (line.split() for line in raw.splitlines() if line)}
    # Content is encoded as ordinary text so untrusted special-token spellings do
    # not gain control semantics. Message framing has a separate admission reserve.
    return tiktoken.Encoding(name='faultlab-o200k-content/v1',pat_str=PATTERN,mergeable_ranks=ranks,special_tokens={})


def input_token_bound(messages,model):
    if model in ('openai/gpt-oss-120b','openai/gpt-oss-20b','gpt-oss-120b','gpt-oss-20b'):
        return 128 + sum(16+len(encoding().encode_ordinary(m['role']))+len(encoding().encode_ordinary(m['content'])) for m in messages)
    return 128+len(canonical_json(messages).encode('utf-8'))


def validate_model_input(messages,model):
    count=input_token_bound(messages,model)
    if count>8000:raise ValueError('Essential evidence exceeds the frozen 8,000-token input budget')
    return count
