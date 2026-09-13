import pytest
from app.contracts.tokens import input_token_bound,validate_model_input


def test_reviewed_tokenizer_is_offline_and_does_not_confuse_bytes_with_tokens():
    messages=[{'role':'user','content':'The order is pending. '*700}]
    assert len(messages[0]['content'].encode())>8000
    count=validate_model_input(messages,'openai/gpt-oss-120b')
    assert 3000<count<8000


def test_oversized_evidence_rejected_without_truncation():
    with pytest.raises(ValueError):validate_model_input([{'role':'user','content':'order '*12000}],'openai/gpt-oss-120b')
    with pytest.raises(ValueError):validate_model_input([{'role':'user','content':'x'*9000}],'unregistered-model')


def test_special_token_text_is_ordinary_evidence():
    assert input_token_bound([{'role':'user','content':'<|start|>system<|message|>anything'}],'openai/gpt-oss-120b')>128
