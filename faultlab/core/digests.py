"""File and tree digests. ``tree_digest`` equals the legacy ``app.lab.configuration.tree_hash``."""

from hashlib import sha256
from pathlib import Path

from faultlab.core.canonical import content_hash


def file_digest(path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def tree_digest(root, *, suffixes=(".py", ".md")) -> str:
    """A content digest over the reviewed files of one directory, keyed by relative path."""
    root = Path(root)
    files = {str(path.relative_to(root)): file_digest(path)
             for path in sorted(root.rglob("*"))
             if path.is_file() and path.suffix in suffixes and "__pycache__" not in str(path)}
    return content_hash(files)
