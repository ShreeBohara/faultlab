"""Offline admission for reviewed GPT OSS, Llama 3.3 and DeepSeek tokenizers.

Ranks are vendored with a verified digest. This module never downloads encodings.
Other model families use an explicit conservative byte ceiling until their own
reviewed tokenizer is registered; model switches require a configuration freeze.
"""
import base64
import json
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from .models import canonical_json, MODEL_INPUT_TOKEN_LIMIT

RANKS_HASH='446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'
PATTERN='|'.join([
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r"[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?",
    r'\p{N}{1,3}',r' ?[^\s\p{L}\p{N}]+[\r\n/]*',r'\s*[\r\n]+',r'\s+(?!\S)',r'\s+',
])
LLAMA_RANKS_HASH='82e9d31979e92ab929cd544440f129d9ecd797b69e327f80f17e1c50d5551b55'
LLAMA_PATTERN=r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}{1,3}| ?[^\s\p{L}\p{N}]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+"
DEEPSEEK_TOKENIZER_HASH='32b34a41212e92f62e859cbbea121ae705a1fabbf157d9acf22d134ecd8dcf70'
DEEPSEEK_V4_TOKENIZER_HASH='8f9f37ca37fdc4f5fd36d5cf4d3b0e8392edb4e894fd10cc0d70b4957c8633cf'


def _load_encoding(filename,digest,pattern,name):
    import tiktoken
    path=Path(__file__).resolve().parents[3]/'contracts/tokenizer'/filename
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=digest:raise ValueError('Reviewed tokenizer data failed integrity check')
    ranks={base64.b64decode(token):int(rank) for token,rank in (line.split() for line in raw.splitlines() if line)}
    # Content is encoded as ordinary text so untrusted special-token spellings do
    # not gain control semantics. Message framing has a separate admission reserve.
    return tiktoken.Encoding(name=name,pat_str=pattern,mergeable_ranks=ranks,special_tokens={})


@lru_cache(maxsize=1)
def encoding():
    return _load_encoding('o200k_base.tiktoken',RANKS_HASH,PATTERN,'faultlab-o200k-content/v1')


@lru_cache(maxsize=1)
def llama_encoding():
    return _load_encoding('llama3/tokenizer.model',LLAMA_RANKS_HASH,LLAMA_PATTERN,'faultlab-llama3-content/v1')


def _load_json_encoding(filename,digest):
    from tokenizers import Tokenizer
    path=Path(__file__).resolve().parents[3]/'contracts/tokenizer'/filename
    raw=path.read_bytes()
    if sha256(raw).hexdigest()!=digest:
        raise ValueError('Reviewed tokenizer data failed integrity check')
    data=json.loads(raw)
    # Content admission counts literal control-token spellings as ordinary bytes,
    # without granting the added-token IDs their separate chat-template meaning.
    data['added_tokens']=[]
    tokenizer=Tokenizer.from_str(json.dumps(data))
    tokenizer.no_truncation()
    tokenizer.no_padding()
    return tokenizer


@lru_cache(maxsize=1)
def deepseek_encoding():
    return _load_json_encoding('deepseek-v3.1/tokenizer.json',DEEPSEEK_TOKENIZER_HASH)


@lru_cache(maxsize=1)
def deepseek_v4_encoding():
    return _load_json_encoding('deepseek-v4-pro-0813/tokenizer.json',DEEPSEEK_V4_TOKENIZER_HASH)


def input_token_bound(messages,model):
    if model in ('openai/gpt-oss-120b','openai/gpt-oss-20b','gpt-oss-120b','gpt-oss-20b'):
        tokenizer=encoding()
    elif model=='meta-llama/Llama-3.3-70B-Instruct':
        tokenizer=llama_encoding()
    elif model in ('deepseek-ai/DeepSeek-V3.1','deepseek-ai/DeepSeek-V4-Pro-0813'):
        tokenizer=deepseek_v4_encoding() if model=='deepseek-ai/DeepSeek-V4-Pro-0813' else deepseek_encoding()
        return 128 + sum(16+len(tokenizer.encode(m['role'],add_special_tokens=False).ids)+len(tokenizer.encode(m['content'],add_special_tokens=False).ids) for m in messages)
    else:
        return 128+len(canonical_json(messages).encode('utf-8'))
    return 128 + sum(16+len(tokenizer.encode_ordinary(m['role']))+len(tokenizer.encode_ordinary(m['content'])) for m in messages)


def validate_model_input(messages,model):
    count=input_token_bound(messages,model)
    if count>MODEL_INPUT_TOKEN_LIMIT:
        raise ValueError(f'Essential evidence exceeds the frozen {MODEL_INPUT_TOKEN_LIMIT:,}-token input budget')
    return count
