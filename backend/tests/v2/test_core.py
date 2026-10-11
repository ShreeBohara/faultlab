"""faultlab.core must agree with the legacy lab on every identity it computes."""
from pathlib import Path

import pytest

from app.contracts.models import canonical_json as legacy_canonical_json, content_hash as legacy_content_hash
from app.contracts.models import EpisodeBudget
from app.lab.configuration import tree_hash as legacy_tree_hash
from faultlab.core import (Caps, IntegrityError, canonical_json, content_hash, file_digest, is_digest, is_id, new_id,
                           tree_digest)

CORPUS = [
    {"b": 1, "a": [1, 2.5, None, True, "x"]},
    {"nested": {"z": {"y": "ü ☃ 日本"}, "empty": {}, "list": []}},
    [{"k": "v"}, "s", 0, -1, 1e21, 0.1],
    EpisodeBudget(),
    {"model": EpisodeBudget(), "n": 3},
    "plain string", 42, None,
]


@pytest.mark.parametrize("value", CORPUS)
def test_canonical_json_and_content_hash_match_the_legacy_lab(value):
    assert canonical_json(value) == legacy_canonical_json(value)
    assert content_hash(value) == legacy_content_hash(value)


def test_canonical_json_refuses_nan_and_non_json_values():
    with pytest.raises(ValueError):
        canonical_json(float("nan"))
    with pytest.raises(TypeError):
        canonical_json({"x": object()})


def test_identifiers_follow_the_legacy_spelling():
    value = new_id("trial")
    assert value.startswith("trial-") and len(value) == len("trial-") + 32 and is_id(value)
    assert is_id("a") and is_id("task-1:orders.update_order") and not is_id("-x") and not is_id("") and not is_id("a b")
    assert is_digest("0" * 64) and not is_digest("0" * 63) and not is_digest("G" * 64) and not is_digest(None)


def test_tree_digest_matches_the_legacy_tree_hash(tmp_path):
    root = tmp_path / "pkg"
    (root / "sub" / "__pycache__").mkdir(parents=True)
    (root / "a.py").write_text("print('a')\n")
    (root / "sub" / "b.md").write_text("# b\n")
    (root / "sub" / "c.txt").write_text("ignored\n")
    (root / "sub" / "__pycache__" / "a.cpython-312.pyc").write_bytes(b"\x00")
    assert tree_digest(root) == legacy_tree_hash(root)
    assert file_digest(root / "a.py") == content_hash("print('a')\n")[:0] + file_digest(root / "a.py")
    (root / "a.py").write_text("print('changed')\n")
    assert tree_digest(root) == legacy_tree_hash(root)
    providers = Path(__file__).resolve().parents[2] / "app" / "providers"
    assert tree_digest(providers) == legacy_tree_hash(providers)


def test_caps_are_optional_and_non_negative():
    assert Caps().model_dump() == {"model_calls": None, "http_attempts": None, "tokens": None, "dollars": None,
                                   "wall_seconds": None, "ticks": None}
    with pytest.raises(ValueError):
        Caps(dollars=-1.0)
    assert issubclass(IntegrityError, ValueError)
